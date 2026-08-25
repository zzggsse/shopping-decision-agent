"""购物任务核心循环(agent loop)。

graph 不做任何购物决策,只负责三件事:
  1. 建立本轮 Context,把用户原话交给决策层
  2. 驱动循环:decide → execute_tool → 结果回填 → 再 decide
  3. 把工具结果转译成 SSE 事件下发前端

"要不要追问、追问什么、是否换品类、候选太少怎么办、结论怎么说"全部由
决策层(app/agent/llm.py)通过调用工具决定。工具实现在 app/agent/toolkit.py。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from ..adapters.base import PlatformAdapter
from ..domain.models import ShoppingTask, TaskState
from ..profile import profile_store
from .llm import SYSTEM_PROMPT, build_llm
from .serialize import build_report, serialize as _serialize
from .toolkit import Context as AgentContext
from .toolkit import execute_tool, tool_schemas

MAX_LOOP_STEPS = 14

#: 这些工具在等用户回话,执行后必须结束本轮
_AWAITING_TOOLS = {"ask_category_choice", "ask_clarifying_question"}


class ShoppingAgent:
    def __init__(
        self,
        adapters: dict[str, PlatformAdapter],
        profiles=None,
        llm=None,
    ) -> None:
        self.adapters = adapters
        self.profiles = profiles if profiles is not None else profile_store
        #: 决策层需要反向读取任务观测
        self._ctx: AgentContext | None = None
        self.llm = llm if llm is not None else build_llm(self._current_context)

    def _current_context(self) -> AgentContext | None:
        return self._ctx

    async def handle_message(
        self, task: ShoppingTask, text: str
    ) -> AsyncIterator[dict[str, Any]]:
        ctx = AgentContext(task=task, profiles=self.profiles, adapters=self.adapters)
        ctx.flow["last_text"] = text
        self._ctx = ctx

        async for event in self._loop(ctx, text):
            yield event

    # ------------------------------------------------------------------
    # Agent 循环
    # ------------------------------------------------------------------

    async def _loop(
        self, ctx: AgentContext, text: str
    ) -> AsyncIterator[dict[str, Any]]:
        task = ctx.task
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ]

        for step in range(MAX_LOOP_STEPS):
            decision = await self.llm.decide(messages, tool_schemas(), _observation(task))

            # 决策层直接给结论(未走 compose_answer)
            if decision.is_final:
                async for event in self._finish(task, decision.final):
                    yield event
                return

            for call in decision.tool_calls:
                name = call["name"]
                result = await execute_tool(ctx, name, call.get("arguments") or {})
                messages.append({
                    "role": "tool",
                    "tool_call_id": f"t{step}",
                    "name": name,
                    "content": _stringify(result),
                })

                for event in self._emit(result, task, name):
                    yield event

                payload = result.get("result")

                # compose_answer:产出报告并收尾
                if name == "compose_answer" and result["type"] == "tool_result":
                    task.state = TaskState.DECISION_READY
                    yield {"type": "task_state", "state": task.state.value}
                    yield {"type": "report", "report": payload["report"]}
                    return

                # 追问类工具:交还控制权给用户
                if (name in _AWAITING_TOOLS
                        and isinstance(payload, dict)
                        and payload.get("awaiting_user")):
                    task.state = TaskState.INTENT_CLARIFY
                    yield {"type": "task_state", "state": task.state.value}
                    return

        # 步数用尽仍未收敛:兜底出报告,避免前端卡住
        async for event in self._finish(task, None):
            yield event

    async def _finish(self, task: ShoppingTask, message: str | None):
        report = build_report(task)
        if message:
            report["summary"] = message
        task.state = TaskState.DECISION_READY
        yield {"type": "task_state", "state": task.state.value}
        yield {"type": "report", "report": report}

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


def _search_message(payload: Any) -> str:
    if not isinstance(payload, dict):
        return "候选已更新"
    return (
        f"已从多平台取得 {payload['offers_gathered']} 条报价,"
        f"对齐为 {payload['groups']} 款商品并完成到手价计算。"
    )


def _stringify(result: dict) -> str:
    """工具结果回填进消息历史。用 JSON,真实 LLM 与离线策略都能稳定解析。"""
    import json
    try:
        return json.dumps(result.get("result"), ensure_ascii=False, default=str)
    except Exception:
        return "{}"


def _observation(task: ShoppingTask) -> str:
    """交给决策层的任务观测。只陈述事实,不暗示下一步。"""
    requirement = task.requirement
    top = ""
    if task.candidates:
        best = task.candidates[0]
        top = f" 当前首选={best.title}"
    return (
        f"品类={task.category or '未确定'} 品类已确认={task.category_set} "
        f"候选数={len(task.candidates)} 缺失槽位={requirement.missing_slots()} "
        f"预算上限={requirement.budget_max} 已追问轮次={task.clarify_rounds}"
        f"{top}"
    )
