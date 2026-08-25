"""测评执行器。

跑法：
    python -m evals.runner                  控制台报告
    python -m evals.runner --json out.json  写 JSON 报告
    python -m evals.runner --update-baseline 把当前轨迹录为基线
    python -m evals.runner --case laptop_basic_gaming  只跑单个用例

测评双轨：
  * 接入了 LLM 凭据 -> LLM-as-judge 为主，行为断言作为硬底线
  * 未接入                -> 行为断言 + 轨迹对比（完全离线可跑）

每个用例跑在全新的 agent 与全新的记忆仓储上，避免用例之间串担保。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
from typing import Any

import yaml

from app.adapters.base import create_adapters
from app.agent.graph import ShoppingAgent
from app.domain.models import ShoppingTask
from app.harness.memory import InMemoryRepository
from app.profile.models import UserProfile
from app.profile.store import ProfileStore

from .judge import build_judge
from .metrics import CaseResult, SuiteResult, compare_trajectory, evaluate_checks

CASES_PATH = pathlib.Path(__file__).with_name("cases.yaml")


def load_cases(path: pathlib.Path | None = None) -> list[dict[str, Any]]:
    """读用例集。"""
    raw = yaml.safe_load((path or CASES_PATH).read_text(encoding="utf-8")) or {}
    return list(raw.get("cases") or [])


def _digest_candidates(task: ShoppingTask, limit: int = 6) -> str:
    """给判官看的候选摘要。只给必要字段，避免把上下文撑爆。"""
    lines = []
    for group in task.candidates[:limit]:
        prices = [o.final_price for o in group.offers if o.final_price is not None]
        best = f"{min(prices):.0f}" if prices else "?"
        lines.append(f"- {group.title}｜最低到手 {best} 元｜{len(group.offers)} 个平台报价")
    return "\n".join(lines) or "（无候选）"


async def run_case(
    case: dict[str, Any],
    judge: Any = None,
) -> CaseResult:
    """跑单个用例。多条 messages 依次发送，共享同一任务与记忆。"""
    case_id = str(case.get("id", "unnamed"))
    category = case.get("category")
    messages = list(case.get("messages") or [])
    expectations = dict(case.get("expect") or {})

    result = CaseResult(
        case_id=case_id,
        category=str(category or "（未指定）"),
        messages=messages,
    )

    # 每个用例全新环境：新档案 + 新记忆仓储
    profiles = ProfileStore()
    profiles.save(UserProfile(**(case.get("profile") or {})))
    agent = ShoppingAgent(
        create_adapters("mock"),
        profiles=profiles,
        memory_repository=InMemoryRepository(),
    )

    task = ShoppingTask(task_id=f"eval-{case_id}")
    if category:
        task.switch_category(str(category))

    event_types: list[str] = []
    tool_calls: list[str] = []
    conclusion_parts: list[str] = []

    try:
        for text in messages:
            async for event in agent.handle_message(task, text):
                kind = event.get("type", "")
                event_types.append(kind)
                if kind in ("message", "final"):
                    content = event.get("content") or event.get("message") or ""
                    if content:
                        conclusion_parts.append(str(content))
                elif kind == "clarify":
                    question = event.get("question") or ""
                    if question:
                        conclusion_parts.append(str(question))
                elif kind == "report":
                    summary = (event.get("report") or {}).get("summary")
                    if summary:
                        conclusion_parts.append(str(summary))
            if agent.last_trace is not None:
                tool_calls.extend(agent.last_trace.tool_calls())
    except Exception as error:
        result.error = f"{type(error).__name__}: {error}"
        return result

    trace = agent.last_trace
    result.tool_calls = tool_calls
    result.conclusion = "\n".join(conclusion_parts)
    result.steps = len(trace.steps) if trace else 0
    result.stop_reason = trace.stop_reason if trace else ""

    # 1) 行为断言（总是跑）
    result.checks = evaluate_checks(
        expectations, tool_calls, event_types, result.conclusion
    )

    # 2) 轨迹对比（有基线才跑）
    baseline = list(case.get("baseline_tool_calls") or [])
    result.baseline_tool_calls = baseline
    if baseline:
        similarity, drift = compare_trajectory(tool_calls, baseline)
        result.trajectory_similarity = similarity
        result.trajectory_drift = drift

    # 3) LLM-as-judge（接入了才跑）
    if judge is not None:
        result.judge = await judge.review(
            messages, result.conclusion, _digest_candidates(task), tool_calls
        )

    return result


async def run_suite(
    cases: list[dict[str, Any]] | None = None,
    use_judge: bool = True,
) -> SuiteResult:
    """跑整套用例。"""
    cases = cases if cases is not None else load_cases()
    judge = build_judge() if use_judge else None
    suite = SuiteResult(judge_backend=judge.name if judge else "行为断言+轨迹对比")
    for case in cases:
        suite.cases.append(await run_case(case, judge))
    return suite


# ----------------------------------------------------------------------
# 控制台报告
# ----------------------------------------------------------------------


def format_report(suite: SuiteResult) -> str:
    lines = [
        "=" * 66,
        f"测评结果：{suite.passed_count}/{suite.total} 通过"
        f"（{suite.pass_rate:.0%}）｜评判方式：{suite.judge_backend}",
        "=" * 66,
    ]
    for case in suite.cases:
        mark = "PASS" if case.passed else "FAIL"
        lines.append(f"[{mark}] {case.case_id}（{case.category}）")
        if case.error:
            lines.append(f"       异常：{case.error}")
        for check in case.failed_checks:
            lines.append(f"       未达预期 {check.kind}={check.target} {check.detail}")
        if case.trajectory_drift:
            lines.append(
                f"       轨迹偏离（相似度 {case.trajectory_similarity}）："
                f"{case.trajectory_drift}"
            )
        if case.judge and case.judge.get("verdict") != "pass":
            lines.append(
                f"       判官：{case.judge.get('verdict')} "
                f"{case.judge.get('reason', '')}"
            )
        lines.append(f"       轨迹：{' -> '.join(case.tool_calls) or '无'}")
    lines.append("=" * 66)
    if suite.regressions:
        lines.append("轨迹偏离的用例：" + "、".join(c.case_id for c in suite.regressions))
    return "\n".join(lines)


def update_baseline(suite: SuiteResult, path: pathlib.Path | None = None) -> None:
    """把本次实际轨迹写回 cases.yaml 作为基线。"""
    target = path or CASES_PATH
    raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    by_id = {case.case_id: case for case in suite.cases}
    for case in raw.get("cases") or []:
        recorded = by_id.get(str(case.get("id")))
        if recorded is not None and not recorded.error:
            case["baseline_tool_calls"] = recorded.tool_calls
    target.write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8",
        newline="",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="购物决策 Agent 测评")
    parser.add_argument("--json", dest="json_path", default="", help="写出 JSON 报告路径")
    parser.add_argument("--case", dest="case_id", default="", help="只跑指定用例")
    parser.add_argument("--no-judge", action="store_true", help="强制不用 LLM 判官")
    parser.add_argument(
        "--update-baseline", action="store_true", help="录制当前轨迹为基线"
    )
    args = parser.parse_args()

    cases = load_cases()
    if args.case_id:
        cases = [c for c in cases if str(c.get("id")) == args.case_id]
        if not cases:
            print(f"没有叫 {args.case_id} 的用例")
            return 2

    suite = asyncio.run(run_suite(cases, use_judge=not args.no_judge))
    print(format_report(suite))

    if args.json_path:
        pathlib.Path(args.json_path).write_text(
            json.dumps(suite.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"JSON 报告已写入：{args.json_path}")

    if args.update_baseline:
        update_baseline(suite)
        print("基线轨迹已写回 cases.yaml")

    return 0 if suite.passed_count == suite.total else 1


if __name__ == "__main__":
    raise SystemExit(main())
