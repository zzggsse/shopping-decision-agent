"""用户档案存储。开发期内存实现,生产替换为数据库,接口不变。"""

from __future__ import annotations

from ..profile.models import UserProfile


class ProfileStore:
    def __init__(self) -> None:
        self._items: dict[str, UserProfile] = {"default": UserProfile()}

    def get(self, user_id: str = "default") -> UserProfile:
        return self._items.setdefault(user_id, UserProfile(user_id=user_id))

    def save(self, profile: UserProfile) -> UserProfile:
        self._items[profile.user_id] = profile
        return profile

    def add_condition(self, condition: str, user_id: str = "default") -> UserProfile:
        profile = self.get(user_id)
        if condition not in profile.conditions:
            profile.conditions.append(condition)
        return self.save(profile)

    def remove_condition(self, condition: str, user_id: str = "default") -> UserProfile:
        profile = self.get(user_id)
        if condition in profile.conditions:
            profile.conditions.remove(condition)
        return self.save(profile)


profile_store = ProfileStore()