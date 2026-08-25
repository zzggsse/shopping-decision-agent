"""Agent 工具接口(单文件)。

所有"能做的事"都在此登记为一个 Tool,LLM(或 mock 决策器)通过
execute_tool 调用。改业务逻辑只需动这个文件;graph 只负责循环与事件下发。

每个 Tool = JSON Schema(供 LLM 理解) + handler(Context, args)。
Context 持有本轮决策状态:task / profiles / adapters / flow。
"""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, field
from typing import Any, Callable

from ..ingredients import (
    analyze as analyze_ingredients,
    rules_for_profile,
)
from ..services import freshness, matching, pricing, ranking
from .extract import (
    adjust_weights,
    detect_category,
    next_question,
    parse_budget,
    parse_brands,
    parse_min_specs,
    parse_slots,
)
from .serialize import build_report, serialize as _serialize


@dataclass(slots=True)
class Context:
    task: Any  # ShoppingTask
    profiles: Any  # ProfileStore
    adapters: dict[str, Any]
    flow: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[[Context, dict[str, Any]], dict[str, Any]]


def _ok(result: Any) -> dict[str, Any]:
    return {"type": "tool_result", "result": result}


def _profile(ctx: Context):
    return ctx.profiles.get()


# ---------------------------------------------------------------------------
# 各工具实现
# ---------------------------------------------------------------------------


def _list_categories(ctx: Context, args: dict) -> dict:
    from ..catalog import registry
    return _ok([{"key": s.key, "label": s.label} for s in registry.all()])


def _category_schema(ctx: Context, args: dict) -> dict:
    from ..catalog import registry
    from .serialize import describe_category
    category = args.get("category") or ctx.task.category
    return _ok(describe_category(category))


async def _gather(ctx: Context, query) -> list:
    async def safe(adapter):
        try:
            return await asyncio.wait_for(adapter.search(query), timeout=8.0)
        except Exception:
            return []

    eligible = [
        adapter for name, adapter in ctx.adapters.items()
        if not adapter.supported_categories()
        or query.category in adapter.supported_categories()
    ]
    return [item for batch in await asyncio.gather(*(safe(a) for a in eligible)) for item in batch]


def _requirement_populated(requirement) -> bool:
    """需求档案里是否已有任何有效约束。"""
    return bool(
        requirement.budget_max
        or requirement.budget_min
        or requirement.slots
        or requirement.min_specs
        or requirement.brand_allow
        or requirement.brand_deny
    )


async def _search_candidates(ctx: Context, args: dict) -> dict:
    from ..catalog import registry

    task = ctx.task
    category = args.get("category") or task.category
    if ctx.flow.get("lock_category"):
        # 品类锁定时忽略参数里的品类,避免 worker 检索到别的品类
        category = task.category
    requirement = task.requirement

    # 需求解析主要由 understand_requirement 负责;此处不覆盖已有约束,
    # 否则会把 relax_constraints 放宽后的预算覆盖回用户最初说的数值。
    # 但工具应可独立调用:需求还是空的时候,就地兜底解析一次原文。
    text = args.get("text", "")
    if text and not _requirement_populated(requirement):
        lowered = text.lower()
        if budget := parse_budget(lowered):
            low, high = budget
            if low:
                requirement.budget_min = low
            if high:
                requirement.budget_max = high
        for key, value in parse_slots(lowered, category).items():
            requirement.slots.setdefault(key, value)
        for key, value in parse_min_specs(lowered, category).items():
            requirement.min_specs.setdefault(key, value)
        allow, deny = parse_brands(lowered, _known_brands(ctx, category))
        requirement.brand_allow = list(dict.fromkeys(requirement.brand_allow + allow))
        requirement.brand_deny = list(dict.fromkeys(requirement.brand_deny + deny))

    from ..adapters.base import SearchQuery
    query = SearchQuery(category=category, budget_min=requirement.budget_min,
                        budget_max=requirement.budget_max)
    raw_items = await _gather(ctx, query)
    groups = matching.align(raw_items)
    for group in groups:
        group.offers = [pricing.compute_final_price(o) for o in group.offers]
    kept = _constrain(task, groups, _profile(ctx))
    task.candidates = _rerank(task, kept, _profile(ctx))
    task.requirement = requirement
    freshness.mark_staleness(task.candidates)

    return _ok({
        "category": category,
        "offers_gathered": len(raw_items),
        "groups": len(task.candidates),
        "missing_slots": requirement.missing_slots(),
        "coverage": requirement.coverage(),
    })


