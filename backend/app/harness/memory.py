"""三层记忆系统。

  会话记忆(session)  一次对话内的轮次,用于上下文装配
  任务记忆(task)     单次决策的进展:看过什么、排除过什么、为什么
  长期记忆(profile)  跨会话的用户画像:健康条件、品牌倾向、价格敏感度

关键能力 **自动沉淀**:用户说"我有糖尿病"、"不要小米"、"太贵了",系统
主动记进长期记忆并告知,而不是等他去前端勾选。

存储走 MemoryRepository 协议。默认内存实现;配了 DATABASE_URL 则用
Postgres(app/harness/repository.py),上层代码不变。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from .context import Turn


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class MemoryItem:
    """一条长期记忆。

    kind: condition / brand_deny / brand_prefer / price_attitude / note
    """

    kind: str
    value: str
    #: 用户明说为 1.0,推断的更低
    confidence: float = 1.0
    #: 证据原文,便于用户核对与撤销
    evidence: str = ""
    created_at: datetime = field(default_factory=_now)

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.value}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "value": self.value,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class SessionMemory:
    """一次对话的轮次记录。"""

    turns: list[Turn] = field(default_factory=list)

    def add_user(self, text: str) -> None:
        if text and text.strip():
            self.turns.append(Turn("user", text.strip()))

    def add_assistant(self, text: str) -> None:
        if text and text.strip():
            self.turns.append(Turn("assistant", text.strip()))

    def recent(self, limit: int = 20) -> list[Turn]:
        return self.turns[-limit:]


@dataclass
class TaskMemory:
    """单次购物决策的进展。"""

    seen_group_ids: set[str] = field(default_factory=set)
    rejected: dict[str, str] = field(default_factory=dict)
    relaxations: list[str] = field(default_factory=list)

    def note_seen(self, group_ids: list[str]) -> None:
        self.seen_group_ids.update(group_ids)

    def note_rejected(self, group_id: str, reason: str) -> None:
        self.rejected[group_id] = reason

    def note_relaxation(self, description: str) -> None:
        self.relaxations.append(description)


class MemoryRepository(Protocol):
    """长期记忆存储协议。内存与 Postgres 两种实现都满足它。"""

    def load(self, user_id: str) -> list[MemoryItem]:
        ...

    def save(self, user_id: str, items: list[MemoryItem]) -> None:
        ...


class InMemoryRepository:
    """默认实现。进程内有效,重启丢失 —— 仅用于开发与测试。"""

    def __init__(self) -> None:
        self._data: dict[str, list[MemoryItem]] = {}

    def load(self, user_id: str) -> list[MemoryItem]:
        return list(self._data.get(user_id, []))

    def save(self, user_id: str, items: list[MemoryItem]) -> None:
        self._data[user_id] = list(items)


class LongTermMemory:
    """跨会话用户画像。去重、可撤销、可摘要给模型。"""

    def __init__(self, repository: MemoryRepository | None = None,
                 user_id: str = "default") -> None:
        self.repository = repository or InMemoryRepository()
        self.user_id = user_id
        self._items: dict[str, MemoryItem] = {
            item.key: item for item in self.repository.load(user_id)
        }

    def all(self) -> list[MemoryItem]:
        return sorted(self._items.values(), key=lambda i: i.created_at)

    def of_kind(self, kind: str) -> list[MemoryItem]:
        return [item for item in self.all() if item.kind == kind]

    def remember(self, item: MemoryItem) -> bool:
        """写入一条记忆。已存在同 key 且置信度不更高则不覆盖。

        返回是否真的新增/更新,便于上层决定要不要告知用户。
        """
        existing = self._items.get(item.key)
        if existing and existing.confidence >= item.confidence:
            return False
        self._items[item.key] = item
        self._flush()
        return True

    def forget(self, kind: str, value: str) -> bool:
        """用户撤销一条记忆。记忆必须可反悔,否则会越记越错。"""
        if self._items.pop(f"{kind}:{value}", None) is None:
            return False
        self._flush()
        return True

    def digest(self) -> str:
        """压成一段话交给模型。空则返回空串,调用方不必判空。"""
        if not self._items:
            return ""
        lines: list[str] = []
        conditions = [describe_memory(i) for i in self.of_kind("condition")]
        if conditions:
            lines.append("健康与生活方式:" + "、".join(conditions))
        deny = [i.value for i in self.of_kind("brand_deny")]
        if deny:
            lines.append("不想要的品牌:" + "、".join(deny))
        prefer = [i.value for i in self.of_kind("brand_prefer")]
        if prefer:
            lines.append("偏好的品牌:" + "、".join(prefer))
        attitude = self.of_kind("price_attitude")
        if attitude:
            label = {"cheap": "偏好性价比,对价格敏感",
                     "premium": "愿意为品质多花钱"}
            lines.append(label.get(attitude[-1].value, attitude[-1].value))
        notes = [i.value for i in self.of_kind("note")]
        if notes:
            lines.append("其他:" + ";".join(notes))
        return "\n".join(lines)

    def _flush(self) -> None:
        self.repository.save(self.user_id, list(self._items.values()))


#: 健康条件的中文说法 -> 档案条件 key。与 catalog 的 concern_rules 对齐。
_CONDITION_PATTERNS: dict[str, tuple[str, ...]] = {
    "diabetes": ("糖尿病", "血糖高", "控糖", "高血糖"),
    "hypertension": ("高血压", "血压高"),
    "nut_allergy": ("坚果过敏", "花生过敏", "对坚果过敏"),
    "pregnant": ("怀孕", "孕期", "备孕", "哺乳"),
    "sensitive_scalp": ("敏感头皮", "头皮敏感", "头皮容易痒"),
    "sulfate_allergy": ("硫酸盐过敏", "sls过敏"),
    "fitness": ("健身", "增肌", "高蛋白", "减脂"),
    "gaming": ("打游戏", "游戏党", "重度游戏", "玩游戏", "电竞"),
}

#: 否定语境,判断"不要 X"
_NEGATIVE = ("不要", "不想要", "不考虑", "别给我", "排除", "讨厌", "不喜欢")


def _brand_surfaces(brand: str) -> list[str]:
    """一个品牌在用户口语里的所有写法。

    用户会说“不要小米”而不是“不要 xiaomi”，而候选数据里的品牌名是
    规范化后的英文。直接复用需求抽取里已有的展开逻辑，不另维护一份别名表。
    """
    try:
        from ..agent.extract import _brand_match_terms
    except ImportError:
        return [brand.strip().lower()]
    return _brand_match_terms(brand)


def extract_memories(text: str, known_brands: list[str] | None = None) -> list[MemoryItem]:
    """从用户原话里抽取值得长期记住的信息。

    离线规则实现。接入 LLM 后可换成模型抽取,返回类型不变。
    只抽"稳定的偏好",不抽"本次需求"—— 预算 7000 是本次需求,
    糖尿病才是长期事实。
    """
    found: list[MemoryItem] = []
    lowered = text.lower()

    for condition, patterns in _CONDITION_PATTERNS.items():
        for pattern in patterns:
            if pattern in lowered:
                found.append(MemoryItem(
                    kind="condition", value=condition,
                    confidence=1.0, evidence=text.strip()[:80],
                ))
                break

    for brand in known_brands or []:
        for alias in _brand_surfaces(brand):
            index = lowered.find(alias)
            if index < 0:
                continue
            window = lowered[max(0, index - 6):index]
            if any(hint in window for hint in _NEGATIVE):
                found.append(MemoryItem(
                    kind="brand_deny", value=brand,
                    confidence=0.9, evidence=text.strip()[:80],
                ))
                break

    if any(word in lowered for word in ("太贵", "便宜点", "性价比", "省钱", "预算紧")):
        found.append(MemoryItem(
            kind="price_attitude", value="cheap",
            confidence=0.6, evidence=text.strip()[:80],
        ))
    elif any(word in lowered for word in ("不在乎价格", "预算充足", "要最好的", "贵点没关系")):
        found.append(MemoryItem(
            kind="price_attitude", value="premium",
            confidence=0.6, evidence=text.strip()[:80],
        ))

    return found


#: 条件 key -> 中文标签。展示给用户与模型时一律用中文。
CONDITION_LABELS = {
    "diabetes": "糖尿病", "hypertension": "高血压",
    "nut_allergy": "坚果过敏", "pregnant": "孕期/备孕",
    "sensitive_scalp": "敏感头皮", "sulfate_allergy": "硫酸盐过敏",
    "fitness": "健身/高蛋白", "gaming": "游戏重度",
}


def describe_memory(item: MemoryItem) -> str:
    """把记忆项说成人话,用于回执"已记住…"。"""
    if item.kind == "condition":
        return CONDITION_LABELS.get(item.value, item.value)
    if item.kind == "brand_deny":
        return f"不要 {item.value}"
    if item.kind == "brand_prefer":
        return f"偏好 {item.value}"
    if item.kind == "price_attitude":
        return "看重性价比" if item.value == "cheap" else "愿为品质加价"
    return item.value
