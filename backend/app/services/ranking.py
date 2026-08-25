"""偏好打分:完全由品类配置驱动,不含任何品类专属逻辑。

维度分 = Σ(属性归一化分 × 属性在该维度内占比)
总分   = Σ(维度分 × 用户权重)

归一化区间取自当前候选池,保证组间可比。
pros/cons 由配置中的模板生成,直接作为推荐理由。
"""

from __future__ import annotations

from typing import Any

from ..catalog import CategorySchema, registry
from ..domain.models import ProductGroup, Requirement, ScoreBreakdown, Weights
from ..ingredients import analyze
from ..profile.models import UserProfile


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _normalize(value: float, low: float, high: float, higher_better: bool) -> float:
    if high <= low:
        return 0.5
    ratio = (value - low) / (high - low)
    return _clamp(ratio if higher_better else 1.0 - ratio)


def _numeric_ranges(
    groups: list[ProductGroup], schema: CategorySchema
) -> dict[str, tuple[float, float]]:
    """统计候选池内各数值属性的取值范围。"""
    ranges: dict[str, tuple[float, float]] = {}
    for key in schema.numeric_attributes:
        values = [
            float(group.spec.get(key))
            for group in groups
            if isinstance(group.spec.get(key), (int, float))
        ]
        if values:
            ranges[key] = (min(values), max(values))
    return ranges


def _attribute_score(
    key: str, value: Any, schema: CategorySchema, ranges: dict[str, tuple[float, float]]
) -> float | None:
    """单个属性归一化为 0-1。无法评分则返回 None,由维度内重新分配占比。"""
    attribute = schema.attribute(key)
    if attribute is None or value is None:
        return None

    if attribute.kind == "enum":
        return attribute.scale.get(str(value))

    if attribute.kind == "number" and isinstance(value, (int, float)):
        bounds = ranges.get(key)
        if bounds is None:
            return None
        return _normalize(
            float(value), bounds[0], bounds[1], attribute.direction != "lower_better"
        )

    return None


def score_candidates(
    groups: list[ProductGroup],
    weights: Weights,
    requirement: Requirement,
    profile: UserProfile | None = None,
) -> list[ScoreBreakdown]:
    """对候选池整体打分。"""
    priced = [group for group in groups if group.best_price is not None]
    if not priced:
        return []

    schema = registry.get(requirement.category)
    ranges = _numeric_ranges(priced, schema)
    normalized_weights = weights.normalized()

    prices = [group.best_price or 0.0 for group in priced]
    price_low, price_high = min(prices), max(prices)

    results: list[ScoreBreakdown] = []
    for group in priced:
        dimensions: dict[str, float] = {}

        for dimension in schema.dimensions:
            if dimension.key == "price":
                dimensions["price"] = _normalize(
                    group.best_price or 0.0, price_low, price_high, higher_better=False
                )
                continue
            if dimension.key == "reputation":
                dimensions["reputation"] = _reputation_score(group)
                continue
            if dimension.key == "ingredient_fit" and schema.ingredient_attribute:
                text = str(group.spec.get(schema.ingredient_attribute) or "")
                analysis = analyze(text, schema, profile)
                dimensions["ingredient_fit"] = analysis.score
                # 把成分结论挂到 group 上,供 _explain 使用
                group.__dict__["_analysis"] = analysis
                continue

            total_share = 0.0
            accumulated = 0.0
            for attribute_key, share in dimension.components.items():
                value = _attribute_score(
                    attribute_key, group.spec.get(attribute_key), schema, ranges
                )
                if value is None:
                    continue
                accumulated += value * share
                total_share += share
            # 缺失属性时按剩余占比重新归一,避免"字段缺失=低分"的误判
            dimensions[dimension.key] = (
                _clamp(accumulated / total_share) if total_share else 0.5
            )

        total = sum(
            normalized_weights.get(key, 0.0) * value for key, value in dimensions.items()
        )
        pros, cons = _explain(group, dimensions, schema, requirement, profile)

        results.append(
            ScoreBreakdown(
                group_id=group.group_id,
                total=round(total * 100, 1),
                dimensions={key: round(value, 3) for key, value in dimensions.items()},
                pros=pros,
                cons=cons,
            )
        )

    results.sort(key=lambda item: item.total, reverse=True)
    return results


def _reputation_score(group: ProductGroup) -> float:
    """口碑维度对所有品类通用,基于评分/店铺/销量。"""
    offer = group.best_offer
    if offer is None:
        return 0.5
    review = _normalize(offer.review_score or 4.0, 3.5, 5.0, True)
    shop = _normalize(offer.shop_rating or 4.5, 4.0, 5.0, True)
    volume = _normalize(min(offer.review_count, 8000), 0, 8000, True)
    return _clamp(review * 0.5 + shop * 0.3 + volume * 0.2)


def _render(template: str, group: ProductGroup) -> str:
    """用商品属性填充理由模板,缺字段则跳过该条理由。"""
    context: dict[str, Any] = {
        "brand": group.spec.brand,
        "model": group.spec.model,
        **group.spec.attributes,
    }
    try:
        return template.format(**context)
    except (KeyError, IndexError):
        return ""


HIGH = 0.70
LOW = 0.32


def _explain(
    group: ProductGroup,
    dimensions: dict[str, float],
    schema: CategorySchema,
    requirement: Requirement,
    profile: UserProfile | None = None,
) -> tuple[list[str], list[str]]:
    """把维度得分翻译成人话。模板来自品类配置。"""
    pros: list[str] = []
    cons: list[str] = []
    price = group.best_price or 0.0

    if dimensions.get("price", 0.5) >= HIGH:
        pros.append(f"到手价 {price:.0f} 元,在当前候选中价格优势明显")
    elif dimensions.get("price", 0.5) <= LOW:
        cons.append(f"到手价 {price:.0f} 元,属于候选中偏贵的一档")

    for dimension in schema.dimensions:
        if dimension.key in ("price", "reputation"):
            continue
        score = dimensions.get(dimension.key)
        if score is None:
            continue
        if score >= HIGH and dimension.pro_template:
            if text := _render(dimension.pro_template, group):
                pros.append(text)
        elif score <= LOW and dimension.con_template:
            if text := _render(dimension.con_template, group):
                cons.append(text)

    # 硬约束未满足时必须显式提示
    for key, minimum in requirement.min_specs.items():
        value = group.spec.get(key)
        if isinstance(value, (int, float)) and value < minimum:
            attribute = schema.attribute(key)
            label = attribute.label if attribute else key
            unit = attribute.unit if attribute else ""
            cons.append(f"{label} {value}{unit} 低于你要求的 {minimum:g}{unit}")

    if requirement.budget_max and price > requirement.budget_max:
        cons.append(f"超出预算上限 {price - requirement.budget_max:.0f} 元")

    analysis: object = group.__dict__.get("_analysis")
    if analysis is not None:
        for avoid in analysis.avoids:
            cons.append(f"禁忌:{avoid}")
        for caution in analysis.cautions[:2]:
            cons.append(caution)
        for benefit in analysis.benefits[:2]:
            pros.append(benefit)

    best = group.best_offer
    if best and best.delivery_days and best.delivery_days > 4:
        cons.append(f"最低价来自 {best.platform},预计 {best.delivery_days} 天送达")

    return pros[:4], cons[:4]