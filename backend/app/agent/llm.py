"""可切换的 LLM 客户端。

接口: 单个方法 `decide`,返回 Decision。
Decision = {"final": str} | {"tool_calls": [{"name":..., "arguments": dict}]}

Provider 由环境变量选择:
  LLM_PROVIDER=mock   默认。确定性策略,离线可测,走真实工具调用
  LLM_PROVIDER=ark    火山方舟(OpenAI 兼容)
  LLM_PROVIDER=openai OpenAI 兼容

敏感凭据一律走环境变量,不允许写进任何文件:
  ARK_API_KEY / ARK_BASE_URL / ARK_MODEL
  OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL
"""

from __future__ import annotations

import os
from typing import Any

SYSTEM_PROMPT = """你是购物决策助手,只做「决策 + 跳转」,不代下单、不碰支付。

你通过调用工具完成任务。每一步都要先看任务观测,再决定下一步做什么。

典型流程(不是死板顺序,按观测自行判断):
1. 品类未确定时:先 detect_category;识别到就 set_category 确认,
   识别不到就 ask_category_choice 请用户选择(调用后本轮结束,等用户回话)。
2. understand_requirement 把用户原话解析进需求档案。
3. 必答槽位缺失且信息不足以检索时,用 ask_clarifying_question 追问
   (调用后本轮结束)。已经追问过多轮就不要再问,直接检索。
4. search_candidates 做多平台检索、同款对齐、到手价计算与打分。
5. 候选为 0 或过少时,用 relax_constraints 放宽预算/品牌/最低规格,再重新检索。
6. 洗发水、食品这类有配料表的品类,调 analyze_ingredients 分析成分,
   结合用户健康档案(get_user_profile)判断利弊。
7. 决策前用 refresh_prices_now 复核 Top 候选价格。
8. 最后调 compose_answer 给出结论:message 要说清推荐哪一款、为什么、
   比其他平台省多少、有什么代价。始终用简体中文。

原则:不要重复调用已经完成且状态未变的工具;拿不到实时价就如实说明,
绝不用旧价冒充。"""


class Decision:
    def __init__(self, *, final: str | None = None, tool_calls: list[dict] | None = None) -> None:
        self.final = final
        self.tool_calls = tool_calls or []

    @property
    def is_final(self) -> bool:
        return self.final is not None and not self.tool_calls


class LLMClient:
    """基类与工厂。实例方法 decide 由子类实现。"""

    async def decide(self, messages: list[dict], tools: list[dict], state: str) -> Decision:
        raise NotImplementedError


