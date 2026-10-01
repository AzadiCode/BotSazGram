"""خطاهای API — هر خطا یک کد وضعیت HTTP و یک پیام فارسی دارد.

لایهٔ API این استثناها را به شکل یکسان {"error": "…"} + کد وضعیت تبدیل می‌کند.
پیام‌ها از messages.py می‌آیند تا منبع واحد متن فارسی یک جا بماند.
"""
from __future__ import annotations

from typing import Any

from app import messages


class ApiError(Exception):
    """پایهٔ همهٔ خطاهای API."""

    status: int = 400
    default_message: str = messages.ERR_INTERNAL

    def __init__(self, message: str | None = None, **extra: Any) -> None:
        self.message = message or self.default_message
        self.extra: dict[str, Any] = extra
        super().__init__(self.message)


class BadRequest(ApiError):
    status = 400
    default_message = messages.ERR_BAD_REQUEST


class Unauthorized(ApiError):
    status = 401
    default_message = messages.ERR_UNAUTHORIZED


class Forbidden(ApiError):
    status = 403
    default_message = messages.ERR_FORBIDDEN


class NotFound(ApiError):
    status = 404
    default_message = messages.ERR_NOT_FOUND


class Conflict(ApiError):
    status = 409


class TooManyRequests(ApiError):
    status = 429
    default_message = messages.ERR_TOO_MANY


class InternalError(ApiError):
    status = 500
    default_message = messages.ERR_INTERNAL


def error_payload(exc: BaseException) -> tuple[dict[str, str], int]:
    """تبدیل هر استثنا به (پاسف JSON، کد وضعیت)."""
    if isinstance(exc, ApiError):
        return {"error": exc.message}, exc.status
    return {"error": messages.ERR_INTERNAL}, 500
