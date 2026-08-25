"""LangGraph 对照实现:用 StateGraph 表达核心循环。

默认不启用(USE_LANGGRAPH=1 打开)。存在的意义是给出一份可运行的对比,
说明"同一套决策逻辑用图框架表达是什么样、代价在哪"。

与自写 while 循环(graph.py:_loop)的关系:
  - **共用**同一个决策层(llm.py)、同一套工具(toolkit.py)、
    同一个预算看门(BudgetGuard)、同一份上下文装配(ContextAssembler)
  - **只替换**"下一步该走哪个节点"的表达方式

图的形状(与 _loop 的控制流一一对应):

    assemble ---> decide ---> [条件边]
       ^                        |
       |                        +--> act ---> assemble  (还要继续)
       |                        +--> finish ---> END    (收尾/预算耗尽)
       +------------------------+

一个必须说清的代价:
  LangGraph 的节点是"函数进、状态出",不能像 async generator 那样边跑边 yield。
  所以 SSE 事件只能先攒进 state.events,等图跑完再吐给前端。
  换句话说**流式体验会退化成批式**,除非再引入 astream_events 那套更复杂的机制。
  这是本项目默认不用它的直接原因之一。
"""

from __future__ import annotations

import time
from typing import Annotated, Any, TypedDict

from .context import ContextAssembler, ContextBudget, estimate_messages_tokens
from .orchestrator import BudgetGuard, RunBudget, RunTrace, TraceStep


def _append(left: list, right: list) -> list:
    """LangGraph reducer:事件与轨迹只增不改。"""
    return (left or []) + (right or [])


class LoopState(TypedDict, total=False):
    """图在节点间传递的状态。

    对应 _loop 里的局部变量 —— 这正是图框架的成本所在:
    原来是函数作用域里的普通变量,现在每个都要显式声明进 State 并考虑归并方式。
    """

    text: str
    observation: str
    messages: list[dict[str, Any]]
    step: int
    #: 决策层输出:待执行的工具调用
    tool_calls: list[dict[str, Any]]
    #: 决策层直接给出的最终答复
    final: str | None
    #: 攒起来的 SSE 事件(不能即时 yield,只能收集)
    events: Annotated[list[dict[str, Any]], _append]
    #: 终止原因,空串表示继续
    stop_reason: str
    done: bool


