"""رجیستری مرکزی کارت‌های جریان — منبعِ واحد متادیتا.

هر کارت یک ورودی دارد: پورت‌های خروجی، دسته، برچسب، آیکون و فیلدهایش.
بک‌اند (اعتبارسنجی) و فرانت‌اند (پالت کارت‌ها و پنل ویژگی‌ها) هر دو از
این یک جا می‌خوانند. کارتی که اینجا نیست فقط پورت پیش‌فرض «run» دارد
(سازگاری رو به عقب با گراف‌های قدیمی).

انواع فیلد:
  string/text  رشتهٔ بریده‌شده (text فقط برای نمایش چندخطیِ فرانت است)
  enum         یکی از گزینه‌های `options`
  bool         درست/نادرست
  number       عدد در بازهٔ [min, max]
  ident        شناسه (حروف انگلیسی/عدد/زیرخط/نقطه)
  strlist      فهرست رشته‌ها
  url          پیوند (بررسی http(s) اگر `scheme` ست باشد)
"""
from __future__ import annotations

from typing import Any, Optional

from app import config

# ── دسته‌بندی کارت‌ها ──────────────────────────────────────────────────────
CAT_MESSAGE = "msg"       # پیام می‌فرستد
CAT_IO = "io"             # ورودی/خروجی کاربر
CAT_LOGIC = "logic"       # پیام نیست: اجرا می‌شود و مسیر می‌سازد
CAT_INTEGRATION = "int"   # شبکه می‌زند (api / ai)

# ── پورت‌ها ─────────────────────────────────────────────────────────────────
PORT_RUN = config.PORT_RUN

# ── سقف فیلدها (هم در اعتبارسنجی هم در فرانت یکسان) ─────────────────────────
ID_MAX = config.NODE_ID_MAX               # ۲۴ — شناسهٔ کارت
NAME_MAX = 32                             # نام دستور
LABEL_MAX = config.TG_BUTTON_TEXT_MAX     # ۶۴ — برچسب کارت
DESC_MAX = config.DESCRIPTION_MAX         # ۶۰
TEXT_MAX = config.TG_TEXT_MAX             # ۴۰۹۶ — متن پیام
CAPTION_MAX = config.TG_CAPTION_MAX       # ۱۰۲۴ — کپشن رسانه
PROMPT_MAX = 2000                         # متن درون کارت‌های تعاملی
URL_MAX = 500
VAR_MAX = 40                              # نام متغیر
VALUE_MAX = 200                           # مقدار مقایسه/تنظیم متغیر
KEYWORD_MAX = 60
KEYWORDS_MAX = 20
WORD_MAX = 30                             # کلمهٔ عبور تیکت
WORDS_MAX = 12
ALIAS_MAX = 6                             # نام مستعار دستور
DEPARTMENT_MAX = 60
AUTOREPLY_MAX = 1000
BODY_MAX = 2000                           # بدنهٔ درخواست API
MODEL_MAX = 60                            # نام مدل AI
REGEX_MAX = 200                           # الگوی کلیدواژه

# ── حالت‌ها و گزینه‌های شمارشی ───────────────────────────────────────────────
KEYWORD_MODES = ("exact", "contains", "regex")
MENU_MODES = ("glass", "persistent", "popup")     # شیشه‌ای / دائمی / شناور
BTN_STYLES = ("default", "glass")                  # ساده / شیشه‌ای
BTN_MODES = ("inline", "reply")                    # اینلاین / زیر صفحه چت
EDIT_MODES = ("new", "edit")                       # پیام جدید / ویرایش پیام قبلی
PARSE_MODES = ("HTML", "Markdown", "none")         # قالب‌بندی متن
LINK_ACTS = ("url", "webapp", "share")             # اکشن‌های کارت پیوند
TICKET_PRIO = ("low", "normal", "high")            # اولویت تیکت
VAR_OPS = ("eq", "neq", "contains", "gt", "lt", "exists", "nexists")
SET_OPS = ("set", "inc", "dec", "append")
HTTP_METHODS = ("GET", "POST")
AI_DEFAULT_MODEL = "gpt-4o-mini"


def _f(
    name: str,
    ftype: str,
    label: str,
    *,
    max: int = 0,
    min: float = 0.0,
    options: Any = None,
    required: bool = False,
    scheme: str = "",
    default: Any = None,
    list_max: int = 0,
) -> dict[str, Any]:
    """ساختن یک ورودی فیلد در رجیستری."""
    out: dict[str, Any] = {"name": name, "type": ftype, "label": label}
    if max:
        out["max"] = max
    if min:
        out["min"] = min
    if options is not None:
        out["options"] = list(options)
    if required:
        out["required"] = True
    if scheme:
        out["scheme"] = scheme
    if default is not None:
        out["default"] = default
    if list_max:
        out["list_max"] = list_max
    return out


