"""توابع کمکی عمومی — زمان، شناسه‌ها، ماسک کردن رازها، ارقام فارسی."""
from __future__ import annotations

import hashlib
import secrets
import time
from datetime import datetime
from typing import Any

from app import config

_FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_EN_DIGITS = "0123456789"
_FA_TABLE = str.maketrans(_EN_DIGITS, _FA_DIGITS)
_EN_TABLE = str.maketrans(_FA_DIGITS, _EN_DIGITS)


def now() -> datetime:
    """همین حالا، با منطقهٔ زمانی ایران."""
    return datetime.now(config.IRAN_TZ)


def now_iso() -> str:
    return now().isoformat()


def today() -> str:
    """تاریخ امروز به‌صورت YYYY-MM-DD (برای آمار روزانه)."""
    return now().strftime("%Y-%m-%d")


def epoch() -> float:
    return time.time()


def to_fa_digits(value: Any) -> str:
    """جایگزینی ارقام انگلیسی با فارسی."""
    return str(value).translate(_FA_TABLE)


def to_en_digits(value: str) -> str:
    """جایگزینی ارقام فارسی/عربی با انگلیسی."""
    return value.translate(_EN_TABLE)


def clean_str(value: Any, limit: int = 0) -> str:
    """تبدیل به رشتهٔ ناصفرِ بریده‌شده از فضاهای اضافی."""
    text = str(value or "").strip()
    return text[:limit] if limit else text


def mask_secret(secret: str | None, keep: int = 4) -> str:
    """نمایش ماسک‌شدهٔ یک راز (توکن/کلید) — هرگز راز کامل برنمی‌گردد."""
    if not secret:
        return ""
    if len(secret) <= keep * 2:
        return "•" * len(secret)
    return f"{secret[:keep]}{'•' * 6}{secret[-keep:]}"


def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def new_referral_code() -> str:
    return secrets.token_urlsafe(8)


def new_bot_id(owner_uid: int, bot_token: str) -> str:
    """شناسهٔ ربات — همان الگوریتم legacy (سازگار با ربات‌های موجود)."""
    seed = f"{owner_uid}{bot_token}{time.time()}"
    return hashlib.md5(seed.encode()).hexdigest()[:12]


def new_ticket_id() -> str:
    return secrets.token_hex(6).upper()


def is_username(value: str) -> bool:
    """آیا مقدار یک username تلگرام معتبر است؟ (۵–۳۲ نویسهٔ الفبایی/زیرخط)."""
    name = clean_str(value).lstrip("@")
    return 5 <= len(name) <= 32 and name.replace("_", "").isalnum()
