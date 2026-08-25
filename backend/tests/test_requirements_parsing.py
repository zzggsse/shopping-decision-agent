"""预算解析与"用户诉求 -> 成分"匹配的回归测试。

这些用例守住两个曾经真实存在的缺陷:
  1. "6000 以上"解析不出预算,且"预算6000以上"被反向读成上限
  2. 用户选了头发问题,但该诉求从未参与打分,导致不同诉求给出同一批结果
"""

from __future__ import annotations

import pytest

from app.agent.extract import parse_budget
from app.catalog import registry
from app.ingredients import analyze
from app.profile.models import UserProfile


# --------------------------------------------------------------------------
# 预算解析
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        # 上限表达
        ("6000以内", (None, 6000)),
        ("500元以内", (None, 500)),
        ("不超过6000", (None, 6000)),
        ("最多8000", (None, 8000)),
        ("控制在4000", (None, 4000)),
        ("预算3500", (None, 3500)),
        # 下限表达:曾经完全无法解析
        ("6000以上", (6000, None)),
        ("预算6000以上", (6000, None)),
        ("1500以上", (1500, None)),
        ("2000起步", (2000, None)),
        ("不低于3000", (3000, None)),
        ("超过2000", (2000, None)),
        ("1万以上", (10000, None)),
        # 区间
        ("3000-5000", (3000, 5000)),
        ("3000到5000", (3000, 5000)),
        # 裸数字兜底
        ("扫地机 5000 养宠物毛发多", (None, 5000)),
        ("笔记本 8000 打游戏", (None, 8000)),
    ],
)
def test_parse_budget_bounds(text: str, expected: tuple) -> None:
    assert parse_budget(text.lower()) == expected


def test_negation_not_read_as_lower_bound() -> None:
    """"不超过"里含"超过",不能因此把上限读成下限。"""
    assert parse_budget("不超过6000") == (None, 6000)
    assert parse_budget("不超过1万") == (None, 10000)


@pytest.mark.parametrize(
    "text",
    [
        "笔记本 16g内存 512g硬盘",
        "要5000mah电池",
        "11000pa吸力",
        "120hz屏幕",
        "降噪45db",
        "洗发水 500ml",
        "16寸屏幕",
    ],
)
def test_spec_numbers_are_not_budgets(text: str) -> None:
    """带单位的规格数字不得被误当成预算。"""
    assert parse_budget(text) is None


# --------------------------------------------------------------------------
# 用户诉求 -> 成分匹配
# --------------------------------------------------------------------------


def test_need_tags_translate_slot_values() -> None:
    """槽位取值应能翻译成成分知识库使用的诉求标签。"""
    schema = registry.get("shampoo")
    tags = schema.need_tags({"hair_issue": "dandruff"})
    assert "头屑" in tags
    assert schema.need_tags({"hair_issue": "dry"}) != tags
    assert schema.need_tags(None) == []
    assert schema.need_tags({}) == []


def test_ingredient_analysis_marks_matched_need() -> None:
    """含对症成分时应记为 matched_needs 并给出理由。"""
    schema = registry.get("shampoo")
    dandruff_shampoo = "水、月桂醇聚醚硫酸酯钠(SLES)、吡硫鎓锌(ZPT)、香精"
    result = analyze(dandruff_shampoo, schema, None, ["头屑"])
    assert "头屑" in result.matched_needs
    assert not result.unmet_needs
    assert any("头屑" in benefit for benefit in result.benefits)


def test_ingredient_analysis_marks_unmet_need() -> None:
    """诉求没有对应有效成分时必须如实标注,不能假装匹配。"""
    schema = registry.get("shampoo")
    plain = "水、月桂醇聚醚硫酸酯钠(SLES)、氯化钠、香精"
    result = analyze(plain, schema, None, ["头屑"])
    assert "头屑" in result.unmet_needs
    assert "头屑" not in result.matched_needs
    assert any("未见" in caution for caution in result.cautions)


def test_matched_need_scores_higher_than_unmet() -> None:
    """对症的配方得分必须高于不对症的,否则诉求等于没起作用。"""
    schema = registry.get("shampoo")
    targeted = analyze("水、吡硫鎓锌(ZPT)、酮康唑、香精", schema, None, ["头屑"])
    generic = analyze("水、月桂醇聚醚硫酸酯钠(SLES)、氯化钠、香精", schema, None, ["头屑"])
    assert targeted.score > generic.score


def test_different_hair_issues_give_different_ranking() -> None:
    """不同头发问题必须导出不同的成分评分,这是雷同答案缺陷的根因。"""
    schema = registry.get("shampoo")
    amino = "水、椰油酰谷氨酸钠(氨基酸表活)、神经酰胺、泛醇"
    antidandruff = "水、月桂醇硫酸酯钠(SLS)、吡硫鎓锌(ZPT)、薄荷醇"

    # 敏感头皮诉求下,氨基酸配方应优于强去屑配方
    assert (
        analyze(amino, schema, None, ["敏感头皮"]).score
        > analyze(antidandruff, schema, None, ["敏感头皮"]).score
    )
    # 头屑诉求下,结论应当反过来
    assert (
        analyze(antidandruff, schema, None, ["头屑"]).score
        > analyze(amino, schema, None, ["头屑"]).score
    )


def test_food_need_tags_work_too() -> None:
    """配置驱动:食品品类同样支持诉求匹配,无需额外代码。"""
    schema = registry.get("food")
    tags = schema.need_tags({"diet_goal": "fitness"})
    assert tags
    high_protein = analyze(
        "浓缩乳清蛋白(蛋白质)、赤藓糖醇(代糖/糖醇)", schema, None, tags
    )
    assert high_protein.matched_needs


def test_hard_filter_still_wins_over_need_match() -> None:
    """即使对症,命中用户禁忌的成分也必须给出 avoid 提示。"""
    schema = registry.get("shampoo")
    sls_antidandruff = "水、月桂醇硫酸酯钠(SLS)、吡硫鎓锌(ZPT)"
    result = analyze(
        sls_antidandruff, schema, UserProfile(conditions=["sensitive_scalp"]), ["头屑"]
    )
    assert "头屑" in result.matched_needs  # 确实对症
    assert result.avoids  # 但仍要如实告知风险
