"""FastAPI 路由:品类 + 对话(SSE 流式)+ 任务 + 候选池 + 跳转校验。"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..adapters.base import create_adapters
from ..agent import extract
from ..agent.graph import ShoppingAgent
from ..agent.serialize import (
    build_report,
    describe_category,
    serialize as _serialize,
)
from ..catalog import registry
from ..config import settings
from ..domain.models import ChatMessage, Weights
from ..profile import UserProfile, profile_store
from ..services import freshness, ranking
from ..services.store import store

router = APIRouter(prefix="/api")
adapters = create_adapters(settings.data_source_mode)
agent = ShoppingAgent(adapters)


class ChatRequest(BaseModel):
    message: str
    task_id: str | None = None
    slot: str | None = None
    option: str | None = None
    #: 前端显式指定品类(如从品类选择器进入)
    category: str | None = None


class WeightsRequest(BaseModel):
    weights: dict[str, float]


class DropRequest(BaseModel):
    group_ids: list[str]


def sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "data_source_mode": settings.data_source_mode,
        "realtime": settings.is_live,
        "platforms": sorted(adapters),
        "categories": registry.keys(),
    }


@router.get("/categories")
async def list_categories() -> list[dict[str, Any]]:
    """前端品类选择器与动态渲染的数据来源。"""
    return [
        {
            **describe_category(schema.key),
            "triggers": schema.triggers,
            "platforms": sorted(
                name
                for name, adapter in adapters.items()
                if not adapter.supported_categories()
                or schema.key in adapter.supported_categories()
            ),
        }
        for schema in registry.all()
    ]


class ProfileUpdate(BaseModel):
    conditions: list[str]
    display_name: str = ""
    notes: str = ""


# 所有可选条件及其说明,供前端渲染开关
PROFILE_CONDITIONS: dict[str, dict[str, str]] = {
    "diabetes": {"label": "糖尿病", "group": "健康状况", "hint": "食品优先低糖/无糖,标注添加糖"},
    "hypertension": {"label": "高血压", "group": "健康状况", "hint": "食品标注高钠与饱和脂肪"},
    "nut_allergy": {"label": "坚果过敏", "group": "过敏/禁忌", "hint": "含坚果成分会被明确标红禁用"},
    "pregnant": {"label": "孕期/备孕", "group": "健康状况", "hint": "洗发水标注水杨酸等慎用成分"},
    "sensitive_scalp": {"label": "敏感头皮", "group": "个护", "hint": "洗发水优先氨基酸,标注 SLS"},
    "sulfate_allergy": {"label": "硫酸盐过敏", "group": "过敏/禁忌", "hint": "含硫酸盐表活会被标红"},
    "fitness": {"label": "健身/高蛋白", "group": "生活方式", "hint": "食品偏好高蛋白、高纤维"},
    "gaming": {"label": "游戏重度", "group": "生活方式", "hint": "电脑/手机更看重性能维度"},
}


@router.get("/profile")
async def get_profile() -> dict[str, Any]:
    profile = profile_store.get()
    return {
        "profile": profile.model_dump(mode="json"),
        "conditions_meta": PROFILE_CONDITIONS,
    }


@router.put("/profile")
async def update_profile(payload: ProfileUpdate) -> dict[str, Any]:
    invalid = set(payload.conditions) - set(PROFILE_CONDITIONS)
    if invalid:
        raise HTTPException(400, f"未知条件:{sorted(invalid)}")
    profile = profile_store.get()
    profile.conditions = payload.conditions
    profile.display_name = payload.display_name
    profile.notes = payload.notes
    profile_store.save(profile)
    return {"profile": profile.model_dump(mode="json")}


@router.post("/chat/stream")
async def chat_stream(payload: ChatRequest) -> StreamingResponse:
    task = store.get_or_create(payload.task_id)
    store.append_message(task.task_id, ChatMessage(role="user", content=payload.message))

    if payload.category and registry.has(payload.category):
        task.switch_category(payload.category)
        task.category_set = True

    # 前端快捷选项点击:直接写槽位,不依赖自由文本解析
    if payload.slot and payload.option:
        task.requirement = extract.apply_quick_option(
            payload.slot, payload.option, task.requirement
        )

    async def stream():
        yield sse({
            "type": "task_created",
            "task_id": task.task_id,
            "category": task.category,
            "schema": describe_category(task.category),
        })
        try:
            async for event in agent.handle_message(task, payload.message):
                yield sse(event)
        except Exception as error:  # 保证前端不会卡在 loading
            yield sse({"type": "error", "message": f"处理失败:{error}"})
        finally:
            store.save(task)
            yield sse({"type": "done"})

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/tasks")
async def list_tasks() -> list[dict[str, Any]]:
    """任务列表,支持用户回来续上未完成的购物决策。"""
    return [
        {
            "task_id": task.task_id,
            "category": task.category,
            "category_label": registry.get(task.category).label,
            "state": task.state.value,
            "candidate_count": len(task.candidates),
            "requirement": task.requirement.model_dump(exclude_none=True),
            "updated_at": task.updated_at.isoformat(),
        }
        for task in store.list_tasks()
    ]


@router.get("/tasks/{task_id}")
async def get_task(task_id: str) -> dict[str, Any]:
    """完整还原决策上下文:品类、需求、候选、权重、时间线。"""
    task = store.get(task_id)
    if task is None:
        raise HTTPException(404, "任务不存在")
    freshness.mark_staleness(task.candidates)
    return {
        "task_id": task.task_id,
        "category": task.category,
        "schema": describe_category(task.category),
        "state": task.state.value,
        "requirement": task.requirement.model_dump(),
        "weights": task.weights.values,
        "candidates": _serialize(task),
        "report": build_report(task) if task.candidates else None,
        "decision_log": [entry.model_dump(mode="json") for entry in task.decision_log],
        "messages": [msg.model_dump(mode="json") for msg in store.history(task_id)],
    }


@router.post("/tasks/{task_id}/weights")
async def update_weights(task_id: str, payload: WeightsRequest) -> dict[str, Any]:
    """权重滑块实时重排:纯本地计算,毫秒级返回。"""
    task = store.get(task_id)
    if task is None:
        raise HTTPException(404, "任务不存在")

    schema = registry.get(task.category)
    valid = {d.key for d in schema.dimensions}
    unknown = set(payload.weights) - valid
    if unknown:
        raise HTTPException(400, f"该品类不存在这些维度:{sorted(unknown)}")

    task.weights = Weights(values={**task.weights.values, **payload.weights})
    task.scores = ranking.score_candidates(task.candidates, task.weights, task.requirement)
    order = {score.group_id: index for index, score in enumerate(task.scores)}
    task.candidates.sort(key=lambda group: order.get(group.group_id, 999))
    task.log("reweight", f"用户调整权重:{task.weights.normalized()}")
    store.save(task)

    return {"candidates": _serialize(task), "report": build_report(task)}


@router.post("/tasks/{task_id}/drop")
async def drop_candidates(task_id: str, payload: DropRequest) -> dict[str, Any]:
    """用户手动排除候选,走 REFINE 语义,记入时间线。"""
    task = store.get(task_id)
    if task is None:
        raise HTTPException(404, "任务不存在")

    dropped = set(payload.group_ids)
    for group in task.candidates:
        if group.group_id in dropped:
            task.log("drop", f"用户手动排除 {group.title}")

    task.dropped_group_ids.extend(dropped)
    task.candidates = [g for g in task.candidates if g.group_id not in dropped]
    task.scores = ranking.score_candidates(task.candidates, task.weights, task.requirement)
    store.save(task)

    return {"candidates": _serialize(task), "report": build_report(task)}


@router.post("/tasks/{task_id}/refresh")
async def refresh_prices(task_id: str, top_n: int = 5) -> dict[str, Any]:
    """手动刷新:对应前端价格置灰后的"立即刷新"按钮。"""
    task = store.get(task_id)
    if task is None:
        raise HTTPException(404, "任务不存在")

    failed = await freshness.refresh_top_candidates(task.candidates, adapters, top_n)
    task.scores = ranking.score_candidates(task.candidates, task.weights, task.requirement)
    store.save(task)
    return {"candidates": _serialize(task), "failed_platforms": failed}


@router.post("/tasks/{task_id}/redirect/{offer_id}")
async def redirect_check(task_id: str, offer_id: str) -> dict[str, Any]:
    """跳转前二次校验:价格偏差超阈值则要求用户确认。"""
    task = store.get(task_id)
    if task is None:
        raise HTTPException(404, "任务不存在")

    for group in task.candidates:
        for offer in group.offers:
            if offer.offer_id != offer_id:
                continue
            result = await freshness.verify_before_redirect(offer, adapters)
            task.log("redirect", f"跳转校验 {offer.platform}:{result['reason']}")
            store.save(task)
            # 只做决策+跳转:附联盟参数,不代下单、不碰支付
            result["redirect_url"] = f"{offer.url}?utm_source=shopping_agent&task={task_id}"
            return result

    raise HTTPException(404, "报价不存在")