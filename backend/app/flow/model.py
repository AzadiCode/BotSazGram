"""مدل گراف جریان — نمای امن و سریعِ گراف یک ربات.

Flow یک «نمای فقط‌خواندنی» از روی دیکشنری ذخیره‌شده می‌سازد: نودها و
یال‌ها را پاکسازی می‌کند، پورت‌ها را ایندکس می‌کند و امکان پرس‌وجو می‌دهد.
هیچ شبکه‌ای صدا نمی‌زند و هیچ وضعیتی در خود نگه نمی‌دارد — کاملاً خالص.

قرارداد یال: {"from", "to", "from_port", "to_port"}.
مبدأ = پیام‌دهنده، مقصد = محتوای پیام (دکمه/پیوند/رسانه) یا مسیر منطقی.
"""
from __future__ import annotations

import random
import re
from typing import Any, Optional

from app import config, messages
from app.flow import templating
from app.flow.registry import (
    INT_KINDS,
    KINDS,
    LOGIC_KINDS,
    PORTS,
    PORT_RUN,
    node_ports,
    port_id,
)

_CB = config.CB_PREFIX
_MAX_DEPTH = config.MAX_CHAIN_DEPTH

# کارت‌هایی که رندر می‌توانند پیام واقعی بسازند
_RENDERABLE = frozenset(
    {
        "cmd", "reply", "image", "album", "link",
        "ticket", "trigger", "input", "menu", "keyboard",
    }
)

# کارت‌هایی که موتور (فاز ۵) باید اجرایشان کند: api/ai شبکه می‌زنند و
# delay صبر می‌کند. resolve_action این‌ها را به موتور برمی‌گرداند تا
# به‌جای ارزیابیِ همگام، اجرای async شوند.
ENGINE_RUN_KINDS: frozenset[str] = frozenset(INT_KINDS | {"delay"})


