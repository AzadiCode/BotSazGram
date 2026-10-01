"""ریپازیتوری نشست‌ها — وضعیت موقت کاربر در یک ربات.

نشست می‌گوید کاربر در کدام نود است و دادهٔ موقت مکالمه (temp) چیست.
انقضای نشست با expires (epoch) کنترل می‌شود.
"""
from __future__ import annotations

from typing import Any, Optional

from app.db.base import Storage


class SessionRepo:
    def __init__(self, storage: Storage) -> None:
        self._s = storage

    def get(self, bot_id: str, uid: int) -> Optional[dict]:
        return self._s.session_get(bot_id, uid)

    def set(
        self,
        bot_id: str,
        uid: int,
        node_id: Optional[str] = None,
        temp: Optional[dict] = None,
        ttl: int = 900,
        merge: bool = True,
    ) -> None:
        self._s.session_set(bot_id, uid, node_id, temp, ttl, merge)

    def set_temp(self, bot_id: str, uid: int, temp: dict, ttl: int = 900) -> None:
        """فقط ادغام temp بدون تغییر نود فعلی."""
        self._s.session_set(bot_id, uid, None, temp, ttl, merge=True)

    def clear(self, bot_id: str, uid: int) -> None:
        self._s.session_clear(bot_id, uid)

    def temp_get(self, bot_id: str, uid: int, key: str, default: Any = None) -> Any:
        session = self.get(bot_id, uid) or {}
        return (session.get("temp") or {}).get(key, default)

    def temp_set(self, bot_id: str, uid: int, key: str, value: Any, ttl: int = 900) -> None:
        self.set_temp(bot_id, uid, {key: value}, ttl)
