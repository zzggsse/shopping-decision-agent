"""四项对照实现的测试:LangGraph / MCP / 多智能体 / few-shot。

这些实现默认全部关闭。测试的重点不是"它们能跑",而是两件事:
  1. **等价性** —— 打开 LangGraph / MCP 之后,决策结果必须与默认路径一致。
     否则"可切换"就是假的,只是换了个会给出不同答案的分支。
  2. **代价可量化** —— few-shot 的 token 增幅、多智能体的品类倍数,
     必须能被测出来,这样 README 里写的代价数字才有出处。
"""

from __future__ import annotations

import asyncio

import pytest

from app.adapters.base import create_adapters
from app.agent.graph import ShoppingAgent
from app.domain.models import ShoppingTask
from app.harness.flags import FeatureFlags, flags


SHAMPOO_TEXT = "洗发水 50以内 头屑头痒"


@pytest.fixture(autouse=True)
def _flags_off(monkeypatch):
    """每个用例开始前把四个开关清干净,避免环境变量泄漏到别的测试。"""
    for name in ("USE_LANGGRAPH", "USE_MCP", "USE_MULTI_AGENT", "USE_FEW_SHOT"):
        monkeypatch.delenv(name, raising=False)
    yield


def run(text: str, category: str | None = None) -> ShoppingTask:
    agent = ShoppingAgent(create_adapters("mock"))
    task = ShoppingTask(task_id="alt-impl")
    if category:
        task.switch_category(category)

    async def go() -> None:
        async for _ in agent.handle_message(task, text):
            pass

    asyncio.run(go())
    return task


def fingerprint(task: ShoppingTask) -> tuple:
    """决策指纹:候选数 + Top3 标题。用于跨实现比对结论是否一致。"""
    return (len(task.candidates), tuple(c.title for c in task.candidates[:3]))


# --------------------------------------------------------------------------
# 开关本身
# --------------------------------------------------------------------------


def test_all_flags_default_off() -> None:
    """默认必须全关 —— 默认路径是经过完整回归的那条。"""
    current = flags()
    assert current.enabled() == []
    assert not current.use_langgraph
    assert not current.use_mcp
    assert not current.use_multi_agent
    assert not current.use_few_shot


@pytest.mark.parametrize("raw,expected", [
    ("1", True), ("true", True), ("TRUE", True), ("yes", True), ("on", True),
    ("0", False), ("false", False), ("", False), ("maybe", False),
])
def test_flag_parsing(monkeypatch, raw: str, expected: bool) -> None:
    monkeypatch.setenv("USE_MCP", raw)
    assert flags().use_mcp is expected


def test_enabled_reports_open_switches(monkeypatch) -> None:
    monkeypatch.setenv("USE_MCP", "1")
    monkeypatch.setenv("USE_FEW_SHOT", "1")
    assert flags().enabled() == ["few_shot", "mcp"]


def test_health_reports_alt_implementations(monkeypatch) -> None:
    """打开了对照实现必须在 /api/health 如实上报,否则排查会看错路径。"""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    assert client.get("/api/health").json()["alt_implementations"] == []

    monkeypatch.setenv("USE_LANGGRAPH", "1")
    assert client.get("/api/health").json()["alt_implementations"] == ["langgraph"]


# --------------------------------------------------------------------------
# 等价性:四种组合结论必须一致
# --------------------------------------------------------------------------


def test_langgraph_and_mcp_reach_same_decision(monkeypatch) -> None:
    baseline = fingerprint(run(SHAMPOO_TEXT))

    for env in ({"USE_LANGGRAPH": "1"}, {"USE_MCP": "1"},
                {"USE_LANGGRAPH": "1", "USE_MCP": "1"}):
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        assert fingerprint(run(SHAMPOO_TEXT)) == baseline, f"{env} 改变了决策结论"
        for key in env:
            monkeypatch.delenv(key)


def test_langgraph_still_emits_report(monkeypatch) -> None:
    """LangGraph 路径下事件是攒完再吐(流式退化成批式),但内容不能丢。"""
    monkeypatch.setenv("USE_LANGGRAPH", "1")
    agent = ShoppingAgent(create_adapters("mock"))
    task = ShoppingTask(task_id="lg-report")

    async def go() -> list[dict]:
        return [event async for event in agent.handle_message(task, SHAMPOO_TEXT)]

    events = asyncio.run(go())
    assert "report" in [event["type"] for event in events]


