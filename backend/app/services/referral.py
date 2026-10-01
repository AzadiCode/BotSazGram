"""سرویس رفرال و سکه — گزارش زیرمجموعه‌ها و جوایز.

جوایز خود ثبت‌نام در UserRepo.register اِعمال می‌شوند (هستهٔ دامنه)؛
این سرویس فقط خواندن و گزارش‌گیری را انجام می‌دهد.
"""
from __future__ import annotations

from app.db.repos import Repos


class ReferralService:
    def __init__(self, repos: Repos) -> None:
        self._r = repos

    def info(self, uid: int) -> dict:
        """اطلاعات رفرال کاربر: کد، تعداد، سکه‌ها."""
        return self._r.users.referral_info(uid)

    def top_referrers(self, limit: int = 5) -> list[dict]:
        """برترین معرف‌ها (برای پنل ادمین)."""
        users = self._r.users.all()
        ranked = sorted(
            (u for u in users if (u.get("referral_count") or 0) > 0),
            key=lambda u: u.get("referral_count") or 0,
            reverse=True,
        )
        return [
            {
                "name": u.get("full_name") or "—",
                "username": u.get("username") or "—",
                "referral_count": u.get("referral_count") or 0,
                "coins": u.get("coins") or 0,
            }
            for u in ranked[:limit]
        ]
