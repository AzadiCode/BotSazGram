"""نقطهٔ ورود سرور GramSaz.

اجرای مستقیم: python wsgi.py
تولید: gunicorn --workers 1 --threads 8 wsgi:app

توجه: حلقهٔ ربات‌ها و state آن‌ها درون‌پروسه است، پس حتماً تک‌پروسه
(--workers 1) اجرا شود.
"""
from __future__ import annotations

import logging

from app import create_app
from app import config

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    level=logging.INFO,
    stream=__import__("sys").stdout,
)


def main() -> None:
    config.validate()
    app = create_app()
    app.run(host=config.API_HOST, port=config.API_PORT, debug=False)


if __name__ == "__main__":
    main()
