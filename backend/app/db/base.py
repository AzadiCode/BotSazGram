"""رابط واحد لایهٔ داده — تنها چیزی که سرویس‌ها با آن حرف می‌زنند.

دو پیاده‌سازی هم‌معنی: Mongo (pymongo) و Memory (حافظهٔ موقت توسعه).
قرارداد اسناد دقیقاً مثل legacy است تا ربات‌های قدیمی بدون تغییر کار کنند:
  - users: {"uid", "username", "full_name", "is_admin", "is_banned", "created_at",
            "bots_created", "coins", "referral_code", "referred_by", "referral_count",
            "password_hash", "auth_token", "registration_ip", "device_id"}
  - bots:  {"bot_id", "owner_uid", "bot_token", "bot_username", "created_at",
            "last_activity", "is_active", "force_join_channel", "bot_users",
            "bot_user_vars", "bot_user_info", "sessions", "pending_tickets",
            "tickets", "ticket_admins", "stats", "daily_stats", "flow",
            "ai_config", "commands", "rules", "welcome_message", "unknown_reply", "auto_menu"}

نکتهٔ مهم: همهٔ متدها داده را کپی می‌کنند تا فراخواننده نتواند سند درون
حافظهٔ پیاده‌سازی را مستقیماً تغییر دهد (مخصوصاً حالت Memory).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

# ── کلیدهای مجاز برای آپدیت جزئی سند ربات ──────────────────────────────────
BOT_CONFIG_FIELDS: frozenset[str] = frozenset(
    {
        "force_join_channel",
        "ticket_admins",
        "flow",
        "ai_config",
        "welcome_message",
        "unknown_reply",
        "auto_menu",
        "rules",
    }
)

# ── فیلدهای راز که هرگز نباید در پاسخ API برگردند ───────────────────────────
BOT_SECRET_FIELDS: frozenset[str] = frozenset({"bot_token"})
USER_SECRET_FIELDS: frozenset[str] = frozenset({"password_hash", "auth_token"})


class Storage(ABC):
    """رابط ذخیره‌سازی.

    همهٔ متدها دیکشنریِ کپی‌شده برمی‌گردانند یا None. هیچ متدی استثنا
    از جنس خطای برنامه پرتاب نمی‌کند (خطای دیتابیس → لاگ + رفتار امن).
    """

    is_memory: bool

    # ── راه‌اندازی ───────────────────────────────────────────────────────
    def close(self) -> None:
        """بستن اتصال (در Mongo لازم است)."""

    # ── کاربران ──────────────────────────────────────────────────────────
    @abstractmethod
    def ensure_user(self, uid: int, username: str = "", full_name: str = "") -> dict: ...

    @abstractmethod
    def get_user(self, uid: int) -> Optional[dict]: ...

    @abstractmethod
    def get_user_by(self, query: dict[str, Any]) -> Optional[dict]: ...

    @abstractmethod
    def get_all_users(self) -> list[dict]: ...

    @abstractmethod
    def update_user(self, uid: int, patch: dict[str, Any]) -> None: ...

    @abstractmethod
    def next_web_uid(self) -> int:
        """شناسهٔ بعدی حساب وب (از WEB_ACCOUNT_UID_START به بالا)."""

    @abstractmethod
    def insert_user(self, user: dict) -> None:
        """درج سند کاربرِ ازپیش‌ساخته‌شده (ثبت‌نام وب)."""

    # ── ربات‌ها ──────────────────────────────────────────────────────────
    @abstractmethod
    def create_bot(self, owner_uid: int, bot_token: str, bot_username: str) -> dict: ...

    @abstractmethod
    def get_bot(self, bot_id: str) -> Optional[dict]: ...

    @abstractmethod
    def get_user_bots(self, uid: int) -> list[dict]: ...

    @abstractmethod
    def get_all_bots(self) -> list[dict]: ...

    @abstractmethod
    def delete_bot(self, bot_id: str, owner_uid: int) -> bool: ...

    @abstractmethod
    def update_bot(self, bot_id: str, patch: dict[str, Any]) -> None:
        """به‌روزرسانی فیلدهای مجاز سند ربات."""

    # ── کاربرانِ ربات ────────────────────────────────────────────────────
    @abstractmethod
    def add_bot_user(self, bot_id: str, uid: int) -> bool: ...

    @abstractmethod
    def get_bot_users(self, bot_id: str) -> list[dict]: ...

    @abstractmethod
    def set_bot_user_info(
        self, bot_id: str, uid: int, full_name: str = "", username: str = ""
    ) -> None: ...

    @abstractmethod
    def get_user_vars(self, bot_id: str, uid: int) -> dict: ...

    @abstractmethod
    def set_user_var(self, bot_id: str, uid: int, name: str, value: Any) -> None: ...

    # ── نشست موقت کاربر ──────────────────────────────────────────────────
    @abstractmethod
    def session_get(self, bot_id: str, uid: int) -> Optional[dict]: ...

    @abstractmethod
    def session_set(
        self,
        bot_id: str,
        uid: int,
        node_id: Optional[str] = None,
        temp: Optional[dict] = None,
        ttl: int = 900,
        merge: bool = True,
    ) -> None: ...

    @abstractmethod
    def session_clear(self, bot_id: str, uid: int) -> None: ...

    # ── تیکت‌ها ──────────────────────────────────────────────────────────
    @abstractmethod
    def ticket_set_pending(self, bot_id: str, uid: int, node_id: str, ttl: int = 900) -> None: ...

    @abstractmethod
    def ticket_pop_pending(self, bot_id: str, uid: int) -> Optional[dict]: ...

    @abstractmethod
    def ticket_add(self, bot_id: str, tid: str, rec: dict) -> None: ...

    @abstractmethod
    def ticket_list(self, bot_id: str, limit: int = 50) -> list[dict]: ...

    @abstractmethod
    def ticket_reply(self, bot_id: str, tid: str, text: str) -> bool: ...

    # ── آمار ─────────────────────────────────────────────────────────────
    @abstractmethod
    def update_bot_stats(self, bot_id: str, received: int = 0, sent: int = 0) -> None: ...

    @abstractmethod
    def record_daily(self, bot_id: str, key: str, amount: int = 1) -> None: ...

    @abstractmethod
    def record_broadcast(self, bot_id: str, sent: int) -> None: ...

    # ── سکه و رفرال ─────────────────────────────────────────────────────
    @abstractmethod
    def add_coins(self, uid: int, amount: int) -> bool: ...

    @abstractmethod
    def inc_referral_count(self, uid: int) -> None: ...

    # ── داده‌های موقتِ TTLدار (کد تأیید، تلاش ورود، ثبت‌نام) ─────────────
    @abstractmethod
    def ttl_set(self, scope: str, key: str, value: Any, ttl: int) -> None:
        """ذخیرهٔ یک مقدار موقت با زمان انقضا (ثانیه)."""

    @abstractmethod
    def ttl_get(self, scope: str, key: str) -> Optional[Any]:
        """خواندن مقدار موقت؛ None یعنی نیست یا منقضی شده."""

    @abstractmethod
    def ttl_delete(self, scope: str, key: str) -> None: ...

    @abstractmethod
    def ttl_count(self, scope: str, key: str, window: int) -> int:
        """تعداد رکوردهای زندهٔ یک کلید در یک پنجرهٔ زمانی (شمارندهٔ نرخ)."""

    @abstractmethod
    def ttl_prune(self, scope: str) -> int:
        """پاکسازی رکوردهای منقضی‌شدهٔ یک scope — تعداد حذف‌شده‌ها را برمی‌گرداند."""


def bot_defaults(bot: dict) -> dict:
    """مقادیر پیش‌فرض سند ربات — مثل legacy، فیلدهای قدیمی را پاک نمی‌کند."""
    bot.setdefault("is_active", True)
    bot.setdefault("bot_username", "")
    bot.setdefault("force_join_channel", None)
    bot.setdefault("bot_users", [])
    bot.setdefault("bot_user_vars", {})
    bot.setdefault("bot_user_info", {})
    bot.setdefault("sessions", {})
    bot.setdefault("pending_tickets", {})
    bot.setdefault("tickets", {})
    bot.setdefault("ticket_admins", [])
    bot.setdefault("flow", None)
    bot.setdefault("ai_config", None)
    bot.setdefault("stats", {
        "messages_received": 0,
        "messages_sent": 0,
        "unique_users": 0,
        "broadcasts_sent": 0,
    })
    bot.setdefault("daily_stats", {})
    # فیلدهای قدیمی (فاز ۴ فقط برای خواندن/مهاجرت از آن‌ها استفاده می‌کند)
    bot.setdefault("commands", {})
    bot.setdefault("rules", [])
    bot.setdefault("welcome_message", "")
    bot.setdefault("unknown_reply", "")
    bot.setdefault("auto_menu", True)
    return bot


def user_defaults(user: dict) -> dict:
    """مقادیر پیش‌فرض سند کاربر."""
    user.setdefault("username", "")
    user.setdefault("full_name", "")
    user.setdefault("first_name", "")
    user.setdefault("last_name", "")
    user.setdefault("photo_url", "")
    user.setdefault("is_admin", False)
    user.setdefault("is_banned", False)
    user.setdefault("bots_created", [])
    user.setdefault("coins", 0)
    user.setdefault("referral_code", "")
    user.setdefault("referred_by", None)
    user.setdefault("referral_count", 0)
    user.setdefault("password_hash", "")
    user.setdefault("auth_token", "")
    user.setdefault("registration_ip", "")
    user.setdefault("device_id", "")
    user.setdefault("settings", {"notify": True})
    return user


def strip_secrets(doc: Optional[dict], fields: frozenset[str]) -> Optional[dict]:
    """حذف فیلدهای راز از یک سند (کپی)."""
    if not doc:
        return doc
    return {k: v for k, v in doc.items() if k not in fields}
