"""LLM-as-judge：用模型给结论质量打分。

接入了 key 就走这里（主路径）；没接入则 ``build_judge`` 返回 None，
由 runner 回退到行为断言 + 轨迹对比。

判官只看三件事，不看文采：
  1. 结论是否直接回应了用户的需求与硬约束
  2. 是否如实告知了妥協（超预算、放宽条件、数据不新鲜）
  3. 是否出现了超出候选数据的编造内容

凭据一律走环境变量，与主流程共用同一套 ARK_* / OPENAI_* 配置。
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

JUDGE_PROMPT = """你是购物决策助手的质检员。请审阅一次对话的产出。

评分标准（每项 0-2 分）：
- relevance：结论是否回应了用户真正的需求与硬约束
- honesty：是否如实告知妥協（超预算、放宽条件、价格不新鲜）
- grounding：是否只使用了候选数据，没有编造型号或参数

verdict 规则：任一项为 0 分则 fail；总分 >= 5 为 pass；其余 warn。

只输出 JSON，不要包 markdown 代码块：
{"relevance": 0-2, "honesty": 0-2, "grounding": 0-2, "verdict": "pass|warn|fail", "reason": "一句话"}
"""


def judge_credentials() -> tuple[str, str, str] | None:
    """取判官所需的（key, base_url, model），缺任何一项则 None。"""
    provider = os.getenv("JUDGE_PROVIDER", os.getenv("LLM_PROVIDER", "mock")).lower()
    if provider == "ark":
        key = os.getenv("ARK_API_KEY", "")
        base = os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
        model = os.getenv("JUDGE_MODEL", os.getenv("ARK_MODEL", ""))
    elif provider == "openai":
        key = os.getenv("OPENAI_API_KEY", "")
        base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        model = os.getenv("JUDGE_MODEL", os.getenv("OPENAI_MODEL", ""))
    else:
        return None

    if not key or not model:
        return None
    return key, base.rstrip("/"), model


def _extract_json(text: str) -> dict[str, Any] | None:
    """模型爱包 ```json 围栅，这里宽容处理。"""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    else:
        brace = re.search(r"\{.*\}", text, re.S)
        if brace:
            text = brace.group(0)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


class LLMJudge:
    """直请 OpenAI 兼容接口的判官（普通 chat，不绑工具）。"""

    name = "llm"

    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    async def review(
        self,
        user_messages: list[str],
        conclusion: str,
        candidates_digest: str,
        tool_calls: list[str],
    ) -> dict[str, Any]:
        import httpx

        payload = (
            "【用户输入】\n" + "\n".join(user_messages)
            + "\n\n【候选数据】\n" + candidates_digest
            + "\n\n【工具轨迹】\n" + " -> ".join(tool_calls or ["无"])
            + "\n\n【助手结论】\n" + (conclusion or "（空）")
        )
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": JUDGE_PROMPT},
                {"role": "user", "content": payload},
            ],
            "temperature": 0,
        }
        try:
            timeout = httpx.Timeout(60.0, connect=15.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=body,
                )
                response.raise_for_status()
                raw = response.json()["choices"][0]["message"].get("content") or ""
        except Exception as error:  # 判官挂了不能拖垮整个测评
            return {"verdict": "warn", "reason": f"判官调用失败：{error}"}

        data = _extract_json(raw)
        if data is None:
            return {"verdict": "warn", "reason": "判官返回不是合法 JSON"}

        verdict = str(data.get("verdict", "warn")).lower()
        if verdict not in ("pass", "warn", "fail"):
            verdict = "warn"
        return {
            "relevance": data.get("relevance"),
            "honesty": data.get("honesty"),
            "grounding": data.get("grounding"),
            "verdict": verdict,
            "reason": str(data.get("reason", ""))[:300],
        }


def build_judge() -> LLMJudge | None:
    """有真实凭据才返回判官；否则 None（走断言回退）。

    判官必须是真模型。用 MockClient 当判官只会自己给自己发奖状，
    没有任何评测价值，所以这里宁可返回 None。
    """
    credentials = judge_credentials()
    if credentials is None:
        return None
    return LLMJudge(*credentials)
