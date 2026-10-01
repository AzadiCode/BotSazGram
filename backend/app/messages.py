"""متن‌های فارسی سمت سرور (ربات مادر، موتور جریان، خطاها).

تمام متن‌های نمایش‌داده‌شده به کاربر اینجا متمرکز است. کلیدها انگلیسی‌اند.
"""
from __future__ import annotations

# ── ربات مادر ───────────────────────────────────────────────────────────────
MOTHER_HELP = (
    "🤖 <b>دستورهای ربات مادر</b>\n\n"
    "<code>/start</code> — باز کردن پنل\n"
    "<code>/mybots</code> — ربات‌های من\n"
    "<code>/tickets <bot_id></code> — آخرین تیکت‌ها\n"
    "<code>/reply <کد> متن</code> — پاسخ به یک تیکت\n\n"
    "💡 برای مدیریت کامل گراف و تیکت‌ها، دکمهٔ پنل را بزنید."
)

MOTHER_START = (
    "🤖 <b>سلام {name}!</b>\n\n"
    "✅ اکانت شما در GramSaz آماده شد.\n\n"
    "📌 <b>Username تلگرام شما:</b> @{username}\n\n"
    "👇 برای ثبت‌نام در پنل، به سایت برگردید و username خود را وارد کنید."
)

MOTHER_BANNED = "🚫 حساب شما مسدود شده است."
MOTHER_OPEN_PANEL = "🚀 باز کردن پنل مدیریت"
MOTHER_ADMIN_STATS = "📊 آمار پلتفرم"
MOTHER_NO_WEBAPP = "⚙️ WEBAPP_URL در سرور تنظیم نشده است."
MOTHER_NOT_ADMIN = "🚫 شما دسترسی ادمین ندارید."
MOTHER_NO_BOTS = "ربتی به حساب شما متصل نیست."
MOTHER_BOTS_HEADER = "🤖 <b>ربات‌ها</b>"
MOTHER_TICKETS_GIVE_ID = (
    "شناسهٔ ربات را بدهید:\n<code>/tickets <bot_id></code>"
)
MOTHER_NOT_YOUR_BOT = "🚫 این ربات مال شما نیست."
MOTHER_NO_TICKETS = "تیکتی ثبت نشده است."
MOTHER_TICKETS_HEADER = "🎟 <b>تیکت‌های @{bot}</b>"
MOTHER_REPLY_HINT = "\nبرای پاسخ: <code>/reply {tid} متن شما</code>"
MOTHER_REPLY_FORMAT = "قالب: <code>/reply <کد تیکت> <متن پاسخ></code>"
MOTHER_TICKET_NOT_FOUND = "تیکت <code>{tid}</code> نیافتم."
MOTHER_REPLY_SAVED_NOT_SENT = (
    "پاسخ ذخیره شد، اما ارسال نشد (ربات خاموش است؟) — از پنل دوباره بفرستید."
)
MOTHER_REPLY_SENT = "✅ پاسخ تیکت {tid} ارسال شد."
MOTHER_REPLY_FAILED = "ثبت پاسخ ناموفق بود."
MOTHER_TICKET_ANSWERED = "🎟 <b>پاسخ تیکت {tid}</b>\n\n{text}"
MOTHER_VERIFY_CODE = (
    "🔐 <b>کد تایید GramSaz</b>\n\n"
    "سلام {name}!\n\n"
    "کد ۶ رقمی شما:\n"
    "<code>{code}</code>\n\n"
    "⏰ این کد تا ۱۰ دقیقه معتبر است.\n"
    "🔒 این کد را با کسی به اشتراک نگذارید."
)

MOTHER_COMMANDS = (
    ("start", "باز کردن پنل مدیریت"),
    ("mybots", "ربات‌های من"),
    ("tickets", "تیکت‌های ربات"),
    ("reply", "پاسخ به یک تیکت"),
    ("help", "راهنما"),
)

