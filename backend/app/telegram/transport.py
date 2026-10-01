"""لایهٔ انتقال — تبدیل دیکشنریِ «render» به پیام تلگرام.

این تنها جایی است که خروجیِ خالصِ `Flow.render` (دیکشنری بدون وابستگی به
تلگرام) به فراخوانی‌های واقعیِ Bot تلگرام تبدیل می‌شود. نگاشت:

    cb          → دکمهٔ اینلاین (callback_data)
    urlb        → دکمهٔ پیوند (url / webapp / share)
    reply_items → ReplyKeyboardMarkup زیر صفحه چت
    glass       → دکمهٔ شیشه‌ای (WebApp روی کیبورد سیستم)
    album       → sendMediaGroup
    url/mtype   → sendPhoto/Video/Audio/Animation/Document
    parseMode   → قالب‌بندی متن (HTML/Markdown/none)
    silent      → disable_notification
    protect     → protect_content
    editMode    → ویرایش پیام قبلی به‌جای پیام جدید

هیچ منطق جریانی اینجا نیست — این لایه فقط نمایش است. موتور (`engine.py`)
تصمیم می‌گیرد چه چیزی فرستاده شود و آمار را به‌روز می‌کند.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from telegram import (
    Bot,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaAnimation,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest

from app import config

log = logging.getLogger("GramSaz.transport")

_BUTTONS_PER_ROW = 3
_MAX_ROWS = 10
_LABEL_FALLBACK = "…"

# متد ارسالِ هر نوع رسانه
_MEDIA_SENDERS = {
    "photo": "send_photo",
    "video": "send_video",
    "audio": "send_audio",
    "animation": "send_animation",
    "document": "send_document",
}
_ALBUM_MEDIA = {
    "photo": InputMediaPhoto,
    "video": InputMediaVideo,
    "animation": InputMediaAnimation,
    "document": InputMediaDocument,
}


# ══════════════════════════════════════════════════════════════════════
# کیبوردها
# ══════════════════════════════════════════════════════════════════════
def _clip(label: Any, limit: int = config.TG_BUTTON_TEXT_MAX) -> str:
    """برچسب دکمه: تکخط و بریده‌شده — در برابر None/خالی مقاوم."""
    lines = str(label if label is not None else "").strip().splitlines()
    return (lines[0] if lines else "")[:limit].strip()


def _url_button(u: dict[str, Any]) -> InlineKeyboardButton:
    """ساخت دکمهٔ پیوند/شیشه‌ای/اشتراک از یک ورودیِ urlb."""
    label = _clip(u.get("text")) or "لینک"
    act = str(u.get("act") or "url").strip()
    if act == "webapp" and str(u.get("webapp") or "").startswith("https://"):
        return InlineKeyboardButton(label, web_app=WebAppInfo(url=u["webapp"]))
    if act == "share":
        return InlineKeyboardButton(label, switch_inline_query=str(u.get("shareText") or "").strip())
    url = str(u.get("url") or "").strip()
    return InlineKeyboardButton(label, url=url or "https://telegram.org")


def inline_rows(msg: dict[str, Any]) -> list[list[InlineKeyboardButton]]:
    """سطرهای کیبورد اینلاین: پیوندها هرکدام یک ردیف، بقیه هر ردیف ۳ دکمه."""
    out: list[list[InlineKeyboardButton]] = []
    for u in msg.get("urlb") or []:
        if isinstance(u, dict):
            out.append([_url_button(u)])
    cbs = [b for b in (msg.get("cb") or []) if isinstance(b, dict) and b.get("data")]
    for i in range(0, len(cbs), _BUTTONS_PER_ROW):
        out.append(
            [
                InlineKeyboardButton(_clip(b.get("text")) or "ادامه", callback_data=str(b["data"]))
                for b in cbs[i : i + _BUTTONS_PER_ROW]
            ]
        )
    return out[:_MAX_ROWS]


def inline_markup(msg: dict[str, Any]) -> Optional[InlineKeyboardMarkup]:
    rows = inline_rows(msg)
    return InlineKeyboardMarkup(rows) if rows else None


def _keyboard_button(item: dict[str, Any]) -> KeyboardButton:
    """یک آیتمِ reply_items → دکمهٔ کیبورد دائمی.

    ReplyKeyboard فقط WebApp و متن ساده را پشتیبانی می‌کند (نه url)؛
    پیوندهای url/share به دکمهٔ ساده تبدیل می‌شوند.
    """
    label = _clip(item.get("text")) or "دکمه"
    link = item.get("link") or {}
    if isinstance(link, dict) and str(link.get("act") or "") == "webapp":
        wa = str(link.get("webapp") or "").strip()
        if wa.startswith("https://"):
            return KeyboardButton(label, web_app=WebAppInfo(url=wa))
    return KeyboardButton(label)


def reply_markup(msg: dict[str, Any]) -> Optional[ReplyKeyboardMarkup]:
    """کیبورد دائمی: دکمهٔ شیشه‌ای بالای همه، سپس آیتم‌ها (هر ردیف ۲ دکمه)."""
    items = [i for i in (msg.get("reply_items") or []) if isinstance(i, dict)]
    glass = msg.get("glass")
    if not items and not glass:
        return None

    nd = msg.get("node") or {}
    rows: list[list[KeyboardButton]] = []
    if isinstance(glass, dict) and str(glass.get("webapp") or "").startswith("https://"):
        rows.append(
            [KeyboardButton(_clip(glass.get("text")) or "منو", web_app=WebAppInfo(url=glass["webapp"]))]
        )
    for i in range(0, len(items), 2):
        rows.append([_keyboard_button(it) for it in items[i : i + 2]])
    if not rows:
        return None

    return ReplyKeyboardMarkup(
        rows,
        resize_keyboard=bool(nd.get("resize", True)),
        one_time_keyboard=bool(nd.get("oneTime", False)),
    )


# ══════════════════════════════════════════════════════════════════════
# پرچم‌های ارسال
# ══════════════════════════════════════════════════════════════════════
def parse_mode(msg: dict[str, Any]) -> Optional[str]:
    """parseMode کارت: «none» یعنی بدون قالب‌بندی (متن خام)."""
    nd = msg.get("node") or {}
    pm = str(nd.get("parseMode") or "HTML").strip()
    if pm.lower() == "none":
        return None
    if pm == "HTML":
        return ParseMode.HTML
    if pm == "Markdown":
        return ParseMode.MARKDOWN
    return ParseMode.HTML


def _send_flags(msg: dict[str, Any]) -> dict[str, Any]:
    """پرچم‌های ارسال مشترک (Noneها حذف می‌شوند تا به تلگرام نروند)."""
    nd = msg.get("node") or {}
    out: dict[str, Any] = {}
    if nd.get("silent"):
        out["disable_notification"] = True
    if nd.get("protect"):
        out["protect_content"] = True
    return out


# ══════════════════════════════════════════════════════════════════════
# ارسال
# ══════════════════════════════════════════════════════════════════════
async def _send_album(bot: Bot, chat_id: int, msg: dict[str, Any]) -> bool:
    """آلبوم چندتایی — sendMediaGroup؛ کپشن روی اولین رسانه."""
    text = msg.get("text") or ""
    pm = parse_mode(msg)
    grp = []
    for i, it in enumerate((msg.get("album") or [])[: config.ALBUM_MAX]):
        if not isinstance(it, dict):
            continue
        url = str(it.get("url") or "").strip()
        if not url:
            continue
        cls = _ALBUM_MEDIA.get(str(it.get("type") or "photo"), InputMediaPhoto)
        cap = text if i == 0 else None
        grp.append(cls(media=url, caption=cap, parse_mode=pm))
    if len(grp) < config.ALBUM_MIN:
        # کمتر از ۲ رسانه → sendMediaGroup خطا می‌دهد؛ مثل رسانهٔ تنها بفرست
        if len(grp) == 1:
            msg = dict(msg)
            msg["mtype"] = str((msg.get("album") or [{}])[0].get("type") or "photo")
            msg["url"] = str((msg.get("album") or [{}])[0].get("url") or "")
            return await _send_media(bot, chat_id, msg)
        return False
    try:
        await bot.send_media_group(chat_id, grp, **_send_flags(msg))
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("ارسال آلبوم ناموفق بود: %s", exc)
        return False


async def _send_media(bot: Bot, chat_id: int, msg: dict[str, Any]) -> bool:
    """رسانهٔ تنها — sendPhoto/Video/Audio/Animation/Document."""
    url = str(msg.get("url") or "").strip()
    if not url:
        return False
    fn_name = _MEDIA_SENDERS.get(str(msg.get("mtype") or "photo"), "send_photo")
    fn = getattr(bot, fn_name, bot.send_photo)
    text = msg.get("text") or ""
    kw = _send_flags(msg)
    if msg.get("spoiler"):
        kw["has_spoiler"] = True
    if msg.get("asFile") and fn_name != "send_document":
        fn, fn_name = bot.send_document, "send_document"
    try:
        await fn(chat_id, url, caption=text or None, parse_mode=parse_mode(msg), **kw)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("ارسال رسانه ناموفق بود (%s): %s", fn_name, exc)
        # رسانه شکست خورد → حداقل متن برود
        if text:
            try:
                await bot.send_message(chat_id, text, parse_mode=parse_mode(msg))
                return True
            except Exception as exc2:  # noqa: BLE001
                log.warning("ارسال متنِ جایگزین ناموفق بود: %s", exc2)
        return False


async def _edit_or_send(
    bot: Bot, chat_id: int, msg: dict[str, Any], message: Any
) -> bool:
    """ویرایش پیام قبلی (editMode=edit) — در صورت عدم امکان، پیام جدید."""
    text = msg.get("text") or _LABEL_FALLBACK
    pm = parse_mode(msg)
    kb = inline_markup(msg)
    try:
        await message.edit_text(text, reply_markup=kb, parse_mode=pm)
        return True
    except BadRequest as exc:
        low = str(exc).lower()
        if "not changed" in low:
            return True
        if "message is not modified" in low:
            return True
        # پیام قبلی قابل ویرایش نیست (رسانه دارد و…) → پیام جدید
    except Exception as exc:  # noqa: BLE001
        log.warning("ویرایش پیام ناموفق بود: %s", exc)
    try:
        await bot.send_message(
            chat_id,
            text,
            reply_markup=kb,
            parse_mode=pm,
            **_send_flags(msg),
        )
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("ارسال پیام جدید پس از ویرایش ناموفق بود: %s", exc)
        return False


async def send(
    bot: Bot,
    chat_id: int,
    msg: Optional[dict[str, Any]],
    *,
    message: Any = None,
) -> bool:
    """ارسال یک پیامِ رندرشده. True یعنی چیزی رسید.

    `message` شیء پیام قبلی است (برای editMode=edit در پاسخ به دکمه).
    """
    if not msg or not isinstance(msg, dict):
        return False
    try:
        if msg.get("album"):
            return await _send_album(bot, chat_id, msg)
        if msg.get("url"):
            return await _send_media(bot, chat_id, msg)
        nd = msg.get("node") or {}
        if message is not None and str(nd.get("editMode") or "new").strip() == "edit":
            return await _edit_or_send(bot, chat_id, msg, message)
        # کیبورد دائمی اولویت دارد؛ در صورت نبود، دکمه‌های اینلاین
        rkb = reply_markup(msg)
        kb = inline_markup(msg)
        text = msg.get("text") or _LABEL_FALLBACK
        await bot.send_message(
            chat_id,
            text,
            reply_markup=rkb or kb,
            parse_mode=parse_mode(msg),
            **_send_flags(msg),
        )
        return True
    except BadRequest as exc:
        # بیشترین خطای رایج: متن تغییر نکرده یا دکمه نامعتبر
        if "not changed" in str(exc).lower():
            return True
        log.warning("ارسال پیام ناموفق بود (BadRequest): %s", exc)
        return False
    except Exception as exc:  # noqa: BLE001
        log.warning("ارسال پیام ناموفق بود: %s", exc)
        return False


async def typing(bot: Bot, chat_id: int) -> None:
    """نمایش حالت «در حال تایپ…» — نادیده‌گیری در صورت خطا."""
    try:
        await bot.send_chat_action(chat_id=chat_id, action="typing")
    except Exception:  # noqa: BLE001
        pass
