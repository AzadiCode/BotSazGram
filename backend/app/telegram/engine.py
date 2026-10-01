"""موتور جریان — اجرای واقعی گراف روی سرور (فاز ۵).

این ماژول جایگزین هندلرهای پیش‌فرض فاز ۳ ساب‌بات می‌شود. `Flow` (فاز ۴)
کاملاً خالص بود و فقط می‌گفت «این کارت چه پیامی دارد»؛ اینجا آن پیام را
می‌سازیم، کارت‌هایی که شبکه/صبر می‌خواهند (api/ai/delay) را اجرا می‌کنیم،
تیکت و ورودی کاربر را مدیریت می‌کنیم و همه چیز را از طریق `transport`
می‌فرستیم.

منابع اجرا:
  - گراف:       `flow_from(bot)` — تنها مسیر خواندن
  - متغیرها:    `repos().bots.get_vars` (دائمی) و `repos().sessions` (موقت)
  - ارسال:      `transport.send` با شیء Bot همین ربات
  - اعلان/تیکت: `mother.deliver` (ربات مادر به ادمین‌ها)

هیچ شبکه‌ای در `Flow` نیست؛ تنها جاهایی که await شبکه داریم اینجاست و در
تست‌ها با Bot نمایشی جایگزین می‌شود.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from html import escape
from typing import Any, Optional

from telegram import Bot, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler, filters

from app import config, messages
from app.core import http
from app.db.repos import repos
from app.flow import ENGINE_RUN_KINDS, flow_from
from app.flow import templating
from app.flow.registry import MODEL_MAX, PORT_RUN
from app.telegram import mother
from app.telegram import transport

log = logging.getLogger("GramSaz.engine")

# عمق زنجیرهٔ کارت‌های یکپارچه‌سازی پشت سر هم (api → api → …)
_MAX_INTEGRATION_DEPTH = 24
_WORD_RE = re.compile(r"^w(\d{1,3})$")


# ══════════════════════════════════════════════════════════════════════
# موتور جریان
# ══════════════════════════════════════════════════════════════════════
class Engine:
    """اجرای گراف جریان یک ربات — یک نمونه به ازای هر آپدیت."""

    def __init__(self, bot_rec: Any) -> None:
        bot_rec = bot_rec if isinstance(bot_rec, dict) else {}
        self.bot_id = str(bot_rec.get("bot_id") or "")
        self.bot = bot_rec
        self.flow = flow_from(bot_rec)

    # ── زمینهٔ اجرا (ctx) ────────────────────────────────────────────────
    def _vctx(
        self,
        chat_id: int,
        user: Optional[dict[str, Any]] = None,
        temp: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """کیسهٔ دادهٔ اجرا: متغیرهای دائمی + دادهٔ موقت نشست + کاربر.

        temp از نشستِ کاربر پر می‌شود تا خروجی یک کارت ورودیِ کارت بعدی
        باشد — حتی در پیام بعدی کاربر.
        """
        r = repos()
        cache: dict[str, Any] = {}
        notify_q: list[str] = []
        sess = r.sessions.get(self.bot_id, chat_id) or {}
        t: dict[str, Any] = dict(sess.get("temp") or {})
        if isinstance(temp, dict):
            t.update(temp)

        def get_var(name: str) -> Any:
            if name not in cache:
                cache.update(r.bots.get_vars(self.bot_id, chat_id) or {})
            return cache.get(name)

        def set_var(name: str, value: Any) -> None:
            cache[name] = value
            r.bots.set_var(self.bot_id, chat_id, name, value)

        def get_temp(name: str, default: Any = None) -> Any:
            return t.get(name, default)

        def set_temp(name: str, value: Any) -> None:
            t[name] = value

        def notify(text: str) -> None:
            notify_q.append(text)

        return {
            "get_var": get_var,
            "set_var": set_var,
            "get_temp": get_temp,
            "set_temp": set_temp,
            "temp": t,
            "user": user or {},
            "chat_id": chat_id,
            "bot_id": self.bot_id,
            "notify": notify,
            "_notify_q": notify_q,
        }

    def _save_session(self, chat_id: int, vctx: Optional[dict[str, Any]]) -> None:
        """temp را در نشست کاربر ذخیره می‌کند تا پیام بعدی آن را ببیند."""
        t = (vctx or {}).get("temp")
        if not isinstance(t, dict) or not t:
            return
        repos().sessions.set_temp(self.bot_id, chat_id, t)

    async def _flush_notify(self, bot: Bot, vctx: Optional[dict[str, Any]]) -> None:
        """کارت‌های notify فقط متن را در صف گذاشته‌اند؛ اینجا واقعاً می‌فرستیم."""
        q = (vctx or {}).get("_notify_q")
        if not q:
            return
        for text in list(q):
            await self._alert_admins(
                bot, messages.ENGINE_NOTIFY.format(text=escape(str(text)))
            )
        q.clear()

    # ── ارسال ──────────────────────────────────────────────────────────
    async def _deliver(
        self,
        bot: Bot,
        chat_id: int,
        msg: Optional[dict[str, Any]],
        *,
        message: Any = None,
    ) -> bool:
        ok = bool(await transport.send(bot, chat_id, msg, message=message))
        if ok:
            r = repos()
            r.bots.update_stats(self.bot_id, sent=1)
            r.bots.record_daily(self.bot_id, "messages_out", 1)
        return ok

    async def _deliver_flow(
        self,
        bot: Bot,
        chat_id: int,
        nd: Optional[dict[str, Any]],
        vctx: Optional[dict[str, Any]] = None,
        *,
        message: Any = None,
        depth: int = 0,
    ) -> bool:
        """مسیر مشترک همهٔ نقاط ورودی: رندر + ارسال + تخلیهٔ صف اعلان.

        اگر کارت اجرایی است (api/ai/delay) به جای رندر، اجرایش می‌کند و
        مسیر را از روی پورتِ خروجی‌اش ادامه می‌دهد.
        """
        if nd is None:
            return False
        if depth > _MAX_INTEGRATION_DEPTH:
            log.warning("موتور: زنجیرهٔ کارت‌ها در %s بیش از حد عمیق شد", self.bot_id)
            return False
        vctx = vctx if vctx is not None else self._vctx(chat_id)

        if nd.get("kind") in ENGINE_RUN_KINDS:
            return await self._run_integration(bot, chat_id, nd, vctx, depth)

        msg = self.flow.render(nd, ctx=vctx)
        if not msg:
            self._save_session(chat_id, vctx)
            return False
        ok = await self._deliver(bot, chat_id, msg, message=message)
        await self._flush_notify(bot, vctx)
        self._save_session(chat_id, vctx)
        return ok

    # ── کارت‌های اجرایی (api / ai / delay) ───────────────────────────────
    async def _run_integration(
        self,
        bot: Bot,
        chat_id: int,
        nd: dict[str, Any],
        vctx: dict[str, Any],
        depth: int,
    ) -> bool:
        kind = nd.get("kind")
        try:
            if kind == "delay":
                await self._do_delay(bot, chat_id, nd)
                nxt = self.flow.outs(nd["id"], PORT_RUN)
            else:
                result = await self._do_integration(bot, nd, vctx)
                port = self.flow.integration_apply(nd, vctx, result)
                save_to = str(nd.get("save_to") or "").strip()
                if save_to and result.get("ok"):
                    val = result.get("text") or result.get("data")
                    if val is not None:
                        vctx["set_var"](save_to, str(val)[:4000])
                nxt = self.flow.outs(nd["id"], port)
        except Exception as exc:  # noqa: BLE001
            log.error("خطا در اجرای کارت %s در %s: %s", kind, self.bot_id, exc)
            self._save_session(chat_id, vctx)
            return False

        if nxt:
            return await self._deliver_flow(
                bot, chat_id, nxt[0], vctx, depth=depth + 1
            )
        self._save_session(chat_id, vctx)
        return True

    async def _do_integration(
        self, bot: Bot, nd: dict[str, Any], vctx: dict[str, Any]
    ) -> dict[str, Any]:
        """اجرای واقعی api/ai. خروجی: {ok, data, text, error}."""
        kind = nd.get("kind")
        try:
            if kind == "api":
                return await self._do_api(nd, vctx)
            if kind == "ai":
                return await self._do_ai(nd, vctx)
        except Exception as exc:  # noqa: BLE001
            log.error("خطا در یکپارچه‌سازی %s (%s): %s", kind, self.bot_id, exc)
            return {"ok": False, "error": str(exc)[:200]}
        return {"ok": False, "error": "نوع کارت ناشناخته"}

    async def _do_delay(self, bot: Bot, chat_id: int, nd: dict[str, Any]) -> None:
        """تاخیر و حالت «در حال تایپ…» — مسیر را کند می‌کند تا طبیعی‌تر شود."""
        try:
            secs = float(nd.get("secs") or 1.0)
        except (TypeError, ValueError):
            secs = 1.0
        secs = max(0.0, min(config.TYPING_MAX_DELAY, secs))
        if nd.get("typing", True):
            await transport.typing(bot, chat_id)
        if secs > 0:
            await asyncio.sleep(secs)

    async def _do_api(self, nd: dict[str, Any], vctx: dict[str, Any]) -> dict[str, Any]:
        """فراخوانی HTTP امن (ضد SSRF) — پاسخ در temp.api_result."""
        url = templating.tpl(nd.get("url") or "", vctx)
        method = str(nd.get("method") or "GET").upper()
        if method not in ("GET", "POST"):
            method = "GET"
        kw: dict[str, Any] = {"timeout": config.HTTP_TIMEOUT}
        if method == "POST":
            kw["json"] = _try_json(templating.tpl(nd.get("body") or "", vctx))
        resp = await asyncio.to_thread(http.safe_request, method, url, **kw)
        if resp.get("error"):
            return {"ok": False, "error": str(resp["error"])[:200]}
        status = int(resp.get("status") or 0)
        data = str(resp.get("text") or "")
        ok = 200 <= status < 300
        return {
            "ok": ok,
            "data": data[:4000],
            "text": data[:4000],
            "error": None if ok else f"HTTP {status}",
        }

    async def _do_ai(self, nd: dict[str, Any], vctx: dict[str, Any]) -> dict[str, Any]:
        """هوش مصنوعی — OpenAI-compatible. کلید از تنظیمات ربات یا env.

        پرامپت با {{input}}/{{var.x}} قالب‌بندی می‌شود؛ پاسخ در temp.ai و
        temp.last_input قرار می‌گیرد.
        """
        cfg = self.bot.get("ai_config")
        cfg = cfg if isinstance(cfg, dict) else {}
        api_key = str(cfg.get("api_key") or config.AI_API_KEY or "").strip()
        if not api_key:
            return {"ok": False, "error": messages.AI_NOT_CONFIGURED}
        base_url = str(cfg.get("base_url") or config.AI_BASE_URL).rstrip("/")
        model = str(nd.get("model") or "").strip()[:MODEL_MAX] or "gpt-4o-mini"
        prompt = templating.tpl(nd.get("text") or "", vctx).strip()
        if not prompt:
            return {"ok": False, "error": "پرامپت خالی است"}

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt[:8000]}],
            "max_tokens": config.AI_MAX_TOKENS,
            "temperature": 0.7,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        resp = await asyncio.to_thread(
            http.safe_post,
            f"{base_url}/chat/completions",
            json=payload,
            headers=headers,
            timeout=config.AI_TIMEOUT,
        )
        if resp.get("error"):
            return {"ok": False, "error": str(resp["error"])[:200]}
        status = int(resp.get("status") or 0)
        if not (200 <= status < 300):
            return {"ok": False, "error": f"HTTP {status}"}
        try:
            data = json.loads(resp.get("text") or "")
            choices = data.get("choices") or []
            text = str((choices[0] if choices else {}).get("message", {}).get("content", "")).strip()
        except (ValueError, TypeError, IndexError, KeyError):
            return {"ok": False, "error": messages.AI_BAD_RESPONSE}
        if not text:
            return {"ok": False, "error": messages.AI_BAD_RESPONSE}
        return {"ok": True, "text": text[:4000], "data": text[:4000]}

    # ── نقاط ورودی ──────────────────────────────────────────────────────
    async def on_command(
        self,
        bot: Bot,
        chat_id: int,
        cmd_name: str,
        user: Optional[dict[str, Any]] = None,
    ) -> bool:
        """اجرای یک دستور. False یعنی چنین دستوری در گراف نیست."""
        nd = self.flow.entry_for(cmd_name)
        if nd is None:
            return False
        await self._deliver_flow(bot, chat_id, nd, self._vctx(chat_id, user))
        return True

    def _match_reply_button(self, text: str) -> Optional[dict[str, Any]]:
        """دکمهٔ کیبورد دائمی پیام متنی است، نه callback.

        کارت menu/keyboardی را پیدا می‌کند که آیتمی با همین متن دارد.
        دکمهٔ شیشه‌ای (webapp) خودش مینی‌اپ را باز می‌کند و نیازی به تطبیق
        متن ندارد، پس نادیده گرفته می‌شود.
        """
        t = (text or "").strip()
        if not t:
            return None
        for nd in self.flow.nodes.values():
            if nd.get("kind") not in ("menu", "keyboard"):
                continue
            msg = self.flow.render(nd)
            if not msg:
                continue
            for it in msg.get("reply_items") or []:
                if it.get("link"):
                    continue
                if str(it.get("text") or "").strip() == t:
                    return it.get("node")
        return None

    async def on_text(
        self,
        bot: Bot,
        chat_id: int,
        text: str,
        user: Optional[dict[str, Any]] = None,
    ) -> bool:
        """متن آزاد کاربر: اول دکمهٔ کیبورد دائمی، بعد کلیدواژه."""
        t = (text or "").strip()
        if not t:
            return False
        vctx = self._vctx(chat_id, user)

        target = self._match_reply_button(t)
        if target is not None:
            await self._deliver_flow(bot, chat_id, target, vctx)
            return True

        nd = self.flow.match_keyword(t)
        if nd is None:
            return False
        await self._deliver_flow(bot, chat_id, nd, vctx)
        return True

    async def on_callback(
        self,
        bot: Bot,
        chat_id: int,
        data: str,
        *,
        message: Any = None,
        user_id: Optional[int] = None,
    ) -> str:
        """دکمهٔ زندهٔ جریان. خروجی: «done» / «unknown».

        «unknown» یعنی این callback_data از جریان نیست (مثلاً دکمهٔ قدیمی).
        """
        parsed = self.flow.parse(data)
        if not parsed:
            return "unknown"
        act, src = parsed["act"], parsed["src"]

        if act == "tk":
            await self._ticket_open(bot, chat_id, src)
            return "done"
        if act == "tka":
            return await self._ticket_toggle(
                bot, chat_id, src, str(parsed.get("raw") or ""), user_id or chat_id
            )
        if act == "in":
            await self._input_open(bot, chat_id, src)
            return "done"
        if act == "go":
            target = parsed["tgt"]
            if target is None:
                return "unknown"
            await self._deliver_flow(
                bot, chat_id, target, self._vctx(user_id or chat_id), message=message
            )
            return "done"
        return "unknown"

    # ─ـ جریان تیکت / ورودی ───────────────────────────────────────────────
    async def on_free_text(
        self,
        bot: Bot,
        chat_id: int,
        text: str,
        user: Optional[dict[str, Any]] = None,
    ) -> bool:
        """پیام آزاد کاربر وقتی تیکت یا کارت «ورودی» در انتظار است."""
        pend = repos().tickets.pop_pending(self.bot_id, chat_id)
        if not pend:
            return False
        nd = self.flow.node(pend.get("node"))
        if nd is not None and nd.get("kind") == "input":
            return await self._input_capture(bot, chat_id, nd, text)
        return await self._ticket_capture(bot, chat_id, nd, pend, text, user)

    async def _ticket_open(self, bot: Bot, chat_id: int, nd: dict[str, Any]) -> None:
        repos().tickets.set_pending(self.bot_id, chat_id, str(nd["id"]))
        await self._deliver_flow(bot, chat_id, nd)

    async def _input_open(self, bot: Bot, chat_id: int, nd: dict[str, Any]) -> None:
        """کارت ورودی همان جایگاه انتظار تیکت را به امانت می‌گیرد — هر کاربر
        در آنِ واحد فقط یک ورودی معلق می‌تواند داشته باشد."""
        repos().tickets.set_pending(self.bot_id, chat_id, str(nd["id"]))
        await self._deliver_flow(bot, chat_id, nd)

    async def _ticket_capture(
        self,
        bot: Bot,
        chat_id: int,
        nd: Optional[dict[str, Any]],
        pend: dict[str, Any],
        text: str,
        user: Optional[dict[str, Any]] = None,
    ) -> bool:
        r = repos()
        body = (text or "").strip()
        if not body:
            r.tickets.set_pending(self.bot_id, chat_id, str(pend.get("node") or ""))
            await _send_html(bot, chat_id, messages.INPUT_INVALID)
            return True

        words = [str(w).strip() for w in (nd or {}).get("words") or [] if str(w).strip()]
        if words and not any(body.lower().startswith(w.lower()) for w in words):
            r.tickets.set_pending(self.bot_id, chat_id, str(pend.get("node") or ""))
            await _send_html(
                bot, chat_id, messages.TICKET_WORD_REQUIRED.format(words=" / ".join(words))
            )
            return True

        meta = {
            "department": str((nd or {}).get("department") or "")[:60],
            "priority": str((nd or {}).get("priority") or "normal"),
            "node": str(pend.get("node") or ""),
        }
        if user:
            meta["name"] = str(user.get("full_name") or "")[:100]
            meta["username"] = str(user.get("username") or "")[:64]
        tid = r.tickets.add(
            self.bot_id, chat_id, body[: config.TICKET_TEXT_MAX], **meta
        )

        auto_reply = str((nd or {}).get("autoReply") or "").strip()
        await _send_html(
            bot, chat_id, auto_reply or messages.TICKET_REGISTERED.format(tid=tid)
        )
        await self._alert_admins(bot, self._ticket_alert(tid, chat_id, body, nd, user))
        r.bots.update_stats(self.bot_id, sent=1)
        return True

    @staticmethod
    def _ticket_alert(
        tid: str,
        uid: int,
        body: str,
        nd: Optional[dict[str, Any]],
        user: Optional[dict[str, Any]] = None,
    ) -> str:
        prio = "normal"
        dept = ""
        if isinstance(nd, dict):
            prio = str(nd.get("priority") or "normal")
            dept = str(nd.get("department") or "").strip()
        mark = {"high": "🔴", "low": "🔵"}.get(prio, "🟡")
        dept_line = f"🏷 بخش: {escape(dept)}\n" if dept else ""
        name = escape(str((user or {}).get("full_name") or "—"))
        return messages.TICKET_ALERT.format(
            tid=escape(tid),
            prio=mark,
            name=name,
            uid=uid,
            dept=dept_line,
            text=escape(body[:1500]),
        )

    async def _ticket_toggle(
        self, bot: Bot, chat_id: int, nd: dict[str, Any], raw: str, who: int
    ) -> str:
        """پذیرندهٔ تیکت با زدن دکمهٔ 🔑 کلمهٔ عبور را برمی‌دارد."""
        m = _WORD_RE.match(raw or "")
        if not m:
            return "done"
        words = [str(w) for w in (nd.get("words") or [])]
        i = int(m.group(1))
        if i >= len(words):
            return "done"
        if who not in self.ticket_admins():
            await _send_html(bot, chat_id, messages.TICKET_WORD_ADMIN_ONLY)
            return "done"
        words.pop(i)
        nd["words"] = words
        self._save_flow()
        await self._deliver(bot, chat_id, self.flow.render(nd, ctx=self._vctx(chat_id)))
        return "done"

    def _save_flow(self) -> None:
        """ذخیرهٔ گرافِ تغییریافته (مثلاً حذف کلمهٔ عبور)."""
        repos().bots.set_flow(self.bot_id, self.flow.to_dict())

    async def _input_capture(
        self, bot: Bot, chat_id: int, nd: dict[str, Any], text: str
    ) -> bool:
        """متن آزاد کاربر را در متغیر کارت input ذخیره می‌کند و ادامه می‌دهد."""
        body = (text or "").strip()
        if not body:
            repos().tickets.set_pending(self.bot_id, chat_id, str(nd["id"]))
            await _send_html(bot, chat_id, messages.INPUT_INVALID)
            return True
        vctx = self._vctx(chat_id)
        vctx["set_temp"]("last_input", body[:4000])
        vctx["set_temp"]("text", body[:4000])
        var = str(nd.get("var") or "").strip()
        if var:
            vctx["set_var"](var, body[:4000])
        nxt = self.flow.outs(nd["id"], PORT_RUN)
        if nxt:
            await self._deliver_flow(bot, chat_id, nxt[0], vctx)
        else:
            self._save_session(chat_id, vctx)
            await _send_html(bot, chat_id, messages.INPUT_STORED)
        return True

    # ─ـ ادمین‌ها ───────────────────────────────────────────────────────────
    def ticket_admins(self) -> set[int]:
        """پذیرندگان تیکت: لیست ربات + مالک + ادمین‌های پلتفرم."""
        admins = {
            int(x)
            for x in (self.bot.get("ticket_admins") or [])
            if str(x).lstrip("-").isdigit()
        }
        owner = self.bot.get("owner_uid")
        if str(owner or "").lstrip("-").isdigit():
            admins.add(int(owner))
        return admins | set(config.ADMIN_IDS)

    async def _alert_admins(self, bot: Bot, text: str) -> None:
        """پیام به پذیرندگان تیکت — ترجیحاً با ربات مادر (ممکن است ساب‌بات را
        استارت نکرده باشند)."""
        targets = sorted(self.ticket_admins())
        if not targets:
            return
        for uid in targets:
            if mother.deliver(uid, text):
                continue
            # ربات مادر در دسترس نیست → خود ساب‌بات
            await _send_html(bot, uid, text)


# ══════════════════════════════════════════════════════════════════════
# کمکی‌های ارسال
# ══════════════════════════════════════════════════════════════════════
async def _send_html(bot: Bot, chat_id: int, text: str) -> None:
    """ارسال متنِ HTMLِ ساده — خطاها بلعیده می‌شوند."""
    if not text:
        return
    try:
        await bot.send_message(chat_id, text, parse_mode="HTML")
    except Exception as exc:  # noqa: BLE001
        log.warning("ارسال متن ناموفق بود (%s): %s", chat_id, exc)


def _try_json(text: str) -> Any:
    """متن را به JSON تبدیل می‌کند؛ اگر نشد، خود متن را برمی‌گرداند."""
    if not text:
        return None
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return text


# ══════════════════════════════════════════════════════════════════════
# هندلرهای ساب‌بات — ساخته‌شده توسط موتور جریان
# ══════════════════════════════════════════════════════════════════════
def build_engine_handlers(bot_id: str) -> list:
    """فهرست هندلرهای یک ساب‌بات — همه از طریق موتور جریان اجرا می‌شوند.

    با `app.telegram.subbot.set_handler_builder(build_engine_handlers)` نصب
    می‌شود (در `wire()`).
    """
    return [
        CommandHandler("start", lambda u, c: _h_start(u, c, bot_id)),
        CallbackQueryHandler(lambda u, c: _h_callback(u, c, bot_id)),
        MessageHandler(filters.TEXT & filters.COMMAND, lambda u, c: _h_command(u, c, bot_id)),
        MessageHandler(filters.TEXT & (~filters.COMMAND), lambda u, c: _h_text(u, c, bot_id)),
    ]


def _touch(bot_id: str, update: Any) -> bool:
    """ثبت کاربرِ ربات و آمار — True یعنی کاربر جدید است."""
    user = getattr(update, "effective_user", None)
    if user is None:
        return False
    r = repos()
    is_new = bool(r.bots.add_user(bot_id, user.id))
    r.bots.set_user_info(bot_id, user.id, user.full_name or "", user.username or "")
    r.bots.update_stats(bot_id, received=1)
    r.bots.record_daily(bot_id, "messages_in", 1)
    return is_new


def _user(update: Any) -> dict[str, Any]:
    u = getattr(update, "effective_user", None)
    if u is None:
        return {}
    return {
        "id": getattr(u, "id", 0),
        "first_name": str(getattr(u, "first_name", "") or ""),
        "last_name": str(getattr(u, "last_name", "") or ""),
        "username": str(getattr(u, "username", "") or ""),
        "full_name": str(getattr(u, "full_name", "") or ""),
        "language": str(getattr(u, "language_code", "") or ""),
    }


async def _check_force_join(bot: Bot, bot_rec: dict[str, Any], update: Any) -> bool:
    """True اگر کاربر عضو کانال است یا عضویت اجباری نیست."""
    ch = str(bot_rec.get("force_join_channel") or "").strip()
    if not ch:
        return True
    uid = getattr(update.effective_user, "id", 0)
    try:
        member = await bot.get_chat_member(ch, uid)
        status = str(getattr(member, "status", "") or "").lower()
        if status.endswith(("member", "administrator", "creator")):
            return True
    except BadRequest:
        return True  # کانال اشتباه/دسترس‌ناپذیر → ربات قفل نشود
    except Exception as exc:  # noqa: BLE001
        log.warning("بررسی عضویت ناموفق بود (%s): %s", ch, exc)
        return True

    disp = ch if ch.startswith("@") else "@" + ch
    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔗 عضو شدن", url=f"https://t.me/{disp.lstrip('@')}")],
            [InlineKeyboardButton(messages.FORCE_JOIN_CHECK, callback_data="fj:check")],
        ]
    )
    try:
        await update.effective_message.reply_text(
            messages.FORCE_JOIN_MESSAGE.format(channel=disp),
            reply_markup=kb,
            parse_mode="HTML",
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("ارسال پیام عضویت اجباری ناموفق بود: %s", exc)
    return False


async def _safe_answer(query: Any, text: str = "", alert: bool = False) -> None:
    try:
        await query.answer(text or None, show_alert=alert or None)
    except Exception as exc:  # noqa: BLE001
        log.warning("پاسخ به callback ناموفق بود: %s", exc)


async def _h_start(update: Any, ctx: Any, bot_id: str) -> None:
    bot_rec = repos().bots.get(bot_id)
    if bot_rec is None:
        return
    chat_id = update.effective_chat.id
    is_new = _touch(bot_id, update)
    if not await _check_force_join(ctx.bot, bot_rec, update):
        return

    if is_new and (bot_rec.get("welcome_message") or "").strip():
        await _send_html(ctx.bot, chat_id, bot_rec["welcome_message"])

    eng = Engine(bot_rec)
    handled = await eng.on_command(ctx.bot, chat_id, "start", _user(update))
    if not handled:
        # رباتی بدون کارت /start — یک پاسخ پیش‌فرض نشان بده
        await _send_html(ctx.bot, chat_id, messages.ENGINE_NO_START)


async def _h_command(update: Any, ctx: Any, bot_id: str) -> None:
    bot_rec = repos().bots.get(bot_id)
    if bot_rec is None:
        return
    _touch(bot_id, update)
    if not await _check_force_join(ctx.bot, bot_rec, update):
        return

    text = (update.effective_message.text or "").strip()
    name = text.lstrip("/").split(maxsplit=1)[0].lower() if text.startswith("/") else ""
    if not name:
        return
    chat_id = update.effective_chat.id
    eng = Engine(bot_rec)
    if await eng.on_command(ctx.bot, chat_id, name, _user(update)):
        return
    unknown = (bot_rec.get("unknown_reply") or "").strip()
    if unknown:
        await _send_html(ctx.bot, chat_id, unknown)


async def _h_text(update: Any, ctx: Any, bot_id: str) -> None:
    bot_rec = repos().bots.get(bot_id)
    if bot_rec is None:
        return
    _touch(bot_id, update)
    if not await _check_force_join(ctx.bot, bot_rec, update):
        return

    text = (update.effective_message.text or "").strip()
    if not text:
        return
    chat_id = update.effective_chat.id
    user = _user(update)
    eng = Engine(bot_rec)

    # ۱) تیکت یا کارت ورودیِ در انتظار
    if await eng.on_free_text(ctx.bot, chat_id, text, user):
        return
    # ۲) دکمهٔ کیبورد دائمی یا کلیدواژهٔ جریان
    if await eng.on_text(ctx.bot, chat_id, text, user):
        return
    # ۳) پاسخِ ناشناختهٔ تنظیم‌شده توسط صاحب ربات
    unknown = (bot_rec.get("unknown_reply") or "").strip()
    if unknown:
        await _send_html(ctx.bot, chat_id, unknown)


async def _h_callback(update: Any, ctx: Any, bot_id: str) -> None:
    query = update.callback_query
    bot_rec = repos().bots.get(bot_id)
    if bot_rec is None:
        await _safe_answer(query)
        return
    _touch(bot_id, update)
    data = query.data or ""
    chat_id = update.effective_chat.id
    uid = update.effective_user.id

    if data == "fj:check":
        ok = await _check_force_join(ctx.bot, bot_rec, update)
        await _safe_answer(
            query,
            "✅ عضویت تأیید شد" if ok else "❌ هنوز عضو نشده‌اید",
            alert=True,
        )
        if ok:
            await _h_start(update, ctx, bot_id)
        return

    eng = Engine(bot_rec)
    try:
        await eng.on_callback(
            ctx.bot, chat_id, data, message=query.message, user_id=uid
        )
    except Exception as exc:  # noqa: BLE001
        log.error("خطا در پردازش دکمهٔ %s (%s): %s", data, bot_id, exc)
    await _safe_answer(query)


# ══════════════════════════════════════════════════════════════════════
# همگام‌سازی منوی دستورهای تلگرام
# ══════════════════════════════════════════════════════════════════════
def menu_commands(bot_rec: Any) -> list[BotCommand]:
    """کارت‌های cmd (با showInMenu) → BotCommand — برای setMyCommands."""
    flow = flow_from(bot_rec)
    out: list[BotCommand] = []
    for nd in flow.cmd_nodes():
        if not bool(nd.get("showInMenu", True)):
            continue
        name = str(nd.get("name") or "").strip().lstrip("/").lower()[:32]
        if not re.fullmatch(r"[a-z0-9_]{1,32}", name):
            continue
        desc = str(nd.get("description") or "").strip()[:256] or name
        out.append(BotCommand(name, desc))
    return out[:100]


async def _set_menu(bot: Bot, cmds: list[BotCommand]) -> None:
    if cmds:
        await bot.set_my_commands(cmds)
    else:
        try:
            await bot.delete_my_commands()
        except Exception as exc:  # noqa: BLE001
            log.warning("حذف منوی دستورها ناموفق بود: %s", exc)


def sync_bot_menu(bot_id: str) -> bool:
    """بهترین تلاش برای همگام‌سازی منوی تلگرامِ یک ربات (fire-and-forget).

    روی حلقهٔ همان ربات برنامه‌ریزی می‌شود تا Telegram API قفل نکند.
    False یعنی ربات روشن نیست یا auto_menu خاموش است.
    """
    from app.telegram.factory import get_factory

    bot_rec = repos().bots.get(bot_id)
    if bot_rec is None or not bool(bot_rec.get("auto_menu", True)):
        return False
    bot = get_factory().get_bot_instance(bot_id)
    loop = get_factory().get_loop(bot_id)
    if bot is None or loop is None:
        return False
    from app.telegram.loop import fire_on_bot_loop

    fire_on_bot_loop(_set_menu(bot, menu_commands(bot_rec)))
    return True
