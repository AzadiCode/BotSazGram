"""بستهٔ اصلی برنامهٔ GramSaz.

create_app() — فکتوری برنامه فلاسک.
"""
from __future__ import annotations

import logging
from typing import Callable

from flask import Flask

from app import config
from app.db import get_storage
from app.db.repos import Repos, repos, set_repos

__all__ = ["create_app"]

log = logging.getLogger("GramSaz")


def create_app() -> Flask:
    """فکتوری برنامه فلاسک — راه‌اندازی Storage، Repos، Services، Factory و Telegram."""
    # Importها در اینجا برای جلوگیری از import دایره‌ای
    from app.api import api_bp
    from app.api.webhook import webhook_bp
    from app.telegram import get_factory, set_factory, shutdown, start_all, wire
    from app.telegram.factory import BotFactory
    from app.telegram.loop import bot_loop
    from app.services import Services, services, set_services

    # اعتبارسنجی تنظیمات
    config.validate()

    app = Flask(__name__)
    app.config["JSON_AS_ASCII"] = False
    app.config["JSON_SORT_KEYS"] = False

    # CORS برای فرانت‌اند
    if config.CORS_ORIGINS:
        try:
            from flask_cors import CORS
        except ImportError:  # pragma: no cover
            # نباید کل سرور از کار بیفتد؛ هدرها دستی هم فرستاده می‌شوند.
            log.warning("flask-cors نصب نیست — هدرهای CORS دستی اعمال می‌شوند")
            CORS = None
        if CORS is not None:
            CORS(app, origins=list(config.CORS_ORIGINS), supports_credentials=True)
        else:
            _add_manual_cors(app)

    # ── Storage / Repos / Services / Factory ──────────────────────────
    storage = get_storage()
    set_repos(Repos(storage))
    set_services(Services(repos()))
    set_factory(BotFactory(runner_builder=_runner_builder))

    # ── لایهٔ تلگرام ──────────────────────────────────────────────────
    wire()
    start_all()

    # ── Blueprintها ──────────────────────────────────────────────────
    app.register_blueprint(api_bp)
    app.register_blueprint(webhook_bp)

    # ── مدیریت چرخهٔ حیات ───────────────────────────────────────────
    @app.teardown_appcontext
    def _teardown(exc: BaseException | None = None) -> None:
        pass

    @app.before_request
    def _log_request() -> None:
        log.debug("↳ %s %s", config.API_HOST, config.API_PORT)

    # ── graceful shutdown ────────────────────────────────────────────
    import atexit

    @atexit.register
    def _shutdown() -> None:
        log.info("Shutting down Telegram layer...")
        shutdown()

    return app


def _add_manual_cors(app: Flask) -> None:
    """راه‌انداز CORS وقتی flask-cors در دسترس نیست.

    preflight (OPTIONS) و پاسخ‌های عادی را پوشش می‌دهد. فقط originهای
    مجاز هدر می‌گیرند — مثل رفتار flask-cors.
    """
    from flask import request

    @app.after_request
    def _cors_headers(response):
        origin = request.headers.get("Origin", "")
        if origin and origin in config.CORS_ORIGINS:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Vary"] = "Origin"
            if request.method == "OPTIONS":
                response.headers["Access-Control-Allow-Methods"] = (
                    "GET, HEAD, POST, OPTIONS, PUT, PATCH, DELETE"
                )
                response.headers["Access-Control-Allow-Headers"] = (
                    "Content-Type, Authorization, X-Telegram-Init-Data, X-Device-ID"
                )
                response.headers["Access-Control-Max-Age"] = "600"
        return response


def _runner_builder(repos: Repos) -> Callable[[str, bool], bool]:
    """سازندهٔ runner برای BotFactory — توسط BotService.set_runner استفاده می‌شود."""

    def runner(bot_id: str, active: bool) -> bool:
        if active:
            bot = repos.bots.get(bot_id)
            if bot is None:
                return False
            ok = get_factory().start_bot(bot_id, bot["bot_token"])
            if ok:
                from app.telegram import engine
                engine.sync_bot_menu(bot_id)
            return ok
        get_factory().stop_bot(bot_id)
        return True

    return runner