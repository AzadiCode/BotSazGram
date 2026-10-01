"""لایهٔ جریان (Flow) — فاز ۴.

اجزای اصلی:
  registry    رجیستری مرکزی کارت‌ها (پورت‌ها، دسته، برچسب، فیلدها)
  templating  جای‌گذاری {{var/user/temp/input}} و HTML امن
  model       کلاس Flow — نمای گراف و رندر پیام (خالص، بدون شبکه)
  validator   clean_flow — اعتبارسنجی سخت‌گیرانه پیش از ذخیره
  migrate     تبدیل commands/rules قدیمی به گراف نسخهٔ ۵

موتور اجرا (فاز ۵) از همین لایه استفاده می‌کند: flow_from(bot) یک Flow
می‌دهد، render() پیام را می‌سازد و لایهٔ انتقال آن را می‌فرستد.
"""
from __future__ import annotations

from app.flow.migrate import (
    flow_from,
    flow_stats,
    graph_of,
    has_graph,
    legacy_to_graph,
)
from app.flow.model import Flow, ENGINE_RUN_KINDS
from app.flow.registry import (
    CARD_REGISTRY,
    INT_KINDS,
    KINDS,
    LOGIC_KINDS,
    PORTS,
    card_meta,
    node_ports,
    port_id,
    registry_payload,
)
from app.flow.templating import ctx_from, html, tpl
from app.flow.validator import clean_flow

__all__ = [
    # مدل
    "Flow",
    "ENGINE_RUN_KINDS",
    "flow_from",
    "graph_of",
    "has_graph",
    "flow_stats",
    # رجیستری
    "CARD_REGISTRY",
    "KINDS",
    "LOGIC_KINDS",
    "INT_KINDS",
    "PORTS",
    "card_meta",
    "node_ports",
    "port_id",
    "registry_payload",
    # اعتبارسنجی
    "clean_flow",
    # مهاجرت
    "legacy_to_graph",
    # قالب‌بندی
    "tpl",
    "html",
    "ctx_from",
]
