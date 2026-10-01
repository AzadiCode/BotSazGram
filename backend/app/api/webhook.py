"""Blueprint وب‌هاک تلگرام — /tgwh/<bot_id> و /tgwh/mother."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from app import config
from app.core.errors import BadRequest
from app.telegram import get_factory, mother

webhook_bp = Blueprint("webhook", __name__, url_prefix=config.WEBHOOK_PATH_PREFIX)


@webhook_bp.route("/mother", methods=["POST"])
def mother_webhook() -> tuple:
    """وب‌هاک ربات مادر — مسیر /tgwh/mother."""
    secret = request.args.get("secret") or request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret != config.mother_secret():
        return jsonify({"error": "Invalid secret"}), 401

    try:
        update = request.get_json(force=True)
    except Exception:
        raise BadRequest("Invalid JSON")

    if not update:
        raise BadRequest("Empty update")

    try:
        mother.dispatch_webhook(secret, update)
    except Exception as e:
        config.log.error("Mother webhook error: %s", e)
        return jsonify({"error": "Internal error"}), 500

    return jsonify({"ok": True}), 200


@webhook_bp.route("/<bot_id>", methods=["POST"])
def bot_webhook(bot_id: str) -> tuple:
    """وب‌هاک ساب‌بات — مسیر /tgwh/<bot_id>."""
    secret = request.args.get("secret") or request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if not secret:
        return jsonify({"error": "Missing secret"}), 401

    try:
        update = request.get_json(force=True)
    except Exception:
        raise BadRequest("Invalid JSON")

    if not update:
        raise BadRequest("Empty update")

    try:
        ok = get_factory().dispatch_webhook(bot_id, secret, update)
    except Exception as e:
        config.log.error("Bot webhook error for %s: %s", bot_id, e)
        return jsonify({"error": "Internal error"}), 500

    if not ok:
        return jsonify({"error": "Invalid secret"}), 401
    return jsonify({"ok": True}), 200