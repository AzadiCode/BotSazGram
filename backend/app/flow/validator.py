"""اعتبارسنجی گراف جریان پیش از ذخیره — clean_flow.

گراف از بیرون (فرانت‌اند) می‌آید و هرگز قابل اعتماد نیست. clean_flow یک
نسخهٔ پاک و نرمال‌شده برمی‌گرداند یا یک پیام خطای فارسی. همهٔ سقف‌ها و
گزینه‌های مجاز از رجیستری می‌آیند (منبع واحد).

خطاها به‌صورت (None, "پیام") برگردانده می‌شوند؛ موفقیت (graph, None).
"""
from __future__ import annotations

import re
from typing import Any, Optional

from app import config, messages
from app.flow.registry import (
    CARD_REGISTRY,
    ID_MAX,
    KEYWORD_MODES,
    REGEX_MAX,
    node_ports,
    port_id,
)

_ID_RE = re.compile(rf"[A-Za-z0-9_\-]{{{config.NODE_ID_MIN},{ID_MAX}}}")
_VAR_RE = re.compile(r"[A-Za-z0-9_.]")
_URL_SCHEMES = ("http://", "https://")


def _s(value: Any, limit: int = 0) -> str:
    """رشتهٔ امنِ بریده‌شده — None و هر نوعی را می‌پذیرد."""
    text = str(value if value is not None else "")
    return text[:limit] if limit else text


def _ident(value: Any, limit: int) -> str:
    """فقط حروف انگلیسی/عدد/زیرخط/نقطه را نگه می‌دارد."""
    return "".join(_VAR_RE.findall(_s(value, limit)))


def _bool(value: Any) -> bool:
    return bool(value)


def _number(value: Any, lo: float, hi: float, default: float) -> float:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, num))


def _enum(value: Any, options: list[Any], default: Any) -> Any:
    v = _s(value, 24).strip()
    return v if v in options else default


def _url(value: Any, limit: int, scheme: str) -> str:
    u = _s(value, limit).strip()
    if not u:
        return ""
    if scheme and not u.startswith(scheme):
        return ""          # نامعتبر — فراخواننده تصمیم می‌گیرد رد کند یا خالی بگذارد
    return u


def _strlist(value: Any, item_max: int, list_max: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_s(v, item_max).strip() for v in value[:list_max] if _s(v).strip()]


def _check_regex(pattern: str) -> Optional[str]:
    """بررسی امنیت الگوی regex — رد کردن ReDoS و الگوی ناقص."""
    if len(pattern) > REGEX_MAX:
        return messages.FLOW_REGEX_TOO_LONG
    depth = 0
    max_depth = 0
    for ch in pattern:
        if ch == "(":
            depth += 1
            max_depth = max(max_depth, depth)
        elif ch == ")":
            depth = max(0, depth - 1)
    if max_depth > 3:
        return messages.FLOW_REGEX_NESTED
    try:
        re.compile(pattern)
    except re.error:
        return messages.FLOW_REGEX_INVALID
    return None


