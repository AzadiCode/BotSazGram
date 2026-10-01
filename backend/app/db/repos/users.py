"""ریپازیتوری کاربران — عملیات دامنه روی حساب‌ها.

این لایه قراردادهای دامنه (هش رمز، توکن، سکه) را می‌شناسد و Storage
فقط نقش ذخیره‌سازی دارد. خروجی‌ها هرگز شامل password_hash/auth_token نیست
مگر اینکه صریحاً درخواست شده باشد.
"""
from __future__ import annotations

from typing import Any, Optional

from app import config, messages
from app.core import security, utils
from app.core.errors import Conflict
from app.db.base import Storage, USER_SECRET_FIELDS, strip_secrets

# scopeهای دادهٔ موقت TTLدار
SCOPE_LOGIN_ATTEMPTS = "login_attempts"
SCOPE_REGISTRATIONS = "registrations"


class UserRepo:
    def __init__(self, storage: Storage) -> None:
        self._s = storage

    # ── خواندن ───────────────────────────────────────────────────────────
    def get(self, uid: int) -> Optional[dict]:
        return strip_secrets(self._s.get_user(uid), USER_SECRET_FIELDS)

    def get_by_username(self, username: str) -> Optional[dict]:
        return strip_secrets(
            self._s.get_user_by({"username": username.lower()}), USER_SECRET_FIELDS
        )

    def get_by_token(self, token: str) -> Optional[dict]:
        if not token:
            return None
        return strip_secrets(self._s.get_user_by({"auth_token": token}), USER_SECRET_FIELDS)

    def get_by_referral_code(self, code: str) -> Optional[dict]:
        if not code:
            return None
        return strip_secrets(self._s.get_user_by({"referral_code": code}), USER_SECRET_FIELDS)

    def find_telegram_user(self, telegram_username: str) -> Optional[dict]:
        """کاربر تلگرامیِ دارای این username (ربات مادر را /start زده).

        تفاوت با get_by_username: کلید جستجو «username» نیست، بلکه
        «telegram_username» است که ربات مادر در ensure_user تنظم می‌کند.
        """
        if not telegram_username:
            return None
        return strip_secrets(
            self._s.get_user_by({"telegram_username": telegram_username.lower()}),
            USER_SECRET_FIELDS,
        )

    def is_registered_by_telegram(self, telegram_username: str) -> bool:
        """آیا یک حساب وبِ کامل‌شده (دارای رمز) برای این username تلگرام هست؟

        حساب وب در زمان ثبت‌نام «telegram_username» را با خود نگه می‌دارد تا
        بتوانیم تشخیص دهیم این هویت تلگرام قبلاً ثبت‌نام کامل کرده یا نه.
        """
        if not telegram_username:
            return False
        target = telegram_username.lower()
        for user in self._s.get_all_users():
            if (
                (user.get("telegram_username") or "").lower() == target
                and user.get("password_hash")
            ):
                return True
        return False

    def is_web_registered(self, uid: int) -> bool:
        """آیا این کاربر حساب وب (با رمز عبور) دارد؟"""
        user = self._s.get_user(uid)
        return bool(user and user.get("password_hash"))

    def set_telegram_profile(
        self, uid: int, username: str = "", first_name: str = "",
        last_name: str = "", photo_url: str = "",
    ) -> None:
        """به‌روزرسانی پروفایل تلگرامی (user_id/username/نام/عکس)."""
        patch: dict[str, Any] = {"telegram_user_id": uid}
        if username:
            patch["telegram_username"] = username.lower()
            patch["username"] = username.lower()
        if first_name:
            patch["first_name"] = first_name
            patch["telegram_first_name"] = first_name
            if not patch.get("full_name"):
                patch["full_name"] = first_name
        if last_name:
            patch["last_name"] = last_name
            if patch.get("full_name") and not patch.get("full_name").endswith(last_name):
                patch["full_name"] = f"{patch['full_name']} {last_name}"
        if photo_url:
            patch["photo_url"] = photo_url
        self._s.update_user(uid, patch)

    def update_settings(self, uid: int, settings: dict[str, Any]) -> None:
        """به‌روزرسانی تنظیمات کاربر (only allowed keys)."""
        current: dict = (self._s.get_user(uid) or {}).get("settings") or {}
        current.update({k: v for k, v in settings.items() if k in ("notify",)})
        self._s.update_user(uid, {"settings": current})

    def all(self) -> list[dict]:
        return [strip_secrets(u, USER_SECRET_FIELDS) for u in self._s.get_all_users()]  # type: ignore[misc]

    # ── ربات مادر / تلگرام ───────────────────────────────────────────────
    def ensure_telegram_user(
        self, uid: int, username: str = "", full_name: str = ""
    ) -> dict:
        """ساخت/به‌روزرسانی کاربر تلگرامی (وقتی ربات مادر /start می‌خورد)."""
        return strip_secrets(
            self._s.ensure_user(uid, username, full_name), USER_SECRET_FIELDS
        )  # type: ignore[return-value]

    # ── ثبت‌نام وب ────────────────────────────────────────────────────────
    def register(
        self,
        username: str,
        password: str,
        full_name: str = "",
        referral_code: str = "",
        ip: str = "",
        device_id: str = "",
        telegram_username: str = "",
    ) -> tuple[dict, str]:
        """ثبت‌نام حساب وب. خروجی: (کاربر بدون راز، توکن).

        فرض: محدودیت‌ها و کد تأیید پیش از این توسط سرویس بررسی شده‌اند.
        telegram_username برای پیوند هویت تلگرام با حساب وب نگه داشته
        می‌شود (تشخیص «قبلاً ثبت‌نام کرده» در send_code).
        """
        username = username.lower()
        if self.get_by_username(username):
            raise Conflict(messages.ERR_USER_EXISTS)

        referrer = self.get_by_referral_code(referral_code) if referral_code else None
        uid = self._s.next_web_uid()
        user = {
            "uid": uid,
            "username": username,
            "password_hash": security.hash_password(password),
            "full_name": full_name or username,
            "is_admin": False,
            "is_banned": False,
            "created_at": utils.now_iso(),
            "bots_created": [],
            "auth_token": security.new_auth_token(),
            "coins": config.REFERRAL_REWARD_NEW_USER if referrer else 0,
            "referral_code": utils.new_referral_code(),
            "referred_by": referrer["uid"] if referrer else None,
            "referral_count": 0,
            "registration_ip": ip,
            "device_id": device_id,
            "telegram_username": (telegram_username or "").lower(),
        }
        self._s.insert_user(user)
        if referrer:
            self._s.add_coins(referrer["uid"], config.REFERRAL_REWARD_REFERRER)
            self._s.inc_referral_count(referrer["uid"])
        return strip_secrets(user, USER_SECRET_FIELDS), user["auth_token"]  # type: ignore[return-value]

    # ── ورود ─────────────────────────────────────────────────────────────
    def login(self, username: str, password: str) -> tuple[dict, str, bool]:
        """ورود. خروجی: (کاربر، توکن جدید، نیاز به ارتقا داشت؟).

        هش قدیمی sha256 در صورت ورود موفق ارتقا می‌یابد.
        """
        stored = self._s.get_user_by({"username": username.lower()})
        if not stored or not security.verify_password(password, stored.get("password_hash")):
            raise _bad_credentials()
        if stored.get("is_banned"):
            raise _banned()

        patch: dict[str, Any] = {"auth_token": security.new_auth_token()}
        needs_upgrade = security.password_needs_upgrade(stored.get("password_hash"))
        if needs_upgrade:
            patch["password_hash"] = security.hash_password(password)
        self._s.update_user(stored["uid"], patch)

        user = strip_secrets(stored, USER_SECRET_FIELDS) or {}
        user["auth_token"] = patch["auth_token"]
        return user, patch["auth_token"], needs_upgrade

    def logout(self, token: str) -> bool:
        user = self.get_by_token(token)
        if not user:
            return False
        self._s.update_user(user["uid"], {"auth_token": ""})
        return True

    # ── سکه و رفرال ─────────────────────────────────────────────────────
    def add_coins(self, uid: int, amount: int) -> bool:
        return self._s.add_coins(uid, amount)

    def inc_referral_count(self, uid: int) -> None:
        self._s.inc_referral_count(uid)

    def referral_info(self, uid: int) -> dict:
        user = self.get(uid) or {}
        return {
            "referral_code": user.get("referral_code", ""),
            "referred_by": user.get("referred_by"),
            "referral_count": user.get("referral_count", 0),
            "coins": user.get("coins", 0),
        }

    # ── محدودیت ثبت‌نام (IP + دستگاه) ────────────────────────────────────
    def check_registration_limit(self, ip: str, device_id: str) -> tuple[bool, str]:
        """آیا این IP/دستگاه مجاز به ثبت‌نام است؟ خروجی: (مجاز، دلیل رد)."""
        if ip:
            count = self._s.ttl_count(SCOPE_REGISTRATIONS, ip, config.REGISTER_IP_WINDOW)
            if count >= config.REGISTER_MAX_PER_IP:
                return False, messages.ERR_REGISTRATION_LIMIT.format(minutes=10)
            if count > 0:
                return False, messages.ERR_REGISTRATION_LIMIT.format(minutes=10)
        if device_id:
            count = self._s.ttl_count(SCOPE_REGISTRATIONS, device_id, config.REGISTER_IP_WINDOW)
            if count >= config.REGISTER_MAX_PER_DEVICE:
                return False, messages.ERR_DEVICE_LIMIT
        return True, ""

    def record_registration(self, ip: str, device_id: str) -> None:
        now = utils.epoch()
        for key in (ip, device_id):
            if not key:
                continue
            stamps = self._s.ttl_get(SCOPE_REGISTRATIONS, key) or []
            if not isinstance(stamps, list):
                stamps = []
            stamps.append(now)
            self._s.ttl_set(
                SCOPE_REGISTRATIONS, key, stamps, ttl=config.REGISTER_IP_WINDOW
            )

    # ── تلاش ورود ناموفق ─────────────────────────────────────────────────
    def check_login_attempts(self, ip: str, username: str) -> bool:
        """آیا این IP+username هنوز زیر سقف تلاش ناموفق است؟"""
        key = _login_key(ip, username)
        return self._s.ttl_count(SCOPE_LOGIN_ATTEMPTS, key, config.LOGIN_WINDOW) < (
            config.LOGIN_MAX_ATTEMPTS
        )

    def record_login_failure(self, ip: str, username: str) -> None:
        key = _login_key(ip, username)
        stamps = self._s.ttl_get(SCOPE_LOGIN_ATTEMPTS, key) or []
        if not isinstance(stamps, list):
            stamps = []
        stamps.append(utils.epoch())
        self._s.ttl_set(SCOPE_LOGIN_ATTEMPTS, key, stamps, ttl=int(config.LOGIN_WINDOW))

    def clear_login_attempts(self, ip: str, username: str) -> None:
        self._s.ttl_delete(SCOPE_LOGIN_ATTEMPTS, _login_key(ip, username))


def _login_key(ip: str, username: str) -> str:
    return f"{ip}:{username.lower()}"


def _bad_credentials() -> Exception:
    from app.core.errors import Unauthorized

    return Unauthorized(messages.ERR_INVALID_CREDENTIALS)


def _banned() -> Exception:
    from app.core.errors import Forbidden

    return Forbidden(messages.MOTHER_BANNED)
