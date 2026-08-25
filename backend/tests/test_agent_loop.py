"""Agent 循环与决策能力测试。

关注点不是"某个函数返回什么",而是"决策层是否真的在按观测选工具":
工具是否被正确编排、候选不足能否自我修复、放宽预算后是否如实告知。
"""

from __future__ import annotations

import asyncio

import pytest

from app.adapters.base import create_adapters
from app.agent.graph import ShoppingAgent
from app.agent.llm import Decision, LLMClient, MockClient
from app.agent.toolkit import Context, execute_tool, tool_schemas
from app.domain.models import ShoppingTask
from app.profile.store import ProfileStore


def collect(task: ShoppingTask, text: str, profiles=None) -> list[dict]:
    agent = ShoppingAgent(create_adapters("mock"), profiles=profiles)

    async def run() -> list[dict]:
        return [event async for event in agent.handle_message(task, text)]

    return asyncio.run(run())


class RecordingClient(LLMClient):
    """包装 MockClient,记录每一步选了哪个工具,用于断言编排顺序。"""

    def __init__(self, inner: MockClient) -> None:
        self.inner = inner
        self.calls: list[str] = []

    async def decide(self, messages, tools, state):
        decision = await self.inner.decide(messages, tools, state)
        for call in decision.tool_calls:
            self.calls.append(call["name"])
        return decision


def trace(task: ShoppingTask, text: str) -> tuple[list[dict], list[str]]:
    agent = ShoppingAgent(create_adapters("mock"))
    recorder = RecordingClient(MockClient(agent._current_context))
    agent.llm = recorder

    async def run() -> list[dict]:
        return [event async for event in agent.handle_message(task, text)]

    return asyncio.run(run()), recorder.calls


# --------------------------------------------------------------------------
# 工具接口
# --------------------------------------------------------------------------


def test_all_tools_expose_valid_schema() -> None:
    """每个工具都要能被 LLM 理解:名称 + 描述 + JSON Schema 参数。"""
    for schema in tool_schemas():
        assert schema["type"] == "function"
        function = schema["function"]
        assert function["name"]
        assert function["description"], f"{function['name']} 缺少描述"
        assert function["parameters"]["type"] == "object"


def test_unknown_tool_is_reported_not_raised() -> None:
    task = ShoppingTask(task_id="unknown-tool")
    task.switch_category("laptop")
    ctx = Context(task=task, profiles=ProfileStore(), adapters=create_adapters("mock"))
    result = asyncio.run(execute_tool(ctx, "no_such_tool", {}))
    assert result["type"] == "tool_error"


# --------------------------------------------------------------------------
# 决策编排
# --------------------------------------------------------------------------


def test_loop_orchestrates_tools_in_sensible_order() -> None:
    """完整需求应走完:识别品类 → 理解 → 检索 → 复核价格 → 给结论。"""
    task = ShoppingTask(task_id="orchestrate")
    _, calls = trace(task, "笔记本预算 7000,主要编程开发,经常带出门")

    assert "detect_category" in calls
    assert "understand_requirement" in calls
    assert "search_candidates" in calls
    assert "refresh_prices_now" in calls
    assert calls[-1] == "compose_answer", f"最后一步应是给结论,实际 {calls[-1]}"
    # 检索必须发生在理解需求之后
    assert calls.index("understand_requirement") < calls.index("search_candidates")


def test_unknown_category_asks_user_instead_of_guessing() -> None:
    task = ShoppingTask(task_id="ask-category")
    events, calls = trace(task, "我想买个东西")

    assert "ask_category_choice" in calls
    assert "search_candidates" not in calls, "品类未定就不该检索"
    assert any(e["type"] == "select_category" for e in events)


def test_missing_slot_triggers_clarify_then_stops() -> None:
    """槽位不全应追问并交还控制权,不该硬着头皮出报告。"""
    task = ShoppingTask(task_id="clarify-stop")
    events, calls = trace(task, "想买笔记本")

    assert "ask_clarifying_question" in calls
    assert "compose_answer" not in calls
    kinds = [e["type"] for e in events]
    assert "clarify" in kinds
    assert "report" not in kinds


def test_clarify_does_not_loop_forever() -> None:
    """反复不给关键信息时,应停止纠缠并给出结果。"""
    task = ShoppingTask(task_id="clarify-cap")
    task.switch_category("laptop")
    for _ in range(5):
        collect(task, "随便吧")
    assert task.clarify_rounds <= MockClient.MAX_CLARIFY_ROUNDS


def test_ingredient_category_analyzes_before_concluding() -> None:
    """有配料表的品类必须先看档案与成分,再下结论。"""
    task = ShoppingTask(task_id="ingredient-order")
    _, calls = trace(task, "洗发水预算 150 以内,头屑头痒")

    assert "analyze_ingredients" in calls
    assert "get_user_profile" in calls
    assert calls.index("analyze_ingredients") < calls.index("compose_answer")


