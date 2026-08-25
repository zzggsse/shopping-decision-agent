"""端到端测试:全品类参数化,验证"新增品类不需改代码"的架构目标。"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.adapters.base import MockAdapter, SearchQuery, create_adapters
from app.agent import extract
from app.agent.graph import ShoppingAgent
from app.catalog import registry
from app.domain.models import ShoppingTask, Weights
from app.main import app
from app.services import freshness, matching, pricing, ranking

client = TestClient(app)

ALL_CATEGORIES = registry.keys()

#: 每个品类一条"需求完整"的自然语言输入,用于驱动全流程
FULL_REQUESTS = {
    "laptop": "笔记本预算 7000 左右,主要编程开发,经常带出门",
    "phone": "手机预算 4000 以内,主要拍照,大屏看着爽",
    "earbuds": "降噪耳机预算 800 以内,通勤地铁用,入耳式",
    "robot_vacuum": "扫地机器人预算 3000 以内,养宠物毛发多,需要基础拖地",
    "shampoo": "洗发水预算 150 以内,头屑头痒",
    "food": "零食预算 50 以内,控糖",
}


def collect(task: ShoppingTask, text: str) -> list[dict]:
    agent = ShoppingAgent(create_adapters("mock"))

    async def run() -> list[dict]:
        return [event async for event in agent.handle_message(task, text)]

    return asyncio.run(run())


def run_full(category: str) -> tuple[ShoppingTask, list[dict]]:
    task = ShoppingTask(task_id=f"t-{category}")
    task.switch_category(category)
    events = collect(task, FULL_REQUESTS[category])
    return task, events


# --------------------------------------------------------------------------
# 品类注册表
# --------------------------------------------------------------------------


def test_registry_has_multiple_categories() -> None:
    assert len(ALL_CATEGORIES) >= 4
    for key in ALL_CATEGORIES:
        schema = registry.get(key)
        assert schema.required_slots, f"{key} 缺少必答槽位"
        assert schema.dimensions, f"{key} 缺少打分维度"
        assert schema.budget_options, f"{key} 缺少预算档位"
        # price 与 reputation 是通用维度,每个品类都应具备
        keys = {d.key for d in schema.dimensions}
        assert {"price", "reputation"} <= keys
        # 权重之和应接近 1,避免配置时手误
        assert abs(sum(schema.default_weights().values()) - 1.0) < 0.02


@pytest.mark.parametrize("text,expected", [
    ("想买个笔记本电脑", "laptop"),
    ("推荐个手机", "phone"),
    ("降噪耳机通勤用", "earbuds"),
    ("扫地机器人养猫家庭", "robot_vacuum"),
    ("今天天气不错", None),
])
def test_category_routing(text: str, expected: str | None) -> None:
    assert extract.detect_category(text) == expected


def test_longest_trigger_wins() -> None:
    """扫地机器人含"机"字,不应被更短的触发词抢走。"""
    assert extract.detect_category("买个扫地机器人") == "robot_vacuum"


# --------------------------------------------------------------------------
# 数据层
# --------------------------------------------------------------------------


@pytest.mark.parametrize("category", ALL_CATEGORIES)
def test_fixtures_exist_for_every_category(category: str) -> None:
    adapter = MockAdapter("jd")
    assert category in adapter.supported_categories()
    items = asyncio.run(adapter.search(SearchQuery(category=category)))
    assert len(items) >= 5
    assert all(item.spec.category == category for item in items)


def test_adapter_reports_category_coverage() -> None:
    """亚马逊不供货手机,应如实反映,便于编排层跳过。"""
    amazon = MockAdapter("amazon")
    assert "phone" not in amazon.supported_categories()
    assert "laptop" in amazon.supported_categories()


# --------------------------------------------------------------------------
# 全品类主流程
# --------------------------------------------------------------------------


@pytest.mark.parametrize("category", ALL_CATEGORIES)
def test_full_pipeline_for_every_category(category: str) -> None:
    task, events = run_full(category)
    kinds = [event["type"] for event in events]
    assert "report" in kinds, f"{category} 未产出报告"

    report = next(e for e in events if e["type"] == "report")["report"]
    assert report["category"] == category
    assert report["picks"], f"{category} 无推荐结果"

    top = report["picks"][0]
    assert top["final_price"] > 0
    assert top["summary"], "缺少属性摘要行"
    # 理由必须有内容,否则打分配置形同虚设
    assert top["pros"] or top["cons"], f"{category} 未生成推荐理由"


@pytest.mark.parametrize("category", ALL_CATEGORIES)
def test_sku_alignment_merges_platforms(category: str) -> None:
    adapters = create_adapters("mock")

    async def gather():
        batches = [
            await adapter.search(SearchQuery(category=category))
            for adapter in adapters.values()
            if category in adapter.supported_categories()
        ]
        return [item for batch in batches for item in batch]

    groups = matching.align(asyncio.run(gather()))
    assert groups
    # 至少有一款商品被聚合到 2 个以上平台,否则比价无意义
    assert any(len(group.offers) >= 2 for group in groups)
    # group_id 必须带品类前缀,防止跨品类串味
    assert all(group.group_id.startswith(category) for group in groups)


@pytest.mark.parametrize("category", ALL_CATEGORIES)
def test_price_spread_computed(category: str) -> None:
    _, events = run_full(category)
    report = next(e for e in events if e["type"] == "report")["report"]
    spreads = [p["price_spread"] for p in report["picks"] if p["price_spread"]]
    assert spreads, f"{category} 未算出跨平台价差"
    assert all(s["saved"] >= 0 for s in spreads)


@pytest.mark.parametrize("category", ALL_CATEGORIES)
def test_clarify_asks_before_searching(category: str) -> None:
    task = ShoppingTask(task_id=f"c-{category}")
    task.switch_category(category)
    schema = registry.get(category)
    events = collect(task, f"想买个{schema.label}")

    clarify = [e for e in events if e["type"] == "clarify"]
    assert clarify, f"{category} 需求不全却未追问"
    assert clarify[0]["options"], "追问缺少快捷选项"
    assert not task.candidates, "槽位不全就检索了"


@pytest.mark.parametrize("category", ALL_CATEGORIES)
def test_quick_options_fill_slots(category: str) -> None:
    """前端快捷选项应能独立填满所有必答槽位。"""
    schema = registry.get(category)
    task = ShoppingTask(task_id=f"q-{category}")
    task.switch_category(category)

    task.requirement = extract.apply_quick_option(
        "budget", schema.budget_options[1], task.requirement
    )
    for slot in schema.slots:
        if slot.required:
            task.requirement = extract.apply_quick_option(
                slot.key, slot.options[0], task.requirement
            )

    assert task.requirement.missing_slots() == []
    assert task.requirement.coverage() == 1.0


# --------------------------------------------------------------------------
# 打分与权重
# --------------------------------------------------------------------------


@pytest.mark.parametrize("category", ALL_CATEGORIES)
def test_weight_extremes_change_ranking(category: str) -> None:
    """把价格权重与主性能维度分别拉满,排序应当变化。"""
    task, _ = run_full(category)
    assert task.candidates

    schema = registry.get(category)
    other = next(d.key for d in schema.dimensions if d.key not in ("price", "reputation"))

    price_first = ranking.score_candidates(
        task.candidates,
        Weights(values={**{d.key: 0.01 for d in schema.dimensions}, "price": 0.9}),
        task.requirement,
    )
    other_first = ranking.score_candidates(
        task.candidates,
        Weights(values={**{d.key: 0.01 for d in schema.dimensions}, other: 0.9}),
        task.requirement,
    )
    assert price_first[0].group_id != other_first[0].group_id, (
        f"{category} 权重反转后排序未变化"
    )


@pytest.mark.parametrize("category", ALL_CATEGORIES)
def test_missing_attribute_does_not_penalize(category: str) -> None:
    """属性缺失应按剩余占比归一,而非直接算低分。"""
    task, _ = run_full(category)
    schema = registry.get(category)
    dimension = next(
        (d for d in schema.dimensions if len(d.components) >= 2), None
    )
    if dimension is None:
        pytest.skip("该品类无多属性合成维度")

    group = task.candidates[0]
    full = ranking.score_candidates([group], task.weights, task.requirement)[0]

    stripped = group.model_copy(deep=True)
    removed = next(iter(dimension.components))
    stripped.spec.attributes.pop(removed, None)
    partial = ranking.score_candidates([stripped], task.weights, task.requirement)[0]

    # 单候选池下归一化区间退化,两者都应落在合法范围内且不为 0
    assert 0 <= partial.dimensions[dimension.key] <= 1
    assert partial.dimensions[dimension.key] > 0


def test_price_evidence_present_for_all_platforms() -> None:
    adapter = MockAdapter("amazon")
    item = asyncio.run(adapter.search(SearchQuery(category="laptop")))[0]
    priced = pricing.compute_final_price(item.offer)
    labels = [component.label for component in priced.components]
    assert "跨境税费" in labels
    assert all(component.evidence for component in priced.components)


# --------------------------------------------------------------------------
# 品类切换
# --------------------------------------------------------------------------


def test_switching_category_resets_context() -> None:
    task = ShoppingTask(task_id="switch")
    collect(task, FULL_REQUESTS["laptop"])
    assert task.category == "laptop"
    assert task.candidates

    events = collect(task, "算了,我想看看降噪耳机,预算 800 以内通勤用入耳式")
    assert task.category == "earbuds"
    assert any(e["type"] == "category" for e in events)
    # 候选池必须换成耳机,不能残留笔记本
    assert all(group.spec.category == "earbuds" for group in task.candidates)
    assert any(entry.action == "category" for entry in task.decision_log)


def test_weights_reset_on_category_switch() -> None:
    task = ShoppingTask(task_id="switch-w")
    task.switch_category("laptop")
    assert "portability" in task.weights.values

    task.switch_category("earbuds")
    assert "noise_cancel" in task.weights.values
    assert "portability" not in task.weights.values


def test_min_spec_parsing_is_category_aware() -> None:
    """手机的 mAh 不应被解析进笔记本需求。"""
    phone = extract.parse_min_specs("要 5000mah 大电池", "phone")
    assert phone.get("battery_mah") == 5000

    laptop = extract.parse_min_specs("要 5000mah 大电池", "laptop")
    assert "battery_mah" not in laptop


def test_brand_deny_filters_candidates() -> None:
    task = ShoppingTask(task_id="deny")
    collect(task, "手机预算 6000 以内主要拍照大屏,不要苹果")
    brands = {matching.normalize_brand(g.spec.brand) for g in task.candidates}
    assert "apple" not in brands
    assert any(entry.action == "drop" for entry in task.decision_log)


# --------------------------------------------------------------------------
# 新鲜度与实时价格
# --------------------------------------------------------------------------


@pytest.mark.parametrize("category", ALL_CATEGORIES)
def test_stale_marking_and_redirect_check(category: str) -> None:
    task, _ = run_full(category)
    offer = task.candidates[0].offers[0]

    offer.fetched_at = offer.fetched_at - timedelta(
        seconds=freshness.DISPLAY_STALE_TTL + 60
    )
    freshness.mark_staleness(task.candidates)
    assert offer.stale

    result = asyncio.run(freshness.verify_before_redirect(offer, create_adapters("mock")))
    assert result["reason"] in ("confirmed", "price_changed")
    assert result["current_price"] is not None


def test_live_mode_never_serves_stale_price_silently() -> None:
    """live 适配器未接入时应诚实标记,而非沿用旧价冒充实时价。"""
    task, _ = run_full("laptop")
    offer = task.candidates[0].offers[0]

    result = asyncio.run(
        freshness.verify_before_redirect(offer, create_adapters("live"))
    )
    assert result["ok"] is False
    assert result["reason"] == "price_unavailable"
    assert result["current_price"] is None


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------


def test_health_lists_categories() -> None:
    data = client.get("/api/health").json()
    assert data["data_source_mode"] == "mock"
    assert set(data["categories"]) == set(ALL_CATEGORIES)


def test_categories_endpoint_describes_schema() -> None:
    items = client.get("/api/categories").json()
    assert len(items) == len(ALL_CATEGORIES)
    for item in items:
        assert item["label"]
        assert item["dimensions"]
        assert item["attributes"]
        assert item["platforms"]


def sse_events(response) -> list[dict]:
    return [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data:")
    ]


@pytest.mark.parametrize("category", ALL_CATEGORIES)
def test_api_chat_stream_per_category(category: str) -> None:
    response = client.post(
        "/api/chat/stream",
        json={"message": FULL_REQUESTS[category], "category": category},
    )
    assert response.status_code == 200
    events = sse_events(response)
    kinds = [event["type"] for event in events]
    assert "report" in kinds

    created = next(e for e in events if e["type"] == "task_created")
    assert created["schema"]["key"] == category

    restored = client.get(f"/api/tasks/{created['task_id']}").json()
    assert restored["category"] == category
    assert restored["candidates"]
    assert restored["report"]["picks"]
    assert restored["decision_log"]


def test_api_weights_rejects_unknown_dimension() -> None:
    response = client.post(
        "/api/chat/stream",
        json={"message": FULL_REQUESTS["earbuds"], "category": "earbuds"},
    )
    task_id = next(
        e["task_id"] for e in sse_events(response) if e["type"] == "task_created"
    )

    ok = client.post(
        f"/api/tasks/{task_id}/weights",
        json={"weights": {"noise_cancel": 0.8, "price": 0.1}},
    )
    assert ok.status_code == 200
    assert ok.json()["candidates"]

    bad = client.post(
        f"/api/tasks/{task_id}/weights",
        json={"weights": {"portability": 0.8}},
    )
    assert bad.status_code == 400

# --------------------------------------------------------------------------
# 枚举可读性
# --------------------------------------------------------------------------


@pytest.mark.parametrize("category", ALL_CATEGORIES)
def test_enum_attributes_have_chinese_labels(category: str) -> None:
    """枚举属性必须配中文标签,否则用户会看到 good / in_ear 这类原始值。"""
    schema = registry.get(category)
    for attribute in schema.attributes:
        if attribute.kind != "enum":
            continue
        assert attribute.labels, f"{category}.{attribute.key} 未配置枚举标签"
        for value in attribute.scale:
            rendered = schema.display(attribute.key, value)
            assert rendered, f"{category}.{attribute.key} 的 {value} 无展示文本"
            # 允许 sRGB / P3 这类通用技术名词原样保留,
            # 但不能出现 good / in_ear 这种纯小写下划线的内部编码
            assert not re.fullmatch(r"[a-z][a-z_]*", rendered), (
                f"{category}.{attribute.key} 展示为内部编码 {rendered}"
            )


@pytest.mark.parametrize("category", ALL_CATEGORIES)
def test_summary_line_is_human_readable(category: str) -> None:
    task, _ = run_full(category)
    summary = task.candidates[0].spec.summary_line()
    assert summary
    # 摘要行中不应出现下划线风格的原始枚举值
    assert "_" not in summary, f"{category} 摘要含原始枚举值:{summary}"


def test_slot_signals_are_chinese() -> None:
    """"已记录"回执不应出现 dev / pet 这类内部编码。"""
    for category, message in FULL_REQUESTS.items():
        task = ShoppingTask(task_id=f"sig-{category}")
        task.switch_category(category)
        events = collect(task, message)
        understood = next((e for e in events if e["type"] == "understood"), None)
        assert understood, f"{category} 未产出理解回执"
        for signal in understood["signals"]:
            assert not re.search(r":[a-z][a-z_]*$", signal), (
                f"{category} 回执含内部编码:{signal}"
            )


# --------------------------------------------------------------------------
# 未知品类不应默认用笔记本追问
# --------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["我想买个沙发", "有没有猫粮推荐", "想买洗衣液"])
def test_unknown_category_prompts_category_selection(text: str) -> None:
    """未注册品类必须先问用户买什么,绝不能拿默认的笔记本去追问。"""
    task = ShoppingTask(task_id=f"unknown-{text}")
    events = collect(task, text)
    kinds = [e["type"] for e in events]

    assert "select_category" in kinds, f"输入「{text}」未触发品类选择"
    event = next(e for e in events if e["type"] == "select_category")
    labels = [c["label"] for c in event["categories"]]
    assert "笔记本电脑" in labels and "无线耳机" in labels

    # 关键:不能出现笔记本专属的预算追问
    clarify = [e for e in events if e["type"] == "clarify"]
    assert not clarify, f"输入「{text}」却直接追问了笔记本槽位"
    assert task.candidates == []


def test_unknown_category_then_pick_one_runs_pipeline() -> None:
    """先识别不出,用户点选品类后应正常进入流程。"""
    task = ShoppingTask(task_id="unknown-pick")
    collect(task, "想买个沙发")
    assert not task.category_set

    events = collect(task, "我想看无线耳机,预算 800 以内通勤入耳")
    assert task.category == "earbuds"
    report = next((e for e in events if e["type"] == "report"), None)
    assert report is not None
    assert report["report"]["category"] == "earbuds"


def test_first_message_with_explicit_category_marks_confirmed() -> None:
    task = ShoppingTask(task_id="explicit-cat")
    events = collect(task, "想买个手机")
    # 手机被识别,应直接进入预算追问,而不是再问品类
    assert task.category_set is True
    assert task.category == "phone"
    assert any(e["type"] == "clarify" for e in events)
    assert not any(e["type"] == "select_category" for e in events)
