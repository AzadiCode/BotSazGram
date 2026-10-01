"""سرویس احراز هویت — دو مسیر ورود: Telegram WebApp initData و توکن Bearer.

این سرویس فقط «هویت را تأیید می‌کند»؛ ساخت کاربر تلگرامی، هش رمز و
صدور توکن در repos/core است و اینجا دوباره پیاده نمی‌شوند.

قرارداد خروجی: کاربرِ عمومی (بدون password_hash/auth_token) یا خطای
Unauthorized/Forbidden از app.core.errors.
"""
from __future__ import annotations

import logging
from typing import Optional

from app import config, messages
from app.core import security
from app.core.errors import Forbidden, Unauthorized
from app.db.repos import Repos

log = logging.getLogger("GramSaz.auth")


class AuthService:
    def __init__(self, repos: Repos) -> None:
        self._r = repos

    # ── مسیر اول: initData تلگرام ────────────────────────────────────────
    def from_init_data(self, init_data: str) -> dict:
        """تأیید هویت با initData مینی‌اپ تلگرام.

        کاربر تلگرامی را با ensure_telegram_user می‌سازد/به‌روز می‌کند تا
        همیشه یک رکورد داشته باشیم. خروجی: کاربر عمومی.
        """
        if not init_data:
            raise Unauthorized(messages.ERR_INVALID_INIT_DATA)

        tg_user = security.verify_init_data(init_data, config.PLATFORM_BOT_TOKEN)
        if not tg_user:
            log.warning("initData نامعتبر رد شد")
            raise Unauthorized(messages.ERR_INVALID_INIT_DATA)

        uid = int(tg_user.get("id") or 0)
        if uid <= 0:
            raise Unauthorized(messages.ERR_INVALID_INIT_DATA)

        user = self._r.users.get(uid)
        if user is None:
            username = (tg_user.get("username") or "").lower()
            full_name = " ".join(
                filter(None, (tg_user.get("first_name"), tg_user.get("last_name")))
            ).strip()
            user = self._r.users.ensure_telegram_user(uid, username, full_name)
        self._r.users.set_telegram_profile(
            uid,
            username=(tg_user.get("username") or ""),
            first_name=(tg_user.get("first_name") or ""),
            last_name=(tg_user.get("last_name") or ""),
            photo_url=(tg_user.get("photo_url") or ""),
        )

        self._require_active(user)
        return user

    # ── مسیر دوم: توکن Bearer ─────────────────────────────────────────────
    def from_token(self, token: str) -> dict:
        """تأیید هویت با توکن نشست وب (Authorization: Bearer …)."""
        if not token:
            raise Unauthorized(messages.ERR_NO_TOKEN)
        user = self._r.users.get_by_token(token)
        if user is None:
            raise Unauthorized(messages.ERR_TOKEN_INVALID)
        self._require_active(user)
        return user

    # ── ترکیب هر دو مسیر (ترتیب: initData اول) ────────────────────────────
    def authenticate(self, init_data: str = "", token: str = "") -> dict:
        """مسیر احراز هویت یکپارچه — مثل legacy، initData اولویت دارد."""
        if init_data:
            return self.from_init_data(init_data)
        return self.from_token(token)

    def logout(self, token: str) -> bool:
        """خروج — باطل کردن توکن نشست."""
        if not token:
            return False
        return self._r.users.logout(token)

    # ── کمکی ─────────────────────────────────────────────────────────────
    @staticmethod
    def _require_active(user: Optional[dict]) -> None:
        if not user:
            raise Unauthorized(messages.ERR_UNAUTHORIZED)
        if user.get("is_banned"):
            log.warning("کاربر مسدودشده تلاش ورود داشت: uid=%s", user.get("uid"))
            raise Forbidden(messages.MOTHER_BANNED)
