"""BotFactory — رابط واحدِ روشن/خاموش کردن ساب‌بات‌ها.

بسته به config.USE_WEBHOOK در پشت صحنه یا BotRunner می‌سازد (polling با یک
thread و حلقهٔ اختصاصی به ازای هر ربات) یا WebhookRunner (بدون thread، روی
حلقهٔ مشترک؛ آپدیت‌ها از مسیر Flask می‌آیند). لایهٔ API فقط با start_bot/
stop_bot/is_running کار می‌کند و از جزئیات بی‌خبر است.

`bot_call` یک کوروتین را روی حلقهٔ درستِ همان ربات اجرا می‌کند (مثلاً
ارسال پاسخ تیکت از ربات مادر به ساب‌بات).
"""
from __future__ import annotations

import asyncio
import logging
import secrets
import threading
import time
from typing import Any, Awaitable, Callable, Optional

from telegram import Bot, Update
from telegram.ext import Application

from app import config
from app.db.repos import repos
from app.telegram.loop import bot_loop, fire_on_bot_loop, run_on_bot_loop
from app.telegram.subbot import build_subbot_handlers

log = logging.getLogger("GramSaz.factory")

ApplicationBuilder = Callable[[str], Any]
UsernameWriter = Callable[[str], None]


def _build_application(token: str) -> Any:
    return Application.builder().token(token).build()


# ══════════════════════════════════════════════════════════════════════
# Runnerهای دو حالت اجرا
# ══════════════════════════════════════════════════════════════════════
class BotRunner:
    """حالت polling — یک thread و یک حلقهٔ اختصاصی برای این ربات."""

    def __init__(
        self,
        bot_id: str,
        bot_token: str,
        handlers: list,
        build_app: Optional[ApplicationBuilder] = None,
        on_username: Optional[UsernameWriter] = None,
    ) -> None:
        self.bot_id = bot_id
        self.bot_token = bot_token
        self._handlers = handlers
        self._build_app = build_app or _build_application
        self._on_username = on_username
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._app: Optional[Any] = None
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self._stopped = threading.Event()

    def start(self) -> bool:
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._ready.clear()
        self._stopped.clear()
        self._thread = threading.Thread(
            target=self._run, name=f"grambot-{self.bot_id}", daemon=True
        )
        self._thread.start()
        self._ready.wait(timeout=20)
        return not self._stopped.is_set()

    def stop(self) -> None:
        if self._loop and self._app and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop)
        self._stopped.wait(timeout=10)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._start())
        except Exception as exc:  # noqa: BLE001
            log.error("ساب‌بات %s خطا در راه‌اندازی: %s", self.bot_id, exc)
        finally:
            self._ready.set()
            self._stopped.set()

    async def _start(self) -> None:
        app = self._build_app(self.bot_token)
        for handler in self._handlers:
            app.add_handler(handler)
        try:
            await app.initialize()
            me = await app.bot.get_me()
            if self._on_username is not None:
                self._on_username(me.username or "")
            self._app = app
            await app.start()
            await app.updater.start_polling(drop_pending_updates=True)
        except Exception:
            await self._shutdown()  # اگر start() زده شدیم، app را می‌بندیم
            raise
        self._ready.set()
        log.info("🟢 ساب‌بات @%s (%s) روی polling روشن شد", self._username(), self.bot_id)
        while not self._stopped.is_set():
            await asyncio.sleep(1)

    async def _shutdown(self) -> None:
        app, self._app = self._app, None
        try:
            if app is not None:
                if getattr(app, "updater", None) is not None and app.updater.running:
                    await app.updater.stop()
                await app.stop()
                await app.shutdown()
        except Exception as exc:  # noqa: BLE001
            log.warning("خطا در خاموش کردن %s: %s", self.bot_id, exc)
        finally:
            self._stopped.set()

    def _username(self) -> str:
        if self._app is not None:
            try:
                return getattr(self._app.bot, "username", "") or ""
            except Exception:  # noqa: BLE001
                pass
        return ""

    def is_running(self) -> bool:
        return self._app is not None and self._thread is not None and self._thread.is_alive()

    def get_bot(self) -> Optional[Bot]:
        return self._app.bot if self._app is not None else None

    def get_loop(self) -> Optional[asyncio.AbstractEventLoop]:
        if self._loop is not None and self._loop.is_running():
            return self._loop
        return None


