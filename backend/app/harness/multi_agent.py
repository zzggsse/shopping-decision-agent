"""多智能体对照实现:跨品类横向对比。

默认不启用(USE_MULTI_AGENT=1 打开)。

为什么这里才是多智能体唯一有正收益的场景:
  单品类决策的子任务(检索 -> 成分分析 -> 排序)是**严格顺序依赖**的,
  拆成多个 agent 只是把函数调用换成 agent 间通信,纯亏。
  但"预算 5000,买笔记本还是买手机 + 平板"这类问题不一样 ——
  各品类的检索与排序**互不依赖**,可以真并行。

采用的范式:Supervisor(主管派发) + 并行 Worker,不用辩论式。
  理由是结论必须可归因:每个品类的推荐要能追溯到自己那条链路的依据,
  而辩论范式产出的折中结论没法回答"为什么这瓶排第一"。

    ┌─ Supervisor:识别涉及哪些品类,派发子任务
    │
    ├─→ Worker(laptop)  ─┐  各自独立的 ShoppingTask
    ├─→ Worker(phone)   ─┼─ asyncio.gather 并行
    └─→ Worker(earbuds) ─┘
              │
              └─→ Supervisor:汇总为一份可对比的结论

诚实的成本说明:
  1. 每个 worker 有独立上下文,token 开销约等于品类数的倍数
  2. 失败点从 1 个变 N 个(靠 return_exceptions 逐个降级,不让单点拖垮全局)
  3. 只有品类数 >= 2 才启用,否则自动退回单 agent —— 不为用而用
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class CategoryVerdict:
    """单个品类 worker 的产出。"""

    category: str
    label: str
    ok: bool
    title: str = ""
    price: float | None = None
    score: float | None = None
    platform: str = ""
    url: str = ""
    reasons: list[str] = field(default_factory=list)
    candidate_count: int = 0
    error: str = ""


def detect_multi_categories(text: str, limit: int = 3) -> list[str]:
    """识别一句话里提到的多个品类。

    单品类或识别不到时返回空列表 —— 调用方据此退回单 agent 路径。
    """
    from ..catalog import registry

    lowered = text.lower()
    hits: list[tuple[int, str]] = []
    for schema in registry.all():
        best = 0
        for trigger in schema.triggers:
            if trigger.lower() in lowered:
                best = max(best, len(trigger))
        if best:
            hits.append((best, schema.key))

    # 按触发词长度降序,长词优先(与 registry.detect 的策略一致)
    hits.sort(reverse=True)
    keys = list(dict.fromkeys(key for _, key in hits))
    return keys[:limit] if len(keys) >= 2 else []


class MultiAgentComparator:
    """Supervisor:派发子任务并汇总。"""

    def __init__(self, *, adapters, profiles, memory_repository=None) -> None:
        self.adapters = adapters
        self.profiles = profiles
        self.memory_repository = memory_repository

    async def compare(self, text: str, categories: list[str]) -> list[CategoryVerdict]:
        """为每个品类起一个 worker 并行跑,返回可对比的结论。"""
        results = await asyncio.gather(
            *(self._worker(text, category) for category in categories),
            return_exceptions=True,
        )

        verdicts: list[CategoryVerdict] = []
        for category, outcome in zip(categories, results):
            if isinstance(outcome, BaseException):
                # 单个品类失败不拖垮整体,如实记下原因
                from ..catalog import registry

                verdicts.append(CategoryVerdict(
                    category=category,
                    label=registry.get(category).label,
                    ok=False,
                    error=str(outcome),
                ))
            else:
                verdicts.append(outcome)
        return verdicts

    async def _worker(self, text: str, category: str) -> CategoryVerdict:
        """单品类 worker:独立的任务与上下文,跑完整决策链路。

        刻意复用 ShoppingAgent 本身而不另写一套逻辑 ——
        worker 与单 agent 路径共用同一份决策与工具,保证结论口径一致。
        """
        from ..adapters.base import PlatformAdapter  # noqa: F401
        from ..agent.graph import ShoppingAgent
        from ..catalog import registry
        from ..domain.models import ShoppingTask

        schema = registry.get(category)
        agent = ShoppingAgent(
            self.adapters,
            profiles=self.profiles,
            memory_repository=self.memory_repository,
            # 关键:worker 不得再次派发,否则无限递归
            allow_multi_agent=False,
            # 横向对比不追问,缺失槽位交给打分兜底
            no_clarify=True,
            # 原文含多个品类触发词,必须锁定,否则所有 worker 塌到同一品类
            lock_category=True,
        )
        task = ShoppingTask(task_id=f"multi-{category}")
        task.switch_category(category)

        async for _ in agent.handle_message(task, text):
            pass

        if not task.candidates:
            return CategoryVerdict(
                category=category, label=schema.label, ok=False,
                candidate_count=0, error="该品类下没有符合条件的候选",
            )

        top = task.candidates[0]
        best = top.best_offer
        score = next(
            (s for s in task.scores if s.group_id == top.group_id), None
        )
        return CategoryVerdict(
            category=category,
            label=schema.label,
            ok=True,
            title=top.title,
            price=best.final_price if best else None,
            score=score.total if score else None,
            platform=best.platform if best else "",
            url=best.url if best else "",
            reasons=(score.pros[:2] if score else []),
            candidate_count=len(task.candidates),
        )


def summarize(verdicts: list[CategoryVerdict]) -> dict[str, Any]:
    """把各品类结论汇总成一份横向对比。

    刻意**不给出"就买这个"的唯一答案** —— 跨品类之间没有可比的公共维度
    (笔记本的性能分和洗发水的成分分不是一个量纲)。
    能诚实提供的是:每个品类各自的最优、价格、依据,由用户自己权衡。
    """
    ok = [v for v in verdicts if v.ok]
    failed = [v for v in verdicts if not v.ok]

    lines = []
    for verdict in ok:
        price = f"{verdict.price:.0f} 元" if verdict.price is not None else "价格待核"
        lines.append(
            f"- {verdict.label}:{verdict.title}，{verdict.platform} {price}"
            + (f"（{verdict.reasons[0]}）" if verdict.reasons else "")
        )
    for verdict in failed:
        lines.append(f"- {verdict.label}:{verdict.error}")

    summary = (
        f"并行比较了 {len(verdicts)} 个品类，各自的最优选择如下。\n"
        + "\n".join(lines)
        + "\n\n跨品类之间没有统一的打分量纲，"
        "所以这里只给出各自最优与依据，最终取舍取决于你更需要哪一类。"
    )

    return {
        "type": "multi_category_report",
        "summary": summary,
        "verdicts": [
            {
                "category": v.category,
                "label": v.label,
                "ok": v.ok,
                "title": v.title,
                "price": v.price,
                "score": v.score,
                "platform": v.platform,
                "url": v.url,
                "reasons": v.reasons,
                "candidate_count": v.candidate_count,
                "error": v.error,
            }
            for v in verdicts
        ],
    }
