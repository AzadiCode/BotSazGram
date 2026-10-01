"""هندلرهای ساب‌بات‌ها.

فاز ۳: فقط زیرساخت — ثبت کاربرِ ربات، ثبت آمار و یک پاسخِ «هنوز آماده نیست».
فاز ۵: موتور جریان با `set_handler_builder` جایگزین این هندلرها می‌شود
(گراف، کارت‌ها، تیکت، کلیدواژه‌ها و غیره).
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler, filters

from app import messages
from app.db.repos import repos

log = logging.getLogger("GramSaz.subbot")

_handler_builder: Optional[Callable[[str], list]] = None


def set_handler_builder(builder: Optional[Callable[[str], list]]) -> None:
    """فاز ۵: سازندهٔ هندلرهای واقعی (موتور جریان) را نصب می‌کند.

    با None دادن، هندلرهای پیش‌فرضِ این فاز برمی‌گردند.
    """
    global _handler_builder
    _handler_builder = builder


def build_subbot_handlers(bot_id: str) -> list:
    """فهرست هندلرهای یک ساب‌بات — یا موتور فاز ۵ یا پیش‌فرض این فاز."""
    if _handler_builder is not None:
        return _handler_builder(bot_id)
    return [
        CommandHandler("start", lambda u, c: on_start(u, c, bot_id)),
        CallbackQueryHandler(lambda u, c: on_callback(u, c, bot_id)),
        MessageHandler(filters.TEXT & filters.COMMAND, lambda u, c: on_command(u, c, bot_id)),
        MessageHandler(filters.TEXT & (~filters.COMMAND), lambda u, c: on_text(u, c, bot_id)),
    ]


# ── زیرساخت مشترک ────────────────────────────────────────────────────────────
async def _touch(bot_id: str, update: Any) -> None:
    """ثبت کاربرِ ربات و به‌روزرسانی آمار — مشترکِ همهٔ هندلرها."""
    user = getattr(update, "effective_user", None)
    if user is None:
        return
    r = repos()
    r.bots.add_user(bot_id, user.id)
    r.bots.set_user_info(bot_id, user.id, user.full_name or "", user.username or "")
    r.bots.update_stats(bot_id, received=1)
    r.bots.record_daily(bot_id, "messages_in", 1)


def _bot_exists(bot_id: str) -> bool:
    return repos().bots.get(bot_id) is not None


# ─ـ هندلرهای پیش‌فرض فاز ۳ ─────────────────────────────────────────────────────
async def on_start(update: Any, ctx: Any, bot_id: str) -> None:
    if not _bot_exists(bot_id):
        return
    await _touch(bot_id, update)
    await _reply_not_ready(update)


async def on_command(update: Any, ctx: Any, bot_id: str) -> None:
    if not _bot_exists(bot_id):
        return
    await _touch(bot_id, update)
    await _reply_not_ready(update)


async def on_text(update: Any, ctx: Any, bot_id: str) -> None:
    if not _bot_exists(bot_id):
        return
    await _touch(bot_id, update)
    await _reply_not_ready(update)


async def on_callback(update: Any, ctx: Any, bot_id: str) -> None:
    query = getattr(update, "callback_query", None)
    if not _bot_exists(bot_id):
        if query is not None:
            await _safe_answer(query)
        return
    await _touch(bot_id, update)
    if query is not None:
        await _safe_answer(query)
    await _reply_not_ready(update)


# ─ـ کمکی ────────────────────────────────────────────────────────────────────────
async def _reply_not_ready(update: Any) -> None:
    message = getattr(update, "effective_message", None)
    if message is None:
        return
    try:
        await message.reply_text(messages.NOT_STARTED)
    except Exception as exc:  # noqa: BLE001
        log.warning("ارسال پاسخِ «آماده نیست» ناموفق بود: %s", exc)


async def _safe_answer(query: Any) -> None:
    try:
        await query.answer()
    except Exception as exc:  # noqa: BLE001
        log.warning("پاسخ به callback ناموفق بود: %s", exc)
