"""سرویس مدیریت ربات‌ها — افزودن، فهرست، حذف و روشن/خاموش.

افزودن ربات سه مرحله دارد: اعتبارسنجی توکن → بررسی تکراری نبودن →
احضای getMe تلگرام (با کلاینت SSRF-safe) → ذخیره. روشن/خاموش کردن
نیاز به factor دارد (فاز ۳) که از بیرون تزریق می‌شود.

توکن ربات هرگز در خروجی‌های این سرویس نیست؛ mask از طریق BotRepo انجام
می‌شود.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Optional

from app import config, messages
from app.core import http
from app.core.errors import BadRequest, Conflict, Forbidden, NotFound
from app.core.utils import clean_str, mask_secret
from app.db.repos import Repos

log = logging.getLogger("GramSaz.bots")


class BotService:
    def __init__(
        self,
        repos: Repos,
        runner: Optional[Callable[[str, bool], bool]] = None,
    ) -> None:
        """`runner(bot_id, active) -> bool` در فاز ۳ به factor وصل می‌شود."""
        self._r = repos
        self._runner = runner
        self._status: Optional[Callable[[str], bool]] = None

    def set_runner(self, runner: Optional[Callable[[str, bool], bool]]) -> None:
        """نصب runner (از طرف telegram.wire در راه‌اندازی سرور)."""
        self._runner = runner

    def set_status_provider(self, provider: Optional[Callable[[str], bool]]) -> None:
        """نصب کال‌بک وضعیت اجرای واقعی (از طرف telegram.wire).

        `provider(bot_id) -> bool` از factory می‌پرسد که ربات روشن است یا نه.
        تا نصب نشده، `is_running` همان `is_active` است.
        """
        self._status = provider

    # ── فهرست ─────────────────────────────────────────────────────────────
    def list(self, owner_uid: int) -> list[dict]:
        """ربات‌های کاربر با وضعیت اجرای فعلی."""
        return [self._with_status(b) for b in self._r.bots.list(owner_uid)]

    def get(self, bot_id: str, owner_uid: int) -> dict:
        """خواندن یک ربات با بررسی مالکیت."""
        return self._with_status(self._r.bots.get_owned(bot_id, owner_uid))

    # ── افزودن ─────────────────────────────────────────────────────────────
    def add(self, owner_uid: int, token: str) -> dict:
        """افزودن ربات جدید — احضای getMe برای تأیید توکن.

        خروجی: ربات ذخیره‌شده (توکن ماسک‌شده).
        """
        token = clean_str(token)
        self._validate_token(token)

        # سقف تعداد ربات
        if len(self._r.bots.list(owner_uid)) >= config.MAX_BOTS_PER_USER:
            raise Forbidden(messages.ERR_BOT_LIMIT)

        # ربات تکراری نباشد
        if self._r.bots.find_by_token(token) is not None:
            raise Conflict(messages.ERR_BOT_EXISTS)

        me = self._call_get_me(token)
        bot = self._r.bots.create(owner_uid, token, me.get("username", ""))
        log.info("ربات اضافه شد: @%s (owner=%s)", me.get("username"), owner_uid)

        if self._runner is not None:
            try:
                self._runner(bot["bot_id"], True)
            except Exception as exc:  # noqa: BLE001
                log.warning("روشن کردن ربات جدید ناموفق بود: %s", exc)
        return self._with_status(bot)

    def set_flow(self, bot_id: str, flow: dict | None) -> None:
        """ذخیرهٔ گراف جریان ربات در storage."""
        self._r.bots.set_flow(bot_id, flow)

    # ── حذف ───────────────────────────────────────────────────────────────
    def delete(self, bot_id: str, owner_uid: int) -> None:
        """حذف ربات — اول خاموش کردن، بعد حذف از storage."""
        self._r.bots.get_owned(bot_id, owner_uid)
        if self._runner is not None:
            try:
                self._runner(bot_id, False)
            except Exception as exc:  # noqa: BLE001
                log.warning("خاموش کردن ربات قبل از حذف ناموفق بود: %s", exc)
        if not self._r.bots.delete(bot_id, owner_uid):
            raise NotFound(messages.ERR_NOT_FOUND)
        log.info("ربات حذف شد: %s", bot_id)

    # ── روشن/خاموش ─────────────────────────────────────────────────────────
    def set_active(self, bot_id: str, owner_uid: int, active: bool) -> dict:
        """روشن یا خاموش کردن ربات — وضعیت ذخیره و factor خبردار می‌شود."""
        bot = self._r.bots.get_owned(bot_id, owner_uid)
        self._r.bots.set_active(bot_id, bool(active))

        running = bool(active)
        if self._runner is not None:
            try:
                running = bool(self._runner(bot_id, active))
            except Exception as exc:  # noqa: BLE001
                log.warning("تغییر وضعیت ربات ناموفق بود: %s", exc)
                running = False
        bot["is_active"] = bool(active)
        return self._with_status(bot, running)

    # ── کمکی ─────────────────────────────────────────────────────────────
    @staticmethod
    def _validate_token(token: str) -> None:
        if ":" not in token or len(token) < config.BOT_TOKEN_MIN_LEN:
            raise BadRequest(messages.ERR_INVALID_TOKEN)

    @staticmethod
    def _call_get_me(token: str) -> dict[str, Any]:
        """احضای getMe تلگرام — فقط روی api.telegram.org با کلاینت امن."""
        resp = http.safe_get(
            f"https://api.telegram.org/bot{token}/getMe", timeout=10.0
        )
        if resp.get("status") != 200:
            log.warning("getMe ناموفق بود: status=%s", resp.get("status"))
            raise BadRequest(messages.ERR_INVALID_TOKEN)
        try:
            payload = json.loads(resp.get("text") or "")
        except (ValueError, TypeError):
            raise BadRequest(messages.ERR_INVALID_TOKEN) from None
        if not payload.get("ok"):
            raise BadRequest(messages.ERR_INVALID_TOKEN)
        return payload.get("result") or {}

    def _with_status(self, bot: dict, running: Optional[bool] = None) -> dict:
        """اضافه کردن is_running و ماسک کردن توکن (اگر خام باشد)."""
        bot = dict(bot)
        if running is None and self._status is not None:
            try:
                running = bool(self._status(bot.get("bot_id")))
            except Exception as exc:  # noqa: BLE001
                log.debug("پرسش وضعیت ربات ناموفق بود: %s", exc)
                running = None
        bot["is_running"] = bool(running) if running is not None else bool(bot.get("is_active"))
        if bot.get("bot_token") and "•" not in str(bot.get("bot_token")):
            bot["bot_token"] = mask_secret(bot["bot_token"])
        return bot