def _ingredient_hard_filter(group, schema, profile):
    """档案 avoid 级规则做硬排除(例:坚果过敏排除含坚果食品)。"""
    if profile is None or not getattr(profile, "conditions", []):
        return None
    if not schema.ingredient_attribute:
        return None
    text = str(group.spec.get(schema.ingredient_attribute) or "")
    if not text:
        return None
    from ..ingredients import split_ingredients
    entries = {e.lower() for e in split_ingredients(text, schema.ingredient_separator)}
    candidates = set()
    for rule in schema.concern_rules:
        if rule.severity != "avoid" or rule.target != "ingredient":
            continue
        if not profile.has(rule.condition):
            continue
        for key in (rule.key,):
            candidates.add(key.lower().replace(" ", ""))
            knowledge = schema.ingredient_knowledge.get(key)
            if knowledge:
                for alias in knowledge.aliases:
                    candidates.add(alias.lower().replace(" ", ""))
    for entry in entries:
        base = entry.split("(", 1)[0].split("（", 1)[0].strip("()（）")
        if base.lower().replace(" ", "") in candidates:
            rule = next(
                (r for r in schema.concern_rules
                 if r.severity == "avoid" and r.target == "ingredient"
                 and profile.has(r.condition)),
                None,
            )
            return (rule.message if rule and rule.message
                    else f"含{base},不适合{profile.conditions}人群")
    return None


def _constrain(task, groups, profile):
    from ..catalog import registry
    requirement = task.requirement
    schema = registry.get(task.category)
    denied = {matching.normalize_brand(b) for b in requirement.brand_deny}
    kept = []
    for group in groups:
        if group.group_id in task.dropped_group_ids:
            continue
        reason = None
        if (f := _ingredient_hard_filter(group, schema, profile)) is not None:
            reason = f"档案禁忌:{f}"
        elif denied and matching.normalize_brand(group.spec.brand) in denied:
            reason = "命中品牌黑名单"
        elif group.best_price is None:
            reason = "全平台无有效报价"
        elif requirement.budget_max and group.best_price > requirement.budget_max * 1.1:
            reason = f"到手价 {group.best_price:.0f} 明显超预算"
        elif (
            requirement.budget_min
            and not requirement.budget_max
            and group.best_price < requirement.budget_min * 0.85
        ):
            reason = f"到手价 {group.best_price:.0f} 低于用户要求的下限"
        else:
            for key, minimum in requirement.min_specs.items():
                value = group.spec.get(key)
                if isinstance(value, (int, float)) and value < minimum * 0.85:
                    attr = schema.attribute(key)
                    label = attr.label if attr else key
                    reason = f"{label} {value:g} 明显低于要求 {minimum:g}"
                    break
        if reason:
            task.log("drop", f"{group.title}:{reason}")
            continue
        kept.append(group)
    return kept


def _rerank(task, groups, profile):
    from ..catalog import registry
    task.weights.model_copy(deep=True)
    weights = task.weights.model_copy(deep=True)
    for rule in rules_for_profile(registry.get(task.category), profile):
        if rule.severity == "boost" and rule.target == "dimension":
            weights.bump(rule.key, rule.weight_delta)
            task.log("profile", rule.message)
    task.scores = ranking.score_candidates(groups, weights, task.requirement, profile)
    order = {score.group_id: index for index, score in enumerate(task.scores)}
    return sorted(groups, key=lambda g: order.get(g.group_id, 999))


def _analyze_ingredients(ctx: Context, args: dict) -> dict:
    from ..catalog import registry
    schema = registry.get(ctx.task.category)
    if not schema.ingredient_attribute:
        return _ok({"analyzed": False, "reason": "该品类无配料表声明"})
    profile = _profile(ctx)
    for group in ctx.task.candidates:
        text = str(group.spec.get(schema.ingredient_attribute) or "")
        group.__dict__["_analysis"] = analyze_ingredients(text, schema, profile)
    return _ok({"analyzed": True})


async def _refresh_prices(ctx: Context, args: dict) -> dict:
    top_n = int(args.get("top_n", 5))
    failed = await freshness.refresh_top_candidates(ctx.task.candidates, ctx.adapters, top_n)
    profile = _profile(ctx)
    ctx.task.candidates = _rerank(ctx.task, ctx.task.candidates, profile)
    return _ok({"failed_platforms": failed})


def _get_profile(ctx: Context, args: dict) -> dict:
    return _ok({"conditions": _profile(ctx).conditions})


def _update_profile(ctx: Context, args: dict) -> dict:
    p = _profile(ctx)
    p.conditions = list(dict.fromkeys(args.get("conditions", [])))
    ctx.profiles.save(p)
    return _ok({"conditions": p.conditions})


