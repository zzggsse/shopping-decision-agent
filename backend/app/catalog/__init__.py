"""品类注册表:全品类扩展的唯一入口。"""

from .definitions import DEFAULT_CATEGORY
from .schema import (
    AttributeDef,
    CategoryRegistry,
    CategorySchema,
    DimensionDef,
    SlotDef,
    registry,
)

__all__ = [
    "AttributeDef",
    "CategoryRegistry",
    "CategorySchema",
    "DEFAULT_CATEGORY",
    "DimensionDef",
    "SlotDef",
    "registry",
]