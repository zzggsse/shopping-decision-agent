"""需求抽取:从自然语言解析品类、预算、槽位与偏好信号。

品类差异全部读取 catalog 配置,本模块不含任何品类专属分支。
当前为规则版(零成本、可测试),可整体替换为 LLM function-calling,
对外接口保持 extract / adjust_weights / next_question 不变。
"""

from __future__ import annotations

import re
from typing import Any

from ..catalog import registry
from ..domain.models import Requirement, Weights

# --------------------------------------------------------------------------
# 品类路由
# --------------------------------------------------------------------------


def detect_category(text: str) -> str | None:
    """识别用户想买什么品类。命中最长触发词者优先。"""
    return registry.detect(text)


# --------------------------------------------------------------------------
# 预算解析
# --------------------------------------------------------------------------


def parse_budget(text: str) -> tuple[int | None, int | None] | None:
    """解析预算表达。

    刻意只设上限、不设下限:用户说"预算 7000"不意味着拒绝 5000 的好东西,
    更便宜的候选应保留在池中,由打分环节权衡。
    """
    span = re.search(r"(\d{2,6})\s*(?:-|~|到|至)\s*(\d{2,6})", text)
    if span:
        low, high = int(span.group(1)), int(span.group(2))
        return (min(low, high), max(low, high))

    wan = re.search(r"(\d(?:\.\d)?)\s*万", text)
    if wan:
        return (None, int(float(wan.group(1)) * 10000))

    around = re.search(r"(\d{2,6})\s*(?:元|块)?\s*(?:左右|上下|前后)", text)
    if around:
        return (None, int(int(around.group(1)) * 1.08))

    cap = re.search(r"(\d{2,6})\s*(?:元|块)?\s*(?:以内|以下|之内|封顶)", text)
    if cap:
        return (None, int(cap.group(1)))

    cap2 = re.search(r"(?:不超过|最多|预算|控制在)\s*(\d{2,6})", text)
    if cap2:
        return (None, int(cap2.group(1)))

    if any(word in text for word in ("预算", "价位", "块", "元")):
        single = re.search(r"(\d{2,6})", text)
        if single:
            return (None, int(single.group(1)))

    return None


# --------------------------------------------------------------------------
# 数值下限解析(全品类共用一套模式)
# --------------------------------------------------------------------------

#: 属性 key -> 匹配模式。用命名组 value 捕获数值。
_MIN_SPEC_PATTERNS: dict[str, list[str]] = {
    "ram_gb": [r"(?P<value>\d{1,3})\s*g(?:b)?\s*(?:内存|运存)"],
    "storage_gb": [r"(?P<value>\d{3,4})\s*g(?:b)?\s*(?:硬盘|存储|固态|机身)"],
    "battery_hours": [r"续航.{0,4}?(?P<value>\d{1,2})\s*(?:个)?小时"],
    "battery_mah": [r"(?P<value>\d{4,5})\s*mah"],
    "charge_w": [r"(?P<value>\d{2,3})\s*w\s*(?:快充|充电)"],
    "main_camera_mp": [r"(?P<value>\d{2,3})\s*(?:mp|万像素|像素)"],
    "suction_pa": [r"(?P<value>\d{4,5})\s*pa"],
    "anc_db": [r"降噪.{0,4}?(?P<value>\d{2})\s*db"],
    "refresh_hz": [r"(?P<value>\d{2,3})\s*hz"],
}

#: TB 单位需换算
_TB_PATTERN = re.compile(r"(?P<value>\d(?:\.\d)?)\s*t(?:b)?")


def parse_min_specs(text: str, category: str) -> dict[str, float]:
    """解析数值下限。只接受当前品类实际拥有的属性,避免跨品类误匹配。"""
    schema = registry.get(category)
    valid = set(schema.numeric_attributes)
    found: dict[str, float] = {}

    for key, patterns in _MIN_SPEC_PATTERNS.items():
        if key not in valid:
            continue
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                found[key] = float(match.group("value"))
                break

    if "storage_gb" in valid and (tb := _TB_PATTERN.search(text)):
        found["storage_gb"] = float(tb.group("value")) * 1024

    return found


# --------------------------------------------------------------------------
# 槽位解析
# --------------------------------------------------------------------------


def parse_slots(text: str, category: str) -> dict[str, Any]:
    """按品类配置的 keywords 解析槽位取值。"""
    schema = registry.get(category)
    found: dict[str, Any] = {}

    for slot in schema.slots:
        # 用户经常直接把选项文字敲进输入框（而不是点按钮），
        # 这类回答比关键词更明确，所以优先按选项原文匹配。
        for label, value in slot.option_values.items():
            if label and label in text:
                found[slot.key] = value
                break
        if slot.key in found:
            continue
        for value, keywords in slot.keywords.items():
            if any(keyword in text for keyword in keywords):
                found[slot.key] = value
                break
    return found


# --------------------------------------------------------------------------
# 品牌解析
# --------------------------------------------------------------------------

_NEGATIVE_HINTS = ("不要", "不考虑", "排除", "别", "不想", "除了")


def _brand_match_terms(brand: str) -> list[str]:
    """把一个归档品牌扩展为可匹配的中文/英文词条(基于 matching 的别名表)。"""
    from ..services.matching import _BRAND_ALIAS, normalize_brand
    canon = normalize_brand(brand)
    terms = {brand.lower(), canon}
    for alias, target in _BRAND_ALIAS.items():
        if target == canon:
            terms.add(alias.lower())
    return sorted({t for t in terms if t}, key=len, reverse=True)