class WebhookRunner:
    """حالت webhook — بدون thread؛ آپدیت‌ها از مسیر Flask روی حلقهٔ مشترک می‌آیند."""

    def __init__(
        self,
        bot_id: str,
        bot_token: str,
        handlers: list,
        build_app: Optional[ApplicationBuilder] = None,
        on_username: Optional[UsernameWriter] = None,
        loop_runner: Callable[[Any], Any] = run_on_bot_loop,
    ) -> None:
        self.bot_id = bot_id
        self.bot_token = bot_token
        self._handlers = handlers
        self._build_app = build_app or _build_application
        self._on_username = on_username
        self._run_on_loop = loop_runner
        self.secret = secrets.token_urlsafe(24)
        self.app: Optional[Any] = None

    def start(self) -> bool:
        try:
            app = self._build_app(self.bot_token)
            for handler in self._handlers:
                app.add_handler(handler)
            self._run_on_loop(app.initialize())
            me = self._run_on_loop(app.bot.get_me())
            if self._on_username is not None:
                self._on_username(me.username or "")
            url = f"{config.WEBHOOK_URL}{config.WEBHOOK_PATH_PREFIX}/{self.bot_id}"
            self._run_on_loop(
                app.bot.set_webhook(
                    url=url,
                    secret_token=self.secret,
                    drop_pending_updates=True,
                    allowed_updates=Update.ALL_TYPES,
                )
            )
            self.app = app
        except Exception as exc:  # noqa: BLE001
            log.error("ساب‌بات %s خطا در راه‌اندازی webhook: %s", self.bot_id, exc)
            self.app = None
            return False
        log.info(
            "🟢 ساب‌بات @%s (%s) روی webhook روشن شد", self._username(), self.bot_id
        )
        return True

    def stop(self) -> None:
        app, self.app = self.app, None
        if app is None:
            return
        try:
            self._run_on_loop(app.bot.delete_webhook(drop_pending_updates=False), timeout=10)
        except Exception as exc:  # noqa: BLE001
            log.warning("خطا در حذف webhook %s: %s", self.bot_id, exc)
        try:
            self._run_on_loop(app.shutdown(), timeout=10)
        except Exception as exc:  # noqa: BLE001
            log.warning("خطا در shutdown %s: %s", self.bot_id, exc)

    def _username(self) -> str:
        if self.app is not None:
            try:
                return getattr(self.app.bot, "username", "") or ""
            except Exception:  # noqa: BLE001
                pass
        return ""

    def is_running(self) -> bool:
        return self.app is not None

    def get_bot(self) -> Optional[Bot]:
        return self.app.bot if self.app is not None else None

    def get_loop(self) -> Optional[asyncio.AbstractEventLoop]:
        return bot_loop() if self.is_running() else None

    async def dispatch(self, update: Update) -> None:
        if self.app is None:
            return
        try:
            await self.app.process_update(update)
        except Exception as exc:  # noqa: BLE001
            log.error("process_update %s (%s): %s", self.bot_id, getattr(update, "update_id", "?"), exc)
            # اگر callback بود حتماً جواب بدهیم تا تلگرام «ساعت‌شنی» نزند
            try:
                cq = getattr(update, "callback_query", None)
                if cq is not None:
                    await cq.answer("خطا در پردازش", show_alert=False)
            except Exception:  # noqa: BLE001
                pass


RunnerBuilder = Callable[[str, str, list], Any]


def _save_username(bot_id: str) -> UsernameWriter:
    def _write(username: str) -> None:
        if not username:
            return
        try:
            repos().bots.set_username(bot_id, username)
        except Exception as exc:  # noqa: BLE001
            log.warning("ذخیرهٔ username ربات %s ناموفق بود: %s", bot_id, exc)

    return _write


def _default_runner_builder(bot_id: str, bot_token: str, handlers: list) -> Any:
    if config.USE_WEBHOOK:
        return WebhookRunner(bot_id, bot_token, handlers, on_username=_save_username(bot_id))
    # فقط در حالت polling: جلوگیری از تداخل 409 با getUpdatesِ قبلی
    time.sleep(1.0)
    return BotRunner(bot_id, bot_token, handlers, on_username=_save_username(bot_id))


