"""سرویس ثبت‌نام و ورود — جریان کامل کد تأیید + ساخت حساب وب.

مراحل ثبت‌نام (مثل legacy):
  ۱) کاربر ربات مادر را /start می‌کند → ensure_telegram_user + پروفایل تلگرام.
  ۲) در پنل username و telegram_username را می‌دهد → send_code کد ۶ رقمی
     را از طریق ربات مادر برایش می‌فرستد.
  ۳) کد + رمز را می‌فرستد → register کد را بررسی کرده و حساب وب می‌سازد.

اعتبارسنجی‌ها، محدودیت ثبت‌نام و شمارندهٔ تلاش ورود در همین سرویس است؛
هش رمز، سکه و صدور توکن در repos/core انجام می‌شود.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from app import config, messages
from app.core import utils
from app.core.errors import (
    BadRequest,
    Conflict,
    NotFound,
    TooManyRequests,
    Unauthorized,
)
from app.db.repos import Repos

log = logging.getLogger("GramSaz.registration")

_USERNAME_RE = re.compile(r"^[a-z0-9_]+$")


class RegistrationService:
    def __init__(self, repos: Repos) -> None:
        self._r = repos
        self._deliver: Optional[callable] = None

    def set_deliver(self, deliver: Optional[callable]) -> None:
        """نصب کال‌بک ارسال کد (از طرف telegram.wire در راه‌اندازی سرور).

        `deliver(chat_id=…, text=…)` باید پیام را از طریق ربات مادر بفرستد.
        """
        self._deliver = deliver

    # ── ارسال کد تأیید ─────────────────────────────────────────────────────
    def send_code(
        self,
        telegram_username: str,
        device_id: str = "",
        ip: str = "",
        deliver: Optional[callable] = None,
    ) -> tuple[str, bool]:
        """صدور کد تأیید برای username تلگرام.

        خروجی: (کد، ارسال شد؟). پارامتر `deliver` یک کال‌بک async یا sync
        است که کد را از طریق ربات مادر می‌فرستد (در فاز ۳ وصل می‌شود).
        اگر داده نشود، کد فقط صادر می‌شود (برای تست).
        """
        username = self._normalize_tg_username(telegram_username)
        if not username:
            raise BadRequest(messages.ERR_TELEGRAM_USERNAME_REQUIRED)

        # حساب وبِ کامل‌شده نباید بتواند دوباره کد بگیرد
        if self._r.users.is_registered_by_telegram(username):
            raise Conflict(messages.ERR_NO_REGISTERED)

        # کاربر باید ربات مادر را استارت زده باشد تا بتوانیم کد را
        # به همان تلگرام بفرستیم (این مالکیت تلگرام را تضمین می‌کند).
        tg_user = self._r.users.find_telegram_user(username)
        if not tg_user:
            raise NotFound(messages.ERR_TELEGRAM_USERNAME_NOT_FOUND)

        # محدودیت ثبت‌نام (IP + دستگاه)
        ok, reason = self._r.users.check_registration_limit(ip, device_id)
        if not ok:
            raise TooManyRequests(reason)

        code = self._r.codes.issue(username)
        log.info("کد تأیید صادر شد برای @%s", username)

        sent = False
        deliver = deliver if deliver is not None else self._deliver
        if deliver is not None:
            try:
                result = deliver(
                    chat_id=tg_user.get("telegram_user_id") or tg_user.get("uid"),
                    text=messages.MOTHER_VERIFY_CODE.format(
                        name=tg_user.get("telegram_first_name")
                        or tg_user.get("full_name")
                        or "دوست عزیز",
                        code=code,
                    ),
                )
                sent = bool(result)
            except Exception as exc:  # noqa: BLE001 — ارسال نباید ثبت‌نام را بشکند
                log.warning("ارسال کد تأیید ناموفق بود: %s", exc)
        if not sent:
            log.warning("کد تأیید برای @%s ارسال نشد (ربات مادر آماده نیست؟)", username)
        return code, sent

    # ── ثبت‌نام حساب وب ─────────────────────────────────────────────────────
    def register(
        self,
        username: str,
        password: str,
        telegram_username: str,
        code: str,
        full_name: str = "",
        referral_code: str = "",
        ip: str = "",
        device_id: str = "",
    ) -> tuple[dict, str]:
        """تکمیل ثبت‌نام: بررسی کد → ساخت حساب وب. خروجی: (کاربر، توکن)."""
        username = self._normalize_username(username)
        password = (password or "").strip()
        tg_username = self._normalize_tg_username(telegram_username)
        code = (code or "").strip()

        self._validate_registration(
            username, password, tg_username, code, device_id
        )

        # کد باید قبلاً برای همین username تلگرام صادر شده باشد
        self._r.codes.verify(tg_username, code)

        user, token = self._r.users.register(
            username,
            password,
            full_name=full_name or username,
            referral_code=referral_code,
            ip=ip,
            device_id=device_id,
            telegram_username=tg_username,
        )
        self._r.users.record_registration(ip, device_id)
        log.info("حساب وب ساخته شد: @%s (uid=%s)", username, user.get("uid"))
        return user, token

    # ── ورود ─────────────────────────────────────────────────────────────────
    def login(self, username: str, password: str, ip: str = "") -> tuple[dict, str]:
        """ورود با نام کاربری و رمز — با محدودیت تلاش ناموفق. خروجی: (کاربر، توکن)."""
        username = self._normalize_username(username)
        password = (password or "").strip()
        if not username or not password:
            raise BadRequest(messages.ERR_BAD_REQUEST)

        if not self._r.users.check_login_attempts(ip, username):
            raise TooManyRequests(messages.ERR_TOO_MANY)

        try:
            user, token, _upgraded = self._r.users.login(username, password)
        except Unauthorized:
            self._r.users.record_login_failure(ip, username)
            raise
        self._r.users.clear_login_attempts(ip, username)
        return user, token

    # ── اعتبارسنجی ─────────────────────────────────────────────────────────
    def _validate_registration(
        self,
        username: str,
        password: str,
        tg_username: str,
        code: str,
        device_id: str,
    ) -> None:
        if not username or len(username) < config.USERNAME_MIN_LEN:
            raise BadRequest(messages.ERR_USERNAME_MIN.format(min=config.USERNAME_MIN_LEN))
        if not _USERNAME_RE.match(username):
            raise BadRequest(messages.ERR_USERNAME_INVALID)
        if len(password) < config.PASSWORD_MIN_LEN:
            raise BadRequest(messages.ERR_PASSWORD_SHORT)
        if not device_id:
            raise BadRequest(messages.ERR_DEVICE_ID_REQUIRED)
        if not tg_username:
            raise BadRequest(messages.ERR_TELEGRAM_USERNAME_REQUIRED)
        if not code:
            raise BadRequest(messages.ERR_CODE_REQUIRED)

    @staticmethod
    def _normalize_username(value: str) -> str:
        return utils.clean_str(value).lower()

    @staticmethod
    def _normalize_tg_username(value: str) -> str:
        return utils.clean_str(value).lower().lstrip("@")
