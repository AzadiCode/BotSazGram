"""Blueprint اصلی API — احراز هویت، مدیریت ربات، فرانت‌اند و ادمین.

تمام endpointهای /api/ در این blueprint ثبت می‌شوند. مسیرهای عمومی
(health، registry، login، register، send-code) نیازی به auth ندارند؛
بقیه از initData یا Bearer token احراز هویت می‌شوند.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from app import config
from app.core.errors import (
    ApiError,
    BadRequest,
    Conflict,
    Forbidden,
    NotFound,
    Unauthorized,
)
from app.flow import clean_flow, flow_from, registry_payload
from app.flow.registry import AI_DEFAULT_MODEL
from app.services import services

api_bp = Blueprint("api", __name__, url_prefix="/api")

_PUBLIC_AUTH_PATHS = {
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/send-code",
}


def _require_auth() -> tuple[int, dict | None, str | None]:
    """احراز هویت از initData یا توکن Authorization.

    Returns:
        (user_id, user_dict, token_type) — token_type یکی از "init_data" یا "auth_token"
        user_dict ممکن است None باشد اگر فقط برای بررسی هویت کافی است.
    """
    init_data = (
        request.args.get("initData")
        or request.headers.get("X-Telegram-Init-Data")
    )
    if init_data:
        user = services().auth.authenticate(init_data=init_data)
        return user["uid"], user, "init_data"

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        user = services().auth.authenticate(token=token)
        return user["uid"], user, "auth_token"

    raise Unauthorized(config.messages.ERR_UNAUTHORIZED)


def _require_bot_owner(bot_id: str, user_id: int) -> dict:
    """بررسی مالکیت ربات و برگشت ربات (با وضعیت اجرا)."""
    bot = services().bots.get(bot_id, user_id)
    if bot is None:
        raise NotFound(config.messages.ERR_NOT_FOUND)
    if bot["owner_uid"] != user_id and not config.is_admin(user_id):
        raise Forbidden(config.messages.ERR_NO_PERMISSION)
    return bot


def _format_bot(bot: dict) -> dict:
    """تبدیل فرمت بک‌اند به فرمت فرانت‌اند (username = bot_username).

    ai_config.api_key هرگز به فرانت نمی‌رود — فقط has_ai_key بلیه می‌فرستیم.
    """
    out = dict(bot)
    out["username"] = out.get("bot_username") or ""
    cfg = out.get("ai_config")
    if isinstance(cfg, dict):
        out["ai_configured"] = bool(cfg.get("api_key"))
        safe_cfg = {k: v for k, v in cfg.items() if k != "api_key"}
        out["ai_config"] = safe_cfg
    else:
        out["ai_configured"] = False
    return out


def _format_user(user: dict) -> dict:
    """تبدیل فرمت کاربر برای فرانت‌اند (referrals = referral_count)."""
    out = dict(user)
    out["referrals"] = out.get("referral_count", 0)
    return out


def _device_id() -> str:
    """شناسهٔ دستگاه مرورگر — برای محدودیت ثبت‌نام."""
    return request.headers.get("X-Device-ID") or ""


def _client_ip() -> str:
    return request.remote_addr or ""


@api_bp.route("/health", methods=["GET"])
def health() -> tuple:
    """بررسی سلامت سرور."""
    return jsonify({"status": "ok"}), 200


# ── احراز هویت ───────────────────────────────────────────────────────────────


@api_bp.route("/auth/me", methods=["GET"])
def auth_me() -> tuple:
    """دریافت پروفایل کاربر فعلی."""
    _, user, _ = _require_auth()
    user["has_password"] = services().repos.users.is_web_registered(user["uid"])
    return jsonify(_format_user(user)), 200


@api_bp.route("/auth/login", methods=["POST"])
def auth_login() -> tuple:
    """ورود با نام کاربری و رمز عبور."""
    data = request.get_json(silent=True) or {}
    username = data.get("username", "")
    password = data.get("password", "")
    ip = _client_ip()
    try:
        user, token = services().registration.login(username, password, ip)
    except BadRequest:
        raise
    except Conflict:
        raise
    except Unauthorized:
        raise
    except Exception:
        raise Unauthorized(config.messages.ERR_INVALID_CREDENTIALS)
    return jsonify({"user": _format_user(user), "token": token}), 200


@api_bp.route("/auth/send-code", methods=["POST"])
def auth_send_code() -> tuple:
    """ارسال کد تأیید به تلگرام (مرحلهٔ قبل از ثبت‌نام)."""
    data = request.get_json(silent=True) or {}
    tg_username = data.get("telegram_username", "")
    device_id = data.get("device_id") or _device_id()
    ip = _client_ip()
    try:
        code, sent = services().registration.send_code(
            tg_username, device_id, ip
        )
    except (BadRequest, Conflict, NotFound) as e:
        raise
    result: dict = {"sent": sent}
    if not sent:
        result["code"] = code
        result["message"] = config.messages.ERR_CODE_SENT if sent else (
            "ربات مادر هنوز آماده نیست؛ کد تأیید در بالا نمایش داده شد."
        )
    else:
        result["message"] = config.messages.OK_CODE_SENT
    return jsonify(result), 200


@api_bp.route("/auth/register", methods=["POST"])
def auth_register() -> tuple:
    """ثبت‌نام حساب وب با کد تأیید."""
    data = request.get_json(silent=True) or {}
    username = data.get("username", "")
    password = data.get("password", "")
    tg_username = data.get("telegram_username", "")
    code = data.get("code", "")
    referral_code = data.get("referral_code", "")
    device_id = data.get("device_id") or _device_id()
    ip = _client_ip()
    full_name = data.get("full_name") or ""
    try:
        user, token = services().registration.register(
            username=username,
            password=password,
            telegram_username=tg_username,
            code=code,
            full_name=full_name,
            referral_code=referral_code,
            ip=ip,
            device_id=device_id,
        )
    except (BadRequest, Conflict, NotFound) as e:
        raise
    return jsonify({"user": _format_user(user), "token": token}), 200


@api_bp.route("/auth/logout", methods=["POST"])
def auth_logout() -> tuple:
    """خروج — باطل کردن توکن نشست."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        services().auth.logout(token)
    return jsonify({"message": config.messages.OK_LOGGED_OUT}), 200