class MockClient(LLMClient):
    """离线策略决策器。

    不接 key 时替代真实 LLM:每一步读取任务观测(候选数、缺失槽位、
    品类是否确认、是否已分析成分等),再选下一个工具。与真实 LLM 走
    完全相同的工具接口和循环,区别只是「怎么选」由策略代码而非模型给出。
    """

    #: 一轮里最多追问几次,避免和用户来回拉锯
    MAX_CLARIFY_ROUNDS = 3
    #: 候选不足时最多逐级放宽几轮约束
    MAX_RELAX_ROUNDS = 3

    def __init__(self, ctx_getter) -> None:
        self._ctx_getter = ctx_getter

    async def decide(self, messages, tools, state):
        ctx = self._ctx_getter()
        task = ctx.task
        flow = ctx.flow
        done = flow.setdefault("done", set())
        text = flow.get("last_text", "")

        from ..catalog import registry

        # --- 1) 品类:先识别,再确认或问用户 ---
        if "detect" not in done:
            done.add("detect")
            return Decision(tool_calls=[
                {"name": "detect_category", "arguments": {"text": text}}
            ])

        detected = self._last_result(messages, "detect_category")
        if not task.category_set:
            target = (detected or {}).get("detected")
            if target:
                return Decision(tool_calls=[
                    {"name": "set_category", "arguments": {"category": target}}
                ])
            if "asked_category" not in done:
                done.add("asked_category")
                return Decision(tool_calls=[
                    {"name": "ask_category_choice", "arguments": {}}
                ])

        # 用户中途改口换品类
        target = (detected or {}).get("detected")
        if target and target != task.category:
            return Decision(tool_calls=[
                {"name": "set_category", "arguments": {"category": target}}
            ])

        # --- 2) 理解需求 ---
        if flow.get("understood_text") != text:
            flow["understood_text"] = text
            return Decision(tool_calls=[
                {"name": "understand_requirement", "arguments": {"text": text}}
            ])

        # --- 3) 槽位不足则追问(已问够就不再纠缠) ---
        missing = task.requirement.missing_slots()
        if (missing and not task.candidates
                and task.clarify_rounds < self.MAX_CLARIFY_ROUNDS):
            return Decision(tool_calls=[
                {"name": "ask_clarifying_question", "arguments": {}}
            ])

        # --- 4) 检索(需求变化后会重新检索) ---
        if flow.get("searched_text") != text:
            flow["searched_text"] = text
            return Decision(tool_calls=[
                {"name": "search_candidates",
                 "arguments": {"category": task.category, "text": text}}
            ])

        # --- 5) 候选太少 → 逐级放宽约束并重新检索 ---
        # 真实场景里一次放宽往往不够(例如预算离市场价差很远),
        # 因此按轮次递进放宽,直到拿到候选或用完额度。
        attempts = int(flow.get("relax_attempts", 0))
        if len(task.candidates) < 2 and attempts < self.MAX_RELAX_ROUNDS:
            flow["relax_attempts"] = attempts + 1
            args: dict[str, Any] = {}
            # 第一轮先松开最低规格,预算按档递增放宽
            if attempts == 0:
                args["clear_min_specs"] = True
            if task.requirement.budget_max:
                args["budget_factor"] = (1.35, 1.6, 2.0)[min(attempts, 2)]
            # 仍然一个候选都没有时,连品牌黑名单一起松开
            if not task.candidates and task.requirement.brand_deny:
                args["clear_brand_deny"] = True
            if not args:
                args["clear_min_specs"] = True
            flow["searched_text"] = None  # 迫使下一步重新检索
            return Decision(tool_calls=[
                {"name": "relax_constraints", "arguments": args}
            ])

        # --- 6) 有配料表的品类:看档案 + 分析成分 ---
        has_ingredient = bool(registry.get(task.category).ingredient_attribute)
        if has_ingredient and task.candidates:
            if "profile" not in done:
                done.add("profile")
                return Decision(tool_calls=[
                    {"name": "get_user_profile", "arguments": {}}
                ])
            if "analyzed" not in done:
                done.add("analyzed")
                return Decision(tool_calls=[
                    {"name": "analyze_ingredients", "arguments": {}}
                ])

        # --- 7) 决策前复核价格 ---
        if task.candidates and "refreshed" not in done:
            done.add("refreshed")
            return Decision(tool_calls=[
                {"name": "refresh_prices_now", "arguments": {"top_n": 5}}
            ])

        # --- 8) 收尾:自己组织结论文案 ---
        return Decision(tool_calls=[
            {"name": "compose_answer",
             "arguments": {
                 "message": self._conclude(task, flow.get("original_budget_max"))
             }}
        ])

    # ------------------------------------------------------------------

    def _last_result(self, messages: list[dict], tool_name: str) -> dict | None:
        """回看某个工具最近一次的返回(graph 以 JSON 回填)。"""
        import json
        for message in reversed(messages):
            if message.get("role") == "tool" and message.get("name") == tool_name:
                try:
                    value = json.loads(message.get("content") or "")
                except Exception:
                    return None
                return value if isinstance(value, dict) else None
        return None

    def _conclude(self, task, original_budget=None) -> str:
        """基于工具产出的结构化数据组织结论,而非直接套用模板摘要。"""
        from .serialize import build_report
        report = build_report(task)
        picks = report.get("picks") or []
        label = report.get("category_label") or "商品"
        if not picks:
            return (
                f"按你的条件暂时没找到合适的{label},"
                "可以放宽预算、去掉品牌限制或调整要求再看看。"
            )

        prefix = ""
        if original_budget:
            prefix = (
                f"按你说的 {original_budget} 元预算没有匹配到合适的{label},"
                f"我把范围适当放宽后再找的。"
            )

        top = picks[0]
        line = prefix + f"在 {len(task.candidates)} 款符合条件的{label}里,我推荐 {top['title']}"
        if top.get("platform") and top.get("final_price") is not None:
            line += f",{top['platform']} 到手 {top['final_price']:.0f} 元"
        line += "。"

        spread = top.get("price_spread") or {}
        if spread.get("saved", 0) > 0:
            line += (
                f"同款在 {spread['max_platform']} 要 {spread['max_price']:.0f} 元,"
                f"这里省 {spread['saved']:.0f} 元。"
            )

        reasons = (top.get("pros") or [])[:2]
        if reasons:
            line += "选它主要因为:" + ";".join(reasons) + "。"
        costs = (top.get("cons") or [])[:1]
        if costs:
            line += "要接受的代价是" + costs[0] + "。"

        if original_budget and top.get("final_price") is not None:
            over = top["final_price"] - original_budget
            if over > 0:
                line += f"要提醒的是,这比你原本的预算高出 {over:.0f} 元。"

        if top.get("needs_recheck"):
            line += "注意这个价格暂时没能实时确认,点进去前请再核对一下。"
        if len(picks) > 1:
            line += f"另外还留了 {len(picks) - 1} 个备选,可以对比着看。"
        return line