# ── فیلدهای مشترک ────────────────────────────────────────────────────────────
def _send_opts() -> list[dict[str, Any]]:
    """گزینهٔ ارسالِ کارت‌های پیام‌دهنده (cmd/reply): ظاهر و جایگاه دکمه و …"""
    return [
        _f("btnStyle", "enum", "سبک دکمه", options=BTN_STYLES, default="default"),
        _f("btnMode", "enum", "جایگاه دکمه", options=BTN_MODES, default="inline"),
        _f("editMode", "enum", "ویرایش پیام", options=EDIT_MODES, default="new"),
        _f("parseMode", "enum", "قالب‌بندی", options=PARSE_MODES, default="HTML"),
        _f("silent", "bool", "بیصدا"),
        _f("protect", "bool", "جلوگیری از انتشار"),
        _f("webapp", "url", "مینی‌اپ شیشه‌ای", max=URL_MAX, scheme="https"),
    ]


# ── رجیستری اصلی ──────────────────────────────────────────────────────────────
CARD_REGISTRY: dict[str, dict[str, Any]] = {
    "cmd": {
        "ports": None,
        "cat": CAT_MESSAGE,
        "label": "دستور",
        "icon": "code",
        "fields": [
            _f("name", "ident", "نام دستور", max=NAME_MAX, required=True),
            _f("text", "text", "متن پاسخ", max=TEXT_MAX),
            _f("description", "string", "توضیحات", max=DESC_MAX),
            _f("aliases", "strlist", "نام مستعار", max=NAME_MAX, list_max=ALIAS_MAX),
            _f("showInMenu", "bool", "نمایش در منو", default=True),
            *_send_opts(),
        ],
    },
    "reply": {
        "ports": None,
        "cat": CAT_MESSAGE,
        "label": "پاسخ",
        "icon": "msg",
        "fields": [
            _f("label", "string", "برچسب دکمه", max=LABEL_MAX),
            _f("text", "text", "متن پاسخ", max=TEXT_MAX),
            _f("role", "enum", "نقش", options=("single", "group"), default="single"),
            *_send_opts(),
        ],
    },
    "image": {
        "ports": None,
        "cat": CAT_MESSAGE,
        "label": "رسانه",
        "icon": "image",
        "fields": [
            _f("url", "url", "پیوند رسانه", max=URL_MAX, scheme="http"),
            _f("text", "text", "کپشن", max=CAPTION_MAX),
            _f("mediaType", "enum", "نوع رسانه", options=config.MEDIA_TYPES, default="photo"),
            _f("spoiler", "bool", "اسپویلر"),
            _f("asFile", "bool", "ارسال به‌عنوان فایل"),
            _f("silent", "bool", "بیصدا"),
        ],
    },
    "album": {
        "ports": None,
        "cat": CAT_MESSAGE,
        "label": "آلبوم",
        "icon": "layers",
        "fields": [
            _f("caption", "text", "کپتن مشترک", max=CAPTION_MAX),
            _f("silent", "bool", "بیصدا"),
        ],
    },
    "link": {
        "ports": None,
        "cat": CAT_MESSAGE,
        "label": "پیوند",
        "icon": "link",
        "fields": [
            _f("act", "enum", "نوع پیوند", options=LINK_ACTS, default="url"),
            _f("url", "url", "پیوند", max=URL_MAX, scheme="http"),
            _f("webapp", "url", "آدرس مینی‌اپ", max=URL_MAX, scheme="https"),
            _f("shareText", "string", "متن اشتراک", max=URL_MAX),
            _f("text", "string", "برچسب", max=CAPTION_MAX),
            _f("btnStyle", "enum", "سبک دکمه", options=BTN_STYLES, default="default"),
        ],
    },
    "ticket": {
        "ports": None,
        "cat": CAT_IO,
        "label": "تیکت",
        "icon": "ticket",
        "fields": [
            _f("text", "text", "متن درخواست", max=PROMPT_MAX),
            _f("words", "strlist", "کلمات عبور", max=WORD_MAX, list_max=WORDS_MAX),
            _f("department", "string", "بخش", max=DEPARTMENT_MAX),
            _f("priority", "enum", "اولویت", options=TICKET_PRIO, default="normal"),
            _f("autoReply", "string", "پاسخ خودکار", max=AUTOREPLY_MAX),
            _f("acceptPhoto", "bool", "پذیرفتن عکس"),
        ],
    },
    "trigger": {
        "ports": None,
        "cat": CAT_IO,
        "label": "کلیدواژه",
        "icon": "spark",
        "fields": [
            _f("keywords", "strlist", "کلیدواژه‌ها", max=KEYWORD_MAX, list_max=KEYWORDS_MAX, required=True),
            _f("mode", "enum", "نوع تطبیق", options=KEYWORD_MODES, default="contains"),
            _f("label", "string", "برچسب", max=LABEL_MAX),
            _f("text", "text", "متن پاسخ", max=TEXT_MAX),
        ],
    },
    "input": {
        "ports": None,
        "cat": CAT_IO,
        "label": "دریافت ورودی",
        "icon": "pencil",
        "fields": [
            _f("var", "ident", "ذخیره در متغیر", max=VAR_MAX, required=True),
            _f("text", "text", "متن درخواست", max=PROMPT_MAX),
            _f("label", "string", "برچسب", max=LABEL_MAX),
        ],
    },
    "menu": {
        "ports": None,
        "cat": CAT_IO,
        "label": "منوی تعاملی",
        "icon": "menu",
        "fields": [
            _f("mode", "enum", "حالت نمایش", options=MENU_MODES, default="glass"),
            _f("title", "string", "عنوان", max=LABEL_MAX),
            _f("text", "text", "متن منو", max=PROMPT_MAX),
            _f("webapp", "url", "آدرس مینی‌اپ", max=URL_MAX, scheme="https"),
            _f("resize", "bool", "تطبیق اندازه", default=True),
            _f("oneTime", "bool", "یکبار مصرف"),
        ],
    },
    "keyboard": {
        "ports": None,
        "cat": CAT_IO,
        "label": "کیبورد دائمی",
        "icon": "kbd",
        "fields": [
            _f("text", "text", "متن", max=PROMPT_MAX),
            _f("resize", "bool", "تطبیق اندازه", default=True),
            _f("oneTime", "bool", "یکبار مصرف"),
            _f("silent", "bool", "بیصدا"),
        ],
    },
    "condition": {
        "ports": [
            {"id": "yes", "label": "اگر درست"},
            {"id": "no", "label": "اگر نادرست"},
        ],
        "cat": CAT_LOGIC,
        "label": "شرط",
        "icon": "branch",
        "fields": [
            _f("var", "ident", "متغیر", max=VAR_MAX, required=True),
            _f("op", "enum", "عملگر", options=VAR_OPS, default="eq"),
            _f("value", "string", "مقدار", max=VALUE_MAX),
            _f("label", "string", "برچسب", max=LABEL_MAX),
        ],
    },
    "setvar": {
        "ports": None,
        "cat": CAT_LOGIC,
        "label": "متغیر",
        "icon": "var",
        "fields": [
            _f("var", "ident", "نام متغیر", max=VAR_MAX, required=True),
            _f("op", "enum", "عملگر", options=SET_OPS, default="set"),
            _f("value", "string", "مقدار", max=VALUE_MAX),
            _f("label", "string", "برچسب", max=LABEL_MAX),
        ],
    },
    "random": {
        "ports": [
            {"id": "p1", "label": "مسیر ۱"},
            {"id": "p2", "label": "مسیر ۲"},
            {"id": "p3", "label": "مسیر ۳"},
            {"id": "p4", "label": "مسیر ۴"},
            {"id": "p5", "label": "مسیر ۵"},
        ],
        "cat": CAT_LOGIC,
        "label": "شاخهٔ تصادفی",
        "icon": "dice",
        "fields": [_f("label", "string", "برچسب", max=LABEL_MAX)],
    },
    "notify": {
        "ports": None,
        "cat": CAT_LOGIC,
        "label": "اعلان به ادمین",
        "icon": "bell",
        "fields": [
            _f("text", "text", "متن اعلان", max=PROMPT_MAX, required=True),
            _f("label", "string", "برچسب", max=LABEL_MAX),
        ],
    },
    "delay": {
        "ports": None,
        "cat": CAT_LOGIC,
        "label": "تاخیر و تایپ",
        "icon": "clock",
        "fields": [
            _f("secs", "number", "ثانیه", min=0.5, max=config.TYPING_MAX_DELAY, default=1.0),
            _f("typing", "bool", "نمایش تایپ", default=True),
        ],
    },
    "api": {
        "ports": [
            {"id": "ok", "label": "پاسخ موفق"},
            {"id": "fail", "label": "خطا"},
        ],
        "cat": CAT_INTEGRATION,
        "label": "فراخوانی API",
        "icon": "globe",
        "fields": [
            _f("url", "url", "آدرس API", max=URL_MAX, scheme="http", required=True),
            _f("method", "enum", "روش", options=HTTP_METHODS, default="GET"),
            _f("body", "text", "بدنه درخواست", max=BODY_MAX),
            _f("save_to", "ident", "ذخیره در متغیر", max=VAR_MAX),
            _f("label", "string", "برچسب", max=LABEL_MAX),
        ],
    },
    "ai": {
        "ports": [
            {"id": "ok", "label": "پاسخ دریافت شد"},
            {"id": "fail", "label": "خطا"},
        ],
        "cat": CAT_INTEGRATION,
        "label": "هوش مصنوعی",
        "icon": "spark",
        "fields": [
            _f("text", "text", "پرامپت", max=PROMPT_MAX, required=True),
            _f("model", "string", "مدل", max=MODEL_MAX, default=AI_DEFAULT_MODEL),
            _f("save_to", "ident", "ذخیره در متغیر", max=VAR_MAX),
            _f("label", "string", "برچسب", max=LABEL_MAX),
        ],
    },
}

