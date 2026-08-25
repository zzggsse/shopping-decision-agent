"""配置。DATA_SOURCE_MODE 决定 mock(开发) / live(生产)。"""

from __future__ import annotations

import os
from dataclasses import dataclass

from .env import load_local_env

# 必须在读任何 os.getenv 之前加载，否则 local.env 里的值不生效
load_local_env()


@dataclass(slots=True)
class Settings:
    #: mock = 本地 fixture,仅开发/CI;live = 真实 API + 爬虫
    data_source_mode: str = os.getenv("DATA_SOURCE_MODE", "mock")
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")

    @property
    def is_live(self) -> bool:
        return self.data_source_mode == "live"


settings = Settings()
