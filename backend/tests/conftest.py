"""测试隔离：长期记忆与用户档案都是进程级单例，需逐例重置。"""

from __future__ import annotations

import pytest

from app.harness.repository import reset_repository
from app.profile.store import profile_store
from app.profile.models import UserProfile


@pytest.fixture(autouse=True)
def _isolate_state():
    reset_repository()
    profile_store.save(UserProfile())
    yield
    reset_repository()
    profile_store.save(UserProfile())
