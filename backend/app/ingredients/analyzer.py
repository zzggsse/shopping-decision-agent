"""成分分析:解析配料表,匹配知识库与用户档案。

通用流程:
  1. 按品类配置的分隔符把成分文本拆成独立条目
  2. 用成分名 + 别名在知识库中匹配
  3. 与用户条件(concern_rules + avoid_for)交叉
  4. 输出结构化结论:适合、需注意、不建议、匹配的头发/身体问题
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..catalog.schema import CategorySchema, ConcernRule, IngredientKnowledge
from ..profile.models import UserProfile


@dataclass(slots=True)
class IngredientAnalysis:
    """单个候选商品的成分分析结论。"""

    raw: str
    recognized: list[IngredientKnowledge] = field(default_factory=list)
    unrecognized: list[str] = field(default_factory=list)
    benefits: list[str] = field(default_factory=list)
    cautions: list[str] = field(default_factory=list)
    avoids: list[str] = field(default_factory=list)
    matched_concerns: list[str] = field(default_factory=list)
    score: float = 0.5  # 0-1,供打分使用

    @property
    def has_data(self) -> bool:
        return bool(self.raw and self.raw.strip())


def split_ingredients(text: str, separator: str) -> list[str]:
    """把配料文本拆成去重、去空白的条目。"""
    if not text:
        return []
    pattern = "|".join(re.escape(sep) for sep in separator if sep.strip())
    parts = re.split(pattern, text)
    seen: set[str] = set()
    result: list[str] = []
    for part in parts:
        cleaned = part.strip().strip("().。 ")
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result


def _match(name: str, knowledge: IngredientKnowledge) -> bool:
    targets = [name, name.split("(", 1)[0], name.split("（", 1)[0]]
    normalized = {t.lower().replace(" ", "").strip("()（）") for t in targets if t.strip()}
    knowledge_names = [knowledge.name, *knowledge.aliases]
    kb = {n.lower().replace(" ", "").strip("()（）") for n in knowledge_names}
    return bool(normalized & kb)


def analyze(
    ingredient_text: str,
    schema: CategorySchema,
    profile: UserProfile | None,
) -> IngredientAnalysis:
    result = IngredientAnalysis(raw=ingredient_text)
    if not ingredient_text:
        return result

    entries = split_ingredients(ingredient_text, schema.ingredient_separator)
    knowledge_by_name = schema.ingredient_knowledge

    for entry in entries:
        matched: IngredientKnowledge | None = None
        for knowledge in knowledge_by_name.values():
            if _match(entry, knowledge):
                matched = knowledge
                break
        if matched:
            result.recognized.append(matched)
        else:
            result.unrecognized.append(entry)

    # 功效与风险汇总(去重)
    for item in result.recognized:
        for benefit in item.helps_with:
            if benefit not in result.matched_concerns:
                result.matched_concerns.append(benefit)
        for benefit in item.benefits:
            if benefit not in result.benefits:
                result.benefits.append(benefit)
        for risk in item.risks:
            if risk not in result.cautions:
                result.cautions.append(risk)

    # 与用户档案交叉
    if profile is not None:
        _apply_profile(result, schema, profile)

    result.score = _score(result)
    return result


def _apply_profile(
    result: IngredientAnalysis,
    schema: CategorySchema,
    profile: UserProfile,
) -> None:
    """把用户条件作用到成分结论上。两层来源:知识库 avoid_for + 品类 concern_rules。"""

    # 1) 成分知识库的人群禁忌
    for item in result.recognized:
        for condition in item.avoid_for:
            if profile.has(condition):
                msg = f"{item.name}:{_condition_message(condition)}"
                if msg not in result.avoids:
                    result.avoids.append(msg)

    # 2) 品类显式声明的规则(成分/属性/维度)
    recognized_names = {item.name for item in result.recognized}
    for rule in schema.concern_rules:
        if not profile.has(rule.condition):
            continue
        if rule.severity == "avoid" and rule.target == "ingredient":
            if rule.key in recognized_names or any(
                rule.key in (item.name, *item.aliases) for item in result.recognized
            ):
                result.avoids.append(rule.message or f"含{rule.key},不建议{rule.condition}人群")
        elif rule.severity == "prefer" and rule.target == "ingredient":
            if rule.key in recognized_names:
                note = rule.message or f"含{rule.key},适合{rule.condition}"
                if note not in result.benefits:
                    result.benefits.append(note)


def _condition_message(condition: str) -> str:
    messages = {
        "pregnant": "孕妇慎用",
        "sulfate_allergy": "硫酸盐过敏者慎用",
        "sensitive_scalp": "敏感头皮可能不适",
        "diabetes": "糖尿病患者需注意",
        "hypertension": "高血压人群需注意",
        "nut_allergy": "坚果过敏者禁用",
    }
    return messages.get(condition, f"{condition} 人群需注意")


def _score(result: IngredientAnalysis) -> float:
    """把成分分析换算为 0-1 分,供打分维度使用。"""
    if not result.recognized:
        return 0.5
    score = 0.5 + 0.04 * len(result.benefits) - 0.12 * len(result.avoids) - 0.04 * len(result.cautions)
    return max(0.0, min(1.0, score))


def rules_for_profile(schema: CategorySchema, profile: UserProfile | None) -> list[ConcernRule]:
    """返回当前用户在该品类下生效的规则,供打分器加权使用。"""
    if profile is None:
        return []
    return [rule for rule in schema.concern_rules if profile.has(rule.condition)]