MOTHER_STATS = (
    "📊 <b>آمار پلتفرم GramSaz</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "👥 <b>کاربران</b>\n"
    "   • کل کاربران: <code>{users_total}</code>\n"
    "   • ثبت‌شده: <code>{users_registered}</code>\n"
    "   • مسدودشده: <code>{users_banned}</code>\n\n"
    "🤖 <b>ربات‌ها</b>\n"
    "   • کل ربات‌ها: <code>{bots_total}</code>\n"
    "   • فعال: <code>{bots_active}</code>\n"
    "   • کاربران ربات‌ها: <code>{bot_users}</code>\n\n"
    "💬 <b>پیام‌ها</b>\n"
    "   • دریافتی: <code>{messages_in}</code>\n"
    "   • ارسالی: <code>{messages_out}</code>\n\n"
    "🪙 <b>سکه‌های توزیع‌شده:</b> <code>{coins}</code>\n\n"
    "💡 برای آمار دقیق‌تر، از پنل وب استفاده کنید."
)
MOTHER_STATS_WEBAPP = "🌐 مشاهده در پنل وب"

# ── کد تأیید ثبت‌نام ────────────────────────────────────────────────────────
VERIFICATION_CODE = (
    "🔐 <b>کد تأیید ثبت‌نام GramSaz</b>\n\n"
    "کد شما: <code>{code}</code>\n\n"
    "⏰ این کد تا ۱۰ دقیقه معتبر است.\n"
    "اگر شما درخواست نکرده‌اید، این پیام را نادیده بگیرید."
)

# ── موتور جریان ─────────────────────────────────────────────────────────────
FORCE_JOIN_MESSAGE = (
    "🔒 برای استفاده از این ربات، ابتدا عضو کانال شوید:\n"
    "👉 {channel}\n\n"
    "بعد از عضویت، دکمهٔ زیر را بزنید."
)
FORCE_JOIN_CHECK = "✅ عضو شدم"
FORCE_JOIN_STILL_NOT = "🚫 هنوز عضو کانال نیستید. ابتدا عضو شوید و دوباره امتحان کنید."
TICKET_PROMPT = "📝 لطفاً پیام خود را در یک پیام بفرستید. تا ۱۵ دقیقه فرصت دارید."
TICKET_TIMEOUT = "⏰ زمان ثبت تیکت به پایان رسید. دوباره تلاش کنید."
TICKET_REGISTERED = "✅ تیکت شما ثبت شد و به پشتیبانی ارسال شد. کد پیگیری: <code>{tid}</code>"
TICKET_REPLY = "🎟 <b>پاسخ تیکت {tid}</b>\n\n{text}"
TICKET_WORD_REQUIRED = (
    "❌ پیام باید با یکی از این کلمه‌ها شروع شود:\n{words}\n"
    "دوباره بنویسید یا دکمهٔ ثبت تیکت را بزنید."
)
TICKET_WORD_ADMIN_ONLY = "🚫 فقط پذیرندهٔ تیکت‌ها می‌تواند کلمات عبور را تغییر دهد."
TICKET_ALERT = (
    "🎯 <b>تیکت جدید — {tid}</b> {prio}\n"
    "👤 {name}\n"
    "🆔 <code>{uid}</code>\n"
    "{dept}"
    "📝\n{text}\n\n"
    "برای پاسخ در تلگرام: <code>/reply {tid} متن پاسخ</code>"
)
ENGINE_NO_START = (
    "👋 سلام! این ربات هنوز جریانی ندارد.\n"
    "صاحب ربات می‌تواند از پنل مدیریت، دستورها و پاسخ‌ها را بسازد."
)
ENGINE_NOTIFY = "🔔 <b>اعلان جریان</b>\n{text}"
INPUT_INVALID = "❌ ورودی نامعتبر است. دوباره تلاش کنید."
INPUT_STORED = "✅ ثبت شد."
NOT_STARTED = "ربات هنوز آماده نیست؛ کمی بعد دوباره تلاش کنید."