def parse_brands(text: str, known_brands: list[str]) -> tuple[list[str], list[str]]:
    """返回 (倾向品牌, 排除品牌)。依据品牌词(含中文别名)前方的否定语境判断。"""
    allow: list[str] = []
    deny: list[str] = []

    for brand in known_brands:
        index = -1
        for term in _brand_match_terms(brand):
            found = text.find(term)
            if found >= 0 and (index < 0 or found < index):
                index = found
        if index < 0:
            continue
        window = text[max(0, index - 6) : index]
        if any(hint in window for hint in _NEGATIVE_HINTS):
            deny.append(brand)
        else:
            allow.append(brand)
    return allow, deny


# --------------------------------------------------------------------------
# 主入口
# --------------------------------------------------------------------------


def extract(
    text: str, requirement: Requirement, known_brands: list[str] | None = None
) -> tuple[Requirement, list[str]]:
    """增量更新需求,返回新需求与本轮识别到的信号说明。"""
    lowered = text.lower()
    updated = requirement.model_copy(deep=True)
    schema = registry.get(updated.category)
    signals: list[str] = []

    if budget := parse_budget(lowered):
        low, high = budget
        if low:
            updated.budget_min = low
        if high:
            updated.budget_max = high
        if updated.budget_min and updated.budget_max:
            signals.append(f"预算 {updated.budget_min}-{updated.budget_max} 元")
        elif updated.budget_max:
            signals.append(f"预算不超过 {updated.budget_max} 元")

    for key, value in parse_slots(lowered, updated.category).items():
        updated.slots[key] = value
        slot = schema.slot(key)
        label = slot.label if slot else key
        signals.append(f"{label}:{schema.slot_label(key, value)}")

    for key, value in parse_min_specs(lowered, updated.category).items():
        updated.min_specs[key] = value
        attribute = schema.attribute(key)
        label = attribute.label if attribute else key
        unit = attribute.unit if attribute else ""
        signals.append(f"{label}不低于 {value:g}{unit}")

    allow, deny = parse_brands(lowered, known_brands or [])
    for brand in allow:
        if brand not in updated.brand_allow:
            updated.brand_allow.append(brand)
            signals.append(f"倾向品牌:{brand}")
    for brand in deny:
        if brand not in updated.brand_deny:
            updated.brand_deny.append(brand)
            signals.append(f"排除品牌:{brand}")
        if brand in updated.brand_allow:
            updated.brand_allow.remove(brand)

    if any(word in lowered for word in ("二手", "官翻", "翻新")):
        for condition in ("refurb", "used"):
            if condition not in updated.condition:
                updated.condition.append(condition)  # type: ignore[arg-type]
        signals.append("接受官翻/二手")

    return updated, signals


# --------------------------------------------------------------------------
# 隐式偏好 -> 权重微调
# --------------------------------------------------------------------------

#: 维度 key -> 触发词。仅当品类拥有该维度时才生效。
_WEIGHT_KEYWORDS: dict[str, list[str]] = {
    "price": ["便宜", "省钱", "性价比", "预算紧", "划算", "太贵"],
    "performance": ["性能", "跑得快", "流畅", "编译", "渲染", "帧率", "卡"],
    "portability": ["轻", "便携", "通勤", "薄"],
    "handfeel": ["手感", "轻", "单手", "重"],
    "battery": ["续航", "电池", "外出", "不带充电", "耐用"],
    "screen": ["屏幕", "色域", "高刷", "护眼", "分辨率", "oled"],
    "camera": ["拍照", "影像", "相机", "长焦", "拍视频"],
    "noise_cancel": ["降噪", "安静", "地铁", "吵"],
    "sound": ["音质", "听感", "低音", "hifi"],
    "latency": ["延迟", "声画同步", "打游戏"],
    "cleaning": ["吸力", "毛发", "地毯", "扫得干净"],
    "automation": ["省心", "自动", "免手洗", "不用管"],
    "navigation": ["避障", "导航", "漏扫", "卡住"],
    "quietness": ["静音", "噪音", "太吵"],
    "reputation": ["口碑", "评价", "售后", "客服", "靠谱", "省心"],
}


def adjust_weights(text: str, weights: Weights, category: str) -> tuple[Weights, list[str]]:
    """从对话抽取隐式偏好并微调权重。前端滑块与此共用同一份权重。"""
    lowered = text.lower()
    updated = weights.model_copy(deep=True)
    schema = registry.get(category)
    notes: list[str] = []

    for dimension in schema.dimensions:
        keywords = _WEIGHT_KEYWORDS.get(dimension.key, [])
        if keywords and any(keyword in lowered for keyword in keywords):
            updated.bump(dimension.key, 0.10)
            notes.append(f"{dimension.label}权重上调")

    return updated, notes


# --------------------------------------------------------------------------
# 追问
# --------------------------------------------------------------------------


def next_question(requirement: Requirement) -> tuple[str, str, list[str]] | None:
    """返回下一个要追问的 (槽位, 问题, 选项)。槽位齐全则返回 None。"""
    schema = registry.get(requirement.category)
    for key in requirement.missing_slots():
        if key == "budget":
            return ("budget", f"你打算花多少钱买{schema.label}?", schema.budget_options)
        slot = schema.slot(key)
        if slot:
            return (slot.key, slot.question, slot.options)
    return None


def apply_quick_option(slot_key: str, option: str, requirement: Requirement) -> Requirement:
    """处理前端快捷选项点击,不依赖自由文本解析。"""
    updated = requirement.model_copy(deep=True)
    schema = registry.get(updated.category)

    if slot_key == "budget":
        if option in schema.budget_values:
            updated.budget_min, updated.budget_max = schema.budget_values[option]
        return updated

    slot = schema.slot(slot_key)
    if slot and option in slot.option_values:
        updated.slots[slot_key] = slot.option_values[option]
    return updated