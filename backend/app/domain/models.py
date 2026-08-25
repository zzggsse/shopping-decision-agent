"""领域模型:全品类通用。

品类差异全部下沉到 catalog 配置,模型层只保留通用结构:
  Requirement  预算 + 品牌约束 + 动态槽位/数值下限
  ProductSpec  品牌 + 型号 + 动态属性字典
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from ..catalog import registry


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TaskState(str, Enum):
    INTENT_CLARIFY = "intent_clarify"
    CANDIDATE_GATHER = "candidate_gather"
    COMPARE = "compare"
    PREFERENCE_RANK = "preference_rank"
    USER_FEEDBACK = "user_feedback"
    DECISION_READY = "decision_ready"
    DONE = "done"


Condition = Literal["new", "refurb", "used"]


class Requirement(BaseModel):
    """通用需求模型。品类专属槽位存于 slots,数值下限存于 min_specs。"""

    category: str = "laptop"
    budget_min: int | None = None
    budget_max: int | None = None
    #: 品类槽位取值,如 {"primary_use": "dev", "portability": "high"}
    slots: dict[str, Any] = Field(default_factory=dict)
    #: 数值属性下限,如 {"ram_gb": 16, "battery_hours": 10}
    min_specs: dict[str, float] = Field(default_factory=dict)
    brand_allow: list[str] = Field(default_factory=list)
    brand_deny: list[str] = Field(default_factory=list)
    condition: list[Condition] = Field(default_factory=lambda: ["new"])

    def missing_slots(self) -> list[str]:
        """按品类配置判断哪些必答槽位未填。预算始终必答。"""
        missing: list[str] = []
        if self.budget_max is None and self.budget_min is None:
            missing.append("budget")
        schema = registry.get(self.category)
        missing.extend(key for key in schema.required_slots if key not in self.slots)
        return missing

    def coverage(self) -> float:
        schema = registry.get(self.category)
        total = len(schema.required_slots) + 1
        filled = total - len(self.missing_slots())
        return filled / total if total else 1.0


class PriceComponent(BaseModel):
    label: str
    amount: float
    evidence: str


class Offer(BaseModel):
    """某平台某 SKU 的一条报价。与品类无关。"""

    offer_id: str
    platform: str
    platform_sku_id: str
    title: str
    list_price: float
    components: list[PriceComponent] = Field(default_factory=list)
    final_price: float | None = None
    shop_name: str | None = None
    shop_rating: float | None = None
    review_count: int = 0
    review_score: float | None = None
    in_stock: bool = True
    delivery_days: int | None = None
    condition: Condition = "new"
    url: str = ""
    fetched_at: datetime = Field(default_factory=utcnow)
    stale: bool = False

    def age_seconds(self, now: datetime | None = None) -> float:
        return ((now or utcnow()) - self.fetched_at).total_seconds()


class ProductSpec(BaseModel):
    """通用商品规格。品类专属参数放在 attributes 里。"""

    category: str
    brand: str
    model: str
    attributes: dict[str, Any] = Field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.attributes.get(key, default)

    def summary_line(self) -> str:
        """按品类配置生成摘要行,前端与报告共用。"""
        schema = registry.get(self.category)
        parts: list[str] = []
        for attribute in schema.attributes:
            if not attribute.summary:
                continue
            value = self.attributes.get(attribute.key)
            if value in (None, ""):
                continue
            if text := schema.display(attribute.key, value):
                parts.append(text)
        return " · ".join(parts)


class ProductGroup(BaseModel):
    """同款商品:一组跨平台 offer 聚合到同一个 spec。"""

    group_id: str
    spec: ProductSpec
    offers: list[Offer] = Field(default_factory=list)

    @property
    def best_offer(self) -> Offer | None:
        priced = [o for o in self.offers if o.final_price is not None and o.in_stock]
        return min(priced, key=lambda o: o.final_price or 0) if priced else None

    @property
    def best_price(self) -> float | None:
        offer = self.best_offer
        return offer.final_price if offer else None

    @property
    def title(self) -> str:
        return f"{self.spec.brand} {self.spec.model}"


class ScoreBreakdown(BaseModel):
    group_id: str
    total: float
    dimensions: dict[str, float] = Field(default_factory=dict)
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)


class Weights(BaseModel):
    """动态权重。键来自品类的 dimensions 配置。"""

    values: dict[str, float] = Field(default_factory=dict)

    @classmethod
    def for_category(cls, category: str) -> "Weights":
        return cls(values=registry.get(category).default_weights())

    def normalized(self) -> dict[str, float]:
        total = sum(self.values.values()) or 1.0
        return {key: value / total for key, value in self.values.items()}

    def bump(self, key: str, delta: float) -> None:
        if key in self.values:
            self.values[key] = max(0.0, self.values[key] + delta)


class DecisionLogEntry(BaseModel):
    at: datetime = Field(default_factory=utcnow)
    state: TaskState
    action: str
    detail: str


class ShoppingTask(BaseModel):
    """可持久化的购物任务,支持跨会话续上。"""

    task_id: str
    category: str = "laptop"
    state: TaskState = TaskState.INTENT_CLARIFY
    requirement: Requirement = Field(default_factory=Requirement)
    weights: Weights = Field(default_factory=lambda: Weights.for_category("laptop"))
    candidates: list[ProductGroup] = Field(default_factory=list)
    dropped_group_ids: list[str] = Field(default_factory=list)
    scores: list[ScoreBreakdown] = Field(default_factory=list)
    decision_log: list[DecisionLogEntry] = Field(default_factory=list)
    clarify_rounds: int = 0
    #: 品类是否已由用户明确选择或被对话识别。False 时不能拿默认品类瞎追问。
    category_set: bool = False
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    def switch_category(self, category: str) -> None:
        """切换品类会重置需求与候选池,因为槽位和维度完全不同。"""
        self.category_set = True
        if category == self.category:
            return
        self.category = category
        self.requirement = Requirement(category=category)
        self.weights = Weights.for_category(category)
        self.candidates = []
        self.scores = []
        self.dropped_group_ids = []
        self.clarify_rounds = 0
        self.log("category", f"切换品类为 {registry.get(category).label}")

    def log(self, action: str, detail: str) -> None:
        self.decision_log.append(
            DecisionLogEntry(state=self.state, action=action, detail=detail)
        )
        self.updated_at = utcnow()


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    at: datetime = Field(default_factory=utcnow)