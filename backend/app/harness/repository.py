"""Postgres 持久化仓储。

设计取舍:
  - 只有配了 DATABASE_URL 才启用;否则自动降级内存实现,
    保证 start.bat 双击即用、CI 无需数据库。
  - 用 asyncpg 直连,不引入 ORM。表结构简单,ORM 的迁移与元类复杂度不划算。
  - 连接失败不让应用崩:降级内存并在 /api/health 暴露真实后端,
    避免用户以为数据存住了其实没存。

环境变量:
  DATABASE_URL=postgresql://user:password@host:5432/dbname
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from .memory import InMemoryRepository, MemoryItem

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS user_memory (
    user_id     TEXT        NOT NULL,
    kind        TEXT        NOT NULL,
    value       TEXT        NOT NULL,
    confidence  REAL        NOT NULL DEFAULT 1.0,
    evidence    TEXT        NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, kind, value)
);

CREATE TABLE IF NOT EXISTS shopping_task (
    task_id     TEXT        PRIMARY KEY,
    user_id     TEXT        NOT NULL DEFAULT 'default',
    category    TEXT,
    state       TEXT,
    payload     JSONB       NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS conversation_turn (
    id          BIGSERIAL   PRIMARY KEY,
    task_id     TEXT        NOT NULL,
    role        TEXT        NOT NULL,
    content     TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_turn_task ON conversation_turn (task_id, id);
"""


class PostgresRepository:
    """长期记忆的 Postgres 实现,满足 MemoryRepository 协议。

    协议是同步的(load/save)而 asyncpg 是异步的,这里用
    「进程内缓存 + 异步回写」桥接:读走缓存,写触发后台任务。
    上层不必全链路 async 化,请求路径也不会被数据库阻塞。
    """

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self._pool: Any = None
        self._cache: dict[str, list[MemoryItem]] = {}
        self._ready = False
        self._pending: set[Any] = set()

    async def connect(self) -> None:
        """建连并建表。失败抛出,由 build_repository 决定是否降级。"""
        import asyncpg
        self._pool = await asyncpg.create_pool(
            self.dsn, min_size=1, max_size=5, timeout=10, command_timeout=10
        )
        async with self._pool.acquire() as conn:
            await conn.execute(SCHEMA)
        self._ready = True
        logger.info("Postgres 已连接,记忆将持久化")

    async def close(self) -> None:
        for task in list(self._pending):
            task.cancel()
        if self._pool is not None:
            await self._pool.close()
        self._ready = False

    @property
    def ready(self) -> bool:
        return self._ready

    async def load_async(self, user_id: str) -> list[MemoryItem]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT kind, value, confidence, evidence, created_at"
                " FROM user_memory WHERE user_id = $1 ORDER BY created_at",
                user_id,
            )
        items = [
            MemoryItem(kind=r["kind"], value=r["value"],
                       confidence=r["confidence"], evidence=r["evidence"],
                       created_at=r["created_at"])
            for r in rows
        ]
        self._cache[user_id] = items
        return list(items)

    def load(self, user_id: str) -> list[MemoryItem]:
        """同步读走缓存;未命中则触发后台预热。"""
        if user_id not in self._cache and self._ready:
            self._schedule(self.load_async(user_id))
        return list(self._cache.get(user_id, []))

    async def save_async(self, user_id: str, items: list[MemoryItem]) -> None:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "DELETE FROM user_memory WHERE user_id = $1", user_id
                )
                if items:
                    await conn.executemany(
                        "INSERT INTO user_memory"
                        " (user_id, kind, value, confidence, evidence, created_at)"
                        " VALUES ($1, $2, $3, $4, $5, $6)",
                        [(user_id, i.kind, i.value, i.confidence,
                          i.evidence, i.created_at) for i in items],
                    )

    def save(self, user_id: str, items: list[MemoryItem]) -> None:
        """同步写:更新缓存 + 异步回写。"""
        self._cache[user_id] = list(items)
        if self._ready:
            self._schedule(self.save_async(user_id, list(items)))

    def _schedule(self, coro) -> None:
        """把协程交给当前事件循环;无循环(同步脚本)则直接跑完。"""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            try:
                asyncio.run(coro)
            except Exception as error:
                logger.warning("记忆持久化失败:%s", error)
            return
        task = loop.create_task(self._guard(coro))
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    @staticmethod
    async def _guard(coro) -> None:
        """持久化失败不影响用户当前请求,只记警告。"""
        try:
            await coro
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.warning("记忆持久化失败:%s", error)


_repository: Any = None
_backend = "memory"


async def build_repository() -> Any:
    """按 DATABASE_URL 构建仓储。未配置或连不上则降级内存。"""
    global _repository, _backend
    dsn = os.getenv("DATABASE_URL", "").strip()

    if not dsn:
        _repository = InMemoryRepository()
        _backend = "memory"
        logger.info("未配置 DATABASE_URL,记忆仅存于内存(重启丢失)")
        return _repository

    candidate = PostgresRepository(dsn)
    try:
        await candidate.connect()
    except Exception as error:
        logger.warning("Postgres 连接失败,降级内存存储:%s", error)
        _repository = InMemoryRepository()
        _backend = "memory (postgres unavailable)"
        return _repository

    _repository = candidate
    _backend = "postgres"
    return _repository


def repository() -> Any:
    """取当前仓储。未初始化则先给内存实现,避免调用方判空。"""
    global _repository
    if _repository is None:
        _repository = InMemoryRepository()
    return _repository


def reset_repository() -> None:
    """清空当前仓储单例，供测试与评测隔离使用。"""
    global _repository, _backend
    _repository = InMemoryRepository()
    _backend = "memory"


def backend_name() -> str:
    """当前存储后端,供 /api/health 如实告知。"""
    return _backend


async def shutdown_repository() -> None:
    global _repository
    if isinstance(_repository, PostgresRepository):
        await _repository.close()
