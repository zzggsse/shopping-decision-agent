"""测评框架：行为断言 + 轨迹对比 + LLM-as-judge。"""

from .metrics import CaseResult, SuiteResult
from .runner import load_cases, run_case, run_suite

__all__ = ["CaseResult", "SuiteResult", "load_cases", "run_case", "run_suite"]