# ── مجموعه‌های مشتق‌شده ────────────────────────────────────────────────────────
KINDS: frozenset[str] = frozenset(CARD_REGISTRY)
NODE_KINDS: tuple[str, ...] = tuple(CARD_REGISTRY)
PORTS: dict[str, list[dict[str, str]]] = {
    k: v["ports"] for k, v in CARD_REGISTRY.items() if v.get("ports")
}
LOGIC_KINDS: frozenset[str] = frozenset(
    {k for k, v in CARD_REGISTRY.items() if v["cat"] in (CAT_LOGIC, CAT_INTEGRATION)}
)
INT_KINDS: frozenset[str] = frozenset(
    {k for k, v in CARD_REGISTRY.items() if v["cat"] == CAT_INTEGRATION}
)
# کارت‌هایی که خروجی‌شان محتوای یک پیام است (دکمه/پیوند/رسانه)
MESSAGE_KINDS: frozenset[str] = frozenset(
    {k for k, v in CARD_REGISTRY.items() if v["cat"] in (CAT_MESSAGE, CAT_IO)}
)


# ── توابع پورت ─────────────────────────────────────────────────────────────────
def port_id(p: Any) -> str:
    """پورت (dict یا رشته) → شناسهٔ آن."""
    if isinstance(p, dict):
        return str(p.get("id") or PORT_RUN)
    return str(p or PORT_RUN)


