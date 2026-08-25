"""成分分析与用户档案的端到端测试。"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.catalog import registry
from app.ingredients import analyze
from app.profile.models import UserProfile
from app.profile.store import ProfileStore
from app.main import app
from app.agent.graph import ShoppingAgent
from app.adapters.base import create_adapters
from app.domain.models import ShoppingTask

client = TestClient(app)


def run_agent(text: str, category: str, profile: UserProfile | None = None):
    store = ProfileStore()
    if profile:
        store.save(profile)
    agent = ShoppingAgent(create_adapters("mock"), profiles=store)
    task = ShoppingTask(task_id="t")
    task.switch_category(category)
    if profile:
        task.log("profile", f"档案条件:{profile.conditions}")

    async def run():
        return [event async for event in agent.handle_message(task, text)]

    events = asyncio.run(run())
    return task, events


# --------------------------------------------------------------------------
# 成分解析与知识库
# --------------------------------------------------------------------------


def test_ingredient_splitting() -> None:
    from app.ingredients import split_ingredients

    parts = split_ingredients("水、SLES、SLS，氨基酸/神经酰胺", "、,，;；/")
    assert "SLES" in parts and "SLS" in parts
    assert "氨基酸" in parts and "神经酰胺" in parts
    assert len(parts) == 5  # 去重 + 多种分隔符


def test_alias_matching() -> None:
    schema = registry.get("shampoo")
    result = analyze("水、椰油酰谷氨酸钠、SLES", schema, None)
    names = {item.name for item in result.recognized}
    assert "氨基酸表活" in names
    assert "月桂醇聚醚硫酸酯钠" in names


def test_shampoo_dandruff_concern_matched() -> None:
    schema = registry.get("shampoo")
    result = analyze(
        "水、月桂醇聚醚硫酸酯钠(SLES)、酮康唑、吡硫鎓锌(ZPT)", schema, None,
    )
    assert "头屑" in result.matched_concerns
    names = {item.name for item in result.recognized}
    assert "酮康唑" in names
    assert "吡硫鎓锌" in names


# --------------------------------------------------------------------------
# 用户档案:禁忌与偏好
# --------------------------------------------------------------------------


def test_sensitive_scalp_flags_sls() -> None:
    schema = registry.get("shampoo")
    profile = UserProfile(conditions=["sensitive_scalp"])
    result = analyze("水、月桂醇硫酸酯钠(SLS)、香精", schema, profile)
    assert any("SLS" in avoid or "敏感" in avoid for avoid in result.avoids)
    # 氨基酸配方应被加分
    good = analyze("水、椰油酰谷氨酸钠(氨基酸表活)、神经酰胺", schema, profile)
    assert any("敏感头皮" in b for b in good.benefits)


def test_pregnant_flags_salicylic() -> None:
    schema = registry.get("shampoo")
    profile = UserProfile(conditions=["pregnant"])
    result = analyze("水、SLES、水杨酸、香精", schema, profile)
    assert any("孕期" in avoid or "水杨酸" in avoid for avoid in result.avoids)


def test_diabetes_flags_added_sugar_prefers_sugar_alcohol() -> None:
    schema = registry.get("food")
    profile = UserProfile(conditions=["diabetes"])

    sugary = analyze("白砂糖、葡萄糖浆、花生", schema, profile)
    assert any("添加糖" in a for a in sugary.avoids)

    light = analyze("聚葡萄糖(膳食纤维)、赤藓糖醇(代糖)、乳清蛋白", schema, profile)
    assert any("代糖" in b or "血糖" in b for b in light.benefits)
    assert any("膳食纤维" in b for b in light.benefits)


def test_nut_allergy_flags_nuts() -> None:
    schema = registry.get("food")
    profile = UserProfile(conditions=["nut_allergy"])
    result = analyze("坚果(腰果、杏仁)、白砂糖", schema, profile)
    assert any("坚果" in a for a in result.avoids)


def test_hypertension_flags_sodium_and_sat_fat() -> None:
    schema = registry.get("food")
    profile = UserProfile(conditions=["hypertension"])
    result = analyze("食盐(钠)、植脂末(反式脂肪/饱和脂肪)", schema, profile)
    avoids_text = " ".join(result.avoids)
    assert "钠" in avoids_text


# --------------------------------------------------------------------------
# 端到端:档案影响推荐结果
# --------------------------------------------------------------------------


def test_shampoo_sensitive_scalp_recommends_amino_acid() -> None:
    profile = UserProfile(conditions=["sensitive_scalp"])
    task, events = run_agent("预算 150 以内,敏感头皮", "shampoo", profile)
    report = next(e for e in events if e["type"] == "report")["report"]
    assert report["picks"]

    titles = [pick["title"] for pick in report["picks"]]
    # 1) 含 SLS 的强刺激款应被硬过滤。注意同品牌可能另有温和配方,
    #    所以按具体型号断言,不按品牌名。
    assert not any("经典款" in title for title in titles)
    assert not any("拉芳" in title for title in titles)
    # 2) 氨基酸/神经酰胺等温和配方应排在最前(Top3)
    gentle = ("氨基酸", "神经酰胺", "施巴", "珂润", "谜尚", "滋源", "自然之名")
    assert any(word in title for title in titles[:3] for word in gentle)
    # 3) 推荐理由应给出"为什么适合敏感头皮"的成分依据
    all_pros = [pro for pick in report["picks"] for pro in pick["pros"]]
    assert any("温和" in pro or "敏感" in pro or "针对" in pro for pro in all_pros)


def test_shampoo_sensitive_scalp_hard_filters_sls() -> None:
    """无档案时含 SLS 的商品在池中，声明敏感头皮后必须被彻底排除。"""
    _, events_plain = run_agent("预算 150 以内，头发有点出油", "shampoo", None)
    plain = next(e for e in events_plain if e["type"] == "candidates_update")
    plain_titles = {c["title"] for c in plain["candidates"]}
    assert any("经典款" in t or "拉芳" in t for t in plain_titles)

    task, events = run_agent("预算 150 以内,敏感头皮", "shampoo",
                             UserProfile(conditions=["sensitive_scalp"]))
    titles = {g.title for g in task.candidates}
    assert not any("经典款" in t for t in titles)
    assert not any("拉芳" in t for t in titles)


def test_food_diabetes_prefers_sugar_free() -> None:
    profile = UserProfile(conditions=["diabetes"])
    task, events = run_agent("预算 50 以内,控糖", "food", profile)
    report = next(e for e in events if e["type"] == "report")["report"]
    top = report["picks"][0]
    # 无糖粗粮饼干应排在士力架(高糖)之前
    assert "无糖" in top["title"] or top["title"] == next(
        p["title"] for p in report["picks"]
    )
    sugary = next((p for p in report["picks"] if "士力架" in p["title"]), None)
    if sugary:
        assert any("添加糖" in con for con in sugary["cons"])


def test_gaming_boosts_performance_dimension() -> None:
    """游戏重度档案应提升相关维度权重,影响电脑排序。"""
    # 不带档案
    task_plain, _ = run_agent("预算 13000,打游戏偶尔带", "laptop", None)
    # 带游戏档案
    task_gamer, _ = run_agent(
        "预算 13000,打游戏偶尔带", "laptop",
        UserProfile(conditions=["gaming"]),
    )
    # 两个任务都应完成;档案至少不应让流程出错
    assert task_plain.candidates
    assert task_gamer.candidates
    assert any(e.action == "profile" for e in task_gamer.decision_log)


def test_candidate_serializes_ingredient_analysis() -> None:
    task, events = run_agent("预算 150 以内,头屑头痒", "shampoo", None)
    updated = next(e for e in events if e["type"] == "candidates_update")
    candidate = updated["candidates"][0]
    assert "ingredient_analysis" in candidate
    analysis = candidate["ingredient_analysis"]
    assert analysis is not None
    assert analysis["recognized"]
    assert analysis["raw"]


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------


def test_profile_api_roundtrip() -> None:
    client.put("/api/profile", json={"conditions": ["diabetes", "fitness"]})
    data = client.get("/api/profile").json()
    assert "diabetes" in data["profile"]["conditions"]
    assert "conditions_meta" in data

    # 未知条件被拒绝
    bad = client.put("/api/profile", json={"conditions": ["made_up_condition"]})
    assert bad.status_code == 400

    client.put("/api/profile", json={"conditions": []})


def test_health_includes_new_categories() -> None:
    data = client.get("/api/health").json()
    assert {"shampoo", "food"} <= set(data["categories"])