async def _verify_price(ctx: Context, args: dict) -> dict:
    offer_id = args.get("offer_id", "")
    for group in ctx.task.candidates:
        for offer in group.offers:
            if offer.offer_id != offer_id:
                continue
            result = await freshness.verify_before_redirect(offer, ctx.adapters)
            result["redirect_url"] = f"{offer.url}?utm_source=shopping_agent&task={ctx.task.task_id}"
            return _ok(result)
    return _ok({"ok": False, "reason": "not_found", "message": "报价不存在"})


def _rerank_weights(ctx: Context, args: dict) -> dict:
    from ..catalog import registry
    schema = registry.get(ctx.task.category)
    valid = {d.key for d in schema.dimensions}
    for key, value in args.get("weights", {}).items():
        if key in valid:
            ctx.task.weights.values[key] = float(value)
    ctx.task.candidates = _rerank(ctx.task, ctx.task.candidates, _profile(ctx))
    return _ok({"candidates": _serialize(ctx.task), "report": build_report(ctx.task)})


def _drop(ctx: Context, args: dict) -> dict:
    ids = set(args.get("group_ids", []))
    for group in ctx.task.candidates:
        if group.group_id in ids:
            ctx.task.log("drop", f"用户手动排除 {group.title}")
    ctx.task.dropped_group_ids.extend(ids)
    ctx.task.candidates = [g for g in ctx.task.candidates if g.group_id not in ids]
    profile = _profile(ctx)
    ctx.task.scores = ranking.score_candidates(
        ctx.task.candidates, ctx.task.weights, ctx.task.requirement, profile
    )
    return _ok({"candidates": _serialize(ctx.task), "report": build_report(ctx.task)})


def _known_brands(ctx: Context, category: str) -> list[str]:
    brands: set[str] = set()
    for adapter in ctx.adapters.values():
        items = getattr(adapter, "_items", None)
        if not callable(items):
            continue
        try:
            for item in items(category):
                brands.add(item.spec.brand.lower())
        except Exception:
            continue
    return sorted(brands)


def _detect_category(ctx: Context, args: dict) -> dict:
    """从用户原文识别品类。识别不到就如实返回 None,由决策层决定是否询问。"""
    from ..catalog import registry
    text = args.get("text", "")
    detected = detect_category(text)
    if ctx.flow.get("lock_category"):
        # 多品类对比的 worker 里品类是外部指定的:原文含多个品类触发词,
        # 若让识别结果覆盖,几个 worker 会全部塌到同一个品类上。
        detected = ctx.task.category
    return _ok({
        "detected": detected,
        "current": ctx.task.category,
        "category_confirmed": ctx.task.category_set,
        "available": [{"key": s.key, "label": s.label} for s in registry.all()],
    })


def _set_category(ctx: Context, args: dict) -> dict:
    """确认/切换品类。切换会重置候选与权重。"""
    from ..catalog import registry
    from .serialize import describe_category
    category = args.get("category", "")
    if category not in registry.keys():
        return {"type": "tool_error", "result": f"未知品类:{category}"}
    task = ctx.task
    previous = task.category
    if ctx.flow.get("lock_category") and category != previous:
        # 品类被锁定(worker 模式),不切换,如实告知决策层
        task.category_set = True
        return _ok({
            "category": previous,
            "label": registry.get(previous).label,
            "switched_from": None,
            "switched": False,
            "locked": True,
            "note": f"当前会话品类已锁定为 {registry.get(previous).label},忽略切换到 {category} 的请求",
            "schema": describe_category(previous),
        })
    switched = category != previous
    if switched:
        task.switch_category(category)
    task.category_set = True
    return _ok({
        "category": category,
        "label": registry.get(category).label,
        "switched_from": previous if switched else None,
        "switched": switched,
        "schema": describe_category(category),
    })


def _ask_category(ctx: Context, args: dict) -> dict:
    """无法确定品类时,请用户从注册表里挑一个。"""
    from ..catalog import registry
    ctx.task.log("clarify", "未识别品类,请用户选择")
    return _ok({
        "question": args.get("question") or "你想买什么?可以直接说品类,也可以点下面选一个:",
        "categories": [{"key": s.key, "label": s.label} for s in registry.all()],
        "awaiting_user": True,
    })


