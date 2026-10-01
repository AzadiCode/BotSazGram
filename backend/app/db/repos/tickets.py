"""ریپازیتوری تیکت‌ها — ثبت، فهرست و پاسخ به تیکت‌های پشتیبانی.

دو مفهوم: ۱) pending (کاربر در حال نوشتن متن تیکت است، مهلت ۱۵ دقیقه)
و ۲) tickets (تیکت ثبت‌شده با کد پیگیری).
"""
from __future__ import annotations

from typing import Optional

from app import config
from app.core import utils
from app.db.base import Storage


class TicketRepo:
    def __init__(self, storage: Storage) -> None:
        self._s = storage

    # ── در حال نوشتن ─────────────────────────────────────────────────────
    def set_pending(self, bot_id: str, uid: int, node_id: str) -> None:
        self._s.ticket_set_pending(bot_id, uid, node_id, ttl=config.TICKET_TTL)

    def pop_pending(self, bot_id: str, uid: int) -> Optional[dict]:
        return self._s.ticket_pop_pending(bot_id, uid)

    # ── تیکت ثبتشده ──────────────────────────────────────────────────────
    def add(self, bot_id: str, uid: int, text: str, **extra) -> str:
        """ثبت یک تیکت جدید — کد پیگیری را برمی‌گرداند."""
        tid = utils.new_ticket_id()
        rec = {
            "tid": tid,
            "uid": uid,
            "t": utils.epoch(),
            "at": utils.now_iso(),
            "text": text,
        }
        rec.update(extra)
        self._s.ticket_add(bot_id, tid, rec)
        return tid

    def list(self, bot_id: str, limit: int = 50) -> list[dict]:
        return self._s.ticket_list(bot_id, limit)

    def reply(self, bot_id: str, tid: str, text: str) -> bool:
        return self._s.ticket_reply(bot_id, tid, text)
