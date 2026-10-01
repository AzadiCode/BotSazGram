"""ریپازیتوری ربات‌ها — عملیات دامنه روی ربات‌ها و داده‌های وابسته.

توکن ربات هرگز در خروجی‌های عمومی قرار نمی‌گیرد؛ mask_token() برای
نمایش ماسک‌شده استفاده می‌شود.
"""
from __future__ import annotations

from typing import Any, Optional

from app import messages
from app.core import utils
from app.core.errors import Forbidden, NotFound
from app.db.base import BOT_SECRET_FIELDS, Storage, strip_secrets


class BotRepo:
    def __init__(self, storage: Storage) -> None:
        self._s = storage

    # ── خواندن ───────────────────────────────────────────────────────────
    def get(self, bot_id: str) -> Optional[dict]:
        return self._s.get_bot(bot_id)

    def find_by_token(self, bot_token: str) -> Optional[dict]:
        """رباتِ دارای این توکن (در صورت وجود) — برای جلوگیری از افزودن تکراری."""
        if not bot_token:
            return None
        for bot in self._s.get_all_bots():
            if bot.get("bot_token") == bot_token:
                return bot
        return None

    def get_owned(self, bot_id: str, owner_uid: int) -> dict:
        """خواندن ربات با بررسی مالکیت — خطا اگر نبود یا مالک نبود."""
        bot = self._s.get_bot(bot_id)
        if not bot:
            raise NotFound(messages.ERR_NOT_FOUND)
        if bot.get("owner_uid") != owner_uid:
            raise Forbidden(messages.ERR_NO_OWNER)
        return bot

    def list(self, owner_uid: int) -> list[dict]:
        return [self._public(b) for b in self._s.get_user_bots(owner_uid)]

    def list_all(self) -> list[dict]:
        return [self._public(b) for b in self._s.get_all_bots()]

    def list_active(self) -> list[dict]:
        """ربات‌های فعال — فقط شناسه و توکن (برای راه‌اندازی factory)."""
        return [
            {"bot_id": b.get("bot_id"), "bot_token": b.get("bot_token")}
            for b in self._s.get_all_bots()
            if b.get("is_active")
        ]

    def _public(self, bot: dict) -> dict:
        """نسخهٔ امن برای پاسخ API — توکن ماسک‌شده و api_key حذف می‌شود."""
        out = strip_secrets(bot, BOT_SECRET_FIELDS) or {}
        out["bot_token"] = utils.mask_secret(bot.get("bot_token"))
        cfg = out.get("ai_config")
        if isinstance(cfg, dict):
            out["ai_config"] = {k: v for k, v in cfg.items() if k != "api_key"}
        return out

    # ── نوشتن ─────────────────────────────────────────────────────────────
    def create(self, owner_uid: int, bot_token: str, bot_username: str) -> dict:
        return self._s.create_bot(owner_uid, bot_token, bot_username)

    def delete(self, bot_id: str, owner_uid: int) -> bool:
        return self._s.delete_bot(bot_id, owner_uid)

    def set_active(self, bot_id: str, active: bool) -> None:
        self._s.update_bot(bot_id, {"is_active": active})

    def set_username(self, bot_id: str, username: str) -> None:
        self._s.update_bot(bot_id, {"bot_username": username})

    def update_config(self, bot_id: str, cfg: dict[str, Any]) -> None:
        """به‌روزرسانی فقط فیلدهای مجاز تنظیمات ربات."""
        from app.db.base import BOT_CONFIG_FIELDS

        patch = {k: cfg[k] for k in BOT_CONFIG_FIELDS if k in cfg}
        if patch:
            self._s.update_bot(bot_id, patch)

    def set_flow(self, bot_id: str, flow: Optional[dict]) -> None:
        self._s.update_bot(bot_id, {"flow": flow})

    def set_force_join(self, bot_id: str, channel: Optional[str]) -> None:
        self._s.update_bot(bot_id, {"force_join_channel": channel})

    def set_ticket_admins(self, bot_id: str, uids: list[int]) -> None:
        self._s.update_bot(bot_id, {"ticket_admins": uids})

    def set_ai_config(self, bot_id: str, ai_config: Optional[dict]) -> None:
        """تنظیمات AI — کلید API فقط سمت سرور نگه داشته می‌شود."""
        self._s.update_bot(bot_id, {"ai_config": ai_config})

    # ── کاربران ربات ─────────────────────────────────────────────────────
    def add_user(self, bot_id: str, uid: int) -> bool:
        return self._s.add_bot_user(bot_id, uid)

    def users(self, bot_id: str) -> list[dict]:
        return self._s.get_bot_users(bot_id)

    def set_user_info(
        self, bot_id: str, uid: int, full_name: str = "", username: str = ""
    ) -> None:
        self._s.set_bot_user_info(bot_id, uid, full_name, username)

    # ── متغیرهای دائمی کاربر ─────────────────────────────────────────────
    def get_vars(self, bot_id: str, uid: int) -> dict:
        return self._s.get_user_vars(bot_id, uid)

    def set_var(self, bot_id: str, uid: int, name: str, value: Any) -> None:
        self._s.set_user_var(bot_id, uid, name, value)

    # ── آمار ─────────────────────────────────────────────────────────────
    def update_stats(self, bot_id: str, received: int = 0, sent: int = 0) -> None:
        self._s.update_bot_stats(bot_id, received, sent)

    def record_daily(self, bot_id: str, key: str, amount: int = 1) -> None:
        self._s.record_daily(bot_id, key, amount)

    def record_broadcast(self, bot_id: str, sent: int) -> None:
        self._s.record_broadcast(bot_id, sent)
