"""候选池/报告序列化辅助。

独立成模块以打破 graph <-> toolkit 的循环依赖。
"""

from __future__ import annotations

from typing import Any

from ..catalog import registry
from ..domain.models import ProductGroup, ShoppingTask
from ..ingredients import analyze as _analyze
from ..profile import profile_store
from ..services import pricing


def describe_category(category: str) -> dict[str, Any]:
    schema = registry.get(category)
    return {
        "key": schema.key,
        "label": schema.label,
        "dimensions": [
            {"key": d.key, "label": d.label, "default_weight": d.default_weight}
            for d in schema.dimensions
        ],
        "attributes": [
            {
                "key": a.key,
                "label": a.label,
                "unit": a.unit,
                "kind": a.kind,
                "summary": a.summary,
                "labels": a.labels,
            }
            for a in schema.attributes
        ],
        "budget_options": schema.budget_options,
    }


def serialize(task: ShoppingTask) -> list[dict[str, Any]]:
    score_map = {score.group_id: score for score in task.scores}
    payload: list[dict[str, Any]] = []

    for group in task.candidates:
        best = group.best_offer
        score = score_map.get(group.group_id)
        payload.append(
            {
                "group_id": group.group_id,
                "category": group.spec.category,
                "title": group.title,
                "brand": group.spec.brand,
                "model": group.spec.model,
                "attributes": group.spec.attributes,
                "display": {
                    key: registry.get(group.spec.category).display(key, value)
                    for key, value in group.spec.attributes.items()
                },
                "ingredient_analysis": analyze_serialized(group),
                "summary": group.spec.summary_line(),
                "best_price": group.best_price,
                "best_platform": best.platform if best else None,
                "best_url": best.url if best else None,
                "price_breakdown": pricing.price_breakdown(best) if best else None,
                "offers": [
                    {
                        **offer.model_dump(mode="json"),
                        "breakdown": pricing.price_breakdown(offer),
                    }
                    for offer in sorted(
                        group.offers, key=lambda o: o.final_price or o.list_price
                    )
                ],
                "score": score.model_dump() if score else None,
                "price_spread": price_spread(group),
            }
        )
    return payload


def price_spread(group: ProductGroup) -> dict[str, Any] | None:
    prices = [
        (offer.platform, offer.final_price)
        for offer in group.offers
        if offer.final_price is not None and offer.in_stock
    ]
    if len(prices) < 2:
        return None
    low = min(prices, key=lambda item: item[1])
    high = max(prices, key=lambda item: item[1])
    return {
        "min_platform": low[0],
        "min_price": low[1],
        "max_platform": high[0],
        "max_price": high[1],
        "saved": round(high[1] - low[1], 2),
    }


def analyze_serialized(group: ProductGroup) -> dict[str, Any] | None:
    analysis = group.__dict__.get("_analysis")
    if analysis is None:
        schema = registry.get(group.spec.category)
        if schema.ingredient_attribute:
            text = str(group.spec.get(schema.ingredient_attribute) or "")
            if text:
                analysis = _analyze(text, schema, profile_store.get())
    if analysis is None or not analysis.has_data:
        return None
    return {
        "raw": analysis.raw,
        "recognized": [
            {"name": item.name, "benefits": item.benefits, "risks": item.risks,
             "helps_with": item.helps_with}
            for item in analysis.recognized
        ],
        "unrecognized": analysis.unrecognized,
        "benefits": analysis.benefits,
        "cautions": analysis.cautions,
        "avoids": analysis.avoids,
        "matched_concerns": analysis.matched_concerns,
        "score": analysis.score,
    }


def build_report(task: ShoppingTask) -> dict[str, Any]:
    schema = registry.get(task.category)

    if not task.candidates or not task.scores:
        return {
            "category": task.category,
            "category_label": schema.label,
            "summary": f"当前没有满足条件的{schema.label},建议放宽预算或调整要求。",
            "picks": [],
        }

    score_map = {score.group_id: score for score in task.scores}
    labels = ["综合最优", "次优选择", "备选"]
    picks = []

    for index, group in enumerate(task.candidates[:3]):
        best = group.best_offer
        if best is None:
            continue
        score = score_map.get(group.group_id)
        picks.append(
            {
                "label": labels[index] if index < len(labels) else "备选",
                "group_id": group.group_id,
                "title": group.title,
                "summary": group.spec.summary_line(),
                "final_price": best.final_price,
                "platform": best.platform,
                "url": best.url,
                "score": score.total if score else None,
                "pros": score.pros if score else [],
                "cons": score.cons if score else [],
                "price_spread": price_spread(group),
                "fetched_at": best.fetched_at.isoformat(),
                "needs_recheck": best.stale,
            }
        )

    top = picks[0] if picks else None
    if top:
        summary = (
            f"在 {len(task.candidates)} 款符合条件的{schema.label}中,推荐 {top['title']},"
            f"{top['platform']} 到手价 {top['final_price']:.0f} 元。"
        )
        if top.get("price_spread") and top["price_spread"]["saved"] > 0:
            spread = top["price_spread"]
            summary += (
                f"同款在 {spread['max_platform']} 需 {spread['max_price']:.0f} 元,"
                f"可省 {spread['saved']:.0f} 元。"
            )
    else:
        summary = "暂无推荐。"

    return {
        "category": task.category,
        "category_label": schema.label,
        "summary": summary,
        "picks": picks,
        "weights": task.weights.normalized(),
        "requirement": task.requirement.model_dump(exclude_none=True),
    }