"""امنیت — اعتبارسنجی initData تلگرام، هش رمز عبور، توکن نشست.

فرمت هش رمز دقیقاً مثل legacy است (pbkdf2$<salt>$<hex>) تا اسناد قدیمی
بدون مهاجرت کار کنند. هش‌های قدیمیِ sha256 هنگام ورود موفق ارتقا می‌یابند.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import time
import urllib.parse

from app import config

log = logging.getLogger("GramSaz.security")

_PW_PREFIX = "pbkdf2$"  # الگوریتم ضمنی: sha256


def verify_init_data(init_data: str, bot_token: str, max_age: int | None = None) -> dict | None:
    """اعتبارسنجی HMAC دادهٔ Telegram WebApp.

    در صورت معتبر بودن، دیکشنری کاربر (فیلد user) را برمی‌گرداند؛
    در غیر این صورت None. هیچ استثنایی پرتاب نمی‌کند.
    """
    if not init_data or not bot_token:
        return None
    try:
        parsed = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
    except ValueError:
        return None

    received_hash = parsed.pop("hash", None)
    if not received_hash:
        log.warning("initData فاقد hash است")
        return None

    age_limit = config.INIT_DATA_MAX_AGE if max_age is None else max_age
    auth_date = parsed.get("auth_date")
    if auth_date:
        try:
            if time.time() - int(auth_date) > age_limit:
                log.warning("initData قدیمی است — پنل دوباره باز شود")
                return None
        except (TypeError, ValueError):
            return None

    data_check = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_hash, received_hash):
        log.warning("هش initData با مقدار محاسبه‌شده مطابقت ندارد")
        return None

    try:
        return json.loads(parsed.get("user", "{}"))
    except (ValueError, TypeError):
        return None


def hash_password(password: str, salt: str | None = None) -> str:
    """هش رمز با PBKDF2-SHA256 و نمک تصادفی."""
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), config.PBKDF2_ITERATIONS
    )
    return f"{_PW_PREFIX}{salt}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    """بررسی رمز در برابر هش ذخیره‌شده (PBKDF2 یا sha256 قدیمی)."""
    if not stored or not password:
        return False
    if stored.startswith(_PW_PREFIX):
        _, salt, digest = stored.split("$", 2)
        return hmac.compare_digest(hash_password(password, salt), stored)
    # هش قدیمی sha256 — برای امکان ارتقای خاموش مقایسه می‌شود
    return hmac.compare_digest(hashlib.sha256(password.encode()).hexdigest(), stored)


def password_needs_upgrade(stored: str | None) -> bool:
    """آیا هش ذخیره‌شده از نوع قدیمی sha256 است و باید ارتقا یابد؟"""
    return bool(stored) and not stored.startswith(_PW_PREFIX)


def new_auth_token() -> str:
    """توکن نشست وب (Bearer)."""
    return secrets.token_urlsafe(32)
