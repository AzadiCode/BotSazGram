"""پیاده‌سازی حافظهٔ موقت — فقط برای توسعه و تست (وقتی MONGODB_URI نیست).

همان رابط Storage را پیاده می‌کند. داده‌ها با کپی عمیق برمی‌گردند تا
فراخواننده نتواند سندهای درونی را مستقیماً تغییر دهد.
"""
from __future__ import annotations

import copy
import threading
import time
from typing import Any, Optional

from app import config
from app.core import utils
from app.db.base import Storage, bot_defaults, user_defaults

_MAX_TICKETS = 200
_MAX_TTL_RECORDS = 5000


class MemoryStorage(Storage):
    is_memory = True

    def __init__(self) -> None:
        self._users: dict[int, dict] = {}
        self._bots: dict[str, dict] = {}
        # scope -> key -> {"v": value, "exp": epoch}
        self._ttl: dict[str, dict[str, dict]] = {}
        self._lock = threading.RLock()

    # ── کمکی ─────────────────────────────────────────────────────────────
    @staticmethod
    def _bot(doc: Optional[dict]) -> Optional[dict]:
        if not doc:
            return None
        out = copy.deepcopy(doc)
        out.pop("_id", None)
        return bot_defaults(out)

    @staticmethod
    def _user(doc: Optional[dict]) -> Optional[dict]:
        if not doc:
            return None
        out = copy.deepcopy(doc)
        out.pop("_id", None)
        return user_defaults(out)

    # ── کاربران ──────────────────────────────────────────────────────────
    def ensure_user(self, uid: int, username: str = "", full_name: str = "") -> dict:
        with self._lock:
            doc = self._users.get(uid)
            if doc is None:
                doc = {
                    "uid": uid,
                    "username": username,
                    "full_name": full_name,
                    "is_admin": config.is_admin(uid),
                    "is_banned": False,
                    "created_at": utils.now_iso(),
                    "bots_created": [],
                    "coins": 0,
                    "referral_code": utils.new_referral_code(),
                    "referred_by": None,
                    "referral_count": 0,
                }
                self._users[uid] = doc
            else:
                if username and doc.get("username") != username:
                    doc["username"] = username
                if full_name and doc.get("full_name") != full_name:
                    doc["full_name"] = full_name
            return self._user(doc)  # type: ignore[return-value]

    def get_user(self, uid: int) -> Optional[dict]:
        with self._lock:
            return self._user(self._users.get(uid))

    def get_user_by(self, query: dict[str, Any]) -> Optional[dict]:
        with self._lock:
            for user in self._users.values():
                if all(user.get(k) == v for k, v in query.items()):
                    return self._user(user)
        return None

    def get_all_users(self) -> list[dict]:
        with self._lock:
            return [self._user(u) for u in self._users.values()]  # type: ignore[misc]

    def update_user(self, uid: int, patch: dict[str, Any]) -> None:
        with self._lock:
            doc = self._users.get(uid)
            if doc is not None:
                doc.update(patch)

    def next_web_uid(self) -> int:
        with self._lock:
            highest = max((u["uid"] for u in self._users.values()), default=0)
            return max(highest, config.WEB_ACCOUNT_UID_START - 1) + 1

    def insert_user(self, user: dict) -> None:
        with self._lock:
            self._users[int(user["uid"])] = user_defaults(dict(user))

    # ── ربات‌ها ──────────────────────────────────────────────────────────
    def create_bot(self, owner_uid: int, bot_token: str, bot_username: str) -> dict:
        bot_id = utils.new_bot_id(owner_uid, bot_token)
        rec = {
            "bot_id": bot_id,
            "owner_uid": owner_uid,
            "bot_token": bot_token,
            "bot_username": bot_username,
            "created_at": utils.now_iso(),
            "last_activity": None,
        }
        with self._lock:
            bot_defaults(rec)
            self._bots[bot_id] = rec
            owner = self._users.get(owner_uid)
            if owner is not None and bot_id not in owner.get("bots_created", []):
                owner.setdefault("bots_created", []).append(bot_id)
            return self._bot(rec)  # type: ignore[return-value]

    def get_bot(self, bot_id: str) -> Optional[dict]:
        with self._lock:
            return self._bot(self._bots.get(bot_id))

    def get_user_bots(self, uid: int) -> list[dict]:
        with self._lock:
            return [
                self._bot(b)  # type: ignore[misc]
                for b in self._bots.values()
                if b.get("owner_uid") == uid
            ]

    def get_all_bots(self) -> list[dict]:
        with self._lock:
            return [self._bot(b) for b in self._bots.values()]  # type: ignore[misc]

    def delete_bot(self, bot_id: str, owner_uid: int) -> bool:
        with self._lock:
            bot = self._bots.get(bot_id)
            if not bot or bot.get("owner_uid") != owner_uid:
                return False
            del self._bots[bot_id]
            owner = self._users.get(owner_uid)
            if owner is not None and bot_id in owner.get("bots_created", []):
                owner["bots_created"].remove(bot_id)
            return True

    def update_bot(self, bot_id: str, patch: dict[str, Any]) -> None:
        with self._lock:
            bot = self._bots.get(bot_id)
            if bot is not None:
                bot.update(patch)

    # ── کاربرانِ ربات ────────────────────────────────────────────────────
    def add_bot_user(self, bot_id: str, uid: int) -> bool:
        with self._lock:
            bot = self._bots.get(bot_id)
            if not bot:
                return False
            users: list = bot.setdefault("bot_users", [])
            if uid in users:
                return False
            users.append(uid)
            stats: dict = bot.setdefault("stats", {})
            stats["unique_users"] = stats.get("unique_users", 0) + 1
            day = utils.today()
            daily: dict = bot.setdefault("daily_stats", {}).setdefault(day, {})
            daily["new_users"] = daily.get("new_users", 0) + 1
            bot["last_activity"] = utils.now_iso()
            return True

    def get_bot_users(self, bot_id: str) -> list[dict]:
        with self._lock:
            bot = self._bots.get(bot_id) or {}
            uids: list = bot.get("bot_users", [])
            info: dict = bot.get("bot_user_info", {})
        out = [
            {
                "uid": uid,
                "name": info.get(str(uid), {}).get("name", ""),
                "username": info.get(str(uid), {}).get("username", ""),
                "joined": info.get(str(uid), {}).get("joined", ""),
            }
            for uid in uids
        ]
        out.sort(key=lambda u: u.get("joined") or "", reverse=True)
        return out

    def set_bot_user_info(
        self, bot_id: str, uid: int, full_name: str = "", username: str = ""
    ) -> None:
        with self._lock:
            bot = self._bots.get(bot_id)
            if not bot:
                return
            info: dict = bot.setdefault("bot_user_info", {})
            key = str(uid)
            rec = info.get(key)
            if rec is None:
                info[key] = {
                    "name": full_name,
                    "username": username,
                    "joined": utils.now_iso(),
                }
                return
            if full_name:
                rec["name"] = full_name
            if username:
                rec["username"] = username

    def get_user_vars(self, bot_id: str, uid: int) -> dict:
        with self._lock:
            bot = self._bots.get(bot_id) or {}
            return dict((bot.get("bot_user_vars") or {}).get(str(uid)) or {})

    def set_user_var(self, bot_id: str, uid: int, name: str, value: Any) -> None:
        name = str(name)[:40]
        if not name:
            return
        if isinstance(value, str):
            value = value[:500]
        with self._lock:
            bot = self._bots.get(bot_id)
            if bot is None:
                return
            bot.setdefault("bot_user_vars", {}).setdefault(str(uid), {})[name] = value

    # ── نشست ─────────────────────────────────────────────────────────────
    def session_get(self, bot_id: str, uid: int) -> Optional[dict]:
        with self._lock:
            bot = self._bots.get(bot_id) or {}
            s = (bot.get("sessions") or {}).get(str(uid))
            if not s or s.get("expires", 0) <= time.time():
                return None
            return copy.deepcopy(s)

    def session_set(
        self,
        bot_id: str,
        uid: int,
        node_id: Optional[str] = None,
        temp: Optional[dict] = None,
        ttl: int = 900,
        merge: bool = True,
    ) -> None:
        with self._lock:
            bot = self._bots.get(bot_id)
            if bot is None:
                return
            key = str(uid)
            cur = (bot.get("sessions") or {}).get(key) or {}
            new: dict[str, Any] = {"expires": time.time() + ttl}
            if node_id is not None:
                new["node_id"] = str(node_id)
            elif merge and cur.get("node_id"):
                new["node_id"] = cur["node_id"]
            temp_data = dict(cur.get("temp") or {})
            if merge:
                temp_data.update(temp or {})
            else:
                temp_data = dict(temp or {})
            new["temp"] = temp_data
            bot.setdefault("sessions", {})[key] = new

    def session_clear(self, bot_id: str, uid: int) -> None:
        with self._lock:
            bot = self._bots.get(bot_id)
            if bot is not None:
                (bot.get("sessions") or {}).pop(str(uid), None)

    # ── تیکت‌ها ──────────────────────────────────────────────────────────
    def ticket_set_pending(self, bot_id: str, uid: int, node_id: str, ttl: int = 900) -> None:
        with self._lock:
            bot = self._bots.get(bot_id)
            if bot is None:
                return
            bot.setdefault("pending_tickets", {})[str(uid)] = {
                "node": node_id,
                "expires": time.time() + ttl,
            }

    def ticket_pop_pending(self, bot_id: str, uid: int) -> Optional[dict]:
        with self._lock:
            bot = self._bots.get(bot_id) or {}
            entry = (bot.get("pending_tickets") or {}).pop(str(uid), None)
        if entry and entry.get("expires", 0) > time.time():
            return entry
        return None

    def ticket_add(self, bot_id: str, tid: str, rec: dict) -> None:
        with self._lock:
            bot = self._bots.get(bot_id)
            if bot is None:
                return
            tickets: dict = bot.setdefault("tickets", {})
            tickets[tid] = rec
            if len(tickets) > _MAX_TICKETS:
                for old in sorted(tickets, key=lambda k: tickets[k].get("t", 0))[
                    :-_MAX_TICKETS
                ]:
                    del tickets[old]

    def ticket_list(self, bot_id: str, limit: int = 50) -> list[dict]:
        with self._lock:
            tickets = (self._bots.get(bot_id) or {}).get("tickets") or {}
            items = list(tickets.values())
        items.sort(key=lambda t: t.get("t", 0), reverse=True)
        return items[:limit]

    def ticket_reply(self, bot_id: str, tid: str, text: str) -> bool:
        with self._lock:
            tickets = (self._bots.get(bot_id) or {}).get("tickets") or {}
            rec = tickets.get(tid)
            if not rec:
                return False
            rec["reply"] = text
            rec["reply_at"] = utils.now_iso()
            return True

    # ── آمار ─────────────────────────────────────────────────────────────
    def update_bot_stats(self, bot_id: str, received: int = 0, sent: int = 0) -> None:
        with self._lock:
            bot = self._bots.get(bot_id)
            if not bot:
                return
            stats: dict = bot.setdefault("stats", {})
            if received:
                stats["messages_received"] = stats.get("messages_received", 0) + received
            if sent:
                stats["messages_sent"] = stats.get("messages_sent", 0) + sent
            if received or sent:
                bot["last_activity"] = utils.now_iso()

    def record_daily(self, bot_id: str, key: str, amount: int = 1) -> None:
        with self._lock:
            bot = self._bots.get(bot_id)
            if not bot:
                return
            day = utils.today()
            daily: dict = bot.setdefault("daily_stats", {}).setdefault(day, {})
            daily[key] = daily.get(key, 0) + amount

    def record_broadcast(self, bot_id: str, sent: int) -> None:
        with self._lock:
            bot = self._bots.get(bot_id)
            if not bot:
                return
            stats: dict = bot.setdefault("stats", {})
            stats["broadcasts_sent"] = stats.get("broadcasts_sent", 0) + 1
            stats["messages_sent"] = stats.get("messages_sent", 0) + sent

    # ── سکه و رفرال ─────────────────────────────────────────────────────
    def add_coins(self, uid: int, amount: int) -> bool:
        with self._lock:
            doc = self._users.get(uid)
            if doc is None:
                return False
            doc["coins"] = doc.get("coins", 0) + amount
            return True

    def inc_referral_count(self, uid: int) -> None:
        with self._lock:
            doc = self._users.get(uid)
            if doc is not None:
                doc["referral_count"] = doc.get("referral_count", 0) + 1

    # ── داده‌های موقتِ TTLدار ────────────────────────────────────────────
    def ttl_set(self, scope: str, key: str, value: Any, ttl: int) -> None:
        with self._lock:
            bucket = self._ttl.setdefault(scope, {})
            if len(bucket) > _MAX_TTL_RECORDS:
                self._prune_locked(scope)
            bucket[key] = {"v": value, "exp": time.time() + ttl}

    def ttl_get(self, scope: str, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._ttl.get(scope, {}).get(key)
            if entry is None:
                return None
            if entry["exp"] <= time.time():
                self._ttl[scope].pop(key, None)
                return None
            return copy.deepcopy(entry["v"])

    def ttl_delete(self, scope: str, key: str) -> None:
        with self._lock:
            self._ttl.get(scope, {}).pop(key, None)

    def ttl_count(self, scope: str, key: str, window: int) -> int:
        """تعداد رکوردهای زندهٔ یک کلید در پنجرهٔ لغزان — برای شمارندهٔ نرخ.

        هر کلید می‌تواند یک لیست از مهرهای زمانی باشد (ثبت‌نام/ورود) یا
        یک مقدار تکی (کد تأیید). برای لیست، تعداد مهرهای داخل پنجره
        برمی‌گردد و لیست هرس می‌شود.
        """
        with self._lock:
            bucket = self._ttl.get(scope, {})
            entry = bucket.get(key)
            if entry is None:
                return 0
            if entry["exp"] <= time.time():
                bucket.pop(key, None)
                return 0
            stamps = entry["v"]
            if not isinstance(stamps, list):
                return 1
            cutoff = time.time() - window
            stamps = [t for t in stamps if t > cutoff]
            entry["v"] = stamps
            return len(stamps)

    def ttl_prune(self, scope: str) -> int:
        with self._lock:
            return self._prune_locked(scope)

    def _prune_locked(self, scope: str) -> int:
        bucket = self._ttl.get(scope)
        if not bucket:
            return 0
        now = time.time()
        dead = [k for k, e in bucket.items() if e["exp"] <= now]
        for k in dead:
            del bucket[k]
        return len(dead)
