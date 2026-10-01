"""قالب‌بندی پیام‌ها — جای‌گذاری متغیرها و امن‌سازی HTML.

دو تابع خالص (بدون وضعیت و بدون شبکه):

  html(text)    امن‌سازی متنِ نوشته‌شده توسط صاحب ربات: اگر تگ معتبر داشته
                باشد دست نمی‌زند (عمداً HTML نوشته)، در غیر این صورت escape.

  tpl(text, ctx)  جای‌گذاری در متن:
    {{var.name}}    متغیر دائمی کاربر
    {{user.field}}  فیلد شیء کاربر تلگرام
    {{temp.key}}    دادهٔ موقت این اجرا (خروجی کارت قبلی)
    {{input} }      میان‌گذار {{temp.last_input}} — آخرین ورودی کاربر

نکتهٔ امنیتی: اسکلتِ قالب را صاحب ربات نوشته (قابل اعتماد — HTML عمدی‌اش
دست‌نخورده می‌ماند)، ولی *مقدارهای* جای‌گذاری‌شده از کاربر نهایی می‌آیند
(مثلاً user.first_name یا متغیرهای ذخیره‌شده). بنابراین با escape=True
فقط مقدارها escape می‌شوند تا تزریق HTML ممکن نباشد.
"""
from __future__ import annotations

import html as _html_lib
import re
from typing import Any, Callable, Optional

_TPL_RE = re.compile(r"\{\{\s*([a-zA-Z_][\w.]*)\s*\}\}")
_TAG_RE = re.compile(r"</?[a-zA-Z][^>]*>")


class _Missing:
    """نشانگر «مسیر قالب ناشناخته» — با None (رشتهٔ خالی) متفاوز است."""


_MISSING = _Missing()

GetVar = Callable[[str], Any]
GetTemp = Callable[..., Any]


def html(text: Any) -> str:
    """متنِ صاحب ربات را امن می‌کند؛ اگر تگ معتبر داشته باشد دست نمی‌زند."""
    t = str(text or "")
    if _TAG_RE.search(t):
        return t
    return _html_lib.escape(t)


def tpl(
    text: Any,
    ctx: Optional[dict[str, Any]] = None,
    *,
    escape: bool = True,
) -> str:
    """جای‌گذاری در متن — بدون ctx، متن دست‌نخورده برمی‌گردد.

    ctx شامل این کلیدهاست:
      get_var(name)        خواندن متغیر دائمی
      get_temp(key)        خواندن دادهٔ موقت
      user                 شیء کاربر تلگرام
    اگر متغیر وجود نداشته باشد به رشتهٔ خالی تبدیل می‌شود.

    escape=True یعنی *مقدارهای* جای‌گذاری‌شده با html.escape امن می‌شوند
    (اسکلت قالب دست‌نخورده می‌ماند — چون صاحب ربات آن را نوشته).
    """
    raw = str(text or "")
    if "{{" not in raw or not ctx:
        return raw

    get_var: GetVar = ctx.get("get_var") or (lambda _n: None)
    get_temp: GetTemp = ctx.get("get_temp") or (lambda _k, _d=None: None)
    user: dict[str, Any] = ctx.get("user") or {}

    def _value(path: str) -> Any:
        if path == "input":
            return get_temp("last_input")
        if path.startswith("var."):
            return get_var(path[4:])
        if path.startswith("user."):
            return user.get(path[5:])
        if path.startswith("temp."):
            return get_temp(path[5:])
        return _MISSING

    def _sub(match: re.Match[str]) -> str:
        try:
            value = _value(match.group(1))
        except Exception:  # noqa: BLE001 — قالب هرگز نباید بشکند
            return match.group(0)
        if value is _MISSING:
            return match.group(0)
        if value is None:
            return ""
        text_value = str(value)
        return _html_lib.escape(text_value) if escape else text_value

    try:
        return _TPL_RE.sub(_sub, raw)
    except Exception:  # noqa: BLE001
        return raw


def ctx_from(
    get_var: GetVar,
    get_temp: GetTemp,
    user: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """ساختن ctx استاندارد برای tpl()."""
    return {"get_var": get_var, "get_temp": get_temp, "user": user or {}}
