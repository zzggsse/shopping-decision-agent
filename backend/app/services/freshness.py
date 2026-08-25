"""数据新鲜度策略:保证用户在决策关键路径上看到的是实时价格。

分层 TTL:
  - 商品基础参数    7 天   (几乎不变)
  - 列表页粗排价格  600 秒 (允许轻微滞后)
  - Top-N 候选到手价 0 秒  (强制实时复核)

三道保障:
  1. refresh_top_candidates  决策报告生成前强制实时拉取
  2. offer.stale + fetched_at 全程暴露给前端,超时自动置灰
  3. verify_before_redirect  用户点"去购买"瞬间二次校验,偏差超阈值则提示
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from ..adapters.base import PlatformAdapter
from ..domain.models import Offer, ProductGroup
from .pricing import compute_final_price

#: 粗排价格可接受的最大滞后(秒)
LIST_PRICE_TTL = 600
#: 展示层超过该时长即置灰并提示刷新(秒)
DISPLAY_STALE_TTL = 900
#: 跳转前允许的价格偏差比例,超过则提示用户
REDIRECT_PRICE_TOLERANCE = 0.02


def mark_staleness(groups: list[ProductGroup], now: datetime | None = None) -> None:
    """按 TTL 标记 stale,前端据此显示"更新于 X 分钟前"及置灰。"""
    moment = now or datetime.now(timezone.utc)
    for group in groups:
        for offer in group.offers:
            offer.stale = offer.age_seconds(moment) > DISPLAY_STALE_TTL


async def refresh_offers(
    offers: list[Offer],
    adapters: dict[str, PlatformAdapter],
) -> list[Offer]:
    """并发实时复核。单条失败不影响整体,失败项标记 stale 而非沿用旧价。"""

    async def refresh_one(offer: Offer) -> Offer:
        adapter = adapters.get(offer.platform)
        if adapter is None:
            fallback = offer.model_copy(deep=True)
            fallback.stale = True
            return fallback
        try:
            fresh = await asyncio.wait_for(adapter.refresh_offer(offer), timeout=6.0)
            return compute_final_price(fresh)
        except (asyncio.TimeoutError, NotImplementedError, Exception):
            # 关键:拿不到实时价就诚实标记,绝不用旧价冒充实时价
            degraded = offer.model_copy(deep=True)
            degraded.stale = True
            return degraded

    return await asyncio.gather(*(refresh_one(offer) for offer in offers))


async def refresh_top_candidates(
    groups: list[ProductGroup],
    adapters: dict[str, PlatformAdapter],
    top_n: int = 5,
) -> list[str]:
    """决策前对 Top-N 候选的全部 offer 强制实时复核。

    返回复核失败(仍为 stale)的平台列表,供报告中如实披露。
    """
    targets = groups[:top_n]
    pending = [offer for group in targets for offer in group.offers]
    if not pending:
        return []

    refreshed = await refresh_offers(pending, adapters)
    by_id = {offer.offer_id: offer for offer in refreshed}

    failed: list[str] = []
    for group in targets:
        group.offers = [by_id.get(offer.offer_id, offer) for offer in group.offers]
        failed.extend(offer.platform for offer in group.offers if offer.stale)

    return sorted(set(failed))


async def verify_before_redirect(
    offer: Offer,
    adapters: dict[str, PlatformAdapter],
) -> dict:
    """跳转前二次校验。价格变动超阈值时返回需要用户确认的信号。"""
    shown_price = offer.final_price or offer.list_price
    fresh = (await refresh_offers([offer], adapters))[0]
    current_price = fresh.final_price or fresh.list_price

    if fresh.stale:
        return {
            "ok": False,
            "reason": "price_unavailable",
            "message": "该平台价格暂时无法实时确认,请到商品页核对后再下单",
            "shown_price": shown_price,
            "current_price": None,
            "offer": fresh.model_dump(mode="json"),
        }

    delta = current_price - shown_price
    changed = abs(delta) / max(shown_price, 1) > REDIRECT_PRICE_TOLERANCE

    return {
        "ok": not changed,
        "reason": "price_changed" if changed else "confirmed",
        "message": (
            f"价格已变动为 {current_price:.0f} 元({'上涨' if delta > 0 else '下降'}"
            f"{abs(delta):.0f} 元),是否继续?"
            if changed
            else "价格已确认,与展示一致"
        ),
        "shown_price": shown_price,
        "current_price": current_price,
        "offer": fresh.model_dump(mode="json"),
    }