@api_bp.route("/auth/settings", methods=["PATCH"])
def auth_settings() -> tuple:
    """به‌روزرسانی تنظیمات کاربر."""
    user_id, _, _ = _require_auth()
    data = request.get_json(silent=True) or {}
    settings_patch = {}
    if "notify" in data:
        settings_patch["notify"] = bool(data["notify"])
    if not settings_patch:
        raise BadRequest(config.messages.ERR_BAD_REQUEST)
    services().repos.users.update_settings(user_id, settings_patch)
    return jsonify({"message": config.messages.OK_SAVED}), 200


# ── مدیریت ربات‌ها ────────────────────────────────────────────────────────────


@api_bp.route("/bots", methods=["GET"])
def list_bots() -> tuple:
    """لیست ربات‌های کاربر."""
    user_id, _, _ = _require_auth()
    bots = [_format_bot(b) for b in services().bots.list(user_id)]
    return jsonify({"bots": bots}), 200


@api_bp.route("/bots", methods=["POST"])
def add_bot() -> tuple:
    """افزودن ربات جدید."""
    user_id, _, _ = _require_auth()
    data = request.get_json(silent=True) or {}
    token = data.get("token", "")
    bot = services().bots.add(user_id, token)
    return jsonify(_format_bot(bot)), 200


@api_bp.route("/bots/<bot_id>", methods=["GET"])
def get_bot(bot_id: str) -> tuple:
    """دریافت جزئیات یک ربات."""
    user_id, _, _ = _require_auth()
    bot = _require_bot_owner(bot_id, user_id)
    return jsonify(_format_bot(bot)), 200


@api_bp.route("/bots/<bot_id>", methods=["PATCH"])
def patch_bot(bot_id: str) -> tuple:
    """به‌روزرسانی ربات (فعال/غیرفعال یا تنظیمات)."""
    user_id, _, _ = _require_auth()
    _require_bot_owner(bot_id, user_id)
    data = request.get_json(silent=True) or {}

    if "is_active" in data:
        bot = services().bots.set_active(bot_id, user_id, bool(data["is_active"]))
        return jsonify(_format_bot(bot)), 200

    if "config" in data and isinstance(data["config"], dict):
        services().repos.bots.update_config(bot_id, data["config"])
        updated = services().bots.get(bot_id, user_id)
        if updated is None:
            raise NotFound(config.messages.ERR_NOT_FOUND)
        return jsonify(_format_bot(updated)), 200

    if "force_join_channel" in data:
        services().repos.bots.set_force_join(
            bot_id, data["force_join_channel"] or None
        )
        return jsonify({"message": config.messages.OK_SAVED}), 200

    raise BadRequest(config.messages.ERR_BAD_REQUEST)


@api_bp.route("/bots/<bot_id>/ai-config", methods=["GET"])
def get_ai_config(bot_id: str) -> tuple:
    """دریافت وضعیت تنظیمات AI (فقط has_ai_key — api_key نیامی‌روده می‌شود)."""
    user_id, _, _ = _require_auth()
    bot = _require_bot_owner(bot_id, user_id)
    cfg = bot.get("ai_config") or {}
    return jsonify({
        "has_api_key": bool(cfg.get("api_key")),
        "base_url": cfg.get("base_url", ""),
        "model": cfg.get("model", AI_DEFAULT_MODEL),
    }), 200