# --------------------------------------------------------------------------
# MCP:schema 往返
# --------------------------------------------------------------------------


def test_mcp_exposes_every_tool_without_rewriting_them() -> None:
    from app.agent.toolkit import tool_schemas
    from app.mcp.server import build_mcp_tools

    ours = tool_schemas()
    mcp_tools = build_mcp_tools()
    assert len(mcp_tools) == len(ours)
    assert {t["name"] for t in mcp_tools} == {s["function"]["name"] for s in ours}
    # MCP 用 inputSchema 承载参数,每个工具都必须有
    assert all(t["inputSchema"]["type"] == "object" for t in mcp_tools)


def test_mcp_schema_roundtrip_is_lossless() -> None:
    """本项目 schema -> MCP -> 本项目,名称/描述/参数都不能丢。"""
    from app.agent.toolkit import tool_schemas
    from app.mcp.server import build_mcp_tools, to_openai_schema

    original = {s["function"]["name"]: s["function"] for s in tool_schemas()}
    for item in to_openai_schema(build_mcp_tools()):
        back = item["function"]
        source = original[back["name"]]
        assert back["description"] == source["description"]
        assert back["parameters"] == source["parameters"]


def test_mcp_bridge_actually_executes_tool() -> None:
    from app.agent.toolkit import Context
    from app.mcp import InProcessMCPBridge
    from app.profile.store import ProfileStore

    task = ShoppingTask(task_id="mcp-call")
    task.switch_category("shampoo")
    ctx = Context(task=task, profiles=ProfileStore(), adapters=create_adapters("mock"))
    bridge = InProcessMCPBridge()
    assert len(bridge.list_tools()) == len(bridge.openai_tools())
    result = asyncio.run(
        bridge.call_tool(ctx, "search_candidates", {"text": SHAMPOO_TEXT})
    )
    assert result["type"] != "tool_error"
    assert task.candidates


def test_mcp_server_builds() -> None:
    from app.mcp.server import build_server

    assert build_server() is not None


# --------------------------------------------------------------------------
# few-shot:代价必须可量化
# --------------------------------------------------------------------------


def test_few_shot_overhead_is_measured() -> None:
    """README 里写的 token 增幅要有出处 —— 就是这个函数算出来的。"""
    from app.agent.few_shot import estimate_overhead

    from app.agent.llm import SYSTEM_PROMPT
    from app.harness.context import estimate_tokens

    extra = estimate_overhead()
    base = estimate_tokens(SYSTEM_PROMPT)
    assert base > 0 and extra > 0
    # 增幅超过 50% 才值得在 README 里被当作"代价"讨论
    assert extra / base > 0.5


def test_few_shot_only_changes_prompt_not_conclusion(monkeypatch) -> None:
    """few-shot 是给真 LLM 看的示范,离线 MockClient 的结论不应被改变。"""
    baseline = fingerprint(run(SHAMPOO_TEXT))
    monkeypatch.setenv("USE_FEW_SHOT", "1")
    assert fingerprint(run(SHAMPOO_TEXT)) == baseline


def test_few_shot_appends_examples_to_prompt(monkeypatch) -> None:
    from app.agent.llm import active_system_prompt

    plain = active_system_prompt()
    monkeypatch.setenv("USE_FEW_SHOT", "1")
    augmented = active_system_prompt()
    assert len(augmented) > len(plain)
    assert plain in augmented


def test_few_shot_examples_carry_no_category_knowledge() -> None:
    """示例只演示决策路径。商品知识属于 app/catalog,写进提示词会造成两处真相。"""
    from app.agent.few_shot import FEW_SHOT_EXAMPLES, render_examples

    rendered = str(FEW_SHOT_EXAMPLES) + render_examples()
    for leaked in ("酮康唑", "MagicBook", "RTX", "水杨酸"):
        assert leaked not in rendered


# --------------------------------------------------------------------------
# 多智能体:只在跨品类时启用
# --------------------------------------------------------------------------


@pytest.mark.parametrize("text,expected", [
    ("预算5000 买笔记本还是手机", ["laptop", "phone"]),
    ("耳机和手机各推荐一个 预算3000", ["phone", "earbuds"]),
    ("洗发水和零食 100以内", ["shampoo", "food"]),
])
def test_detect_multi_categories(text: str, expected: list[str]) -> None:
    from app.harness.multi_agent import detect_multi_categories

    assert sorted(detect_multi_categories(text)) == sorted(expected)


