"""测评指标：行为断言与轨迹对比。

这一层不需要 LLM，因此无论是否接入 key 都能跑。
断言四类：
  tool_used / tool_not_used   必须（不）调用某工具
  event_type                  必须产出某类事件（如 report / clarify）
  text_contains               结论文本必须包含关键信息（如“超出预算”）
  text_excludes               结论文本不得出现某些内容（如被硬过滤的商品）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any


@dataclass(slots=True)
class Check:
    """单条断言结果。"""

    kind: str
    target: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "target": self.target,
            "passed": self.passed,
            "detail": self.detail,
        }


@dataclass
class CaseResult:
    """一个用例的完整结果。"""

    case_id: str
    category: str
    messages: list[str] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)
    tool_calls: list[str] = field(default_factory=list)
    baseline_tool_calls: list[str] = field(default_factory=list)
    trajectory_similarity: float | None = None
    trajectory_drift: str = ""
    conclusion: str = ""
    stop_reason: str = ""
    steps: int = 0
    judge: dict[str, Any] | None = None
    error: str = ""

    @property
    def passed(self) -> bool:
        if self.error:
            return False
        if not all(check.passed for check in self.checks):
            return False
        if self.judge is not None and self.judge.get("verdict") == "fail":
            return False
        return True

    @property
    def failed_checks(self) -> list[Check]:
        return [check for check in self.checks if not check.passed]

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "category": self.category,
            "passed": self.passed,
            "checks": [check.to_dict() for check in self.checks],
            "tool_calls": self.tool_calls,
            "baseline_tool_calls": self.baseline_tool_calls,
            "trajectory_similarity": self.trajectory_similarity,
            "trajectory_drift": self.trajectory_drift,
            "conclusion": self.conclusion[:600],
            "stop_reason": self.stop_reason,
            "steps": self.steps,
            "judge": self.judge,
            "error": self.error,
        }


@dataclass
class SuiteResult:
    """整个测评集的汇总。"""

    cases: list[CaseResult] = field(default_factory=list)
    judge_backend: str = "none"

    @property
    def total(self) -> int:
        return len(self.cases)

    @property
    def passed_count(self) -> int:
        return sum(1 for case in self.cases if case.passed)

    @property
    def pass_rate(self) -> float:
        return self.passed_count / self.total if self.total else 0.0

    @property
    def regressions(self) -> list[CaseResult]:
        """轨迹与基线偏离的用例，即使断言全过也值得看。"""
        return [c for c in self.cases if c.trajectory_drift]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "passed": self.passed_count,
            "pass_rate": round(self.pass_rate, 4),
            "judge_backend": self.judge_backend,
            "regressions": [c.case_id for c in self.regressions],
            "cases": [c.to_dict() for c in self.cases],
        }


# ----------------------------------------------------------------------
# 行为断言
# ----------------------------------------------------------------------


def evaluate_checks(
    expectations: dict[str, Any],
    tool_calls: list[str],
    event_types: list[str],
    conclusion: str,
) -> list[Check]:
    """把用例的 expect 字段逐条跑成断言结果。"""
    checks: list[Check] = []
    called = set(tool_calls)
    seen_events = set(event_types)

    for name in expectations.get("tool_used", []) or []:
        checks.append(Check(
            kind="tool_used",
            target=name,
            passed=name in called,
            detail="" if name in called else f"未调用，实际调用：{tool_calls}",
        ))

    for name in expectations.get("tool_not_used", []) or []:
        checks.append(Check(
            kind="tool_not_used",
            target=name,
            passed=name not in called,
            detail="" if name not in called else "不应该调用却调用了",
        ))

    for event in expectations.get("event_type", []) or []:
        checks.append(Check(
            kind="event_type",
            target=event,
            passed=event in seen_events,
            detail="" if event in seen_events else f"实际事件：{sorted(seen_events)}",
        ))

    for keyword in expectations.get("text_contains", []) or []:
        hit = keyword in conclusion
        checks.append(Check(
            kind="text_contains",
            target=keyword,
            passed=hit,
            detail="" if hit else "结论文本未提及",
        ))

    for keyword in expectations.get("text_excludes", []) or []:
        hit = keyword in conclusion
        checks.append(Check(
            kind="text_excludes",
            target=keyword,
            passed=not hit,
            detail="" if not hit else "结论文本不应出现该内容",
        ))

    max_steps = expectations.get("max_steps")
    if max_steps is not None:
        ok = len(tool_calls) <= int(max_steps)
        checks.append(Check(
            kind="max_steps",
            target=str(max_steps),
            passed=ok,
            detail="" if ok else f"工具调用 {len(tool_calls)} 次，超出上限",
        ))

    return checks


# ----------------------------------------------------------------------
# 轨迹对比
# ----------------------------------------------------------------------


def compare_trajectory(
    actual: list[str], baseline: list[str]
) -> tuple[float, str]:
    """与基线轨迹比对，返回（相似度, 偏离描述）。

    相似度用序列匹配而不是集合比较，因为调用顺序本身就是行为的一部分：
    先检索再刷价与先刷价再检索是两种不同的策略。
    """
    if not baseline:
        return 1.0, ""
    similarity = SequenceMatcher(a=baseline, b=actual).ratio()
    if similarity >= 0.999:
        return 1.0, ""

    added = [name for name in actual if name not in baseline]
    missing = [name for name in baseline if name not in actual]
    parts = []
    if missing:
        parts.append("缺少：" + "、".join(dict.fromkeys(missing)))
    if added:
        parts.append("新增：" + "、".join(dict.fromkeys(added)))
    if not parts:
        parts.append("调用顺序变了")
    return round(similarity, 4), "；".join(parts)
