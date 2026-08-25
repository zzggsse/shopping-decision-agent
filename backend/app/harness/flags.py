"""可切换的对照实现开关（默认全部关闭）。

为什么做成开关而不是直接替换:
  这四项技术在当前项目规模下都不是必需品(理由见 README 第 5 章)。
  但"没用"和"不会用"是两件事,所以每一项都提供一份**可运行的对照实现**,
  默认走精简路径,打开开关即切换到对照实现,便于直接对比效果与开销。

对照实现的硬约束:
  1. 默认关闭时,行为必须与开关引入前**完全一致**(由回归测试守)
  2. 打开后如果依赖缺失,必须**明确报错**而不是静默退回,
     否则你以为在用 LangGraph,其实跑的还是原路径
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass(slots=True)
class FeatureFlags:
    """对照实现开关。全部默认关闭。"""

    #: 用 LangGraph 的 StateGraph 驱动核心循环,替代自写 while
    use_langgraph: bool = False
    #: 工具层通过 MCP 协议暴露/调用,替代进程内直接调用
    use_mcp: bool = False
    #: 跨品类横向对比时,为每个品类派一个子 agent 并行跑
    use_multi_agent: bool = False
    #: 系统提示里追加 few-shot 示例
    use_few_shot: bool = False

    @classmethod
    def from_env(cls) -> "FeatureFlags":
        return cls(
            use_langgraph=_flag("USE_LANGGRAPH"),
            use_mcp=_flag("USE_MCP"),
            use_multi_agent=_flag("USE_MULTI_AGENT"),
            use_few_shot=_flag("USE_FEW_SHOT"),
        )

    def enabled(self) -> list[str]:
        """当前打开了哪些对照实现,用于 /api/health 如实上报。"""
        names = {
            "langgraph": self.use_langgraph,
            "mcp": self.use_mcp,
            "multi_agent": self.use_multi_agent,
            "few_shot": self.use_few_shot,
        }
        return sorted(key for key, on in names.items() if on)


def flags() -> FeatureFlags:
    """每次读取环境变量,便于测试内切换。"""
    return FeatureFlags.from_env()