def _parse_arguments(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        import json
        try:
            return json.loads(raw)
        except Exception:
            return {}
    return {}


class OpenAICompatibleClient(LLMClient):
    """OpenAI / 火山方舟(OpenAI 兼容)。凭据只从环境变量读取。"""

    def __init__(self, *, api_key: str, base_url: str, model: str) -> None:
        if not api_key:
            raise ValueError("缺少 API Key:请设置 ARK_API_KEY 或 OPENAI_API_KEY 环境变量,不要写入文件")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def decide(self, messages, tools, state):
        import httpx

        from ..agent.toolkit import tool_schemas

        payload = {
            "model": self.model,
            "messages": messages,
            "tools": tool_schemas(),
            "tool_choice": "auto",
        }
        timeout = httpx.Timeout(60.0, connect=15.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            message = data["choices"][0]["message"]

            if message.get("tool_calls"):
                calls = [
                    {
                        "name": call["function"]["name"],
                        "arguments": _parse_arguments(call["function"].get("arguments", "")),
                    }
                    for call in message["tool_calls"]
                ]
                return Decision(tool_calls=calls)

            content = message.get("content") or ""
            return Decision(final=content)


def build_llm(ctx_getter) -> LLMClient:
    """根据环境变量构建客户端。默认 mock(不联网、不需 key)。"""
    provider = os.getenv("LLM_PROVIDER", "mock").lower()

    if provider in ("ark", "openai"):
        if provider == "ark":
            key = os.getenv("ARK_API_KEY")
            base = os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
            model = os.getenv("ARK_MODEL", "")
        else:
            key = os.getenv("OPENAI_API_KEY")
            base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
            model = os.getenv("OPENAI_MODEL", "")

        if not model:
            raise ValueError(
                f"LLM_PROVIDER={provider} 需要设置模型/接入点环境变量:"
                f"{'ARK_MODEL' if provider == 'ark' else 'OPENAI_MODEL'}"
            )
        return OpenAICompatibleClient(api_key=key, base_url=base, model=model)

    return MockClient(ctx_getter)