def _understand_requirement(ctx: Context, args: dict) -> dict:
    """把用户原文解析进需求档案,并按隐含偏好微调权重。返回本轮识别到的信号。"""
    from .extract import extract as extract_requirement
    task = ctx.task
    text = args.get("text", "")
    requirement, signals = extract_requirement(
        text, task.requirement, _known_brands(ctx, task.category)
    )
    weights, weight_notes = adjust_weights(text, task.weights, task.category)
    task.requirement = requirement
    task.weights = weights
    if signals or weight_notes:
        task.log("understand", "; ".join(signals + weight_notes))
    return _ok({
        "signals": signals,
        "weight_notes": weight_notes,
        "missing_slots": requirement.missing_slots(),
        "coverage": requirement.coverage(),
        "budget_max": requirement.budget_max,
        "slots": dict(requirement.slots),
    })


def _ask_clarifying_question(ctx: Context, args: dict) -> dict:
    """针对某个缺失槽位追问。slot 省略时自动取下一个缺失项。"""
    from ..catalog import registry
    task = ctx.task
    requirement = task.requirement
    schema = registry.get(requirement.category)
    slot_key = args.get("slot")

    if slot_key:
        if slot_key == "budget":
            question = args.get("question") or f"你打算花多少钱买{schema.label}?"
            options = schema.budget_options
        else:
            slot = schema.slot(slot_key)
            if slot is None:
                return {"type": "tool_error", "result": f"{requirement.category} 无此槽位:{slot_key}"}
            question = args.get("question") or slot.question
            options = slot.options
    else:
        nxt = next_question(requirement)
        if nxt is None:
            return _ok({"asked": False, "reason": "槽位已齐全,无需追问"})
        slot_key, question, options = nxt
        question = args.get("question") or question

    # 跨品类横向对比时不追问:用户问的是"买哪一类",不是某一类的细节。
    # 这时缺失槽位应当留空由打分兜底,而不是把用户拦在追问上。
    if ctx.flow.get("no_clarify"):
        # 登记为已放弃,否则 missing_slots 一直报缺失,决策层会反复调本工具
        if slot_key not in requirement.waived_slots:
            requirement.waived_slots.append(slot_key)
        task.log("clarify", f"跳过追问 {slot_key}(跨品类对比模式)")
        return _ok({
            "asked": False,
            "reason": "跨品类对比模式下不追问,缺失槽位交给打分兜底",
            "slot": slot_key,
            "missing_slots": requirement.missing_slots(),
        })

    task.clarify_rounds += 1
    task.log("clarify", f"追问 {slot_key}(第 {task.clarify_rounds} 轮)")
    return _ok({
        "asked": True,
        "slot": slot_key,
        "question": question,
        "options": list(options),
        "coverage": requirement.coverage(),
        "clarify_rounds": task.clarify_rounds,
        "awaiting_user": True,
    })


def _relax_constraints(ctx: Context, args: dict) -> dict:
    """候选太少时放宽约束:上调预算上限 / 清空品牌黑名单 / 清除最低规格。"""
    task = ctx.task
    requirement = task.requirement
    changed: list[str] = []

    factor = float(args.get("budget_factor", 0) or 0)
    if factor and requirement.budget_max:
        before = requirement.budget_max
        # 记录用户最初的预算,结论里必须如实说明超支,不能悄悄放宽
        ctx.flow.setdefault("original_budget_max", before)
        requirement.budget_max = int(round(before * factor))
        changed.append(f"预算上限 {before} → {requirement.budget_max}")

    if args.get("clear_brand_deny") and requirement.brand_deny:
        changed.append(f"取消品牌排除:{'、'.join(requirement.brand_deny)}")
        requirement.brand_deny = []

    if args.get("clear_min_specs") and requirement.min_specs:
        changed.append("取消最低规格限制")
        requirement.min_specs = {}

    if changed:
        task.log("relax", "放宽约束:" + "; ".join(changed))
    return _ok({"changed": changed, "budget_max": requirement.budget_max})


def _compose_answer(ctx: Context, args: dict) -> dict:
    """产出面向用户的最终结论。传入 message 则用它,否则回退到模板摘要。"""
    task = ctx.task
    report = build_report(task)
    original = ctx.flow.get("original_budget_max")
    if original:
        report["original_budget_max"] = original
    message = (args.get("message") or "").strip()
    if message:
        report["summary"] = message
    task.log("conclude", "产出决策结论")
    return _ok({"report": report, "final": True})


# ---------------------------------------------------------------------------
# 注册表
# ---------------------------------------------------------------------------

