"""ربات مادر — دستورهای start/help/mybots/tickets/reply + دکمهٔ پنل.

دو حالت اجرا:
  - polling: روی حلقهٔ مشترک با start_polling (بدون تردِ جدا)
  - webhook: روی همان حلقهٔ مشترک؛ آپدیت از مسیر Flask می‌آید

`deliver` از هر تردی (مثلاً ترد Flask) قابل صدا زدن است و کد تأیید ثبت‌نام
را از طریق ربات مادر می‌فرستد.
"""
from __future__ import annotations

import asyncio
import logging
import secrets
from html import escape
from typing import Any, Optional

from telegram import Bot, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.constants import ParseMode
from telegram.ext import Application, CallbackQueryHandler, CommandHandler

from app import config, messages
from app.db.repos import repos
from app.services import services
from app.telegram.factory import get_factory
from app.telegram.loop import bot_loop, fire_on_bot_loop, run_on_bot_loop

log = logging.getLogger("GramSaz.mother")

_mother: dict[str, Any] = {"bot": None, "loop": None, "app": None, "secret": secrets.token_urlsafe(24)}


def _html(text: Any) -> str:
    if not text:
        return ""
    return escape(str(text))


def _set_mother(
    bot: Optional[Bot] = None,
    loop: Optional[asyncio.AbstractEventLoop] = None,
    app: Optional[Any] = None,
) -> None:
    if bot is not None:
        _mother["bot"] = bot
    if loop is not None:
        _mother["loop"] = loop
    if app is not None:
        _mother["app"] = app


def mother_bot() -> Optional[Bot]:
    return _mother["bot"]


def mother_loop() -> Optional[asyncio.AbstractEventLoop]:
    return _mother["loop"]


def mother_secret() -> str:
    """secret مسیر webhook ربات مادر (برای مقایسه در لایهٔ API)."""
    return _mother["secret"]


def _reset() -> None:
    """تنظیم مجدد状態 (برای تست)."""
    _mother["bot"] = None
    _mother["loop"] = None
    _mother["app"] = None
    _mother["secret"] = secrets.token_urlsafe(24)


# ══════════════════════════════════════════════════════════════════════
# هندلرها
# ══════════════════════════════════════════════════════════════════════
async def mother_start(update: Any, ctx: Any) -> None:
    user = update.effective_user
    r = repos()
    r.users.ensure_telegram_user(user.id, (user.username or "").lower(), (user.full_name or "").strip())
    r.users.set_telegram_profile(user.id, user.username or "", user.first_name or "")

    stored = r.users.get(user.id)
    if stored is not None and stored.get("is_banned"):
        await update.effective_message.reply_text(messages.MOTHER_BANNED)
        return

    text = messages.MOTHER_START.format(
        name=_html(user.first_name or "دوست عزیز"),
        username=_html(user.username) or "ندارید",
    )
    rows: list[list[InlineKeyboardButton]] = []
    if config.WEBAPP_URL:
        rows.append(
            [InlineKeyboardButton(messages.MOTHER_OPEN_PANEL, web_app=WebAppInfo(url=config.WEBAPP_URL))]
        )
    if config.is_admin(user.id):
        rows.append([InlineKeyboardButton(messages.MOTHER_ADMIN_STATS, callback_data="admin_stats")])

    await update.effective_message.reply_text(
        text, parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(rows) if rows else None,
    )


async def mother_help(update: Any, ctx: Any) -> None:
    uid = update.effective_user.id
    if not config.is_admin(uid) and repos().users.get(uid) is None:
        return
    await update.effective_message.reply_text(
        messages.MOTHER_HELP, parse_mode=ParseMode.HTML
    )


async def mother_my_bots(update: Any, ctx: Any) -> None:
    uid = update.effective_user.id
    r = repos()
    bots = r.bots.list(uid) if r.users.get(uid) is not None else []
    if config.is_admin(uid) and not bots:
        bots = r.bots.list_all()[:20]
    if not bots:
        await update.effective_message.reply_text(messages.MOTHER_NO_BOTS)
        return
    lines = []
    for b in bots[:30]:
        state = "🟢" if get_factory().is_running(b["bot_id"]) else "⚪"
        lines.append(
            f"{state} <code>@{_html(b.get('bot_username') or '—')}</code> · "
            f"<code>{_html(b['bot_id'])}</code>"
        )
    await update.effective_message.reply_text(
        messages.MOTHER_BOTS_HEADER + "\n" + "\n".join(lines), parse_mode=ParseMode.HTML
    )


