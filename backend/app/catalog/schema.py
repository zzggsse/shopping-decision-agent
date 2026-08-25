"""品类注册表:全品类能力的核心。

新增一个品类 = 写一份 CategorySchema 配置 + 一份数据 fixture,
不需要改动 agent / ranking / matching / api 任何代码。

三块可配置内容:
  slots      需求槽位(含追问话术、快捷选项、解析规则)
  attributes 商品属性(含单位、方向、对齐是否参与 group key)
  dimensions 打分维度(含默认权重、由哪些属性合成)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
from typing import Callable, Literal

Direction = Literal["higher_better", "lower_better", "none"]
Severity = Literal["avoid", "prefer", "boost"]


@dataclass(slots=True)
class AttributeDef:
    """商品属性定义。"""

    key: str
    label: str
    #: 数值属性用于打分归一化;枚举/文本属性用于展示与硬过滤
    kind: Literal["number", "enum", "text"] = "number"
    unit: str = ""
    direction: Direction = "none"
    #: 枚举属性的档位映射,用于换算为 0-1 分值
    scale: dict[str, float] = field(default_factory=dict)
    #: 枚举值的中文展示名。缺省则直接显示原值
    labels: dict[str, str] = field(default_factory=dict)
    #: 是否参与 SKU 同款判定(如内存/容量差异即非同款)
    identity: bool = False
    #: 是否在卡片摘要行展示
    summary: bool = True


@dataclass(slots=True)
class SlotDef:
    """需求槽位定义。"""

    key: str
    label: str
    question: str
    options: list[str] = field(default_factory=list)
    #: 快捷选项 -> 结构化值
    option_values: dict[str, object] = field(default_factory=dict)
    #: 是否为必答槽位(缺失即触发追问)
    required: bool = False
    #: 关键词 -> 值,用于自由文本解析
    keywords: dict[str, list[str]] = field(default_factory=dict)

    def value_label(self, value: object) -> str:
        """把槽位取值转为中文,复用快捷选项的措辞。"""
        for option, mapped in self.option_values.items():
            if mapped == value:
                return option
        return str(value)


@dataclass(slots=True)
class DimensionDef:
    """打分维度定义。"""

    key: str
    label: str
    default_weight: float
    #: 维度分由哪些属性加权合成:{属性 key: 该属性在本维度内的占比}
    components: dict[str, float] = field(default_factory=dict)
    #: 正向描述模板,用于生成推荐理由
    pro_template: str = ""
    con_template: str = ""


@dataclass(slots=True)
class CategorySchema:
    """一个品类的完整定义。"""

    key: str
    label: str
    #: 用户提问中命中这些词即路由到本品类
    triggers: list[str]
    #: 默认检索词,适配器可据此改写为各平台搜索语法
    search_term: str
    slots: list[SlotDef]
    attributes: list[AttributeDef]
    dimensions: list[DimensionDef]
    #: 典型预算档位,用于追问选项与冷启动
    budget_options: list[str] = field(default_factory=list)
    budget_values: dict[str, tuple[int | None, int | None]] = field(default_factory=dict)
    #: 型号归一化时需剔除的品类噪音词
    noise_words: list[str] = field(default_factory=list)
    #: 成分表所在的属性 key(如洗发水 ingredients / 食品 nutrition)
    ingredient_attribute: str | None = None
    #: 成分条目的分隔符,用于把文本拆成独立成分
    ingredient_separator: str = "、,，;；/"
    #: 该品类下,健康/生活方式条件如何影响推荐
    concern_rules: list["ConcernRule"] = field(default_factory=list)
    #: 成分知识库:成分名 -> 知识条目
    ingredient_knowledge: dict[str, "IngredientKnowledge"] = field(default_factory=dict)

    # ---- 便捷查询 ----

    def attribute(self, key: str) -> AttributeDef | None:
        return next((a for a in self.attributes if a.key == key), None)

    def slot(self, key: str) -> SlotDef | None:
        return next((s for s in self.slots if s.key == key), None)

    @property
    def required_slots(self) -> list[str]:
        return [slot.key for slot in self.slots if slot.required]

    @property
    def identity_attributes(self) -> list[str]:
        return [a.key for a in self.attributes if a.identity]

    @property
    def numeric_attributes(self) -> list[str]:
        return [a.key for a in self.attributes if a.kind == "number"]

    def slot_label(self, slot_key: str, value: object) -> str:
        """槽位取值的中文说明,用于"已记录"回执与决策日志。"""
        slot = self.slot(slot_key)
        return slot.value_label(value) if slot else str(value)

    def display(self, key: str, value: object) -> str:
        """把属性原始值转为用户可读文本(枚举转中文、补单位)。"""
        attribute = self.attribute(key)
        if attribute is None or value is None:
            return "" if value is None else str(value)
        if attribute.kind == "enum":
            return attribute.labels.get(str(value), str(value))
        return f"{value}{attribute.unit}" if attribute.unit else str(value)

    def default_weights(self) -> dict[str, float]:
        return {d.key: d.default_weight for d in self.dimensions}

    def dimension(self, key: str) -> DimensionDef | None:
        return next((d for d in self.dimensions if d.key == key), None)


@dataclass(slots=True)
class IngredientKnowledge:
    """单个成分的知识库条目。可由成分库统一导入。"""

    name: str
    aliases: list[str] = field(default_factory=list)
    benefits: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    #: 哪些条件人群应避免(对应 UserProfile.conditions)
    avoid_for: list[str] = field(default_factory=list)
    #: 对哪些头发/皮肤/身体问题有帮助(自由文本标签)
    helps_with: list[str] = field(default_factory=list)
    category: str = ""


@dataclass(slots=True)
class ConcernRule:
    """用户条件对某品类的影响规则。

    severity:
      avoid  命中即作为禁忌,加入 cons 并可用于过滤
      prefer 倾向:命中成分/属性时加分并写入 pros
      boost  维度加权:提升某打分维度的权重
    """

    condition: str
    severity: Severity
    target: str  # ingredient | attribute | dimension
    key: str
    expect: object = None
    message: str = ""
    weight_delta: float = 0.15


class CategoryRegistry:
    """品类注册中心。"""

    def __init__(self) -> None:
        self._items: dict[str, CategorySchema] = {}

    def register(self, schema: CategorySchema) -> None:
        self._items[schema.key] = schema

    def get(self, key: str) -> CategorySchema:
        if key not in self._items:
            raise KeyError(f"未注册的品类:{key}")
        return self._items[key]

    def has(self, key: str) -> bool:
        return key in self._items

    def keys(self) -> list[str]:
        return list(self._items)

    def all(self) -> list[CategorySchema]:
        return list(self._items.values())

    def detect(self, text: str) -> str | None:
        """从自由文本识别品类。命中最长触发词者优先,避免"手机支架"误判为"手机"。"""
        lowered = text.lower()
        best: tuple[int, str] | None = None
        for schema in self._items.values():
            for trigger in schema.triggers:
                if trigger.lower() in lowered:
                    if best is None or len(trigger) > best[0]:
                        best = (len(trigger), schema.key)
        return best[1] if best else None


registry = CategoryRegistry()