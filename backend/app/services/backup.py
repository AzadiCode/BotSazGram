"""سرویس پشتیبان‌گیری — خروجی و بازگردانی تنظیمات یک ربات.

نسخهٔ پشتیبان شامل تنظیمات، قوانین و گراف جریان است. گراف در بازگردانی
با clean_flow (فاز ۴) اعتبارسنجی می‌شود تا پشتیبانِ خراب نتواند ربات را
خراب کند.
"""
from __future__ import annotations

import logging
from typing import Any

from app import config, messages
from app.core import utils
from app.core.errors import BadRequest
from app.db.repos import Repos
from app.flow import clean_flow

log = logging.getLogger("GramSaz.backup")

_SETTINGS_FIELDS = (
    "welcome_message",
    "unknown_reply",
    "auto_menu",
    "force_join_channel",
    "ticket_admins",
)


class BackupService:
    def __init__(self, repos: Repos) -> None:
        self._r = repos

    # ── گرفتن پشتیبان ─────────────────────────────────────────────────────
    def export(self, bot_id: str, owner_uid: int) -> dict:
        """خروجی گرفتن از تنظیمات ربات — فقط مالک."""
        bot = self._r.bots.get_owned(bot_id, owner_uid)
        return {
            "version": config.BACKUP_VERSION,
            "exported_at": utils.now_iso(),
            "bot_username": bot.get("bot_username") or "",
            "flow": bot.get("flow"),
            "rules": bot.get("rules") or [],
            "settings": {k: bot.get(k) for k in _SETTINGS_FIELDS},
        }

    # ── بازگردانی ─────────────────────────────────────────────────────────
    def restore(self, bot_id: str, owner_uid: int, payload: dict) -> dict:
        """بازگردانی پشتیبان — خروجی: فهرست بخش‌های بازیابی‌شده.

        payload می‌تواند مستقیم شیء پشتیبان یا {"backup": …} باشد.
        """
        self._r.bots.get_owned(bot_id, owner_uid)
        backup = payload.get("backup") if isinstance(payload, dict) else None
        if not isinstance(backup, dict):
            backup = payload if isinstance(payload, dict) else {}
        if not backup:
            raise BadRequest(messages.ERR_RESTORE_EMPTY)

        done: list[str] = []

        # گراف جریان (برندهٔ نهایی است و بعد از قوانین می‌آید)
        flow = backup.get("flow")
        if isinstance(flow, dict) and flow.get("nodes"):
            cleaned, verr = clean_flow(flow)
            if verr or cleaned is None:
                raise BadRequest(verr or messages.ERR_VALIDATION)
            self._r.bots.set_flow(bot_id, cleaned)
            done.append("گراف")

        # قوانین
        rules = backup.get("rules")
        if isinstance(rules, list):
            self._r.bots.update_config(bot_id, {"rules": rules})
            done.append("قوانین")

        # تنظیمات
        settings = backup.get("settings")
        if isinstance(settings, dict):
            patch: dict[str, Any] = {}
            for key in ("welcome_message", "unknown_reply", "auto_menu"):
                if key in settings:
                    patch[key] = settings[key]
            if patch:
                self._r.bots.update_config(bot_id, patch)
            if "force_join_channel" in settings:
                self._r.bots.set_force_join(
                    bot_id, settings["force_join_channel"] or None
                )
            if isinstance(settings.get("ticket_admins"), list):
                self._r.bots.set_ticket_admins(
                    bot_id,
                    [
                        int(x)
                        for x in settings["ticket_admins"]
                        if str(x).lstrip("-").isdigit()
                    ][: config.TICKET_ADMIN_MAX],
                )
            if patch or any(k in settings for k in _SETTINGS_FIELDS):
                done.append("تنظیمات")

        if not done:
            raise BadRequest(messages.ERR_RESTORE_EMPTY)
        log.info("پشتیبان بازیابی شد برای %s: %s", bot_id, "، ".join(done))
        return {"restored": done, "message": messages.OK_RESTORE.format(parts="، ".join(done))}