async def mother_list_tickets(update: Any, ctx: Any) -> None:
    r = repos()
    parts = (update.effective_message.text or "").split(maxsplit=1)
    bot_id = parts[1].strip() if len(parts) > 1 else ""
    bot = r.bots.get(bot_id) if bot_id else None
    if bot is None:
        mine = r.bots.list(update.effective_user.id)
        if len(mine) == 1:
            bot = r.bots.get(mine[0]["bot_id"])
        else:
            await update.effective_message.reply_text(
                messages.MOTHER_TICKETS_GIVE_ID, parse_mode=ParseMode.HTML
            )
            return
    if not _can_manage(bot, update.effective_user.id):
        await update.effective_message.reply_text(messages.MOTHER_NOT_YOUR_BOT)
        return

    tickets = r.tickets.list(bot["bot_id"], 10)
    if not tickets:
        await update.effective_message.reply_text(messages.MOTHER_NO_TICKETS)
        return
    out = [messages.MOTHER_TICKETS_HEADER.format(bot=_html(bot.get("bot_username") or ""))]
    for t in tickets:
        st = "✅" if t.get("reply") else "🔵"
        out.append(f"{st} <code>{_html(t.get('tid'))}</code> — {_html((t.get('text') or '')[:60])}")
    out.append(messages.MOTHER_REPLY_HINT.format(tid=tickets[0].get("tid")))
    await update.effective_message.reply_text("\n".join(out), parse_mode=ParseMode.HTML)


async def mother_reply_ticket(update: Any, ctx: Any) -> None:
    parts = (update.effective_message.text or "").split(maxsplit=2)
    if len(parts) < 3:
        await update.effective_message.reply_text(
            messages.MOTHER_REPLY_FORMAT, parse_mode=ParseMode.HTML
        )
        return
    tid, text = parts[1].strip().upper(), parts[2].strip()
    uid = update.effective_user.id

    target = _find_ticket_bot(tid, uid)
    if target is None:
        await update.effective_message.reply_text(
            messages.MOTHER_TICKET_NOT_FOUND.format(tid=_html(tid)), parse_mode=ParseMode.HTML
        )
        return

    if not repos().tickets.reply(target["bot_id"], tid, text[: config.TICKET_TEXT_MAX]):
        await update.effective_message.reply_text(messages.MOTHER_REPLY_FAILED)
        return

    ticket = next(
        (
            t
            for t in repos().tickets.list(target["bot_id"], 200)
            if t.get("tid") == tid
        ),
        None,
    )
    sub = get_factory().get_bot_instance(target["bot_id"])
    if sub is not None and ticket is not None:
        try:
            await get_factory().bot_call(
                target["bot_id"],
                lambda: sub.send_message(
                    ticket["uid"],
                    messages.MOTHER_TICKET_ANSWERED.format(tid=tid, text=_html(text)),
                    parse_mode=ParseMode.HTML,
                ),
            )
            await update.effective_message.reply_text(
                messages.MOTHER_REPLY_SENT.format(tid=tid), parse_mode=ParseMode.HTML
            )
            return
        except Exception as exc:  # noqa: BLE001
            log.warning("ارسال پاسخ تیکت %s ناموفق بود: %s", tid, exc)
    await update.effective_message.reply_text(messages.MOTHER_REPLY_SAVED_NOT_SENT)


async def mother_callback(update: Any, ctx: Any) -> None:
    query = update.callback_query
    await query.answer()
    user = query.from_user
    data = query.data or ""

    if data == "admin_stats":
        if not config.is_admin(user.id):
            await query.message.reply_text(messages.MOTHER_NOT_ADMIN)
            return
        await _send_stats(query.message)
        return

    await query.message.reply_text(messages.MOTHER_HELP, parse_mode=ParseMode.HTML)


async def _send_stats(message: Any) -> None:
    try:
        stats = services().stats.platform()
    except Exception as exc:  # noqa: BLE001
        log.error("دریافت آمار ناموفق بود: %s", exc)
        await message.reply_text("❌ خطا در دریافت آمار.")
        return
    text = messages.MOTHER_STATS.format(
        users_total=stats["users"]["total"],
        users_registered=stats["users"]["registered"],
        users_banned=stats["users"]["banned"],
        bots_total=stats["bots"]["total"],
        bots_active=stats["bots"]["active"],
        bot_users=stats["bots"]["bot_users"],
        messages_in=stats["bots"]["messages_received"],
        messages_out=stats["bots"]["messages_sent"],
        coins=stats["users"]["coins"],
    )
    rows: list[list[InlineKeyboardButton]] = []
    if config.WEBAPP_URL:
        rows.append(
            [InlineKeyboardButton(messages.MOTHER_STATS_WEBAPP, web_app=WebAppInfo(url=config.WEBAPP_URL))]
        )
    await message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(rows) if rows else None,
    )


