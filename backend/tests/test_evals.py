"""把测评集接入 pytest，让行为回归跟单测一起守。

这里永远走离线双轨（行为断言 + 轨迹对比），不调真实 LLM：
单测必须确定、快、不花钱。LLM-as-judge 手动跑：
    python -m evals.runner
"""

from __future__ import annotations

import pytest

from evals.runner import load_cases, run_case


@pytest.mark.parametrize("case", load_cases(), ids=lambda c: str(c["id"]))
@pytest.mark.asyncio
async def test_eval_case(case) -> None:
    result = await run_case(case, judge=None)

    assert not result.error, f"{result.case_id} 运行异常：{result.error}"

    failures = [
        f"{check.kind}={check.target} {check.detail}" for check in result.failed_checks
    ]
    assert not failures, f"{result.case_id} 未达预期：" + "；".join(failures)

    assert not result.trajectory_drift, (
        f"{result.case_id} 轨迹偏离基线（相似度 "
        f"{result.trajectory_similarity}）：{result.trajectory_drift}\n"
        f"当前：{result.tool_calls}\n基线：{result.baseline_tool_calls}\n"
        f"确认行为变更合理后跑：python -m evals.runner --update-baseline"
    )