def clean_flow(raw: Any) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """اعتبارسنجی سخت‌گیرانهٔ گراف پیش از ذخیره.

    خروجی: (گراف پاک, None) یا (None, پیام خطا).
    """
    if not isinstance(raw, dict):
        return None, messages.FLOW_BAD_SHAPE
    nodes_raw = raw.get("nodes")
    edges_raw = raw.get("edges") or []
    if not isinstance(nodes_raw, list) or not isinstance(edges_raw, list):
        return None, messages.FLOW_BAD_SHAPE
    if len(nodes_raw) > config.MAX_NODES:
        return None, messages.FLOW_TOO_MANY_NODES.format(max=config.MAX_NODES)
    if len(edges_raw) > config.MAX_EDGES:
        return None, messages.FLOW_TOO_MANY_EDGES.format(max=config.MAX_EDGES)

    nodes: dict[str, dict[str, Any]] = {}
    seen_cmd: set[str] = set()

    for nd in nodes_raw:
        if not isinstance(nd, dict):
            return None, messages.FLOW_NODE_NOT_OBJECT
        nid = _s(nd.get("id"), ID_MAX).strip()
        if not _ID_RE.fullmatch(nid):
            return None, messages.FLOW_BAD_ID.format(id=nid)
        kind = _s(nd.get("kind"), 24)
        entry = CARD_REGISTRY.get(kind)
        if entry is None:
            return None, messages.FLOW_BAD_KIND.format(kind=kind)

        try:
            x = int(float(nd.get("x") or 0))
            y = int(float(nd.get("y") or 0))
        except (TypeError, ValueError):
            x = y = 0
        clean: dict[str, Any] = {
            "id": nid,
            "kind": kind,
            "x": max(-20000, min(20000, x)),
            "y": max(-20000, min(20000, y)),
        }

        # فیلدهای عمومی از رجیستری
        for field in entry["fields"]:
            name, ftype = field["name"], field["type"]
            if ftype in ("string", "text"):
                clean[name] = _s(nd.get(name), field.get("max", 0))
            elif ftype == "enum":
                clean[name] = _enum(nd.get(name), field.get("options", []), field.get("default"))
            elif ftype == "bool":
                clean[name] = _bool(nd.get(name)) if name in nd else field.get("default", False)
            elif ftype == "number":
                clean[name] = _number(
                    nd.get(name), field.get("min", 0), field.get("max", 0), field.get("default", 0)
                )
            elif ftype == "ident":
                clean[name] = _ident(nd.get(name), field.get("max", 40))
            elif ftype == "strlist":
                clean[name] = _strlist(nd.get(name), field.get("max", 60), field.get("list_max", 20))
            elif ftype == "url":
                clean[name] = _url(nd.get(name), field.get("max", 500), field.get("scheme", ""))

        # پاکسازی outputs دلخواه کارت (پورت‌های سفارشی)
        declared = nd.get("outputs")
        if isinstance(declared, list) and declared:
            outs = []
            for p in declared:
                pid = _s((p or {}).get("id") if isinstance(p, dict) else p, ID_MAX).strip()
                if pid:
                    outs.append(
                        {
                            "id": pid,
                            "label": _s((p or {}).get("label") if isinstance(p, dict) else pid, 64),
                        }
                    )
            if outs:
                clean["outputs"] = outs

        # ── قوانین خاص هر کارت ─────────────────────────────────────────────
        if kind == "cmd":
            name = re.sub(r"[^a-z0-9_]", "", (clean.get("name") or "").lower())
            if not name:
                return None, messages.FLOW_CMD_NO_NAME.format(id=nid)
            if name in seen_cmd:
                return None, messages.FLOW_CMD_DUPLICATE.format(name=name)
            seen_cmd.add(name)
            clean["name"] = name
            aliases = [
                re.sub(r"[^a-z0-9_]", "", str(a).strip().lower())
                for a in (clean.get("aliases") or [])
                if str(a).strip()
            ][:6]
            if aliases:
                clean["aliases"] = aliases
            elif "aliases" in clean:
                clean.pop("aliases")
        elif kind == "trigger":
            kws = clean.get("keywords") or []
            if not kws:
                return None, messages.FLOW_NO_KEYWORDS.format(id=nid)
            if clean.get("mode") not in KEYWORD_MODES:
                return None, messages.FLOW_BAD_MATCH_MODE.format(id=nid)
            if clean.get("mode") == "regex":
                for kw in kws:
                    err = _check_regex(kw)
                    if err:
                        return None, f"کارت «{nid}»: {err}"
        elif kind == "link":
            act = clean.get("act") or "url"
            if act == "url" and clean.get("url") and not clean["url"].startswith(_URL_SCHEMES):
                return None, messages.FLOW_BAD_URL.format(id=nid)
            if act == "webapp" and not (clean.get("webapp") or "").startswith("https://"):
                return None, messages.FLOW_BAD_WEBAPP.format(id=nid)
        elif kind == "image":
            url = clean.get("url") or ""
            if url and not url.startswith(_URL_SCHEMES):
                return None, messages.FLOW_BAD_URL.format(id=nid)
        elif kind == "album":
            items = _clean_album_items(nd.get("items"))
            if not items:
                return None, messages.FLOW_EMPTY_ALBUM.format(id=nid)
            clean["items"] = items
        elif kind in ("condition", "setvar", "input"):
            if not clean.get("var"):
                return None, messages.FLOW_NO_VAR.format(id=nid)
            if clean["var"].startswith("temp.") and len(clean["var"]) <= len("temp."):
                return None, messages.FLOW_BAD_TEMP_VAR.format(id=nid)
        elif kind == "notify":
            if not (clean.get("text") or "").strip():
                return None, messages.FLOW_NO_NOTIFY_TEXT.format(id=nid)
        elif kind == "api":
            url = clean.get("url") or ""
            if not url:
                return None, messages.FLOW_NO_API_URL.format(id=nid)
            if not url.startswith(_URL_SCHEMES):
                return None, messages.FLOW_BAD_URL.format(id=nid)
        elif kind == "ai":
            if not (clean.get("text") or "").strip():
                return None, messages.FLOW_NO_PROMPT.format(id=nid)

        nodes[nid] = clean

    # ── یال‌ها ───────────────────────────────────────────────────────────────
    edges: list[dict[str, str]] = []
    seen_edge: set[tuple[str, str, str, str]] = set()
    for e in edges_raw:
        if not isinstance(e, dict):
            continue
        f, t = _s(e.get("from"), ID_MAX), _s(e.get("to"), ID_MAX)
        if f not in nodes or t not in nodes or f == t:
            continue
        fp = _s(e.get("from_port"), ID_MAX) or config.PORT_RUN
        tp = _s(e.get("to_port"), ID_MAX) or config.PORT_RUN
        # پورت مبدأ باید واقعاً یکی از پورت‌های این کارت باشد
        valid = {port_id(p) for p in node_ports(nodes[f])}
        if fp not in valid:
            fp = config.PORT_RUN
        key = (f, fp, t, tp)
        if key in seen_edge:
            continue
        seen_edge.add(key)
        edges.append({"from": f, "to": t, "from_port": fp, "to_port": tp})

    # عمق تودرتویی گروه‌ها: موتور فقط ۳ سطح را باز می‌کند
    kids: dict[str, list[str]] = {}
    for e in edges:
        if nodes[e["from"]].get("role") == "group" and nodes[e["to"]].get("role") == "group":
            kids.setdefault(e["from"], []).append(e["to"])

    def _depth(i: str, trail: set[str]) -> int:
        best = 0
        for j in kids.get(i, ()):
            if j in trail:
                continue
            best = max(best, 1 + _depth(j, trail | {j}))
        return best

    for nid in nodes:
        if nodes[nid].get("role") == "group" and _depth(nid, {nid}) > 2:
            return None, messages.FLOW_GROUP_TOO_DEEP.format(id=nid)

    out: dict[str, Any] = {
        "version": config.FLOW_VERSION,
        "nodes": list(nodes.values()),
        "edges": edges,
    }
    view = raw.get("view")
    if isinstance(view, dict):                       # جای دوربین روی بوم — فقط رابط کاربری
        try:
            out["view"] = {
                "x": int(view.get("x") or 0),
                "y": int(view.get("y") or 0),
                "z": min(2.4, max(0.35, float(view.get("z") or 1))),
            }
        except (TypeError, ValueError):
            pass
    return out, None


def _clean_album_items(raw: Any) -> list[dict[str, str]]:
    """رسانه‌های آلبوم: تا ALBUM_MAX مورد با پیوند http(s)."""
    if not isinstance(raw, list):
        return []
    items: list[dict[str, str]] = []
    for it in raw[: config.ALBUM_MAX]:
        if not isinstance(it, dict):
            continue
        url = _s(it.get("url"), 500).strip()
        if not url.startswith(_URL_SCHEMES):
            continue
        items.append(
            {
                "type": _enum(it.get("type"), list(config.MEDIA_TYPES), "photo"),
                "url": url,
            }
        )
    return items