# ── کارت هوش مصنوعی ───────────────────────────────────────────────────────────
AI_NOT_CONFIGURED = (
    "🤖 هوش مصنوعی پیکربندی نشده — کلید API را در تنظیمات ربات قرار دهید."
)
AI_BAD_RESPONSE = "🤖 پاسخ هوش مصنوعی نامعتبر بود."

# ── اعتبارسنجی گراف جریان ─────────────────────────────────────────────────────
FLOW_BAD_SHAPE = "قالب نقشه نامعتبر است — کارت‌ها و سیم‌ها باید فهرست باشند."
FLOW_NODE_NOT_OBJECT = "هر کارت باید یک شیء باشد."
FLOW_BAD_ID = "شناسهٔ کارت نامعتبر است (۲ تا ۲۴ نویسه انگلیسی): {id!r}"
FLOW_BAD_KIND = "نوع کارت نامعتبر است: {kind!r}"
FLOW_TOO_MANY_NODES = "حداکثر {max} کارت مجاز است."
FLOW_TOO_MANY_EDGES = "حداکثر {max} اتصال مجاز است."
FLOW_CMD_NO_NAME = "کارت «{id}»: دستور باید نام داشته باشد."
FLOW_CMD_DUPLICATE = "دستور تکراری: /{name}"
FLOW_NO_KEYWORDS = "کارت «{id}»: حداقل یک کلیدواژه لازم است."
FLOW_BAD_MATCH_MODE = "کارت «{id}»: نوع تطبیق نامعتبر است."
FLOW_BAD_URL = "کارت «{id}»: پیوند باید با http:// یا https:// شروع شود."
FLOW_BAD_WEBAPP = "کارت «{id}»: آدرس مینی‌اپ باید با https:// شروع شود."
FLOW_EMPTY_ALBUM = "کارت «{id}»: آلبوم خالی است — حداقل یک رسانه لازم است."
FLOW_NO_VAR = "کارت «{id}»: نام متغیر لازم است."
FLOW_BAD_TEMP_VAR = "کارت «{id}»: نام متغیر موقت ناقص است."
FLOW_NO_NOTIFY_TEXT = "کارت «{id}»: متن اعلان لازم است."
FLOW_NO_API_URL = "کارت «{id}»: آدرس API لازم است."
FLOW_NO_PROMPT = "کارت «{id}»: پرامپت لازم است."
FLOW_GROUP_TOO_DEEP = "گروه «{id}» بیش از ۳ سطح تودرتو است — ساده‌اش کنید."
FLOW_REGEX_TOO_LONG = "الگوی regex بیش از ۲۰۰ نویسه است."
FLOW_REGEX_NESTED = "الگوی regex تو در توی عمیق دارد (خطر ReDoS)."
FLOW_REGEX_INVALID = "الگوی regex نامعتبر است."

