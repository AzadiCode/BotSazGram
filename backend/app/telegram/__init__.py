"""لایهٔ تلگرام — ربات مادر، factory ساب‌بات‌ها و حلقهٔ رویداد مشترک.

`wire()` اتصال‌های بین این لایه و سرویس‌ها را برقرار می‌کند و `start_all()`
همه را راه‌اندازی می‌کند. هر دو در فاز ۶ (create_app) صدا زده می‌شوند.
"""
from __future__ import annotations

import logging
from typing import Callable

from app import config
from app.db.repos import Repos, repos
from app.services import services
from app.telegram import engine, mother
from app.telegram.factory import BotFactory, get_factory, set_factory
from app.telegram.loop import bot_loop, start_bot_loop
from app.telegram.subbot import set_handler_builder

log = logging.getLogger("GramSaz.telegram")

__all__ = [
    "BotFactory",
    "bot_loop",
    "engine",
    "get_factory",
    "mother",
    "set_factory",
    "set_handler_builder",
    "start_all",
    "wire",
]


def start_all() -> None:
    """راه‌اندازی کامل لایهٔ تلگرام (یک‌بار در استارتاپ سرور)."""
    start_bot_loop()
    use_webhook = config.USE_WEBHOOK
    if use_webhook:
        log.info("حالت اجرای ربات‌ها: webhook — %s", config.WEBHOOK_URL)
    else:
        log.info("حالت اجرای ربات‌ها: polling")
    get_factory().start_all_active()
    for bot in repos().bots.list_active():
        engine.sync_bot_menu(bot["bot_id"])
    if use_webhook:
        mother.start_mother_webhook()
    else:
        mother.start_mother_polling()


def wire() -> None:
    """اتصال لایهٔ تلگرام به سرویس‌ها — قبل از start_all() صدا زده شود.

      - موتور جریان جایگزین هندلرهای پیش‌فرض ساب‌بات‌ها می‌شود
      - BotService.runner → factory (روشن/خاموش واقعیِ ساب‌بات‌ها)
      - BotService.is_running → factory.is_running (وضعیت اجرای واقعی)
      - RegistrationService.deliver → ربات مادر (ارسال واقعی کد تأیید)
    """
    svcs = services()
    f = get_factory()
    set_handler_builder(engine.build_engine_handlers)
    svcs.bots.set_runner(_bot_runner(svcs.repos))
    svcs.bots.set_status_provider(f.is_running)
    svcs.registration.set_deliver(mother.deliver)


def _bot_runner(repos: Repos) -> Callable[[str, bool], bool]:
    """ساخت runner(bot_id, active) که BotService به factory وصل می‌کند."""

    def runner(bot_id: str, active: bool) -> bool:
        if active:
            bot = repos.bots.get(bot_id)
            if bot is None:
                return False
            ok = get_factory().start_bot(bot_id, bot["bot_token"])
            if ok:
                engine.sync_bot_menu(bot_id)
            return ok
        get_factory().stop_bot(bot_id)
        return True

    return runner


def shutdown() -> None:
    """خاموش کردن همهٔ ربات‌ها (در پایان کار سرور)."""
    get_factory().stop_all()