# ── کمکی ────────────────────────────────────────────────────────────────────────
def _can_manage(bot: Optional[dict], uid: int) -> bool:
    if bot is None:
        return False
    admins = {int(x) for x in (bot.get("ticket_admins") or []) if str(x).lstrip("-").isdigit()}
    admins |= {int(bot.get("owner_uid") or 0)} | set(config.ADMIN_IDS)
    return uid in admins


def _find_ticket_bot(tid: str, uid: int) -> Optional[dict]:
    """رباتی که این تیکت به آن است و کاربر اجازهٔ مدیریتش را دارد."""
    r = repos()
    for bot in r.bots.list_all():
        if not _can_manage(bot, uid):
            continue
        if any(t.get("tid") == tid for t in r.tickets.list(bot["bot_id"], 200)):
            return bot
    return None


# ══════════════════════════════════════════════════════════════════════
# راه‌اندازی
# ══════════════════════════════════════════════════════════════════════
def build_mother_handlers() -> list:
    return [
        CommandHandler("start", mother_start),
        CommandHandler("mybots", mother_my_bots),
        CommandHandler("tickets", mother_list_tickets),
        CommandHandler("reply", mother_reply_ticket),
        CommandHandler("help", mother_help),
        CallbackQueryHandler(mother_callback),
    ]


def _build_app() -> Any:
    if not config.PLATFORM_BOT_TOKEN:
        raise RuntimeError("PLATFORM_BOT_TOKEN تنظیم نشده")
    app = Application.builder().token(config.PLATFORM_BOT_TOKEN).build()
    for handler in build_mother_handlers():
        app.add_handler(handler)
    return app


def _set_my_commands(app: Any) -> None:
    try:
        run_on_bot_loop(
            app.bot.set_my_commands(
                [BotCommand(name, desc) for name, desc in messages.MOTHER_COMMANDS]
            )
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("تنظیم command menu ناموفق بود: %s", exc)


def start_mother_polling() -> None:
    """ربات مادر روی حلقهٔ مشترک با polling (بدون ترد جدا)."""
    app = _build_app()
    run_on_bot_loop(app.initialize())
    _set_my_commands(app)
    run_on_bot_loop(app.start())
    run_on_bot_loop(app.updater.start_polling(drop_pending_updates=True))
    _set_mother(bot=app.bot, loop=bot_loop(), app=app)
    log.info("🤖 ربات مادر روی polling روشن شد")


def start_mother_webhook() -> None:
    """ربات مادر روی webhook (روی حلقهٔ مشترک)."""
    app = _build_app()
    run_on_bot_loop(app.initialize())
    _set_my_commands(app)
    run_on_bot_loop(
        app.bot.set_webhook(
            url=f"{config.WEBHOOK_URL}{config.MOTHER_WEBHOOK_PATH}",
            secret_token=_mother["secret"],
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
        )
    )
    _set_mother(bot=app.bot, loop=bot_loop(), app=app)
    log.info("🤖 ربات مادر روی webhook روشن شد")


def dispatch_webhook(secret: str, update: Update) -> bool:
    """از مسیر Flask /tgwh/mother صدا زده می‌شود. False یعنی secret اشتباه است."""
    app = _mother["app"]
    if app is None or secret != _mother["secret"]:
        return False
    fire_on_bot_loop(app.process_update(update))
    return True


# ══════════════════════════════════════════════════════════════════════
# ارسال پیام از طریق ربات مادر
# ══════════════════════════════════════════════════════════════════════
async def _send_async(bot: Bot, chat_id: int, text: str) -> bool:
    try:
        await bot.send_message(chat_id, text, parse_mode=ParseMode.HTML)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("ارسال پیام ربات مادر به %s ناموفق بود: %s", chat_id, exc)
        return False


def deliver(chat_id: int, text: str) -> bool:
    """ارسال یک پیام از طریق ربات مادر — از هر تردی قابل صدا زدن است.

    خروجی False یعنی ربات مادر هنوز آماده نیست یا ارسال شکست خورد.
    این تابع synchronous است و روی نتیجهٔ ارسال منتظر می‌ماند.
    """
    bot = mother_bot()
    loop = mother_loop()
    if bot is None or loop is None:
        return False
    try:
        current = asyncio.get_running_loop()
    except RuntimeError:
        current = None
    if current is loop:
        # از درون حلقهٔ ربات مادر صدا زده شده؛ نمی‌توانیم منتظر بمانیم.
        loop.create_task(_send_async(bot, chat_id, text))
        return True
    try:
        return bool(run_on_bot_loop(_send_async(bot, chat_id, text), timeout=15.0))
    except Exception as exc:  # noqa: BLE001
        log.warning("deliver به %s ناموفق بود: %s", chat_id, exc)
        return False
