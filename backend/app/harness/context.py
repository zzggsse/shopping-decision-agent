"""上下文装配与预算管理。

解决的核心问题:原先 _loop 每轮从零重建 messages,只放当前一句用户输入,
历史全部丢弃 —— 用户说"太贵了"时模型看不到上一轮推荐了什么。

职责:
  1. 把「系统指令 + 历史对话 + 本轮工具结果」装配成模型可消费的 messages
  2. 控制 token 预算:超限时按优先级压缩,而不是无脑截断
  3. 裁剪工具结果:候选列表这类大对象只保留决策所需字段

设计原则:宁可丢细节,也要保住「用户说过什么」和「最近一步工具结果」。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

#: 粗略估算:中文约 1.5 字符/token,英文约 4 字符/token。取保守值。
_CHARS_PER_TOKEN = 2.0

#: 单条工具结果最多占多少字符,超出则裁剪
MAX_TOOL_RESULT_CHARS = 1200

#: 保留最近多少轮对话原文(更早的会被摘要替代)
KEEP_RECENT_TURNS = 6


def estimate_tokens(text: str) -> int:
    """粗略估 token。不追求精确,只用于预算控制的相对比较。"""
    if not text:
        return 0
    return max(1, int(len(text) / _CHARS_PER_TOKEN))


def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    total = 0
    for message in messages:
        total += estimate_tokens(str(message.get("content") or ""))
        total += 4  # 角色与结构开销
    return total


@dataclass(slots=True)
class Turn:
    """一轮对话。role 为 user 或 assistant。"""

    role: str
    content: str


@dataclass(slots=True)
class ContextBudget:
    """上下文预算。超限时触发压缩。"""

    max_tokens: int = 8000
    #: 留给模型输出的余量
    reserve_for_output: int = 1000

    @property
    def usable(self) -> int:
        return max(500, self.max_tokens - self.reserve_for_output)


@dataclass
class ContextAssembler:
    """把多来源信息装配成 messages。

    与 LLM 客户端解耦:只产出标准的 messages 列表,谁来消费不管。
    """

    system_prompt: str
    budget: ContextBudget = field(default_factory=ContextBudget)

    #: 本轮循环内累积的工具调用与结果
    _tool_trace: list[dict[str, Any]] = field(default_factory=list, init=False)

    def reset_tools(self) -> None:
        self._tool_trace.clear()

    def record_tool(self, step: int, name: str, result: Any) -> None:
        """记录一次工具执行。result 会被裁剪后存入。"""
        self._tool_trace.append({
            "step": step,
            "name": name,
            "content": clip_tool_result(result),
        })

    def build(
        self,
        *,
        history: list[Turn],
        current_input: str,
        observation: str,
        memory_digest: str = "",
    ) -> list[dict[str, Any]]:
        """装配 messages。

        顺序:系统指令 → 长期记忆摘要 → 历史对话 → 当前观测 → 本轮用户输入
        → 本轮已执行的工具结果。
        """
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt}
        ]

        if memory_digest:
            messages.append({
                "role": "system",
                "content": f"[关于这位用户我已经知道的]\n{memory_digest}",
            })

        messages.extend(self._history_messages(history))

        if observation:
            messages.append({
                "role": "system",
                "content": f"[当前任务状态]\n{observation}",
            })

        messages.append({"role": "user", "content": current_input})

        for entry in self._tool_trace:
            messages.append({
                "role": "tool",
                "tool_call_id": f"call_{entry['step']}_{entry['name']}",
                "name": entry["name"],
                "content": entry["content"],
            })

        return self._fit_budget(messages)

    # ------------------------------------------------------------------

    def _history_messages(self, history: list[Turn]) -> list[dict[str, Any]]:
        """历史对话。过长时把早期轮次压成一条摘要。"""
        if not history:
            return []

        if len(history) <= KEEP_RECENT_TURNS:
            return [{"role": t.role, "content": t.content} for t in history]

        older = history[:-KEEP_RECENT_TURNS]
        recent = history[-KEEP_RECENT_TURNS:]

        digest = summarize_turns(older)
        messages: list[dict[str, Any]] = []
        if digest:
            messages.append({
                "role": "system",
                "content": f"[更早的对话摘要]\n{digest}",
            })
        messages.extend({"role": t.role, "content": t.content} for t in recent)
        return messages

    def _fit_budget(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """超预算时按优先级压缩。

        丢弃优先级(先丢价值低的):
          1. 较早的工具结果(只留最近 3 条)
          2. 较早的历史对话
        永不丢弃:系统指令、当前用户输入、最近一条工具结果。
        """
        if estimate_messages_tokens(messages) <= self.budget.usable:
            return messages

        # 第一步:压工具结果
        tool_indexes = [i for i, m in enumerate(messages) if m["role"] == "tool"]
        if len(tool_indexes) > 3:
            drop = set(tool_indexes[:-3])
            messages = [m for i, m in enumerate(messages) if i not in drop]
            if estimate_messages_tokens(messages) <= self.budget.usable:
                return messages

        # 第二步:压历史对话(保住最后一条 user,即本轮输入)
        last_user = max(
            (i for i, m in enumerate(messages) if m["role"] == "user"), default=-1
        )
        conversational = [
            i for i, m in enumerate(messages)
            if m["role"] in ("user", "assistant") and i != last_user
        ]
        for index in conversational:
            messages = [m for i, m in enumerate(messages) if i != index]
            if estimate_messages_tokens(messages) <= self.budget.usable:
                break
            # 索引已变,重新计算
            last_user = max(
                (i for i, m in enumerate(messages) if m["role"] == "user"), default=-1
            )
            conversational = [
                i for i, m in enumerate(messages)
                if m["role"] in ("user", "assistant") and i != last_user
            ]
            if not conversational:
                break

        return messages


def clip_tool_result(result: Any) -> str:
    """把工具结果序列化并裁剪到预算内。

    候选列表这类大对象只保留决策必要字段,避免一条结果吃掉整个上下文。
    """
    payload = result.get("result") if isinstance(result, dict) else result
    payload = _shrink(payload)

    try:
        text = json.dumps(payload, ensure_ascii=False, default=str)
    except Exception:
        text = str(payload)

    if len(text) <= MAX_TOOL_RESULT_CHARS:
        return text
    return text[:MAX_TOOL_RESULT_CHARS] + f"…(已截断,原长 {len(text)} 字符)"


def _shrink(payload: Any) -> Any:
    """递归精简大结构。只保留决策用得上的字段。"""
    if isinstance(payload, dict):
        shrunk = {}
        for key, value in payload.items():
            if key == "candidates" and isinstance(value, list):
                shrunk[key] = [_shrink_candidate(c) for c in value[:5]]
                if len(value) > 5:
                    shrunk["candidates_omitted"] = len(value) - 5
            elif key == "schema":
                # 品类配置很长,决策层用不到全文
                shrunk[key] = "(已省略,可用 get_category_schema 查询)"
            else:
                shrunk[key] = _shrink(value)
        return shrunk
    if isinstance(payload, list):
        return [_shrink(item) for item in payload[:10]]
    return payload


def _shrink_candidate(candidate: Any) -> Any:
    """候选只保留标题、价格、平台、评分与关键理由。"""
    if not isinstance(candidate, dict):
        return candidate
    keep = ("group_id", "title", "best_price", "final_price", "platform",
            "best_platform", "score", "summary")
    shrunk = {k: candidate[k] for k in keep if k in candidate}
    score = shrunk.get("score")
    if isinstance(score, dict):
        shrunk["score"] = {
            "total": score.get("total"),
            "pros": (score.get("pros") or [])[:2],
            "cons": (score.get("cons") or [])[:1],
        }
    return shrunk


def summarize_turns(turns: list[Turn]) -> str:
    """把多轮对话压成简短摘要。

    离线实现:抽取用户话语要点。接入 LLM 后可替换为模型摘要,
    调用方无需改动。
    """
    if not turns:
        return ""
    user_says = [t.content.strip() for t in turns if t.role == "user" and t.content.strip()]
    if not user_says:
        return ""
    if len(user_says) <= 3:
        return "用户先前说过:" + ";".join(user_says)
    head = ";".join(user_says[:2])
    tail = ";".join(user_says[-2:])
    return f"用户先前说过:{head}……{tail}(共 {len(user_says)} 条)"
