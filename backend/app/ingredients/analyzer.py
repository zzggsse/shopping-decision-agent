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
    #: 命中用户诉求的标签(如"头屑"),即这瓶真的对症
    matched_needs: list[str] = field(default_factory=list)
    #: 用户提出但配料表里没有对应有效成分的诉求
    unmet_needs: list[str] = field(default_factory=list)
    #: 对症成分的名字,用于生成"因为含 X 所以对症"的理由
    effective_for_needs: list[str] = field(default_factory=list)
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
    """判断一条配料是否命中某个知识库条目。

    配料表有两种常见写法都要支持:
      "月桂醇硫酸酯钠(SLS)"  -> 括号外是全称,括号内是简称
      "浓缩乳清蛋白(蛋白质)" -> 括号外是具体成分,括号内是归类
    所以括号内外都要参与匹配,并且允许子串包含。
    """
    targets = [name]
    # 括号外
    for sep in ("(", "（"):
        if sep in name:
            targets.append(name.split(sep, 1)[0])
    # 括号内(可能是简称,也可能是归类名)
    for inner in re.findall(r"[(（]([^)）]*)[)）]", name):
        targets.extend(re.split(r"[/、,，]", inner))

    def norm(text: str) -> str:
        return text.lower().replace(" ", "").strip("()（）")

    normalized = {norm(t) for t in targets if t.strip()}
    knowledge_names = [knowledge.name, *knowledge.aliases]
    kb = {norm(n) for n in knowledge_names if n.strip()}

    if normalized & kb:
        return True
    # 允许包含关系:配料"浓缩乳清蛋白"应命中别名"乳清蛋白"
    return any(
        key and target and (key in target or target in key)
        for target in normalized
        for key in kb
        if len(key) >= 2 and len(target) >= 2
    )


def analyze(
    ingredient_text: str,
    schema: CategorySchema,
    profile: UserProfile | None,
    need_tags: list[str] | None = None,
) -> IngredientAnalysis:
    """分析配料表。need_tags 为用户诉求标签(来自槽位),决定是否对症。"""
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

    # 与用户诉求交叉:这瓶到底解不解决他说的问题
    _apply_needs(result, need_tags or [])

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
    # 对症与否是这类品类的主导因素,权重高于泛泛的"成分不错"
    score += 0.18 * len(result.matched_needs)
    score -= 0.15 * len(result.unmet_needs)
    return max(0.0, min(1.0, score))


def _apply_needs(result: IngredientAnalysis, need_tags: list[str]) -> None:
    """把用户诉求与成分的 helps_with 求交集,区分对症与未覆盖。

    这是"用户说的头发问题"真正影响排序的地方:含对症成分加分,
    诉求完全没被覆盖则明确写进 cautions,而不是假装匹配。
    """
    if not need_tags:
        return
    for tag in need_tags:
        hitting = [
            item.name
            for item in result.recognized
            if any(tag in help_tag or help_tag in tag for help_tag in item.helps_with)
        ]
        if hitting:
            if tag not in result.matched_needs:
                result.matched_needs.append(tag)
            for name in hitting:
                if name not in result.effective_for_needs:
                    result.effective_for_needs.append(name)
            note = f"含{'、'.join(hitting[:2])},针对{tag}有效"
            if note not in result.benefits:
                result.benefits.append(note)
        elif tag not in result.unmet_needs:
            result.unmet_needs.append(tag)
    for tag in result.unmet_needs:
        note = f"配料表中未见针对{tag}的有效成分"
        if note not in result.cautions:
            result.cautions.append(note)


def rules_for_profile(schema: CategorySchema, profile: UserProfile | None) -> list[ConcernRule]:
    """返回当前用户在该品类下生效的规则,供打分器加权使用。"""
    if profile is None:
        return []
    return [rule for rule in schema.concern_rules if profile.has(rule.condition)]