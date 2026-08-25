"""任务存储。开发期用内存实现,生产替换为 Postgres 仓储,接口不变。"""

from __future__ import annotations

import uuid

from ..domain.models import ChatMessage, ShoppingTask


class TaskStore:
    def __init__(self) -> None:
        self._tasks: dict[str, ShoppingTask] = {}
        self._history: dict[str, list[ChatMessage]] = {}

    def create(self) -> ShoppingTask:
        task = ShoppingTask(task_id=uuid.uuid4().hex[:12])
        self._tasks[task.task_id] = task
        self._history[task.task_id] = []
        return task

    def get(self, task_id: str) -> ShoppingTask | None:
        return self._tasks.get(task_id)

    def get_or_create(self, task_id: str | None) -> ShoppingTask:
        if task_id and (task := self._tasks.get(task_id)):
            return task
        return self.create()

    def save(self, task: ShoppingTask) -> None:
        self._tasks[task.task_id] = task

    def list_tasks(self) -> list[ShoppingTask]:
        return sorted(self._tasks.values(), key=lambda t: t.updated_at, reverse=True)

    def append_message(self, task_id: str, message: ChatMessage) -> None:
        self._history.setdefault(task_id, []).append(message)

    def history(self, task_id: str) -> list[ChatMessage]:
        return self._history.get(task_id, [])


store = TaskStore()
