"""成分分析子系统。"""

from .analyzer import IngredientAnalysis, analyze, rules_for_profile, split_ingredients

__all__ = ["IngredientAnalysis", "analyze", "rules_for_profile", "split_ingredients"]