# ══════════════════════════════════════════════════════════════════════
# BotFactory
# ══════════════════════════════════════════════════════════════════════
class BotFactory:
    """رابط یکسان برای بالا — start/stop/is_running بدون دانستن جزئیات اجرا."""

    def __init__(self, runner_builder: Optional[RunnerBuilder] = None) -> None:
        self._builder = runner_builder or _default_runner_builder
        self._runners: dict[str, Any] = {}
        self._lock = threading.Lock()

    # ── چرخهٔ عمر ───────────────────────────────────────────────────────────
    def start_bot(
        self,
        bot_id: str,
        bot_token: str,
        handlers: Optional[list] = None,
    ) -> bool:
        with self._lock:
            self._stop_locked(bot_id)
            if handlers is None:
                handlers = build_subbot_handlers(bot_id)
            runner = self._builder(bot_id, bot_token, handlers)
            ok = runner.start()
            if ok:
                self._runners[bot_id] = runner
            return ok

    def stop_bot(self, bot_id: str) -> None:
        with self._lock:
            self._stop_locked(bot_id)

    def _stop_locked(self, bot_id: str) -> None:
        runner = self._runners.pop(bot_id, None)
        if runner is not None:
            runner.stop()

    def start_all_active(self) -> None:
        """روشن کردن همهٔ ربات‌های فعال (در راه‌اندازی سرور)."""
        for bot in repos().bots.list_active():
            self.start_bot(bot["bot_id"], bot["bot_token"])

    def stop_all(self) -> None:
        """خاموش کردن همهٔ ربات‌های در حال اجرا (در پایان کار سرور)."""
        with self._lock:
            for bot_id in list(self._runners.keys()):
                self._stop_locked(bot_id)

    # ── وضعیت ─────────────────────────────────────────────────────────────
    def is_running(self, bot_id: str) -> bool:
        with self._lock:
            runner = self._runners.get(bot_id)
        return runner is not None and runner.is_running()

    def get_bot_instance(self, bot_id: str) -> Optional[Bot]:
        with self._lock:
            runner = self._runners.get(bot_id)
        return runner.get_bot() if runner is not None else None

    def get_loop(self, bot_id: str) -> Optional[asyncio.AbstractEventLoop]:
        """حلقه‌ای که کوروتین‌های این ربات باید روی آن اجرا شوند.

        در حالت webhook همه روی حلقهٔ مشترک‌اند؛ در polling هر ربات حلقهٔ
        خودش را دارد. ربات خاموش → None.
        """
        with self._lock:
            runner = self._runners.get(bot_id)
        if runner is None:
            return None
        return runner.get_loop()

    # ── webhook ─────────────────────────────────────────────────────────────
    def dispatch_webhook(self, bot_id: str, secret: str, update: Update) -> bool:
        """از مسیر Flask /tgwh/<bot_id> صدا زده می‌شود.

        False یعنی secret اشتباه است یا ربات روی webhook روشن نیست.
        """
        with self._lock:  # تا toggle همزمان، آپدیت را به appِ خاموش‌شده ندهد
            runner = self._runners.get(bot_id)
            if runner is None or not runner.is_running():
                return False
            if getattr(runner, "secret", None) != secret:
                return False
            fire_on_bot_loop(runner.dispatch(update))
        return True

    # ── فراخوانی روی حلقهٔ ربات ─────────────────────────────────────────────
    async def bot_call(self, bot_id: str, coro_fn: Callable[[], Awaitable[Any]]) -> Any:
        """اجرای یک کوروتین روی حلقهٔ درستِ همان ربات و منتظر ماندن برای نتیجه.

          - اگر حلقهٔ مقصر همان حلقهٔ جاری باشد، مستقیم await می‌شود
            (run_coroutine_threadsafe روی همان loop می‌تواند قفل کند).
          - اگر ربات خاموش باشد RuntimeError می‌دهد تا فراخواننده پیام روشن بدهد.
        `coro_fn` یک تابع بی‌arg است (کوروتین را تنبل می‌سازد تا اگر ربات
        خاموش بود، ساخته نشود).
        """
        loop = self.get_loop(bot_id)
        if loop is None:
            raise RuntimeError("ربات خاموش است")
        try:
            current = asyncio.get_running_loop()
        except RuntimeError:
            current = None
        if loop is current:
            return await coro_fn()
        return await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(coro_fn(), loop))


# ── تک‌نمونهٔ پروسه ─────────────────────────────────────────────────────────
_factory: Optional[BotFactory] = None


def get_factory() -> BotFactory:
    """دسترسی سراسری به factory (یک نمونه در هر پروسه)."""
    global _factory
    if _factory is None:
        _factory = BotFactory()
    return _factory


def set_factory(value: Optional[BotFactory]) -> None:
    """تزریق factory (برای تست)."""
    global _factory
    _factory = value
