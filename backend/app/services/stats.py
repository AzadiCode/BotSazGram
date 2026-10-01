"""سرویس آمار — آمار پلتفرم برای پنل ادمین.

داده‌ها از repos خوانده می‌شوند و فقط تجمیع/مرتب‌سازی در اینجاست.
خروجی‌ها توکن/رمز ندارند چون از repoهای عمومی می‌آیند.
"""
from __future__ import annotations

from app.db.repos import Repos


class StatsService:
    def __init__(self, repos: Repos) -> None:
        self._r = repos

    def platform(self) -> dict:
        """آمار کامل پلتفرم (فقط ادمین باید آن را ببیند)."""
        users = self._r.users.all()
        bots = self._r.bots.list_all()

        total_messages_received = sum(
            (b.get("stats") or {}).get("messages_received", 0) for b in bots
        )
        total_messages_sent = sum(
            (b.get("stats") or {}).get("messages_sent", 0) for b in bots
        )
        total_broadcasts = sum(
            (b.get("stats") or {}).get("broadcasts_sent", 0) for b in bots
        )
        total_bot_users = sum(len(b.get("bot_users") or []) for b in bots)

        return {
            "users": {
                "total": len(users),
                "registered": sum(1 for u in users if u.get("password_hash")),
                "active": sum(
                    1 for u in users if u.get("auth_token") or u.get("telegram_user_id")
                ),
                "banned": sum(1 for u in users if u.get("is_banned")),
                "coins": sum(u.get("coins") or 0 for u in users),
                "referrals": sum(1 for u in users if u.get("referred_by")),
            },
            "bots": {
                "total": len(bots),
                "active": sum(1 for b in bots if b.get("is_active")),
                "messages_received": total_messages_received,
                "messages_sent": total_messages_sent,
                "broadcasts_sent": total_broadcasts,
                "bot_users": total_bot_users,
            },
            "top_bots": self._top_bots(bots),
            "top_users": self._top_users(users),
        }

    def _top_bots(self, bots: list[dict], limit: int = 10) -> list[dict]:
        ranked = sorted(
            bots,
            key=lambda b: (b.get("stats") or {}).get("messages_received", 0),
            reverse=True,
        )
        out: list[dict] = []
        for b in ranked[:limit]:
            owner = self._r.users.get(b.get("owner_uid") or 0) or {}
            out.append(
                {
                    "bot_id": b.get("bot_id"),
                    "username": b.get("bot_username") or "—",
                    "owner_name": owner.get("full_name") or "—",
                    "owner_username": owner.get("username") or "—",
                    "messages": (b.get("stats") or {}).get("messages_received", 0),
                    "users": len(b.get("bot_users") or []),
                    "is_active": bool(b.get("is_active")),
                }
            )
        return out

    def _top_users(self, users: list[dict], limit: int = 10) -> list[dict]:
        ranked = sorted(
            users, key=lambda u: len(u.get("bots_created") or []), reverse=True
        )
        return [
            {
                "uid": u.get("uid"),
                "name": u.get("full_name") or "—",
                "username": u.get("username") or "—",
                "bots_count": len(u.get("bots_created") or []),
                "coins": u.get("coins") or 0,
                "is_admin": bool(u.get("is_admin")),
                "is_banned": bool(u.get("is_banned")),
            }
            for u in ranked[:limit]
            if u.get("bots_created")
        ]
