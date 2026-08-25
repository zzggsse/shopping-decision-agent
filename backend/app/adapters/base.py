"""适配器层:统一协议 + Mock(fixture)/Live 两种实现。

全品类支持:fixture 按 <platform>/<category>.json 分目录存放,
search 时只加载目标品类,避免跨品类污染候选池。

Agent 与服务层只依赖 PlatformAdapter,不关心数据来自 API、爬虫还是本地样本。
"""

from __future__ import annotations

import json
import pathlib
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone

from ..domain.models import Offer, ProductSpec

FIXTURE_DIR = pathlib.Path(__file__).parent / "fixtures"


@dataclass(slots=True)
class SearchQuery:
    category: str
    keyword: str = ""
    budget_max: int | None = None
    budget_min: int | None = None
    limit: int = 60


@dataclass(slots=True)
class RawOffer:
    """适配器输出的原始条目:报价 + 平台声称的规格。"""

    offer: Offer
    spec: ProductSpec
    vendor_group_hint: str | None = None


class PlatformAdapter(ABC):
    platform: str
    #: 是否为实时数据源。mock 为 False,生产 API/爬虫为 True。
    realtime: bool = False

    @abstractmethod
    async def search(self, query: SearchQuery) -> list[RawOffer]:
        """按需求搜索候选,用于粗排,允许命中缓存。"""

    @abstractmethod
    async def refresh_offer(self, offer: Offer) -> Offer:
        """对单条 offer 做强制实时复核,用于决策前和跳转前校验。"""

    @abstractmethod
    def supported_categories(self) -> list[str]:
        """本平台可供货的品类。用于跳过无关平台,减少无效请求。"""


class MockAdapter(PlatformAdapter):
    """开发/CI 使用:读取本地 fixture,永不发起外部请求。"""

    realtime = False

    def __init__(self, platform: str, fixture_dir: pathlib.Path | None = None) -> None:
        self.platform = platform
        self._dir = fixture_dir or FIXTURE_DIR / platform
        self._cache: dict[str, list[RawOffer]] = {}

    def supported_categories(self) -> list[str]:
        if not self._dir.exists():
            return []
        return sorted(path.stem for path in self._dir.glob("*.json"))

    def _items(self, category: str) -> list[RawOffer]:
        if category not in self._cache:
            self._cache[category] = _load_fixture(self._dir / f"{category}.json")
        return self._cache[category]

    async def search(self, query: SearchQuery) -> list[RawOffer]:
        results: list[RawOffer] = []
        keyword = query.keyword.lower().strip()

        for item in self._items(query.category):
            if keyword and not _keyword_hit(keyword, item):
                continue
            price = item.offer.final_price or item.offer.list_price
            # 只按上限过滤;更便宜的候选保留,由打分环节权衡
            if query.budget_max is not None and price > query.budget_max * 1.15:
                continue
            results.append(_clone(item))

        return results[: query.limit]

    async def refresh_offer(self, offer: Offer) -> Offer:
        """模拟真实世界的价格波动,便于验证"价格已变动"提示链路。"""
        fresh = offer.model_copy(deep=True)
        if fresh.final_price is not None:
            fresh.final_price = round(fresh.final_price * random.uniform(0.98, 1.02), 2)
        fresh.fetched_at = datetime.now(timezone.utc)
        fresh.stale = False
        return fresh


class LiveAdapter(PlatformAdapter):
    """生产实现骨架:优先联盟/开放 API,缺失字段再由爬虫补齐。"""

    realtime = True

    def __init__(self, platform: str, categories: list[str] | None = None) -> None:
        self.platform = platform
        self._categories = categories or []

    def supported_categories(self) -> list[str]:
        return list(self._categories)

    async def search(self, query: SearchQuery) -> list[RawOffer]:
        raise NotImplementedError(
            f"{self.platform} live adapter 未接入:请先配置联盟 API 凭据或爬虫解析器"
        )

    async def refresh_offer(self, offer: Offer) -> Offer:
        raise NotImplementedError(
            f"{self.platform} live adapter 未接入:无法执行实时价格复核"
        )


def _keyword_hit(keyword: str, item: RawOffer) -> bool:
    haystack = " ".join(
        [item.offer.title, item.spec.brand, item.spec.model]
        + [str(value) for value in item.spec.attributes.values()]
    ).lower()
    return all(token in haystack for token in keyword.split())


def _clone(item: RawOffer) -> RawOffer:
    return RawOffer(
        offer=item.offer.model_copy(deep=True),
        spec=item.spec.model_copy(deep=True),
        vendor_group_hint=item.vendor_group_hint,
    )


def _load_fixture(path: pathlib.Path) -> list[RawOffer]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [
        RawOffer(
            offer=Offer(**row["offer"]),
            spec=ProductSpec(**row["spec"]),
            vendor_group_hint=row.get("vendor_group_hint"),
        )
        for row in payload
    ]


PLATFORMS = ("jd", "tmall", "pdd", "amazon")


def create_adapters(mode: str) -> dict[str, PlatformAdapter]:
    """按 DATA_SOURCE_MODE 构建适配器集合。"""
    if mode == "live":
        return {name: LiveAdapter(name) for name in PLATFORMS}
    return {name: MockAdapter(name) for name in PLATFORMS}