"""حلقهٔ رویداد مشترکِ همهٔ ربات‌ها.

چون state ربات‌ها و خودِ PTB درون‌پروسه است، سرور باید تک‌پروسه اجرا شود.
در حالت webhook همهٔ ربات‌ها (مادر + ساب‌بات‌ها) روی همین یک حلقه‌اند و
فقط وقتی تلگرام آپدیتی پوش می‌کند بیدار می‌شوند؛ در حالت polling هر
ساب‌بات حلقهٔ خودش را دارد (درون BotRunner) ولی ربات مادر باز هم روی همین
حلقهٔ مشترک اجرا می‌شود تا `deliver` بتواند از ترد فلاسک پیام بفرستد.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Optional

log = logging.getLogger("GramSaz.loop")

BOT_LOOP: Optional[asyncio.AbstractEventLoop] = None
_loop_ready = threading.Event()


def bot_loop() -> Optional[asyncio.AbstractEventLoop]:
    """حلقهٔ مشترک (یا None اگر هنوز راه‌اندازی نشده)."""
    return BOT_LOOP


def start_bot_loop() -> None:
    """یک‌بار در راه‌اندازی سرور صدا زده می‌شود (idempotent)."""
    global BOT_LOOP
    if BOT_LOOP is not None:
        return
    thread = threading.Thread(target=_loop_main, name="grambot-loop", daemon=True)
    thread.start()
    if not _loop_ready.wait(timeout=10):
        raise RuntimeError("راه‌اندازی حلقهٔ رویداد مشترک شکست خورد")
    log.info("حلقهٔ رویداد مشترک ربات‌ها آماده است")


def _loop_main() -> None:
    global BOT_LOOP
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    BOT_LOOP = loop
    _loop_ready.set()
    try:
        loop.run_forever()
    finally:
        loop.close()


def run_on_bot_loop(coro: Any, timeout: float = 20.0) -> Any:
    """اجرای یک کوروتین روی حلقهٔ مشترک و منتظر ماندن برای نتیجه.

    از هر ترد دیگری (مثل ترد Flask) قابل صدا زدن است. اگر حلقه هنوز
    راه‌اندازی نشده RuntimeError می‌دهد.
    """
    loop = BOT_LOOP
    if loop is None:
        raise RuntimeError("حلقهٔ ربات‌ها راه‌اندازی نشده — ابتدا start_bot_loop()")
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=timeout)


def fire_on_bot_loop(coro: Any) -> Any:
    """اجرای fire-and-forget یک کوروتین روی حلقهٔ مشترک.

    برای پردازش آپدیت‌های ورودیِ webhook تا پاسخ HTTP به تلگرام زود برگردد.
    خطاها لاگ می‌شوند و فراخواننده خبردار نمی‌شود.
    """
    loop = BOT_LOOP
    if loop is None:
        raise RuntimeError("حلقهٔ ربات‌ها راه‌اندازی نشده")
    future = asyncio.run_coroutine_threadsafe(coro, loop)

    def _on_done(fut: Any) -> None:
        exc = fut.exception()
        if exc is not None:
            log.error("خطا در پردازش آپدیتِ webhook: %s", exc)

    future.add_done_callback(_on_done)
    return future