class LangGraphLoop:
    """把 ShoppingAgent 的核心循环表达成 StateGraph。

    调用方(graph.py)只需要 `async for event in loop.run(...)`,
    与自写循环的接口保持一致,便于对照。
    """

    def __init__(
        self,
        *,
        llm,
        tool_schemas,
        execute_tool,
        observe,
        emit,
        finish,
        remember,
        system_prompt: str,
        budget: RunBudget,
    ) -> None:
        self.llm = llm
        self.tool_schemas = tool_schemas
        self.execute_tool = execute_tool
        self.observe = observe
        self.emit = emit
        self.finish = finish
        self.remember = remember
        self.system_prompt = system_prompt
        self.budget = budget

    # ------------------------------------------------------------------
    # 图的构建
    # ------------------------------------------------------------------

    def _build(self):
        from langgraph.graph import END, StateGraph

        builder = StateGraph(LoopState)
        builder.add_node("assemble", self._node_assemble)
        builder.add_node("decide", self._node_decide)
        builder.add_node("act", self._node_act)

        builder.set_entry_point("assemble")
        # 装配完直接决策;但预算耗尽时 assemble 会置 done,直接结束
        builder.add_conditional_edges(
            "assemble",
            lambda state: END if state.get("done") else "decide",
            {END: END, "decide": "decide"},
        )
        builder.add_conditional_edges(
            "decide",
            lambda state: END if state.get("done") else "act",
            {END: END, "act": "act"},
        )
        # 行动完:要么回到装配继续下一轮,要么结束
        builder.add_conditional_edges(
            "act",
            lambda state: END if state.get("done") else "assemble",
            {END: END, "assemble": "assemble"},
        )
        # 递归上限交给自己的 BudgetGuard 管,这里给一个宽松的兜底
        return builder.compile()

    # ------------------------------------------------------------------
    # 节点实现
    # ------------------------------------------------------------------

    async def _node_assemble(self, state: LoopState) -> dict[str, Any]:
        """装配上下文,并在此处检查预算(对应 _loop 循环开头的 guard 检查)。"""
        step = state.get("step", 0)
        if reason := self._guard.exhausted(step):
            self._trace.stop_reason = reason
            self._task.log("budget", f"预算触顶:{reason}")
            return {"done": True, "stop_reason": reason}

        observation = self.observe(self._task, self._guard)
        messages = self._assembler.build(
            history=self._history,
            current_input=state["text"],
            observation=observation,
            memory_digest=self._digest,
        )
        return {"observation": observation, "messages": messages}

    async def _node_decide(self, state: LoopState) -> dict[str, Any]:
        """调用决策层。"""
        step = state.get("step", 0)
        started = time.monotonic()
        try:
            decision = await self.llm.decide(
                state["messages"], self.tool_schemas(), state["observation"]
            )
        except Exception as error:
            self._trace.add(TraceStep(index=step, kind="error", name="decide",
                                      ok=False, detail=str(error)))
            self._trace.stop_reason = f"决策层异常:{error}"
            return {
                "done": True,
                "stop_reason": f"决策层异常:{error}",
                "events": [{"type": "warning",
                            "message": f"决策出错,已给出当前结论:{error}"}],
            }

        self._trace.add(TraceStep(
            index=step,
            kind="decide",
            name="final" if decision.is_final else "tool_calls",
            elapsed_ms=int((time.monotonic() - started) * 1000),
            tokens=estimate_messages_tokens(state["messages"]),
            detail=", ".join(c["name"] for c in decision.tool_calls),
        ))

        if decision.is_final:
            self._trace.stop_reason = "决策层直接给出结论"
            return {"step": step + 1, "done": True, "final": decision.final,
                    "stop_reason": "决策层直接给出结论"}

        return {"step": step + 1, "tool_calls": decision.tool_calls}

    async def _node_act(self, state: LoopState) -> dict[str, Any]:
        """执行工具并收集事件。"""
        step = state.get("step", 0)
        events: list[dict[str, Any]] = []

        for call in state.get("tool_calls") or []:
            name = call["name"]
            arguments = call.get("arguments") or {}

            if self._guard.should_give_up(name):
                self._trace.add(TraceStep(index=step, kind="tool", name=name,
                                          ok=False, detail="连续失败过多,已放弃"))
                continue

            started = time.monotonic()
            result = await self.execute_tool(self._ctx, name, arguments)
            ok = result["type"] != "tool_error"
            self._guard.record_tool_result(name, ok)

            self._trace.add(TraceStep(
                index=step, kind="tool", name=name, arguments=arguments,
                ok=ok, detail="" if ok else str(result.get("result", "")),
                elapsed_ms=int((time.monotonic() - started) * 1000),
            ))
            self._assembler.record_tool(step, name, result)
            events.extend(self.emit(result, self._task, name))

            payload = result.get("result")
            self.remember(self._task, name, payload)

            # 收尾工具与等待用户回话:与 _loop 的终止条件保持一致
            terminal = self._terminal_check(name, ok, payload)
            if terminal is not None:
                return {"done": True, "events": events, **terminal}

        return {"events": events}

    def _terminal_check(self, name: str, ok: bool, payload) -> dict | None:
        """判断该工具是否终止本轮。返回 None 表示继续。"""
        from ..domain.models import TaskState

        if name == "compose_answer" and ok:
            self._trace.stop_reason = "compose_answer"
            report = payload["report"]
            self._session.add_assistant(report.get("summary", ""))
            self._task.state = TaskState.DECISION_READY
            return {
                "stop_reason": "compose_answer",
                "events": [
                    {"type": "task_state", "state": self._task.state.value},
                    {"type": "report", "report": report},
                ],
            }

        if (name in self._awaiting_tools and isinstance(payload, dict)
                and payload.get("awaiting_user")):
            self._trace.stop_reason = "等待用户回话"
            self._session.add_assistant(payload.get("question", ""))
            self._task.state = TaskState.INTENT_CLARIFY
            return {
                "stop_reason": "等待用户回话",
                "events": [{"type": "task_state", "state": self._task.state.value}],
            }
        return None

    # ------------------------------------------------------------------
    # 对外入口
    # ------------------------------------------------------------------

    async def run(
        self, *, ctx, text: str, session, history, digest: str,
        awaiting_tools: set[str], trace: RunTrace,
    ):
        """驱动图执行,把攒下的事件按序 yield 出来。

        注意这里的**流式退化**:图跑完才有事件可吐。
        自写循环是边跑边 yield,用户能实时看到每一步。
        """
        self._ctx = ctx
        self._task = ctx.task
        self._session = session
        self._history = history
        self._digest = digest
        self._awaiting_tools = awaiting_tools
        self._trace = trace
        self._guard = BudgetGuard(self.budget, trace)
        self._assembler = ContextAssembler(
            system_prompt=self.system_prompt, budget=ContextBudget()
        )

        app = self._build()
        # recursion_limit 给足:真正的终止由 BudgetGuard 决定
        final_state = await app.ainvoke(
            {"text": text, "step": 0, "events": [], "done": False},
            config={"recursion_limit": self.budget.max_steps * 3 + 10},
        )

        for event in final_state.get("events") or []:
            yield event

        # 收尾:与自写循环共用同一个 _finish
        if final_state.get("stop_reason") not in ("compose_answer", "等待用户回话"):
            async for event in self.finish(
                self._task, final_state.get("final"), session, trace
            ):
                yield event
        else:
            yield {"type": "trace", "trace": trace.to_dict()}
