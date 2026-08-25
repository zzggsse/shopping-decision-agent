"""Few-shot 对照实现:可切换的示例注入。

默认不启用(USE_FEW_SHOT=1 打开)。

为什么默认不用(README 第 5 章有完整论证,这里说代码层面的理由):
  1. function calling 的 JSON Schema 在**解码层**约束模型输出,
     few-shot 只是在 prompt 里"请求"模型照做 —— 后者更弱
  2. 六品类 × 各种表达方式,几个示例覆盖不了,
     反而容易让模型把后续输入往示例出现过的品类上靠
  3. 每次请求固定多花 token(实测见 estimate 函数)

那什么时候该打开:
  - 换了不支持 function calling 的模型,只能靠文本约束输出格式
  - 发现某个模型总是漏掉某个步骤(如从不调用 refresh_prices_now)

示例的选择原则:
  只放**决策路径**的示例,不放具体品类的商品知识 ——
  品类知识属于 app/catalog/ 的职责,塞进 prompt 会造成两处维护。
"""

from __future__ import annotations

from typing import Any

#: 每条示例演示一种决策模式,刻意跨品类以避免把模型带偏到单一品类
FEW_SHOT_EXAMPLES: list[dict[str, Any]] = [
    {
        "note": "品类明确 + 需求完整 -> 直接检索,不要多余追问",
        "user": "想买个 5000 左右的轻薄本,主要写代码,经常带出门",
        "calls": [
            {"name": "detect_category", "arguments": {"text": "轻薄本"}},
            {"name": "understand_requirement",
             "arguments": {"text": "5000 左右 写代码 经常带出门"}},
            {"name": "search_candidates", "arguments": {}},
        ],
    },
    {
        "note": "品类不明 -> 必须先问品类,不许假设默认品类",
        "user": "帮我推荐点东西",
        "calls": [
            {"name": "detect_category", "arguments": {"text": "帮我推荐点东西"}},
            {"name": "ask_category_choice", "arguments": {}},
        ],
    },
    {
        "note": "候选为 0 -> 先放宽再重新检索,并在结论里如实告知超预算",
        "user": "1000 块的游戏本",
        "calls": [
            {"name": "understand_requirement", "arguments": {"text": "1000 块 游戏本"}},
            {"name": "search_candidates", "arguments": {}},
            {"name": "relax_constraints", "arguments": {"reason": "候选为空"}},
            {"name": "search_candidates", "arguments": {}},
        ],
    },
    {
        "note": "有配料表的品类 -> 分析成分并结合健康档案",
        "user": "敏感头皮用什么洗发水,100 以内",
        "calls": [
            {"name": "detect_category", "arguments": {"text": "洗发水"}},
            {"name": "understand_requirement",
             "arguments": {"text": "敏感头皮 100 以内"}},
            {"name": "search_candidates", "arguments": {}},
            {"name": "get_user_profile", "arguments": {}},
            {"name": "analyze_ingredients", "arguments": {}},
        ],
    },
]


def render_examples() -> str:
    """把示例渲染成可追加到系统提示后的文本。"""
    blocks = []
    for index, example in enumerate(FEW_SHOT_EXAMPLES, 1):
        calls = "\n".join(
            f"     {i}. {call['name']}({_brief(call['arguments'])})"
            for i, call in enumerate(example["calls"], 1)
        )
        blocks.append(
            f"示例 {index}（{example['note']}）\n"
            f"   用户:{example['user']}\n"
            f"   工具调用顺序:\n{calls}"
        )
    return "\n\n".join(blocks)


def _brief(arguments: dict) -> str:
    if not arguments:
        return ""
    items = [f'{k}="{v}"' if isinstance(v, str) else f"{k}={v}"
             for k, v in arguments.items()]
    return ", ".join(items)


def augment_prompt(base_prompt: str) -> str:
    """在系统提示后追加 few-shot 示例。"""
    return (
        f"{base_prompt}\n\n"
        "以下是几个决策示例,只用于说明工具调用的节奏,"
        "不要把示例里的品类或价格当成用户的真实需求:\n\n"
        f"{render_examples()}"
    )


def estimate_overhead() -> int:
    """估算打开 few-shot 后每次请求多花的 token,用于如实上报成本。"""
    from ..harness.context import estimate_tokens

    return estimate_tokens(render_examples())
