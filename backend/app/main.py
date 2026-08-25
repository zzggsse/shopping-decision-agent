"""应用入口。"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router
from .harness.repository import build_repository, shutdown_repository
from .config import settings

@asynccontextmanager
async def lifespan(_: FastAPI):
    """启动时接记忆仓储，关闭时收尾。

    没配 DATABASE_URL 或连不上 Postgres 都不会阻断启动，
    而是降级到内存并在 /api/health 里如实告知。
    """
    await build_repository()
    try:
        yield
    finally:
        await shutdown_repository()


app = FastAPI(
    title="购物决策 Agent 助手",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "laptop-shopping-agent", "docs": "/docs"}
