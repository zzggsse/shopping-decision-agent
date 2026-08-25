"""用户档案:跨会话的健康状况与生活方式偏好。

设计要点:
  - conditions 是声明式标签(糖尿病/敏感肌/孕妇/游戏重度...),可从对话累积
  - 每个条件如何影响推荐,由 catalog 里品类的 concern_rules 决定,
    这样新增品类时不必改档案模型
  - 档案与单次购物任务解耦:任务创建时读取档案快照,用户可在前端随时编辑
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["avoid", "prefer", "boost"]


class ConditionEffect(BaseModel):
    """某条件对一个品类属性/成分的影响声明。"""

    condition: str
    category: str
    severity: Severity
    #: 匹配维度:"ingredient"(成分名)、"attribute"(商品属性)、"dimension"(打分维度)
    target: Literal["ingredient", "attribute", "dimension"]
    key: str
    #: target=attribute/dimension 时的期望值或权重调整方向
    expect: float | str | bool | None = None
    message: str


class UserProfile(BaseModel):
    user_id: str = "default"
    display_name: str = ""
    conditions: list[str] = Field(default_factory=list)
    notes: str = ""
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def has(self, *conditions: str) -> bool:
        return any(condition in self.conditions for condition in conditions)