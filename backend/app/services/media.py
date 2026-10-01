"""سرویس رسانه — آپلود فایل به Catbox.moe.

فایل از طریق لایهٔ API به‌صورت بایت خوانده می‌شود (آپلود جریانی در فاز ۶
تا سقف حجم خوانده می‌شود) و این سرویس فقط آپلود + تشخیص نوع را انجام
می‌دهد. URL خروجی باید https باشد (مثل legacy).
"""
from __future__ import annotations

import logging
import secrets
import time
from typing import Any

import requests

from app import config, messages
from app.core.errors import BadRequest, InternalError
from app.core.utils import clean_str

log = logging.getLogger("GramSaz.media")

_TYPE_BY_EXT: dict[str, str] = {
    # تصویر
    "jpg": "photo",
    "jpeg": "photo",
    "png": "photo",
    "webp": "photo",
    # ویدیو
    "mp4": "video",
    "webm": "video",
    "mov": "video",
    "avi": "video",
    "mkv": "video",
    # صوت
    "mp3": "audio",
    "ogg": "audio",
    "m4a": "audio",
    "wav": "audio",
    "flac": "audio",
    # انیمیشن
    "gif": "animation",
}

_TYPE_NAMES: dict[str, str] = {
    "photo": "تصویر",
    "video": "ویدیو",
    "audio": "صوت",
    "animation": "انیمیشن",
    "document": "فایل",
}

_TYPE_ICONS: dict[str, str] = {
    "photo": "🖼",
    "video": "🎬",
    "audio": "🎵",
    "animation": "🎞",
    "document": "📎",
}

_MAX_BY_TYPE: dict[str, int] = {
    "photo": config.MEDIA_PHOTO_MAX_BYTES,
}


class MediaService:
    def __init__(self, uploader: Any = None) -> None:
        """`uploader` برای تزریق کلاینت در تست (پیش‌فرض: requests.post)."""
        self._upload = uploader or requests.post

    # ── آپلود ─────────────────────────────────────────────────────────────
    def upload(
        self,
        data: bytes,
        filename: str = "",
        content_type: str = "",
    ) -> dict:
        """آپلود بایت‌های فایل به Catbox — خروجی: {url, filename, size, type, …}."""
        if not data:
            raise BadRequest(messages.ERR_NO_FILE)

        size = len(data)
        if size < config.MEDIA_MIN_BYTES:
            raise BadRequest(messages.ERR_UPLOAD_TOO_SMALL)

        media_type = self._detect_type(filename)
        max_bytes = _MAX_BY_TYPE.get(media_type, config.MEDIA_FILE_MAX_BYTES)
        if size > max_bytes:
            raise BadRequest(
                messages.ERR_UPLOAD_TOO_BIG.format(max=max_bytes // (1024 * 1024))
            )

        safe_name = self._safe_filename(filename)
        log.info("آپلود %s به Catbox (%s بایت)", media_type, size)

        try:
            response = self._upload(
                config.CATBOX_URL,
                data={"reqtype": "fileupload"},
                files={"fileToUpload": (safe_name, data, content_type or "application/octet-stream")},
                timeout=config.UPLOAD_TIMEOUT,
            )
        except requests.RequestException as exc:
            log.error("خطا در آپلود: %s", exc)
            raise InternalError(messages.ERR_UPLOAD_FAILED) from exc

        if response.status_code != 200:
            log.error("Catbox وضعیت %s را برگرداند", response.status_code)
            raise InternalError(messages.ERR_UPLOAD_FAILED)

        url = (response.text or "").strip()
        if not url.startswith("https://"):
            log.error("پاسخ نامعتبر از Catbox")
            raise InternalError(messages.ERR_UPLOAD_FAILED)

        log.info("رسانه آپلود شد: %s", url)
        return {
            "url": url,
            "filename": clean_str(filename) or safe_name,
            "size": size,
            "type": media_type,
            "icon": _TYPE_ICONS.get(media_type, "📎"),
            "type_name": _TYPE_NAMES.get(media_type, "فایل"),
        }

    # ── کمکی ─────────────────────────────────────────────────────────────
    @staticmethod
    def _detect_type(filename: str) -> str:
        ext = ""
        if "." in (filename or ""):
            ext = filename.rsplit(".", 1)[1].lower()
        return _TYPE_BY_EXT.get(ext, "document")

    @staticmethod
    def _safe_filename(filename: str) -> str:
        ext = ""
        if "." in (filename or ""):
            ext = filename.rsplit(".", 1)[1].lower()
        return f"gramsaz_{int(time.time())}_{secrets.token_hex(4)}.{ext}"
