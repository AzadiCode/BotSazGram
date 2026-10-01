"""مهاجرت ربات‌های قدیمی به گراف جریان نسخهٔ ۵.

ربات‌های legacy ساختار «commands + callbacks + rules» داشتند. این ماژول آن
ساختار را به گراف نود/سیم تبدیل می‌کند — بدون از دست رفتن داده.

قرارداد یال: مبدأ = پیام‌دهنده، مقصد = محتوای پیام (دکمه/پیوند/رسانه).

شناسهٔ کارت‌ها از محتوایشان مشتق می‌شود (آرام‌شونده) تا مهاجرتِ دوبارهٔ یک
ربات همان گراف را بدهد و گرافِ مهاجرت‌داده‌شده روی ذخیرهٔ مکرر پایدار بماند.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Optional

from app import config
from app.flow.model import Flow

_ID_RE = re.compile(r"[^a-z0-9_]")


def _short_id(prefix: str, name: str) -> str:
    """شناسهٔ کوتاه و پایدار از یک نام."""
    slug = _ID_RE.sub("", (name or "").lower())[:16] or "x"
    nid = f"{prefix}_{slug}"
    if len(nid) > config.NODE_ID_MAX:
        nid = nid[:16] + hashlib.sha1(nid.encode()).hexdigest()[:6]
    return nid


def _hash_id(prefix: str, *parts: str) -> str:
    """شناسهٔ پایدار بر اساس هشِ چند بخش (برای دکمه/رسانهٔ تکراری)."""
    key = "|".join(str(p) for p in parts)
    return f"{prefix}_" + hashlib.sha1(key.encode()).hexdigest()[:10]


def _media_node(cmd_name: str, media: Optional[dict]) -> Optional[dict[str, Any]]:
    """رسانهٔ یک دستور قدیمی → کارت image."""
    if not (isinstance(media, dict) and media.get("url")):
        return None
    return {
        "id": _hash_id("i", cmd_name, str(media.get("url"))),
        "kind": "image",
        "url": str(media["url"])[:500],
        "mediaType": str(media.get("type") or "photo"),
        "text": "",
    }


def legacy_to_graph(bot: Optional[dict]) -> dict[str, Any]:
    """ربات قدیمی (commands/callbacks/rules) را به گراف تبدیل می‌کند.

    اگر گراف واقعی از قبل وجود داشته باشد همان برگردانده نمی‌شود — از
    graph_of() استفاده کنید. این تابع همیشه از روی فیلدهای قدیمی می‌سازد.
    """
    bot = bot if isinstance(bot, dict) else {}
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    seen_ids: set[str] = set()

    def _add(node: dict[str, Any]) -> Optional[str]:
        if node["id"] in seen_ids:
            return node["id"]
        seen_ids.add(node["id"])
        nodes.append(node)
        return node["id"]

    # ── دستورها ──────────────────────────────────────────────────────────────
    for name, cmd in (bot.get("commands") or {}).items():
        if not isinstance(cmd, dict):
            continue
        nid = _add(
            {
                "id": _short_id("c", str(name)),
                "kind": "cmd",
                "name": str(name).lower()[:32],
                "text": str(cmd.get("response") or "")[: config.TG_TEXT_MAX],
                "description": str(cmd.get("description") or "")[: config.DESCRIPTION_MAX],
            }
        )
        # رسانهٔ دستور (photo قدیمی یا media جدید)
        media = cmd.get("media")
        if not media and cmd.get("photo"):
            media = {"type": "photo", "url": cmd["photo"]}
        if media:
            mid = _add(_media_node(str(name), media) or {})
            if mid:
                edges.append({"from": nid, "to": mid})
        # دکمه‌ها
        for row in cmd.get("buttons") or []:
            for b in row or []:
                if not isinstance(b, dict):
                    continue
                txt = str(b.get("text") or "").strip()
                if not txt:
                    continue
                if b.get("url"):
                    lid = _add(
                        {
                            "id": _hash_id("l", str(name), txt, str(b["url"])),
                            "kind": "link",
                            "act": "url",
                            "text": txt[: config.TG_CAPTION_MAX],
                            "url": str(b["url"])[:500],
                        }
                    )
                    if lid:
                        edges.append({"from": nid, "to": lid})
                    continue
                cbid = str(b.get("id") or txt)
                resp = str((cmd.get("callbacks") or {}).get(cbid, ""))
                rid = _add(
                    {
                        "id": _hash_id("r", str(name), cbid, resp),
                        "kind": "reply",
                        "label": txt,
                        "text": resp[: config.TG_TEXT_MAX],
                    }
                )
                if rid:
                    edges.append({"from": nid, "to": rid})

    # ── قوانین پاسخ خودکار ────────────────────────────────────────────────────
    for rule in bot.get("rules") or []:
        if not isinstance(rule, dict):
            continue
        kws = [str(k).strip() for k in (rule.get("keywords") or []) if str(k).strip()]
        if not kws:
            continue
        rid = rule.get("id") or _hash_id("t", *kws)
        nid = _add(
            {
                "id": _short_id("t", str(rid)),
                "kind": "trigger",
                "keywords": kws[:20],
                "mode": str(rule.get("mode") or "contains"),
                "label": kws[0][:64],
                "text": str(rule.get("response") or "")[: config.TG_TEXT_MAX],
            }
        )
        media = rule.get("media")
        if media:
            mid = _add(_media_node(str(rid), media) or {})
            if mid:
                edges.append({"from": nid, "to": mid})

    return {
        "version": config.FLOW_VERSION,
        "nodes": nodes,
        "edges": edges,
    }


def has_graph(bot: Optional[dict]) -> bool:
    """آیا این ربات گراف جریان واقعی دارد (نه فیلدهای قدیمی)؟"""
    if not isinstance(bot, dict):
        return False
    flow = bot.get("flow")
    return isinstance(flow, dict) and bool(flow.get("nodes"))


def graph_of(bot: Optional[dict]) -> dict[str, Any]:
    """گراف ذخیره‌شده، یا گرافِ مشتق‌شده از فیلدهای قدیمی.

    این تابع مسیر اصلی خواندن گراف است: اگر ربات گراف واقعی داشته باشد
    همان برمی‌گردد، در غیر این صورت از روی commands/rules ساخته می‌شود.
    """
    if has_graph(bot):
        return dict(bot.get("flow") or {})          # type: ignore[arg-type]
    return legacy_to_graph(bot)


def flow_from(bot: Optional[dict]) -> Flow:
    """یک نمونهٔ Flow از روی سند ربات (گراف ذخیره‌شده یا مهاجرت‌داده‌شده)."""
    return Flow(graph_of(bot))


def flow_stats(bot: Optional[dict]) -> dict[str, Any]:
    """آمار گراف یک ربات — برای پاسخ API."""
    return flow_from(bot).stats()