TOOLS: list[Tool] = [
    Tool("list_categories", "列出当前支持的购物品类。",
         {"type": "object", "properties": {}}, _list_categories),
    Tool("get_category_schema", "获取某品类的槽位、维度、预算档位等配置。",
         {"type": "object", "properties": {"category": {"type": "string"}},
          "required": ["category"]}, _category_schema),
    Tool("search_candidates",
         "在多个平台检索候选商品,做同款对齐、到手价计算并打分(多平台比价+个性化排序)。",
         {"type": "object", "properties": {
             "category": {"type": "string"},
             "text": {"type": "string", "description": "用户需求原文,含预算/用途/槽位"}},
          "required": ["category", "text"]}, _search_candidates),
    Tool("analyze_ingredients",
         "对候选商品做配料表/营养成分分析(仅洗发水/食品等含配料表的品类有意义)。",
         {"type": "object", "properties": {}}, _analyze_ingredients),
    Tool("refresh_prices_now",
         "对 TopN 候选做实时价格复核,确保决策价格最新。",
         {"type": "object", "properties": {"top_n": {"type": "integer"}}}, _refresh_prices),
    Tool("get_user_profile", "获取用户健康与偏好档案条件。",
         {"type": "object", "properties": {}}, _get_profile),
    Tool("update_user_profile", "更新用户健康与偏好档案条件。",
         {"type": "object", "properties": {
             "conditions": {"type": "array", "items": {"type": "string"}}},
          "required": ["conditions"]}, _update_profile),
    Tool("verify_price_before_redirect",
         "用户点击购买前校验价格并返回真实跳转链接。",
         {"type": "object", "properties": {"offer_id": {"type": "string"}},
          "required": ["offer_id"]}, _verify_price),
    Tool("rerank_with_weights", "按用户偏好权重重新排序候选。",
         {"type": "object", "properties": {
             "weights": {"type": "object", "description": "维度->权重,需为本品类有效维度"}}},
         _rerank_weights),
    Tool("detect_category",
         "从用户原话里识别购物品类。识别不到会返回 detected=None 和可选品类清单。",
         {"type": "object", "properties": {
             "text": {"type": "string", "description": "用户原话"}},
          "required": ["text"]}, _detect_category),
    Tool("set_category", "确认或切换当前品类(切换会重置候选与权重)。",
         {"type": "object", "properties": {"category": {"type": "string"}},
          "required": ["category"]}, _set_category),
    Tool("ask_category_choice", "无法确定用户想买什么时,请用户从品类清单里选择。",
         {"type": "object", "properties": {"question": {"type": "string"}}},
         _ask_category),
    Tool("understand_requirement",
         "把用户原话解析进需求档案(预算/用途/槽位/品牌/最低规格),并按隐含偏好微调权重。",
         {"type": "object", "properties": {
             "text": {"type": "string", "description": "用户原话"}},
          "required": ["text"]}, _understand_requirement),
    Tool("ask_clarifying_question",
         "就某个缺失的必答槽位向用户追问。slot 省略则自动取下一个缺失项;"
         "可用 question 覆盖默认话术。调用后应结束本轮,等用户回答。",
         {"type": "object", "properties": {
             "slot": {"type": "string", "description": "槽位 key,可省略"},
             "question": {"type": "string", "description": "自定义追问话术,可省略"}}},
         _ask_clarifying_question),
    Tool("relax_constraints",
         "候选太少或全被过滤时放宽约束,然后应重新 search_candidates。",
         {"type": "object", "properties": {
             "budget_factor": {"type": "number", "description": "预算上限乘数,如 1.3"},
             "clear_brand_deny": {"type": "boolean"},
             "clear_min_specs": {"type": "boolean"}}},
         _relax_constraints),
    Tool("compose_answer",
         "给出最终结论并结束本轮。message 为面向用户的自然语言结论(建议自己组织,"
         "说明为什么推荐它、比其他平台省多少、有什么代价);省略则用模板摘要兜底。",
         {"type": "object", "properties": {
             "message": {"type": "string", "description": "面向用户的结论文案"}}},
         _compose_answer),
    Tool("drop_candidates", "把用户明确不要的候选排除。",
         {"type": "object", "properties": {
             "group_ids": {"type": "array", "items": {"type": "string"}}},
          "required": ["group_ids"]}, _drop),
]


def tool_by_name(name: str) -> Tool | None:
    return next((t for t in TOOLS if t.name == name), None)


def tool_schemas() -> list[dict[str, Any]]:
    return [
        {"type": "function", "function": {
            "name": t.name, "description": t.description, "parameters": t.parameters}}
        for t in TOOLS
    ]


async def execute_tool(ctx: Context, name: str, args: dict[str, Any]) -> dict[str, Any]:
    tool = tool_by_name(name)
    if tool is None:
        return {"type": "tool_error", "result": f"未知工具:{name}"}
    try:
        result = tool.handler(ctx, args or {})
        if inspect.isawaitable(result):
            result = await result
        return result
    except Exception as exc:
        return {"type": "tool_error", "result": f"工具 {name} 执行失败:{exc}"}