"""SKU 对齐:把跨平台的同款商品聚合成 ProductGroup。

全品类通用。同款判定键 = 品牌 + 型号 + 品类配置中标记 identity 的属性 + 成色。
identity 属性由 catalog 定义,例如笔记本的内存/存储、耳机的佩戴形式。
"""

from __future__ import annotations

import re

from ..adapters.base import RawOffer
from ..catalog import registry
from ..domain.models import ProductGroup

_SEP = re.compile(r"[\s\-_/（）()【】\[\]]+")
_YEAR = re.compile(r"20\d{2}款?")

_BRAND_ALIAS = {
    "苹果": "apple", "联想": "lenovo", "thinkpad": "lenovo",
    "华硕": "asus", "戴尔": "dell", "华为": "huawei", "惠普": "hp",
    "红米": "redmi", "redmibook": "redmi", "小米": "xiaomi", "米家": "xiaomi",
    "索尼": "sony", "森海塞尔": "sennheiser", "漫步者": "edifier",
    "石头": "roborock", "科沃斯": "ecovacs", "追觅": "dreame", "云鲸": "narwal",
    "荣耀": "honor", "一加": "oneplus", "真我": "realme", "三星": "samsung",
    "vivo": "vivo", "oppo": "oppo",
}


def normalize_brand(brand: str) -> str:
    key = brand.strip().lower()
    return _BRAND_ALIAS.get(key, key)


def normalize_model(model: str, category: str) -> str:
    """剔除品类噪音词后压缩空白,提高跨平台标题的一致性。"""
    text = model.lower()
    for word in registry.get(category).noise_words:
        text = text.replace(word.lower(), "")
    text = _YEAR.sub("", text)
    return _SEP.sub("", text)


def group_key(item: RawOffer) -> str:
    """同款判定键。配置差异(如 16G/512G vs 32G/1T)不算同款,不能混着比价。"""
    spec = item.spec
    schema = registry.get(spec.category)
    parts = [
        spec.category,
        normalize_brand(spec.brand),
        normalize_model(spec.model, spec.category),
    ]
    for key in schema.identity_attributes:
        value = spec.get(key)
        parts.append(f"{key}={value}" if value is not None else f"{key}=?")
    parts.append(item.offer.condition)
    return "|".join(parts)


def align(items: list[RawOffer]) -> list[ProductGroup]:
    """聚合为 ProductGroup 列表。同 key 内保留属性最完整的 spec 作为代表。"""
    buckets: dict[str, list[RawOffer]] = {}
    for item in items:
        buckets.setdefault(group_key(item), []).append(item)

    groups: list[ProductGroup] = []
    for key, members in buckets.items():
        representative = max(members, key=_spec_completeness)
        merged = representative.spec.model_copy(deep=True)
        # 跨平台字段互补:任一平台提供了属性即补齐
        for member in members:
            for attribute_key, value in member.spec.attributes.items():
                if merged.attributes.get(attribute_key) in (None, "") and value not in (None, ""):
                    merged.attributes[attribute_key] = value

        groups.append(
            ProductGroup(
                group_id=key,
                spec=merged,
                offers=[member.offer.model_copy(deep=True) for member in members],
            )
        )
    return groups


def _spec_completeness(item: RawOffer) -> int:
    return sum(1 for value in item.spec.attributes.values() if value not in (None, "", 0))


def _semantic_fallback(unmatched: list[RawOffer]) -> list[list[RawOffer]]:
    """预留:规则未命中时的语义对齐入口。

    计划实现:标题 embedding 召回 Top-K → 交叉判定是否同款,
    仅对疑难对调用 LLM 以控制成本。
    """
    return [[item] for item in unmatched]