# --------------------------------------------------------------------------
# 自我修复:候选不足
# --------------------------------------------------------------------------


def test_too_few_candidates_triggers_progressive_relax() -> None:
    """预算离市场价太远时,应自己逐级放宽并重新检索,而不是直接放弃。"""
    task = ShoppingTask(task_id="relax")
    events, calls = trace(task, "笔记本预算 1000 以内,主要编程,经常带出门")

    assert calls.count("relax_constraints") >= 2, "一次放宽不够时应继续放宽"
    # 放宽后必须重新检索
    assert calls.count("search_candidates") >= 2
    report = next(e["report"] for e in events if e["type"] == "report")
    assert report["picks"], "放宽后应能给出候选"


def test_relaxed_budget_is_disclosed_to_user() -> None:
    """悄悄放宽预算等于欺骗:结论必须说明超出原预算多少。"""
    task = ShoppingTask(task_id="disclose")
    events, _ = trace(task, "笔记本预算 1000 以内,主要编程,经常带出门")

    summary = next(e["report"] for e in events if e["type"] == "report")["summary"]
    assert "1000" in summary, "应提到用户原本的预算"
    assert "高出" in summary or "超" in summary, f"未说明超预算:{summary}"


def test_within_budget_does_not_mention_overspend() -> None:
    task = ShoppingTask(task_id="no-overspend")
    events, _ = trace(task, "笔记本预算 7000,主要编程开发,经常带出门")

    summary = next(e["report"] for e in events if e["type"] == "report")["summary"]
    assert "高出" not in summary


# --------------------------------------------------------------------------
# 结论质量
# --------------------------------------------------------------------------


def test_conclusion_explains_choice_and_tradeoff() -> None:
    """结论要说清推荐什么、为什么、多少钱,而不是干巴巴一句话。"""
    task = ShoppingTask(task_id="why")
    events, _ = trace(task, "笔记本预算 7000,主要编程开发,经常带出门")

    report = next(e["report"] for e in events if e["type"] == "report")
    summary = report["summary"]
    top = report["picks"][0]

    assert top["title"] in summary, "结论应点明推荐哪一款"
    assert str(int(top["final_price"])) in summary, "结论应给出到手价"
    assert "因为" in summary, "结论应解释理由"


def test_loop_terminates_even_if_decider_never_finishes() -> None:
    """决策层失控时,循环必须靠步数上限收敛,不能挂死。"""

    class NeverFinishes(LLMClient):
        async def decide(self, messages, tools, state):
            return Decision(tool_calls=[{"name": "get_user_profile", "arguments": {}}])

    task = ShoppingTask(task_id="runaway")
    task.switch_category("laptop")
    agent = ShoppingAgent(create_adapters("mock"), llm=NeverFinishes())

    async def run() -> list[dict]:
        return [event async for event in agent.handle_message(task, "笔记本 7000")]

    events = asyncio.run(run())
    assert any(e["type"] == "report" for e in events), "应兜底产出报告"


def test_tool_failure_does_not_abort_the_loop() -> None:
    """单个工具报错应降级继续,并把问题告知用户。"""

    class BadArgs(LLMClient):
        def __init__(self) -> None:
            self.step = 0

        async def decide(self, messages, tools, state):
            self.step += 1
            if self.step == 1:
                # 不存在的品类,工具会返回 tool_error
                return Decision(tool_calls=[
                    {"name": "set_category", "arguments": {"category": "spaceship"}}
                ])
            return Decision(tool_calls=[{"name": "compose_answer", "arguments": {}}])

    task = ShoppingTask(task_id="bad-tool")
    task.switch_category("laptop")
    agent = ShoppingAgent(create_adapters("mock"), llm=BadArgs())

    async def run() -> list[dict]:
        return [event async for event in agent.handle_message(task, "笔记本 7000")]

    events = asyncio.run(run())
    kinds = [e["type"] for e in events]
    assert "warning" in kinds, "工具失败应提示用户"
    assert "report" in kinds, "失败后仍应收敛出结果"


# --------------------------------------------------------------------------
# 品类切换
# --------------------------------------------------------------------------


def test_switching_category_mid_conversation() -> None:
    task = ShoppingTask(task_id="switch")
    collect(task, "笔记本预算 7000,主要编程开发,经常带出门")
    assert task.category == "laptop"

    events = collect(task, "算了,看看洗发水吧,预算 150,头屑头痒")
    assert task.category == "shampoo"
    report = next(e["report"] for e in events if e["type"] == "report")
    assert report["category"] == "shampoo"
    assert report["picks"]
