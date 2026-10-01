"""ریپازیتوری‌ها — لایهٔ دامنه روی Storage.

سرویس‌ها با این ریپازیتوری‌ها کار می‌کنند، نه با Storage مستقیماً.
هر ریپازیتوری یک مسئولیت دارد: کاربران، ربات‌ها، نشست‌ها، تیکت‌ها، کدها.
"""
from __future__ import annotations

from app.db import get_storage
from app.db.base import Storage
from app.db.repos.bots import BotRepo
from app.db.repos.codes import CodeRepo
from app.db.repos.sessions import SessionRepo
from app.db.repos.tickets import TicketRepo
from app.db.repos.users import UserRepo

__all__ = [
    "BotRepo",
    "CodeRepo",
    "SessionRepo",
    "TicketRepo",
    "UserRepo",
    "repos",
]


class Repos:
    """نگهدارندهٔ یکپارچهٔ همهٔ ریپازیتوری‌ها — یک Storage مشترک."""

    def __init__(self, storage: Storage) -> None:
        self.storage = storage
        self.users = UserRepo(storage)
        self.bots = BotRepo(storage)
        self.sessions = SessionRepo(storage)
        self.tickets = TicketRepo(storage)
        self.codes = CodeRepo(storage)


_repos: Repos | None = None


def repos() -> Repos:
    """دسترسی سراسری به ریپازیتوری‌ها (بر اساس Storage تک‌نمونهٔ پروسه)."""
    global _repos
    if _repos is None:
        _repos = Repos(get_storage())
    return _repos


def set_repos(value: Repos) -> None:
    """تزریق ریپازیتوری‌ها (برای تست)."""
    global _repos
    _repos = value
