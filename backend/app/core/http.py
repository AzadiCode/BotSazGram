"""کلاینت HTTP امن (ضد SSRF).

قواعد: فقط http/https، resolve کردن DNS و رد کردن IPهای loopback/private/
link-local/metadata، محدودیت اندازهٔ پاسخ، timeout و سقف redirect.
هر خطا به‌جای استثنا، با status=0 برمی‌گردد (مثل legacy).
"""
from __future__ import annotations

import ipaddress
import logging
import socket
import urllib.parse

import requests

from app import config

log = logging.getLogger("GramSaz.http")

_BLOCKED_HOSTS = frozenset(
    {
        "localhost",
        "metadata.google.internal",
        "instance-data",
        "instance-metadata",
        "169.254.169.254",
        "metadata.azure.com",
    }
)


def _is_unsafe_ip(raw: str) -> bool:
    """فقط برای IPهای مستقیم — hostnameها با resolve کردن بررسی می‌شوند."""
    try:
        addr = ipaddress.ip_address(raw)
    except ValueError:
        return False  # hostname نیست؛ در ادامه DNS آن بررسی می‌شود
    return (
        addr.is_loopback
        or addr.is_private
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def _resolved_ips(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return []
    seen: list[str] = []
    for info in infos:
        ip = info[4][0]
        if ip not in seen:
            seen.append(ip)
    return seen


def is_safe_url(url: str) -> tuple[bool, str]:
    """بررسی امن بودن URL — خروجی (امن، دلیل رد)."""
    try:
        parsed = urllib.parse.urlparse(url or "")
    except ValueError:
        return False, "url نامعتبر"
    if parsed.scheme not in ("http", "https"):
        return False, "فقط http/https مجاز است"
    host = (parsed.hostname or "").lower()
    if not host:
        return False, "میزبان خالی"
    if host in _BLOCKED_HOSTS or host.endswith(".localhost") or host.endswith(".internal"):
        return False, "میزبان مسدود"
    if _is_unsafe_ip(host):
        return False, "IP مستقیم غیرعمومی"
    for ip in _resolved_ips(host):
        if _is_unsafe_ip(ip):
            return False, f"میزبان به IP غیرعمومی resolve می‌شود ({ip})"
    return True, ""


def _read_capped(resp: requests.Response) -> str:
    """خواندن متن پاسخ تا سقف HTTP_MAX_RESPONSE_BYTES."""
    cap = config.HTTP_MAX_RESPONSE_BYTES
    chunks: list[bytes] = []
    total = 0
    try:
        for chunk in resp.iter_content(chunk_size=8192):
            if not chunk:
                continue
            total += len(chunk)
            if total > cap:
                chunks.append(chunk[: cap - (total - len(chunk))])
                break
            chunks.append(chunk)
    except OSError:
        pass
    return b"".join(chunks).decode("utf-8", errors="replace")


def safe_request(
    method: str,
    url: str,
    *,
    json: dict | None = None,
    headers: dict[str, str] | None = None,
    timeout: float | None = None,
) -> dict:
    """درخواست GET/POST امن. خروجی: {"status", "text", "error"}.

    status برابر ۰ یعنی خطا/مسدودیت. redirectها دستی و دوباره اعتبارسنجی می‌شوند.
    """
    if not url:
        return {"status": 0, "text": "", "error": "url خالی"}
    ok, reason = is_safe_url(url)
    if not ok:
        log.warning("درخواست مسدود شد: %s — %s", url, reason)
        return {"status": 0, "text": "", "error": reason}

    timeout = timeout if timeout is not None else config.HTTP_TIMEOUT
    req_headers = dict(headers or {})
    req_headers.setdefault("User-Agent", "GramSaz/1.0")
    req_headers.setdefault("Accept", "application/json, text/plain, */*")

    current_url = url
    for _ in range(config.HTTP_MAX_REDIRECTS + 1):
        try:
            with requests.request(
                method,
                current_url,
                json=json if method.upper() == "POST" else None,
                headers=req_headers,
                timeout=timeout,
                stream=True,
                allow_redirects=False,
            ) as resp:
                if resp.is_redirect:
                    location = resp.headers.get("Location", "")
                    next_url = urllib.parse.urljoin(current_url, location)
                    ok, reason = is_safe_url(next_url)
                    if not ok:
                        return {"status": 0, "text": "", "error": f"redirect ناامن: {reason}"}
                    current_url = next_url
                    continue
                return {
                    "status": resp.status_code,
                    "text": _read_capped(resp),
                }
        except requests.RequestException as exc:
            return {"status": 0, "text": "", "error": str(exc)[:200]}
    return {"status": 0, "text": "", "error": "بیش از حد مجاز redirect"}


def safe_get(url: str, **kw) -> dict:
    return safe_request("GET", url, **kw)


def safe_post(url: str, **kw) -> dict:
    return safe_request("POST", url, **kw)
