"""到手价引擎:比价的真正价值所在。

到手价 = 标价 − 各类券/补贴 + 运费 + 税费 − 返现折现
每一项都带 evidence,前端可展开,避免"算出个数字用户不信"。
"""

from __future__ import annotations

from ..domain.models import Offer, PriceComponent

#: 各平台返现/积分折现比例(联盟返佣中让给用户的部分)
CASHBACK_RATE = {
    "jd": 0.010,
    "tmall": 0.015,
    "pdd": 0.008,
    "amazon": 0.000,
}

#: 跨境平台综合税率
IMPORT_TAX_RATE = {"amazon": 0.09}


def compute_final_price(offer: Offer) -> Offer:
    """基于 components 重算到手价,补齐税费与返现项。"""
    priced = offer.model_copy(deep=True)
    components = [item for item in priced.components if item.label not in ("跨境税费", "返现折现")]

    if not components:
        components = [
            PriceComponent(label="标价", amount=priced.list_price, evidence="商品页标价")
        ]

    subtotal = sum(item.amount for item in components)

    tax_rate = IMPORT_TAX_RATE.get(priced.platform, 0.0)
    if tax_rate:
        components.append(
            PriceComponent(
                label="跨境税费",
                amount=round(subtotal * tax_rate, 2),
                evidence=f"跨境综合税率 {tax_rate:.1%},以实际清关金额为准",
            )
        )

    cashback_rate = CASHBACK_RATE.get(priced.platform, 0.0)
    if cashback_rate:
        components.append(
            PriceComponent(
                label="返现折现",
                amount=-round(subtotal * cashback_rate, 2),
                evidence=f"通过本站链接下单可返 {cashback_rate:.1%}",
            )
        )

    priced.components = components
    priced.final_price = round(sum(item.amount for item in components), 2)
    return priced


def price_breakdown(offer: Offer) -> dict:
    """给前端"点价格看明细"用的结构。"""
    return {
        "final_price": offer.final_price,
        "list_price": offer.list_price,
        "saved": round(offer.list_price - (offer.final_price or offer.list_price), 2),
        "components": [item.model_dump() for item in offer.components],
        "fetched_at": offer.fetched_at.isoformat(),
        "stale": offer.stale,
    }
