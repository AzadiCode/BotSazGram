"""سرویس‌ها — لایهٔ منطق برنامه روی ریپازیتوری‌ها.

هر سرویس یک مسئولیت دارد و با repos کار می‌کند، نه با Storage مستقیماً.
قراردادهای مهم:
  - سرویس‌ها منطقهٔ دامنه (هش، سکه، ماسک) را دوباره پیاده نمی‌کنند؛
    همه در repos/core هست.
  - خطاها از طریق app.core.errors با پیام فارسی پرتاب می‌شوند.
  - `runner` بات‌ها در این فاز تزریق نمی‌شود (در فاز ۳ به factor وصل می‌شود).
"""
from __future__ import annotations

from app.db import get_storage
from app.db.repos import Repos
from app.services.auth import AuthService
from app.services.backup import BackupService
from app.services.bots import BotService
from app.services.media import MediaService
from app.services.registration import RegistrationService
from app.services.referral import ReferralService
from app.services.stats import StatsService

__all__ = [
    "AuthService",
    "BackupService",
    "BotService",
    "MediaService",
    "RegistrationService",
    "ReferralService",
    "Services",
    "StatsService",
    "services",
    "set_services",
]


class Services:
    """نگهدارندهٔ یکپارچهٔ همهٔ سرویس‌ها — یک Repos مشترک."""

    def __init__(self, repos: Repos) -> None:
        self.repos = repos
        self.auth = AuthService(repos)
        self.registration = RegistrationService(repos)
        self.referral = ReferralService(repos)
        self.bots = BotService(repos)
        self.stats = StatsService(repos)
        self.backup = BackupService(repos)
        self.media = MediaService()


_services: Services | None = None


def services() -> Services:
    """دسترسی سراسری به سرویس‌ها (بر اساس Repos تک‌نمونهٔ پروسه)."""
    global _services
    if _services is None:
        _services = Services(Repos(get_storage()))
    return _services


def set_services(value: Services) -> None:
    """تزریق سرویس‌ها (برای تست)."""
    global _services
    _services = value
