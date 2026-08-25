"""编排层:预算、追踪、重试、收敛。

把原先散在 graph._loop 里的循环控制抽出来,补上生产必需的几件事:

  预算  步数 / token / 墙钟时间三重上限,任一触顶即收敛
  追踪  每步决策与工具结果落成 TraceStep,可回放、可诊断、可测评
  重试  工具瞬时失败自动重试;连续失败则放弃该工具
  收敛  永远保证产出结果,不让前端卡在 loading

这一层不含购物逻辑 —— 它不知道什么是预算、什么是洗发水,
只知道「决策者、工具、预算、追踪」。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class RunBudget:
    """单轮运行预算。任一维度触顶就停止继续决策。"""

    max_steps: int = 14
    max_tokens: int = 60000
    max_seconds: float = 90.0
    #: 同一个工具最多连续失败几次
    max_tool_retries: int = 2


@dataclass(slots=True)
class TraceStep:
    """一步的完整记录。测评与调试都依赖它。"""

    index: int
    kind: str
    name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    ok: bool = True
    detail: str = ""
    elapsed_ms: int = 0
    tokens: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "kind": self.kind,
            "name": self.name,
            "arguments": self.arguments,
            "ok": self.ok,
            "detail": self.detail[:300],
            "elapsed_ms": self.elapsed_ms,
            "tokens": self.tokens,
        }


@dataclass
class RunTrace:
    """一次 handle_message 的完整轨迹。"""

    steps: list[TraceStep] = field(default_factory=list)
    started_at: float = field(default_factory=time.monotonic)
    tokens_used: int = 0
    stop_reason: str = ""

    def add(self, step: TraceStep) -> None:
        self.steps.append(step)
        self.tokens_used += step.tokens

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.started_at

    def tool_calls(self) -> list[str]:
        """按顺序列出调用过的工具名。轨迹对比测评用它。"""
        return [s.name for s in self.steps if s.kind == "tool"]

    def failures(self) -> list[TraceStep]:
        return [s for s in self.steps if not s.ok]

    def to_dict(self) -> dict[str, Any]:
        return {
            "steps": [s.to_dict() for s in self.steps],
            "tool_calls": self.tool_calls(),
            "tokens_used": self.tokens_used,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "stop_reason": self.stop_reason,
            "failure_count": len(self.failures()),
        }


class BudgetGuard:
    """预算看守。每步询问一次是否还能继续。"""

    def __init__(self, budget: RunBudget, trace: RunTrace) -> None:
        self.budget = budget
        self.trace = trace
        #: 工具名 -> 连续失败次数
        self._failures: dict[str, int] = {}

    def exhausted(self, step_index: int) -> str:
        """返回耗尽原因;还有余量则返回空串。"""
        if step_index >= self.budget.max_steps:
            return f"步数达到上限 {self.budget.max_steps}"
        if self.trace.tokens_used >= self.budget.max_tokens:
            return f"token 达到上限 {self.budget.max_tokens}"
        if self.trace.elapsed_seconds >= self.budget.max_seconds:
            return f"耗时达到上限 {self.budget.max_seconds}s"
        return ""

    def record_tool_result(self, name: str, ok: bool) -> None:
        if ok:
            self._failures.pop(name, None)
        else:
            self._failures[name] = self._failures.get(name, 0) + 1

    def should_give_up(self, name: str) -> bool:
        """该工具是否已连续失败太多次,不该再试。"""
        return self._failures.get(name, 0) > self.budget.max_tool_retries

    def blocked_tools(self) -> list[str]:
        return [n for n in self._failures
                if self._failures[n] > self.budget.max_tool_retries]


def summarize_trace(trace: RunTrace) -> str:
    """把轨迹压成一行,便于日志与前端调试面板展示。"""
    calls = trace.tool_calls()
    parts = [f"{len(trace.steps)} 步"]
    if calls:
        parts.append("→".join(calls))
    parts.append(f"{trace.elapsed_seconds:.1f}s")
    if trace.tokens_used:
        parts.append(f"~{trace.tokens_used} tokens")
    if trace.stop_reason:
        parts.append(f"收敛于:{trace.stop_reason}")
    failures = trace.failures()
    if failures:
        parts.append(f"{len(failures)} 次失败")
    return " | ".join(parts)