class Flow:
    """نمای امن و سریعِ گراف جریان یک ربات."""

    def __init__(self, raw: Any) -> None:
        raw = raw if isinstance(raw, dict) else {}
        self.nodes: dict[str, dict[str, Any]] = {}
        for nd in raw.get("nodes") or []:
            if isinstance(nd, dict) and nd.get("id") and nd.get("kind") in KINDS:
                self.nodes[str(nd["id"])] = nd

        self.edges: list[dict[str, str]] = []
        for e in raw.get("edges") or []:
            if not isinstance(e, dict):
                continue
            f, t = str(e.get("from") or ""), str(e.get("to") or "")
            if f in self.nodes and t in self.nodes and f != t:
                self.edges.append(
                    {
                        "from": f,
                        "to": t,
                        "from_port": str(e.get("from_port") or "").strip()[: config.NODE_ID_MAX] or PORT_RUN,
                        "to_port": str(e.get("to_port") or "").strip()[: config.NODE_ID_MAX] or PORT_RUN,
                    }
                )

        # ── مهاجرت در زمان خواندن (گراف‌های نسخهٔ ۳ و قدیمی‌تر) ──
        # یال‌های قدیمی پورت ندارند؛ کارت شرط با «ترتیب» یال‌ها کار می‌کرد:
        # اولین یال = yes، دومی = no. همین قانون را به پورت تبدیل می‌کنیم
        # تا گراف‌های قدیمی بدون تغییر داده با معنای جدید کار کنند.
        for nid, nd in self.nodes.items():
            if nd.get("kind") not in PORTS:
                continue
            declared = [port_id(p) for p in PORTS[nd["kind"]]]
            mine = [e for e in self.edges if e["from"] == nid]
            if not mine:
                continue
            taken = {e["from_port"] for e in mine if e["from_port"] != PORT_RUN}
            need = [p for p in declared if p not in taken]
            for e in mine:
                if e["from_port"] != PORT_RUN:
                    continue
                if not need:
                    break
                e["from_port"] = need.pop(0)

        self._reindex()

    # ─ـ ایندکس ──────────────────────────────────────────────────────────────
    def _reindex(self) -> None:
        """ساختارهای دسترسی سریع — کلید (node, port)."""
        self._out: dict[tuple[str, str], list[tuple[str, str]]] = {}
        self._in: dict[tuple[str, str], list[tuple[str, str]]] = {}
        for e in self.edges:
            self._out.setdefault((e["from"], e["from_port"]), []).append(
                (e["to"], e["to_port"])
            )
            self._in.setdefault((e["to"], e["to_port"]), []).append(
                (e["from"], e["from_port"])
            )
            # کلید بدون پورت هم همهٔ یال‌ها را ببیند (برای ins/outs قدیمی)
            self._out.setdefault((e["from"], PORT_RUN), [])
            self._in.setdefault((e["to"], PORT_RUN), [])

    # ── دسترسی ───────────────────────────────────────────────────────────────
    def node(self, nid: Any) -> Optional[dict[str, Any]]:
        return self.nodes.get(str(nid)) if nid is not None else None

    def outs(self, nid: Any, port: Optional[str] = PORT_RUN) -> list[dict[str, Any]]:
        """کارتهای مقصدِ یک پورت خاص. port=None یعنی همهٔ یال‌های خروجی."""
        n = str(nid)
        if port is None:
            targets: set[str] = set()
            for (src, _p), tgts in self._out.items():
                if src == n:
                    targets.update(t for t, _tp in tgts)
            return [self.nodes[t] for t in targets]
        return [self.nodes[t] for t, _tp in self._out.get((n, port), [])]

    def out_edges(self, nid: Any, port: str = PORT_RUN) -> list[dict[str, str]]:
        """یال‌های خروجی یک پورت — برای ساختن دکمه با مقصدِ پورت‌دار."""
        n = str(nid)
        return [
            {"to": t, "to_port": tp, "from": n, "from_port": port}
            for t, tp in self._out.get((n, port), [])
        ]

    def ins(self, nid: Any) -> list[dict[str, Any]]:
        """همهٔ کارت‌هایی که به این کارت وصل‌اند (بدون توجه به پورت)."""
        n = str(nid)
        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        for (t, _tp), srcs in self._in.items():
            if t != n:
                continue
            for f, _fp in srcs:
                if f not in seen:
                    seen.add(f)
                    out.append(self.nodes[f])
        return out

    def edge(self, src_id: Any, tgt_id: Any) -> Optional[dict[str, str]]:
        for e in self.edges:
            if e["from"] == str(src_id) and e["to"] == str(tgt_id):
                return e
        return None

    # ── شناسهٔ دکمه‌ها ────────────────────────────────────────────────────────
    @staticmethod
    def cid(act: str, src: Any, tgt: Any = None, port: Any = None) -> str:
        """callback_data: «act:src:tgt@port».

        پورت مقصد هم کد می‌شود تا دکمهٔ «اگر درست» واقعاً از پورت yes بیاید.
        """
        sid = src["id"] if isinstance(src, dict) else (src or "_")
        tid = tgt["id"] if isinstance(tgt, dict) else (tgt or "")
        port_s = str(port or "").strip()
        tail = f"{tid}@{port_s}" if port_s and port_s != PORT_RUN else tid
        return f"{_CB}{act}:{sid}:{tail}"[: config.TG_CALLBACK_MAX]

    def parse(self, data: Any) -> Optional[dict[str, Any]]:
        """callback_data → {act, src, tgt, port, raw} | None.

        اعتبارسنجی با گراف زنده: مبدأ باید در این گراف باشد.
        """
        s = str(data or "")
        if not s.startswith(_CB):
            return None
        parts = s[len(_CB):].split(":", 2)
        if not parts or not parts[0]:
            return None
        act = parts[0]
        src = self.node(parts[1]) if len(parts) > 1 and parts[1] else None
        if src is None:
            return None
        raw = parts[2] if len(parts) > 2 else ""
        port = PORT_RUN
        if "@" in raw:
            raw, port = raw.rsplit("@", 1)
            port = port.strip()[: config.NODE_ID_MAX] or PORT_RUN
        tgt = self.node(raw) if raw else None
        return {"act": act, "src": src, "tgt": tgt, "port": port, "raw": raw}

    # ── ورودی‌ها ──────────────────────────────────────────────────────────────
    def cmd_nodes(self) -> list[dict[str, Any]]:
        return [n for n in self.nodes.values() if n.get("kind") == "cmd"]

    def entry_for(self, name: Any) -> Optional[dict[str, Any]]:
        """کارت دستوری که این نام (یا نام مستعارش) را دارد — یا None."""
        want = (name or "").strip().lstrip("/").lower()
        if not want:
            return None
        for n in self.cmd_nodes():
            if (n.get("name") or "").strip().lstrip("/").lower() == want:
                return n
            for a in n.get("aliases") or []:
                if str(a).strip().lstrip("/").lower() == want:
                    return n
        return None

    def keyword_nodes(self) -> list[dict[str, Any]]:
        return [n for n in self.nodes.values() if n.get("kind") == "trigger"]

    def match_keyword(self, text: Any) -> Optional[dict[str, Any]]:
        """اولین کارت کلیدواژه‌ای که با این متن تطبیق دارد — یا None."""
        t = (text or "").strip().lower()
        if not t:
            return None
        for n in self.keyword_nodes():
            mode = n.get("mode") or "contains"
            for kw in n.get("keywords") or []:
                k = str(kw).strip().lower()
                if not k:
                    continue
                if mode == "exact" and t == k:
                    return n
                if mode == "contains" and k in t:
                    return n
                if mode == "regex":
                    try:
                        if re.search(str(kw), str(text or ""), re.IGNORECASE):
                            return n
                    except re.error:
                        pass
        return None

    # ── رندر: نود + سیم‌های خروجی‌اش → پیام آماده ─────────────────────────────
    def parts(self, nd: dict[str, Any], depth: int = 0) -> tuple[list, list, Optional[dict]]:
        """سیم‌های خروجی یک نود = محتوای همان پیام: دکمه/لینک/رسانه.

        نود reply با role=group مثل پوشش عمل می‌کند: عضوهایش به پیام والد
        اضافه می‌شوند. کارت‌های menu و keyboard هم سیم‌های خروجی‌شان =
        آیتم‌های منو/دکمه‌ها هستند.

        خروجی: (دکمه‌ها، پیوندها، رسانه) — هر دکمه یک تاپل (کارت مقصد، پورت).
        """
        btns: list[tuple[dict[str, Any], str]] = []
        urls: list[dict[str, Any]] = []
        media: Optional[dict[str, Any]] = None
        for e in self.out_edges(nd["id"]):
            t, tp = self.nodes[e["to"]], e["to_port"]
            k = t.get("kind")
            # پیوند url فقط دکمهٔ اینلاین است؛ پیوند شیشه‌ای/اشتراک می‌تواند
            # هم اینلاین باشد هم آیتمِ منو/کیبورد دائمی.
            if k == "link" and (t.get("act") or "url") == "url" and t.get("url"):
                urls.append(t)
            elif k == "link":
                btns.append((t, tp))
            elif k == "image" and t.get("url") and media is None:
                media = t
            elif k == "album" and (t.get("items") or []) and media is None:
                media = t                        # آلبوم چندتایی به‌عنوان رسانهٔ پیام
            elif k == "delay":
                continue                         # تاخیر دکمه نیست — مسیر را کند می‌کند
            elif k == "reply" and t.get("role") == "group" and depth < 3:
                sub_b, sub_u, sub_m = self.parts(t, depth + 1)
                btns.extend(sub_b)
                urls.extend(sub_u)
                if media is None and sub_m:
                    media = sub_m
            else:
                btns.append((t, tp))
        return btns, urls, media

    def render(
        self,
        nd: Optional[dict[str, Any]],
        ctx: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        """نود → پیام رندرشده (دیکشنری خالص، بدون وابستگی به تلگرام).

        اگر نود یک کارت منطقی باشد، بی‌صدا پیمایش می‌شود تا به اولین کارت
        پیام‌دار برسیم (resolve_action). خروجی None یعنی چیزی برای نمایش نیست.
        """
        if not nd:
            return None
        if nd.get("kind") in LOGIC_KINDS:
            nd = self.resolve_action(nd, ctx)
            if not nd:
                return None
        kind = nd.get("kind")
        if kind not in _RENDERABLE:
            return None
        btns, urls, media = self.parts(nd)

        if kind == "image":
            return self._render_image(nd, ctx)
        if kind == "album":
            return self._render_album(nd, ctx)
        if kind == "ticket":
            return self._render_ticket(nd, ctx, urls)
        if kind == "input":
            return self._render_input(nd, ctx, urls)
        if kind in ("menu", "keyboard"):
            return self._render_menu(nd, btns, urls, ctx)

        # cmd / reply / trigger
        return self._render_text(nd, btns, urls, media, ctx)

    # ── رندرکننده‌های هر نوع کارت ──────────────────────────────────────────────
    @staticmethod
    def _send_flags(nd: dict[str, Any]) -> dict[str, Any]:
        """گزینهٔ ارسال که کارت روی پیامش تنظیم کرده — برای لایهٔ انتقال."""
        return {
            "parseMode": nd.get("parseMode") or "HTML",
            "silent": bool(nd.get("silent")),
            "protect": bool(nd.get("protect")),
            "editMode": nd.get("editMode") or "new",
        }

    def _render_image(self, nd: dict[str, Any], ctx: Any) -> Optional[dict[str, Any]]:
        if not nd.get("url"):
            return None
        # asFile: رسانه به‌جای نوع اصلی، به‌عنوان فایل (document) ارسال می‌شود
        mtype = "document" if nd.get("asFile") else (nd.get("mediaType") or "photo")
        return {
            "mtype": mtype,
            "url": nd["url"],
            "text": templating.tpl(nd.get("caption") or nd.get("text"), ctx),
            "cb": [],
            "urlb": [],
            "spoiler": bool(nd.get("spoiler")),
            "asFile": bool(nd.get("asFile")),
            "node": nd,
            **self._send_flags(nd),
        }

    def _render_album(self, nd: dict[str, Any], ctx: Any) -> Optional[dict[str, Any]]:
        # آلبوم چندتایی: تلگرام sendMediaGroup می‌خواهد — حداقل ۲ رسانه
        items = [
            it
            for it in (nd.get("items") or [])
            if isinstance(it, dict)
            and str(it.get("url") or "").startswith(("http://", "https://"))
        ]
        if len(items) < config.ALBUM_MIN:
            # یک رسانهٔ تنها → مثل کارت رسانهٔ معمولی رفتار کن
            if len(items) == 1:
                it = items[0]
                return {
                    "mtype": str(it.get("type") or "photo"),
                    "url": it["url"],
                    "text": templating.tpl(nd.get("caption"), ctx),
                    "cb": [],
                    "urlb": [],
                    "spoiler": False,
                    "asFile": False,
                    "node": nd,
                    **self._send_flags(nd),
                }
            return None
        return {
            "mtype": "album",
            "url": None,
            "album": items,
            "text": templating.tpl(nd.get("caption"), ctx),
            "cb": [],
            "urlb": [],
            "spoiler": False,
            "asFile": False,
            "node": nd,
            **self._send_flags(nd),
        }

    def _render_ticket(
        self, nd: dict[str, Any], ctx: Any, urls: list[dict[str, Any]]
    ) -> dict[str, Any]:
        words = [str(w).strip() for w in (nd.get("words") or []) if str(w).strip()]
        cb = [{"text": "🎟 ثبت تیکت", "data": self.cid("tk", nd)}]
        for i, w in enumerate(words):
            cb.append(
                {"text": f"🔑 {w[:18]}", "data": self.cid("tka", nd, {"id": f"w{i}"})}
            )
        return {
            "mtype": None,
            "url": None,
            "ready": True,
            "text": templating.tpl(nd.get("text") or messages.TICKET_PROMPT, ctx),
            "cb": cb,
            "urlb": urls,
            "words": words,
            "node": nd,
            **self._send_flags(nd),
        }

    def _render_input(
        self, nd: dict[str, Any], ctx: Any, urls: list[dict[str, Any]]
    ) -> dict[str, Any]:
        cb = [{"text": "✏️ پاسخ بده", "data": self.cid("in", nd)}]
        return {
            "mtype": None,
            "url": None,
            "ready": True,
            "text": templating.tpl(nd.get("text") or "پاسخ خود را بنویسید.", ctx),
            "cb": cb,
            "urlb": urls,
            "node": nd,
            **self._send_flags(nd),
        }

    def _render_text(
        self,
        nd: dict[str, Any],
        btns: list[tuple[dict[str, Any], str]],
        urls: list[dict[str, Any]],
        media: Optional[dict[str, Any]],
        ctx: Any,
    ) -> dict[str, Any]:
        text = templating.tpl(nd.get("text") or nd.get("response"), ctx)
        cb: list[dict[str, Any]] = []
        reply_items: list[dict[str, Any]] = []
        for t, tp in btns:
            label = _btn_label(t)
            # پیوند شیشه‌ای/اشتراک، دکمهٔ callback نیست — از سازندهٔ مستقیم ساخته می‌شود
            if t.get("kind") == "link" and (t.get("act") or "url") != "url":
                urlb = {
                    "text": label,
                    "act": t.get("act"),
                    "url": t.get("url"),
                    "webapp": t.get("webapp"),
                    "shareText": t.get("shareText"),
                }
                urls.append(urlb)
                # پیوند شیشه‌ای می‌تواند هم اینلاین باشد هم زیر صفحه چت
                if nd.get("btnMode") == "reply":
                    reply_items.append({"text": label, "node": t, "link": urlb})
                continue
            item = {
                "text": label,
                "data": self.cid("go", nd, t, tp),
                "node": t,
                "port": tp,
                "parent": nd,
            }
            cb.append(item)
            # btnMode=reply: دکمه‌ها به‌جای اینلاین، در کیبورد دائمی می‌روند
            if nd.get("btnMode") == "reply":
                reply_items.append(item)
        # دکمهٔ شیشه‌ای روی خودِ این کارت (webapp مستقل از پیوندها)
        glass = None
        wa = (nd.get("webapp") or "").strip()
        if wa.startswith("https://"):
            glass = {"text": nd.get("label") or "منو", "webapp": wa}
        return {
            "mtype": (media or {}).get("mediaType") or "photo",
            "url": (media or {}).get("url") if media else None,
            "album": (media or {}).get("items") if media and media.get("kind") == "album" else None,
            "text": text,
            "cb": cb,
            "urlb": urls,
            "ready": True,
            "node": nd,
            "reply_items": reply_items or None,
            "glass": glass,
            **self._send_flags(nd),
        }

    def _render_menu(
        self,
        nd: dict[str, Any],
        btns: list[tuple[dict[str, Any], str]],
        urls: list[dict[str, Any]],
        ctx: Any,
    ) -> dict[str, Any]:
        """کارت منوی تعاملی / کیبورد دائمی — سه حالت: شیشه‌ای، دائمی، شناور.

        سیم‌های خروجی = آیتم‌های منو. هر آیتم یک دکمه است که به کارت مقصد وصل است.
        """
        mode = nd.get("mode") or ("glass" if nd.get("kind") == "menu" else "persistent")
        text = templating.tpl(nd.get("text") or nd.get("title"), ctx)
        webapp = (nd.get("webapp") or "").strip()

        # آیتم‌های منو = دکمه‌هایی که به کارت‌های مقصد وصل‌اند
        items: list[dict[str, Any]] = []
        for t, tp in btns:
            label = _btn_label(t)
            # پیوند شیشه‌ای/اشتراک در کیبورد دائمی فقط یک دکمهٔ متنی ساده است
            if t.get("kind") == "link" and (t.get("act") or "url") != "url":
                items.append(
                    {
                        "text": label,
                        "node": t,
                        "link": {
                            "act": t.get("act"),
                            "url": t.get("url"),
                            "webapp": t.get("webapp"),
                            "shareText": t.get("shareText"),
                        },
                    }
                )
                continue
            items.append(
                {"text": label, "data": self.cid("go", nd, t, tp), "node": t, "port": tp}
            )

        # حالت شیشه‌ای: یک دکمهٔ WebApp روی کیبورد سیستم + آیتم‌ها زیر صفحه چت
        if mode == "glass" and webapp:
            glass = {"text": nd.get("title") or "منو", "webapp": webapp}
            return {
                "mtype": None,
                "url": None,
                "ready": True,
                "text": text,
                "cb": [],
                "urlb": urls,
                "menu_mode": "glass",
                "glass": glass,
                "reply_items": items,
                "node": nd,
                **self._send_flags(nd),
            }

        # حالت دائمی: همهٔ آیتم‌ها در کیبورد زیر صفحه چت
        if mode in ("glass", "persistent"):
            return {
                "mtype": None,
                "url": None,
                "ready": True,
                "text": text,
                "cb": [],
                "urlb": urls,
                "menu_mode": "persistent",
                "reply_items": items,
                "node": nd,
                **self._send_flags(nd),
            }

        # حالت شناور: آیتم‌ها به‌صورت اینلاین
        return {
            "mtype": None,
            "url": None,
            "ready": True,
            "text": text,
            "cb": items,
            "urlb": urls,
            "menu_mode": "popup",
            "node": nd,
            **self._send_flags(nd),
        }

    # ── کارت‌های منطقی: مسیر واقعی را پیدا می‌کنند ──────────────────────────────
    @staticmethod
    def _cast(a: Any, b: Any) -> Optional[tuple[float, float]]:
        try:
            return float(a), float(b)
        except (TypeError, ValueError):
            return None

    def _eval_condition(self, nd: dict[str, Any], ctx: Any) -> bool:
        """شرط می‌تواند متغیر دائمی (var.x) یا دادهٔ موقت (temp.x) را بخواند."""
        get_var = (ctx or {}).get("get_var") or (lambda _n: None)
        get_temp = (ctx or {}).get("get_temp") or (lambda _k, _d=None: None)
        name = nd.get("var") or ""
        v = get_temp(name[5:]) if name.startswith("temp.") else get_var(name)
        val, op = nd.get("value"), nd.get("op") or "eq"
        if op == "exists":
            return v is not None
        if op == "nexists":
            return v is None
        if op == "contains":
            return str(val or "") in str(v if v is not None else "")
        if op in ("gt", "lt"):
            nums = self._cast(v, val)
            if nums is None:
                return False
            return nums[0] > nums[1] if op == "gt" else nums[0] < nums[1]
        if op == "neq":
            return str(v if v is not None else "") != str(val if val is not None else "")
        return str(v if v is not None else "") == str(val if val is not None else "")

    @staticmethod
    def _apply_setvar(nd: dict[str, Any], ctx: Any) -> None:
        """مقدار می‌تواند از temp بخواند — اگر value با temp. شروع شود."""
        set_var = (ctx or {}).get("set_var")
        get_var = (ctx or {}).get("get_var") or (lambda _n: None)
        get_temp = (ctx or {}).get("get_temp") or (lambda _k, _d=None: None)
        if not set_var:
            return
        name, op, val = nd.get("var"), nd.get("op") or "set", nd.get("value")
        if not name:
            return
        # خواندن مقدار از کیسهٔ موقت: value = "temp.last_input"
        if isinstance(val, str) and val.startswith("temp."):
            val = get_temp(val[5:])
        if op in ("inc", "dec"):
            try:
                cur = float(get_var(name) or 0)
            except (TypeError, ValueError):
                cur = 0
            try:
                delta = float(val or 0)
            except (TypeError, ValueError):
                delta = 0
            nv = cur + delta if op == "inc" else cur - delta
            set_var(name, int(nv) if nv % 1 == 0 else nv)
        elif op == "append":
            set_var(name, str(get_var(name) or "") + str(val if val is not None else ""))
        else:
            set_var(name, val)

    @staticmethod
    def _apply_notify(nd: dict[str, Any], ctx: Any) -> None:
        """کارت اعلان پیام نیست: متن را در صف اعلان (ctx) می‌گذارد تا لایهٔ
        async بعداً برای پذیرندگان تیکت بفرستد — Flow هرگز شبکه صدا نمی‌زند."""
        notify = (ctx or {}).get("notify")
        text = templating.tpl(nd.get("text") or nd.get("label") or "", ctx)
        if notify is not None and text:
            notify(text)

    def integration_plan(self, nd: dict[str, Any], ctx: Any) -> Optional[dict[str, Any]]:
        """اگر این کارت یکپارچه‌سازی (api/ai) است، برنامهٔ اجرایش را
        برمی‌گرداند؛ وگرنه None. اجرای واقعی در موتور (فاز ۵) انجام می‌شود."""
        if nd.get("kind") not in INT_KINDS:
            return None
        return {"kind": nd["kind"], "node": nd, "ctx": ctx}

    @staticmethod
    def integration_apply(nd: dict[str, Any], ctx: Any, result: dict[str, Any]) -> str:
        """نتیجهٔ اجرای یکپارچه‌سازی را در temp می‌نویسد و پورت بعدی را برمی‌گرداند."""
        ok = bool(result.get("ok"))
        set_temp = (ctx or {}).get("set_temp")
        if set_temp:
            set_temp("api_result", result.get("data"))
            set_temp("api_ok", ok)
            set_temp("api_error", result.get("error") if not ok else None)
            # برای کارت AI: متن پاسخ هم در temp.ai و temp.last_input قرار می‌گیرد
            if nd.get("kind") == "ai":
                txt = result.get("text") or result.get("data")
                set_temp("ai", txt)
                set_temp("last_input", txt)
        return "ok" if ok else "fail"

    def resolve_action(
        self,
        nd: Optional[dict[str, Any]],
        ctx: Any = None,
        depth: int = 0,
    ) -> Optional[dict[str, Any]]:
        """پیمایش کارت‌های منطقی (شرط/متغیر/تصادفی/اعلان) تا رسیدن به کارتِ
        واقعاً قابل‌نمایش.

        مسیرها از روی **پورت** انتخاب می‌شوند، نه ترتیب یال‌ها:
        condition → yes/no، random → p1..p5، api/ai → ok/fail، بقیه → run.
        کارت‌های api/ai شبکه می‌زنند و delay صبر می‌کند — هیچ‌کدام نمی‌توانند
        اینجا (همگام) اجرا شوند، پس خودِ کارت برمی‌گردد تا موتور آن را اجرا کند.
        """
        seen: set[str] = set()
        while nd and nd.get("kind") in LOGIC_KINDS and depth < _MAX_DEPTH:
            if nd["id"] in seen:
                return None
            seen.add(nd["id"])
            depth += 1
            if nd.get("kind") in ENGINE_RUN_KINDS:
                return nd                                  # اجرا در موتور
            if nd["kind"] == "setvar":
                self._apply_setvar(nd, ctx)
                nd = self._first_out(nd)
            elif nd["kind"] == "notify":
                self._apply_notify(nd, ctx)
                nd = self._first_out(nd)
            elif nd["kind"] == "random":
                # یک پورتِ متصل را تصادفی انتخاب کن، بعد مقصدش را
                ports = [p["id"] for p in node_ports(nd)]
                avail = [p for p in ports if self.outs(nd["id"], p)]
                nd = self.outs(nd["id"], random.choice(avail))[0] if avail else None
            else:                                            # condition
                port = "yes" if self._eval_condition(nd, ctx) else "no"
                got = self.outs(nd["id"], port)
                nd = got[0] if got else None
        return nd

    def _first_out(self, nd: dict[str, Any]) -> Optional[dict[str, Any]]:
        got = self.outs(nd["id"], PORT_RUN)
        return got[0] if got else None

    # ── خلاصه ────────────────────────────────────────────────────────────────
    def stats(self) -> dict[str, Any]:
        by_kind: dict[str, int] = {}
        for nd in self.nodes.values():
            k = nd.get("kind") or "?"
            by_kind[k] = by_kind.get(k, 0) + 1
        return {
            "nodes": len(self.nodes),
            "edges": len(self.edges),
            "by_kind": by_kind,
        }

    def to_dict(self) -> dict[str, Any]:
        """گرداندن مدل به دیکتنری قابل ذخیره."""
        return {
            "version": config.FLOW_VERSION,
            "nodes": list(self.nodes.values()),
            "edges": list(self.edges),
        }


def _btn_label(t: dict[str, Any]) -> str:
    """برچسب نمایشی یک کارت مقصد — بریده و تکخط."""
    label = str(t.get("label") or t.get("name") or t.get("text") or "ادامه")
    return str(label).strip().splitlines()[0][: config.TG_BUTTON_TEXT_MAX] or "ادامه"