def node_ports(nd: Any) -> list[dict[str, str]]:
    """پورت‌های خروجی یک کارت — همیشه حداقل [{"id": "run"}] برمی‌گرداند.

    اگر کارت خودش `outputs` صریح داشته باشد آن مقدم است (کارت‌های سفارشی).
    """
    if not isinstance(nd, dict):
        return [{"id": PORT_RUN, "label": PORT_RUN}]
    declared = nd.get("outputs")
    if isinstance(declared, list) and declared:
        out: list[dict[str, str]] = []
        for p in declared:
            pid = (p or {}).get("id") if isinstance(p, dict) else str(p)
            pid = str(pid or "").strip()[:ID_MAX]
            if pid:
                out.append(
                    {
                        "id": pid,
                        "label": (
                            str((p or {}).get("label") or pid)[:LABEL_MAX]
                            if isinstance(p, dict)
                            else pid
                        ),
                    }
                )
        if out:
            return out
    return PORTS.get(nd.get("kind")) or [{"id": PORT_RUN, "label": PORT_RUN}]


def card_meta(kind: str) -> Optional[dict[str, Any]]:
    """متادیتای عمومی یک کارت (بدون فیلدها) — برای پالت فرانت."""
    entry = CARD_REGISTRY.get(kind)
    if not entry:
        return None
    return {
        "kind": kind,
        "ports": node_ports({"kind": kind}),
        "cat": entry["cat"],
        "label": entry["label"],
        "icon": entry["icon"],
    }


def registry_payload() -> dict[str, Any]:
    """کل رجیستری برای ارسال به فرانت‌اند (پالت + پنل ویژگی‌ها)."""
    return {
        "version": config.FLOW_VERSION,
        "cards": {
            kind: {
                "kind": kind,
                "ports": node_ports({"kind": kind}),
                "cat": entry["cat"],
                "label": entry["label"],
                "icon": entry["icon"],
                "fields": entry["fields"],
            }
            for kind, entry in CARD_REGISTRY.items()
        },
        "cats": {
            CAT_MESSAGE: "پیام",
            CAT_IO: "ورودی/خروجی",
            CAT_LOGIC: "منطق",
            CAT_INTEGRATION: "یکپارچه‌سازی",
        },
    }