@pytest.mark.parametrize("text", [SHAMPOO_TEXT, "笔记本 预算7000 打游戏", "随便看看"])
def test_single_category_falls_back_to_single_agent(text: str) -> None:
    """品类数 < 2 时必须返回空 —— 多智能体在单品类上是纯开销。"""
    from app.harness.multi_agent import detect_multi_categories

    assert detect_multi_categories(text) == []


def test_multi_agent_keeps_categories_separate(monkeypatch) -> None:
    """每个 worker 必须只看自己的品类。

    这里守的是一个真实踩过的 bug:原文含多个品类触发词,worker 内部的
    detect_category/set_category 会把品类改回同一个,导致几个 worker
    返回同一件商品。修法是 ctx.flow["lock_category"]。
    """
    monkeypatch.setenv("USE_MULTI_AGENT", "1")
    from app.harness.multi_agent import MultiAgentComparator
    from app.profile.store import profile_store

    text = "耳机和手机各推荐一个 预算3000"
    comparator = MultiAgentComparator(
        adapters=create_adapters("mock"), profiles=profile_store
    )
    verdicts = asyncio.run(comparator.compare(text, ["phone", "earbuds"]))

    assert [v.category for v in verdicts] == ["phone", "earbuds"]
    assert all(v.ok for v in verdicts), [v.error for v in verdicts]
    # 关键断言:两个品类不能返回同一件商品
    assert verdicts[0].title != verdicts[1].title
    assert verdicts[0].url != verdicts[1].url


def test_multi_agent_worker_does_not_recurse(monkeypatch) -> None:
    """worker 内部不能再次派发,否则无限递归。"""
    monkeypatch.setenv("USE_MULTI_AGENT", "1")
    agent = ShoppingAgent(create_adapters("mock"), allow_multi_agent=False)
    task = ShoppingTask(task_id="no-recurse")
    task.switch_category("phone")

    async def go() -> list[dict]:
        return [
            event
            async for event in agent.handle_message(task, "耳机和手机各推荐一个 预算3000")
        ]

    events = asyncio.run(go())
    assert "multi_category_report" not in [event["type"] for event in events]


def test_multi_agent_summary_refuses_single_winner() -> None:
    """跨品类没有公共量纲,总结必须给各自最优而不是硬选一个冠军。"""
    from app.harness.multi_agent import CategoryVerdict, summarize

    report = summarize([
        CategoryVerdict(category="phone", label="智能手机", ok=True,
                        title="A", price=2999.0, platform="jd"),
        CategoryVerdict(category="earbuds", label="无线耳机", ok=True,
                        title="B", price=599.0, platform="tmall"),
    ])
    assert report["type"] == "multi_category_report"
    assert len(report["verdicts"]) == 2
    assert "A" in report["summary"] and "B" in report["summary"]


def test_multi_agent_failure_does_not_break_others() -> None:
    """一个品类失败只影响它自己,并如实写出原因。"""
    from app.harness.multi_agent import CategoryVerdict, summarize

    report = summarize([
        CategoryVerdict(category="phone", label="智能手机", ok=True,
                        title="A", price=2999.0, platform="jd"),
        CategoryVerdict(category="food", label="零食", ok=False, error="检索超时"),
    ])
    assert "检索超时" in report["summary"]


# --------------------------------------------------------------------------
# 品类锁(修 bug 时引入,单独守住)
# --------------------------------------------------------------------------


def test_lock_category_blocks_switch() -> None:
    from app.agent.toolkit import Context, execute_tool
    from app.profile.store import ProfileStore

    task = ShoppingTask(task_id="locked")
    task.switch_category("earbuds")
    ctx = Context(task=task, profiles=ProfileStore(), adapters=create_adapters("mock"))
    ctx.flow["lock_category"] = True

    result = asyncio.run(execute_tool(ctx, "set_category", {"category": "phone"}))
    assert result["type"] != "tool_error"
    assert result["result"]["locked"] is True
    assert task.category == "earbuds"


def test_unlocked_category_switch_still_works() -> None:
    """默认路径不受影响:没锁的时候切换品类照常。"""
    from app.agent.toolkit import Context, execute_tool
    from app.profile.store import ProfileStore

    task = ShoppingTask(task_id="unlocked")
    task.switch_category("earbuds")
    ctx = Context(task=task, profiles=ProfileStore(), adapters=create_adapters("mock"))

    result = asyncio.run(execute_tool(ctx, "set_category", {"category": "phone"}))
    assert result["result"]["switched"] is True
    assert task.category == "phone"
