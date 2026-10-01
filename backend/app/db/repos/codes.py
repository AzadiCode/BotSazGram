"""ریپازیتوری کدهای تأیید — کد ۶ رقمی ثبت‌نام که از طریق ربات مادر ارسال می‌شود.

کدها پشت رابط Storage با TTL ذخیره می‌شوند (Mongo: ایندکس expireAfterSeconds،
Memory: پاکسازی خودکار) تا ریستارت سرور آن‌ها را از بین نبرد.
"""
from __future__ import annotations

import secrets
from typing import Optional

from app import config, messages
from app.core.errors import BadRequest, TooManyRequests
from app.db.base import Storage

SCOPE_CODES = "verification_codes"


class CodeRepo:
    def __init__(self, storage: Storage) -> None:
        self._s = storage

    def issue(self, key: str) -> str:
        """صدور کد ۶ رقمی جدید برای key (معمولاً username تلگرام)."""
        code = "".join(secrets.choice("0123456789") for _ in range(6))
        self._s.ttl_set(
            SCOPE_CODES,
            key,
            {"code": code, "attempts": 0},
            ttl=config.VERIFICATION_CODE_TTL,
        )
        return code

    def verify(self, key: str, code: str) -> str:
        """بررسی کد — خروجی: کد تاییدشده، یا خطای مناسب.

        پیام خطا شامل تعداد تلاش‌های انجام‌شده است (مثل legacy).
        """
        if not code:
            raise BadRequest(messages.ERR_BAD_REQUEST)
        entry = self._s.ttl_get(SCOPE_CODES, key)
        if not entry:
            raise BadRequest(messages.ERR_CODE_NOT_FOUND)

        attempts = int(entry.get("attempts", 0)) + 1
        if attempts > config.VERIFICATION_CODE_MAX_ATTEMPTS:
            self._s.ttl_delete(SCOPE_CODES, key)
            raise TooManyRequests(messages.ERR_CODE_MAX_ATTEMPTS)

        entry["attempts"] = attempts
        self._s.ttl_set(SCOPE_CODES, key, entry, ttl=config.VERIFICATION_CODE_TTL)
        if entry.get("code") != code.strip():
            raise BadRequest(
                messages.ERR_CODE_INVALID.format(
                    attempts=attempts, max=config.VERIFICATION_CODE_MAX_ATTEMPTS
                )
            )
        self._s.ttl_delete(SCOPE_CODES, key)
        return code.strip()

    def peek(self, key: str) -> Optional[str]:
        """کد فعلی بدون مصرف آن — فقط برای ارسال مجدد (resend)."""
        entry = self._s.ttl_get(SCOPE_CODES, key)
        return entry.get("code") if entry else None
