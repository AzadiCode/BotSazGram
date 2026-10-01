"""لایهٔ db — انتخاب بک‌اند و ساخت شیء واحد Storage.

سرویس‌ها فقط با این رابط کار می‌کنند، نه با pymongo یا ساختار درونی Memory.
"""
from __future__ import annotations

import logging

from app import config
from app.db.base import Storage
from app.db.memory import MemoryStorage

log = logging.getLogger("GramSaz.db")

_storage: Storage | None = None


def get_storage() -> Storage:
    """شیء Storage سراسری (تنها یک نمونه در طول عمر پروسه)."""
    global _storage
    if _storage is None:
        _storage = build_storage()
    return _storage


def build_storage() -> Storage:
    """ساخت Storage بر اساس MONGODB_URI — بدون URI، حافظهٔ موقت."""
    if not config.MONGODB_URI:
        log.warning("MONGODB_URI تنظیم نشده — از حافظهٔ موقت استفاده می‌شود")
        return MemoryStorage()
    # ایمپورت دیرهنگام تا pymongo فقط وقتی لازم است بارگذاری شود
    from app.db.mongo import connect

    return connect(config.MONGODB_URI)


def set_storage(storage: Storage) -> None:
    """تزریق Storage (برای تست)."""
    global _storage
    _storage = storage


__all__ = ["get_storage", "build_storage", "set_storage", "Storage"]
