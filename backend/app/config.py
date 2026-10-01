"""خواندن متغیرهای محیطی، اعتبارسنجی و ثابت‌های سراسری.

هیچ رازی (توکن/کلید/رمز) در این فایل یا هر فایل دیگری وجود ندارد؛
همه‌چیز از env خوانده می‌شود. PLATFORM_BOT_TOKEN الزامی است.
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import timedelta, timezone

log = logging.getLogger("GramSaz")

# secret ربات مادر — مقداردهی در import زمان اجرا می‌شود
def mother_secret() -> str:
    """secret مسیر webhook ربات مادر (برای مقایسه در لایهٔ API)."""
    from app.telegram.mother import mother_secret as _mother_secret
    return _mother_secret()


from app import messages


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


# ── توکن و آدرس‌ها ────────────────────────────────────────────────────────
PLATFORM_BOT_TOKEN: str = _env("PLATFORM_BOT_TOKEN")
MONGODB_URI: str = _env("MONGODB_URI")
WEBAPP_URL: str = _env("WEBAPP_URL").rstrip("/")
WEBHOOK_URL: str = _env("WEBHOOK_URL").rstrip("/")
API_HOST: str = _env("API_HOST", "0.0.0.0")
API_PORT: int = int(_env("PORT") or _env("API_PORT") or "8000")

# WEBHOOK_URL فقط با https معتبر است (تلگرام set_webhook غیر-https را رد می‌کند)
if WEBHOOK_URL and not WEBHOOK_URL.startswith("https://"):
    log.error("WEBHOOK_URL باید با https شروع شود — مقدار فعلی نادیده گرفته شد")
    WEBHOOK_URL = ""

USE_WEBHOOK: bool = bool(WEBHOOK_URL)
WEBHOOK_PATH_PREFIX: str = "/tgwh"
MOTHER_WEBHOOK_PATH: str = f"{WEBHOOK_PATH_PREFIX}/mother"

# ── ادمین‌ها و امنیت ───────────────────────────────────────────────────────
ADMIN_IDS: frozenset[int] = frozenset(
    int(x) for x in _env("ADMIN_IDS").replace(" ", "").split(",") if x.lstrip("-").isdigit()
)
INIT_DATA_MAX_AGE: int = int(_env("INIT_DATA_MAX_AGE", "86400"))

# originهای مجاز برای CORS: WEBAPP_URL + (در حالت dev) از env
CORS_ORIGINS: tuple[str, ...] = tuple(
    {o for o in (WEBAPP_URL, *_env("DEV_CORS_ORIGINS").split(",")) if o}
)

# ── منطقهٔ زمانی ───────────────────────────────────────────────────────────
IRAN_TZ = timezone(timedelta(hours=3, minutes=30))


def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS


# ── ثابت‌های دامنه ─────────────────────────────────────────────────────────
MEDIA_TYPES: tuple[str, ...] = ("photo", "video", "audio", "animation", "document")

# نسخهٔ گراف جریان (نسخهٔ هدف بازنویسی)
FLOW_VERSION: int = 5
PORT_RUN: str = "run"
CB_PREFIX: str = "gs:"

# سقف‌های گراف
MAX_NODES: int = 400
MAX_EDGES: int = 800
NODE_ID_MIN: int = 2
NODE_ID_MAX: int = 24
MAX_CHAIN_DEPTH: int = 12  # جلوگیری از حلقهٔ بی‌نهایت در زنجیرهٔ کارت‌های منطقی

# سقف‌های تلگرام
TG_TEXT_MAX: int = 4096
TG_CAPTION_MAX: int = 1024
TG_CALLBACK_MAX: int = 64
TG_BUTTON_TEXT_MAX: int = 64
ALBUM_MIN: int = 2
ALBUM_MAX: int = 10

# موتور
TICKET_TTL: int = 900  # ۱۵ دقیقه مهلت نوشتن متن تیکت
TYPING_MAX_DELAY: float = 5.0

# احراز هویت وب
PBKDF2_ITERATIONS: int = 120_000
WEB_ACCOUNT_UID_START: int = 1_000_000
LOGIN_MAX_ATTEMPTS: int = 8
LOGIN_WINDOW: float = 60.0
VERIFICATION_CODE_TTL: int = 600
VERIFICATION_CODE_MAX_ATTEMPTS: int = 5
VERIFICATION_CODE_MAX_STORED: int = 500

# محدودیت ثبت‌نام: حداکثر ۲ حساب از هر IP در ۲۴ ساعت با فاصلهٔ ۱۰ دقیقه
REGISTER_MAX_PER_IP: int = 2
REGISTER_IP_WINDOW: int = 86400
REGISTER_IP_COOLDOWN: int = 600
REGISTER_MAX_PER_DEVICE: int = 1
REGISTER_COOLDOWN_MESSAGE_MINUTES: int = 10

# نام کاربری/رمز وب
USERNAME_MIN_LEN: int = 3
PASSWORD_MIN_LEN: int = 6
TELEGRAM_USERNAME_MIN_LEN: int = 3

# سکه و رفرال
REFERRAL_REWARD_NEW_USER: int = 50
REFERRAL_REWARD_REFERRER: int = 100

# سقف‌های ربات و رسانه
MAX_BOTS_PER_USER: int = 20
BOT_TOKEN_MIN_LEN: int = 30
BACKUP_VERSION: int = 4
TICKET_ADMIN_MAX: int = 20
TICKET_TEXT_MAX: int = 4000
BROADCAST_TEXT_MAX: int = 4096
SETTINGS_TEXT_MAX: int = 4000
DESCRIPTION_MAX: int = 60
MEDIA_MIN_BYTES: int = 100
MEDIA_PHOTO_MAX_BYTES: int = 10 * 1024 * 1024
MEDIA_FILE_MAX_BYTES: int = 50 * 1024 * 1024
UPLOAD_TIMEOUT: float = 60.0

# کارت HTTP (SSRF-safe)
HTTP_MAX_RESPONSE_BYTES: int = 2 * 1024 * 1024
HTTP_TIMEOUT: float = 15.0
HTTP_MAX_REDIRECTS: int = 3

# کارت AI
AI_BASE_URL: str = _env("AI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
AI_API_KEY: str = _env("AI_API_KEY")
AI_TIMEOUT: float = 30.0
AI_MAX_TOKENS: int = 1000

# رسانه (Catbox)
CATBOX_URL: str = "https://catbox.moe/user/api.php"
MEDIA_MAX_BYTES: int = 100 * 1024 * 1024


def validate() -> None:
    """اعتبارسنجی متغیرهای حیاتی؛ در صورت نقص با پیام روشن خارج می‌شود."""
    if not PLATFORM_BOT_TOKEN:
        log.critical("PLATFORM_BOT_TOKEN تنظیم نشده!")
        sys.exit(1)
    if not WEBAPP_URL:
        log.warning("WEBAPP_URL تنظیم نشده — دکمه WebApp کار نخواهد کرد")
    if not ADMIN_IDS:
        log.warning("ADMIN_IDS تنظیم نشده — پنل ادمین غیرفعال است")