# ── خطاهای API ──────────────────────────────────────────────────────────────
ERR_UNAUTHORIZED = "احراز هویت نشده‌اید."
ERR_FORBIDDEN = "دسترسی ندارید."
ERR_NOT_FOUND = "یافت نشد."
ERR_BAD_REQUEST = "درخواست نامعتبر است."
ERR_TOO_MANY = "تعداد تلاش‌ها بیش از حد مجاز است — یک دقیقه صبر کنید."
ERR_INTERNAL = "خطای داخلی سرور."
ERR_INVALID_TOKEN = "توکن ربات نامعتبر است."
ERR_BOT_EXISTS = "این ربات قبلاً اضافه شده."
ERR_BOT_LIMIT = "به سقف تعداد ربات‌ها رسیده‌اید."
ERR_NO_BOTS = "رباتی وجود ندارد."
ERR_INVALID_CREDENTIALS = "نام کاربری یا رمز عبور اشتباه است."
ERR_USER_EXISTS = "این نام کاربری قبلاً ثبت شده است."
ERR_REGISTRATION_LIMIT = "لطفاً {minutes} دقیقه دیگر تلاش کنید."
ERR_DEVICE_LIMIT = "از این دستگاه قبلاً حسابی ثبت شده است."
ERR_CODE_EXPIRED = "کد تایید منقضی شده است."
ERR_CODE_INVALID = "کد تایید نادرست است ({attempts}/{max} تلاش)."
ERR_CODE_NOT_FOUND = "کد تایید منقضی شده است."
ERR_CODE_MAX_ATTEMPTS = "تعداد تلاش‌ها بیش از حد مجاز."
ERR_NO_CODE_REQUESTED = "ابتدا کد تایید درخواست کنید."
ERR_TELEGRAM_USERNAME_REQUIRED = "نام کاربری تلگرام الزامی است."
ERR_TELEGRAM_USERNAME_NOT_FOUND = (
    "ابتدا ربات مادر را /start کنید تا حساب شما ساخته شود."
)
ERR_PASSWORD_SHORT = "رمز عبور باید حداقل ۶ کاراکتر باشد."
ERR_DEVICE_ID_REQUIRED = "شناسهٔ دستگاه الزامی است."
ERR_NO_FLOW = "گراف جریان وجود ندارد."
ERR_VALIDATION = "گراف نامعتبر است."
ERR_NO_TRIGGER = "حداقل یک کارت شروع لازم است."
ERR_NO_OWNER = "این ربات متعلق به شما نیست."
ERR_INVALID_INIT_DATA = "initData نامعتبر است."
ERR_NO_TOKEN = "توکن ارسال نشده است."
ERR_TOKEN_INVALID = "توکن نامعتبر یا منقضی شده است."
ERR_USERNAME_MIN = "نام کاربری باید حداقل {min} کاراکتر باشد."
ERR_USERNAME_INVALID = "نام کاربری فقط می‌تواند حروف انگلیسی، عدد و زیرخط باشد."
ERR_CODE_REQUIRED = "کد تایید الزامی است."
ERR_NO_REGISTERED = "این کاربر قبلاً ثبت‌نام کرده است. از بخش ورود استفاده کنید."
ERR_UPLOAD_FAILED = "خطا در آپلود فایل."
ERR_UPLOAD_TOO_SMALL = "فایل خیلی کوچک است."
ERR_UPLOAD_TOO_BIG = "حجم فایل باید کمتر از {max} مگابایت باشد."
ERR_NO_FILE = "فایلی ارسال نشده است."
ERR_RESTORE_EMPTY = "فایل پشتیبان خالی یا نامعتبر است."
ERR_NO_PERMISSION = "شما دسترسی مدیریت این ربات را ندارید."
ERR_NOT_ADMIN = "دسترسی ادمین ندارید."
OK_CODE_SENT = "کد تأیید ارسال شد."

# ── موفقیت ──────────────────────────────────────────────────────────────────
OK_SAVED = "ذخیره شد."
OK_APPLIED = "گراف با موفقیت اعمال شد."
OK_BOT_ADDED = "ربات با موفقیت اضافه شد."
OK_BOT_REMOVED = "ربات حذف شد."
OK_BOT_STARTED = "ربات روشن شد."
OK_BOT_STOPPED = "ربات خاموش شد."
OK_REGISTERED = "ثبت‌نام موفق"
OK_REFERRAL_GIFT = "ثبت‌نام موفق - ۵۰ کوین هدیه دریافت کردید!"
OK_LOGGED_OUT = "خروج با موفقیت انجام شد."
OK_BROADCAST_SENT = "پیام همگانی ارسال شد."
OK_BACKUP_RESTORED = "پشتیبان بازیابی شد."
OK_MENU_SYNCED = "منوی ربات همگام‌سازی شد."
OK_CODE_SENT = "کد تایید به تلگرام شما ارسال شد."
OK_BOT_ADD = "ربات @{username} با موفقیت اضافه شد."
OK_RESTORE = "بازیابی پشتیبان انجام شد: {parts}."
OK_UPLOAD = "فایل با موفقیت آپلود شد."
