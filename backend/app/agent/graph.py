"""购物任务核心循环(agent loop)。

graph 不做任何购物决策,只负责三件事:
  1. 建立本轮 Context,把用户原话交给决策层
  2. 驱动循环:decide → execute_tool → 结果回填 → 再 decide
  3. 把工具结果转译成 SSE 事件下发前端

"要不要追问、追问什么、是否换品类、候选太少怎么办、结论怎么说"全部由
决策层(app/agent/llm.py)通过调用工具决定。工具实现在 app/agent/toolkit.py。
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

from ..adapters.base import PlatformAdapter
from ..domain.models import ShoppingTask, TaskState
from ..harness.context import (
    ContextAssembler,
    ContextBudget,
    Turn,
    estimate_messages_tokens,
)
from ..harness.memory import (
    LongTermMemory,
    SessionMemory,
    TaskMemory,
    describe_memory,
    extract_memories,
)
from ..harness.orchestrator import BudgetGuard, RunBudget, RunTrace, TraceStep
from ..harness.repository import repository
from ..profile import profile_store
from .llm import SYSTEM_PROMPT, build_llm
from .serialize import build_report, serialize as _serialize
from .toolkit import Context as AgentContext
from .toolkit import execute_tool, tool_schemas

#: 这些工具在等用户回话,执行后必须结束本轮
_AWAITING_TOOLS = {"ask_category_choice", "ask_clarifying_question"}


class ShoppingAgent:
    def __init__(
        self,
        adapters: dict[str, PlatformAdapter],
        profiles=None,
        llm=None,
        budget: RunBudget | None = None,
        memory_repository=None,
    ) -> None:
        self.adapters = adapters
        self.profiles = profiles if profiles is not None else profile_store
        self.budget = budget or RunBudget()
        self._memory_repository = memory_repository
        #: 决策层需要反向读取任务观测
        self._ctx: AgentContext | None = None
        self.llm = llm if llm is not None else build_llm(self._current_context)
        #: task_id -> 会话记忆 / 任务记忆
        self._sessions: dict[str, SessionMemory] = {}
        self._task_memories: dict[str, TaskMemory] = {}
        #: 最近一次运行轨迹,供 API 与测评读取
        self.last_trace: RunTrace | None = None

    def _current_context(self) -> AgentContext | None:
        return self._ctx

    # ------------------------------------------------------------------
    # 记忆访问
    # ------------------------------------------------------------------

    def session(self, task_id: str) -> SessionMemory:
        return self._sessions.setdefault(task_id, SessionMemory())

    def task_memory(self, task_id: str) -> TaskMemory:
        return self._task_memories.setdefault(task_id, TaskMemory())

    def long_term(self, user_id: str = "default") -> LongTermMemory:
        repo = self._memory_repository or repository()
        return LongTermMemory(repo, user_id=user_id)

    async def handle_message(
        self, task: ShoppingTask, text: str
    ) -> AsyncIterator[dict[str, Any]]:
        ctx = AgentContext(task=task, profiles=self.profiles, adapters=self.adapters)
        ctx.flow["last_text"] = text
        self._ctx = ctx

        session = self.session(task.task_id)
        session.add_user(text)

        memory = self.long_term()
        async for event in self._absorb_memories(text, memory, task):
            yield event

        async for event in self._loop(ctx, text, session, memory):
            yield event

    async def _absorb_memories(
        self, text: str, memory: LongTermMemory, task: ShoppingTask
    ) -> AsyncIterator[dict[str, Any]]:
        """从用户原话自动沉淀长期偏好,并如实告知。

        记忆必须可感知、可撤销,否则用户会觉得系统在背后乱记东西。
        """
        learned: list[str] = []
        for item in extract_memories(text, self._known_brands(task.category)):
            if memory.remember(item):
                label = describe_memory(item)
                learned.append(label)
                task.log("memory", f"记住:{label}")

        if learned:
            yield {
                "type": "memory_updated",
                "learned": learned,
                "message": "已记住:" + "、".join(learned) + "(可在档案里修改)",
                "digest": memory.digest(),
            }

        # 健康类条件同步进档案,让既有的 concern_rules 硬过滤生效
        conditions = [item.value for item in memory.of_kind("condition")]
        if conditions:
            profile = self.profiles.get()
            merged = list(dict.fromkeys(list(profile.conditions) + conditions))
            if merged != list(profile.conditions):
                profile.conditions = merged
                self.profiles.save(profile)

    # ------------------------------------------------------------------
    # Agent 循环
    # ------------------------------------------------------------------

    async def _loop(
        self,
        ctx: AgentContext,
        text: str,
        session: SessionMemory,
        memory: LongTermMemory,
    ) -> AsyncIterator[dict[str, Any]]:
        task = ctx.task
        trace = RunTrace()
        self.last_trace = trace
        guard = BudgetGuard(self.budget, trace)

        assembler = ContextAssembler(
            system_prompt=SYSTEM_PROMPT, budget=ContextBudget()
        )
        # 历史里排掉刚写入的本轮输入,避免与 current_input 重复
        history = session.recent()[:-1]
        digest = memory.digest()

        step = 0
        while True:
            if reason := guard.exhausted(step):
                trace.stop_reason = reason
                task.log("budget", f"预算收敛:{reason}")
                async for event in self._finish(task, None, session, trace):
                    yield event
                return

            observation = _observation(task, guard)
            messages = assembler.build(
                history=history,
                current_input=text,
                observation=observation,
                memory_digest=digest,
            )

            started = time.monotonic()
            try:
                decision = await self.llm.decide(
                    messages, tool_schemas(), observation
                )
            except Exception as error:
                trace.add(TraceStep(index=step, kind="error", name="decide",
                                    ok=False, detail=str(error)))
                trace.stop_reason = f"决策层异常:{error}"
                yield {"type": "warning",
                       "message": f"决策出错,已给出当前结果:{error}"}
                async for event in self._finish(task, None, session, trace):
                    yield event
                return

            trace.add(TraceStep(
                index=step,
                kind="decide",
                name="final" if decision.is_final else "tool_calls",
                elapsed_ms=int((time.monotonic() - started) * 1000),
                tokens=estimate_messages_tokens(messages),
                detail=", ".join(c["name"] for c in decision.tool_calls),
            ))
            step += 1

            if decision.is_final:
                trace.stop_reason = "决策层直接给出结论"
                async for event in self._finish(task, decision.final, session, trace):
                    yield event
                return

            for call in decision.tool_calls:
                name = call["name"]
                arguments = call.get("arguments") or {}

                if guard.should_give_up(name):
                    trace.add(TraceStep(index=step, kind="tool", name=name,
                                        ok=False, detail="连续失败过多,已跳过"))
                    continue

                started = time.monotonic()
                result = await execute_tool(ctx, name, arguments)
                ok = result["type"] != "tool_error"
                guard.record_tool_result(name, ok)

                trace.add(TraceStep(
                    index=step, kind="tool", name=name, arguments=arguments,
                    ok=ok, detail="" if ok else str(result.get("result", "")),
                    elapsed_ms=int((time.monotonic() - started) * 1000),
                ))
                assembler.record_tool(step, name, result)

                for event in self._emit(result, task, name):
                    yield event

                payload = result.get("result")
                self._remember_progress(task, name, payload)

                if name == "compose_answer" and ok:
                    trace.stop_reason = "compose_answer"
                    report = payload["report"]
                    session.add_assistant(report.get("summary", ""))
                    task.state = TaskState.DECISION_READY
                    yield {"type": "task_state", "state": task.state.value}
                    yield {"type": "report", "report": report}
                    yield {"type": "trace", "trace": trace.to_dict()}
                    return

                if (name in _AWAITING_TOOLS and isinstance(payload, dict)
                        and payload.get("awaiting_user")):
                    trace.stop_reason = "等待用户回话"
                    session.add_assistant(payload.get("question", ""))
                    task.state = TaskState.INTENT_CLARIFY
                    yield {"type": "task_state", "state": task.state.value}
                    yield {"type": "trace", "trace": trace.to_dict()}
                    return

    def _remember_progress(self, task: ShoppingTask, name: str, payload: Any) -> None:
        """把工具进展记进任务记忆,供后续轮次参考。"""
        memory = self.task_memory(task.task_id)
        if name == "search_candidates" and task.candidates:
            memory.note_seen([group.group_id for group in task.candidates])
        elif name == "relax_constraints" and isinstance(payload, dict):
            for change in payload.get("changed") or []:
                memory.note_relaxation(change)

    async def _finish(
        self,
        task: ShoppingTask,
        message: str | None,
        session: SessionMemory | None = None,
        trace: RunTrace | None = None,
    ):
        report = build_report(task)
        if message:
            report["summary"] = message
        if session is not None:
            session.add_assistant(report.get("summary", ""))
        task.state = TaskState.DECISION_READY
        yield {"type": "task_state", "state": task.state.value}
        yield {"type": "report", "report": report}
        if trace is not None:
            yield {"type": "trace", "trace": trace.to_dict()}

    # ------------------------------------------------------------------
    # 工具结果 → SSE 事件
    # ------------------------------------------------------------------

    def _emit(self, result: dict, task: ShoppingTask, name: str):
        if result["type"] == "tool_error":
            yield {"type": "warning", "message": str(result.get("result", ""))}
            return

        payload = result.get("result")

        if name == "set_category" and isinstance(payload, dict):
            if payload.get("switched"):
                yield {
                    "type": "category",
                    "category": payload["category"],
                    "label": payload["label"],
                    "switched_from": payload.get("switched_from"),
                    "schema": payload["schema"],
                }
            return

        if name == "ask_category_choice" and isinstance(payload, dict):
            yield {
                "type": "select_category",
                "question": payload["question"],
                "categories": payload["categories"],
            }
            return

        if name == "understand_requirement" and isinstance(payload, dict):
            signals = payload.get("signals") or []
            notes = payload.get("weight_notes") or []
            if signals or notes:
                yield {"type": "understood", "signals": signals, "weight_notes": notes}
            return

        if name == "ask_clarifying_question" and isinstance(payload, dict):
            if payload.get("asked"):
                yield {
                    "type": "clarify",
                    "slot": payload["slot"],
                    "question": payload["question"],
                    "options": payload["options"],
                    "coverage": payload["coverage"],
                }
            return

        if name == "relax_constraints" and isinstance(payload, dict):
            changed = payload.get("changed") or []
            if changed:
                yield {"type": "progress", "message": "条件放宽了一些:" + "；".join(changed)}
            return

        if name == "search_candidates":
            if not task.candidates:
                yield {"type": "progress", "message": "没有找到符合条件的商品。"}
                return
            task.state = TaskState.COMPARE
            yield {"type": "task_state", "state": TaskState.COMPARE.value}
            yield {"type": "progress", "message": _search_message(payload)}
            yield {"type": "candidates_update", "candidates": _serialize(task)}
            return

        if name in ("analyze_ingredients", "refresh_prices_now", "rerank_with_weights",
                    "drop_candidates"):
            failed = payload.get("failed_platforms") if isinstance(payload, dict) else None
            if failed:
                yield {"type": "warning",
                       "message": f"以下平台价格暂无法实时确认:{', '.join(failed)}"}
            if task.candidates:
                yield {"type": "candidates_update", "candidates": _serialize(task)}


    # ------------------------------------------------------------------

    def _known_brands(self, category: str) -> list[str]:
        """本品类在各平台出现过的品牌,供品牌偏好识别使用。"""
        brands: set[str] = set()
        for adapter in self.adapters.values():
            items = getattr(adapter, "_items", None)
            if not callable(items):
                continue
            try:
                for item in items(category):
                    brands.add(item.spec.brand.lower())
            except Exception:
                continue
        return sorted(brands)


def _search_message(payload: Any) -> str:
    if not isinstance(payload, dict):
        return "候选已更新"
    return (
        f"已从多平台取得 {payload['offers_gathered']} 条报价,"
        f"对齐为 {payload['groups']} 款商品并完成到手价计算。"
    )


def _observation(task: ShoppingTask, guard: BudgetGuard | None = None) -> str:
    """交给决策层的任务观测。只陈述事实,不暗示下一步。"""
    requirement = task.requirement
    parts = [
        f"品类={task.category or '未确定'}",
        f"品类已确认={task.category_set}",
        f"候选数={len(task.candidates)}",
        f"缺失槽位={requirement.missing_slots()}",
        f"预算上限={requirement.budget_max}",
        f"已追问轮次={task.clarify_rounds}",
    ]
    if task.candidates:
        parts.append(f"当前首选={task.candidates[0].title}")
    if guard is not None and (blocked := guard.blocked_tools()):
        parts.append(f"已不可用的工具={blocked}")
    return " ".join(parts)