@api_bp.route("/bots/<bot_id>/ai-config", methods=["PATCH"])
def patch_ai_config(bot_id: str) -> tuple:
    """به‌روزرسانی تنظیمات AI — api_key، base_url، model."""
    user_id, _, _ = _require_auth()
    _require_bot_owner(bot_id, user_id)
    data = request.get_json(silent=True) or {}

    cfg_patch = {}
    if "api_key" in data:
        cfg_patch["api_key"] = data["api_key"] or None
    if "base_url" in data:
        cfg_patch["base_url"] = data["base_url"] or None
    if "model" in data:
        cfg_patch["model"] = data["model"] or None

    if not cfg_patch:
        raise BadRequest(config.messages.ERR_BAD_REQUEST)

    existing = services().repos.bots.get(bot_id)
    existing_cfg = (existing or {}).get("ai_config") or {}
    merged = {**existing_cfg, **cfg_patch}
    if not any(merged.values()):
        merged = None
    services().repos.bots.set_ai_config(bot_id, merged)

    return jsonify({"message": config.messages.OK_SAVED}), 200


@api_bp.route("/bots/<bot_id>", methods=["DELETE"])
def delete_bot(bot_id: str) -> tuple:
    """حذف ربات."""
    user_id, _, _ = _require_auth()
    _require_bot_owner(bot_id, user_id)
    services().bots.delete(bot_id, user_id)
    return jsonify({"message": config.messages.OK_BOT_REMOVED}), 200


# ── گراف جریان ───────────────────────────────────────────────────────────────


@api_bp.route("/bots/<bot_id>/flow", methods=["GET"])
def get_flow(bot_id: str) -> tuple:
    """دریافت گراف جریان ربات."""
    user_id, _, _ = _require_auth()
    bot = _require_bot_owner(bot_id, user_id)

    from app.flow import has_graph, graph_of
    from app.flow import Flow

    if not has_graph(bot):
        raise NotFound(config.messages.ERR_NO_FLOW)
    fl = Flow(graph_of(bot))
    return jsonify(fl.to_dict()), 200


@api_bp.route("/bots/<bot_id>/flow", methods=["PUT"])
def put_flow(bot_id: str) -> tuple:
    """اعتبارسنجی و ذخیرهٔ گراف جریان ربات."""
    user_id, _, _ = _require_auth()
    bot = _require_bot_owner(bot_id, user_id)

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise BadRequest(config.messages.FLOW_BAD_SHAPE)

    graph, error = clean_flow(data)
    if error:
        raise BadRequest(f"{config.messages.ERR_VALIDATION}: {error}")

    services().bots.set_flow(bot_id, graph)

    return jsonify({"message": config.messages.OK_APPLIED, "graph": graph}), 200


# ── رجیستری کارت‌ها ───────────────────────────────────────────────────────────


@api_bp.route("/flow/registry", methods=["GET"])
def get_registry() -> tuple:
    """دریافت رجیستری کامل کارت‌ها برای فرانت‌اند."""
    payload = registry_payload()
    return jsonify(payload), 200


# ── پشتیبان‌گیری ─────────────────────────────────────────────────────────────


@api_bp.route("/bots/<bot_id>/backup", methods=["POST"])
def create_backup(bot_id: str) -> tuple:
    """خروجی گرفتن از تنظیمات ربات."""
    user_id, _, _ = _require_auth()
    data = services().backup.export(bot_id, user_id)
    return jsonify({"backup": data}), 200


@api_bp.route("/bots/<bot_id>/restore", methods=["POST"])
def restore_backup(bot_id: str) -> tuple:
    """بازگردانی پشتیبان ربات."""
    user_id, _, _ = _require_auth()
    data = request.get_json(silent=True) or {}
    result = services().backup.restore(bot_id, user_id, data)
    return jsonify(result), 200


# ── ادمین ────────────────────────────────────────────────────────────────────


@api_bp.route("/admin/stats", methods=["GET"])
def admin_stats() -> tuple:
    """آمار پلتفرم (فقط ادمین)."""
    user_id, _, _ = _require_auth()
    if not config.is_admin(user_id):
        raise Forbidden(config.messages.ERR_NOT_ADMIN)
    return jsonify(services().stats.platform()), 200


# ── میان‌افزه‌ها ─────────────────────────────────────────────────────────────


@api_bp.before_request
def _attach_user() -> tuple | None:
    """ملحق کردن user_id به request برای endpointهای احراز هویت.

    مسیرهای عمومی (health، registry، login، register، send-code)
    نیازی به احراز هویت ندارند.
    """
    path = request.path
    if path == "/api/health":
        return None
    if path == "/api/flow/registry":
        return None
    if path in _PUBLIC_AUTH_PATHS:
        return None
    try:
        user_id, user, token_type = _require_auth()
        request.user_id = user_id  # type: ignore[attr-defined]
        request.user = user  # type: ignore[attr-defined]
        request.token_type = token_type  # type: ignore[attr-defined]
    except ApiError:
        raise
    except Exception:
        raise Unauthorized(config.messages.ERR_UNAUTHORIZED)
    return None


@api_bp.errorhandler(ApiError)
def _handle_api_error(e: ApiError) -> tuple:
    return jsonify({"error": e.message}), e.status
