"""پیاده‌سازی MongoDB — همان رابط Storage، سازگار با اسناد legacy.

دو کالکشن: users (یکتا روی uid) و bots (یکتا روی bot_id، ایندکس owner_uid).
در صورت خطای اتصال، خود را به MemoryStorage تنزل نمی‌دهد؛ انتخاب بک‌اند
در db/__init__.py انجام می‌شود تا رفتار صریح و قابل پیش‌بینی بماند.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

from pymongo import ASCENDING, MongoClient
from pymongo.errors import DuplicateKeyError, PyMongoError

from app import config
from app.core import utils
from app.db.base import Storage, bot_defaults, user_defaults
from app.db.memory import MemoryStorage

log = logging.getLogger("GramSaz.mongo")

_MAX_TICKETS = 200
_SERVER_SELECTION_MS = 8000


class MongoStorage(Storage):
    is_memory = False

    def __init__(self, uri: str) -> None:
        self._client = MongoClient(uri, serverSelectionTimeoutMS=_SERVER_SELECTION_MS)
        db = self._client.get_default_database()
        self._users = db["users"]
        self._bots = db["bots"]
        self._users.create_index("uid", unique=True)
        self._users.create_index("auth_token")
        self._users.create_index("referral_code")
        self._bots.create_index("bot_id", unique=True)
        self._bots.create_index("owner_uid")
        # کالکشن کوچک برای داده‌های موقت TTLدار (کد تأیید، تلاش ورود، ثبت‌نام)
        self._kv = db["kv"]
        self._kv.create_index("exp", expireAfterSeconds=0)
        self._kv.create_index([("scope", ASCENDING), ("key", ASCENDING)], unique=True)

    def close(self) -> None:
        try:
            self._client.close()
        except PyMongoError as exc:
            log.warning("بستن اتصال Mongo ناموفق بود: %s", exc)

    # ── کمکی ─────────────────────────────────────────────────────────────
    @staticmethod
    def _clean(doc: Optional[dict]) -> Optional[dict]:
        if not doc:
            return None
        doc = dict(doc)
        doc.pop("_id", None)
        return doc

    # ── کاربران ──────────────────────────────────────────────────────────
    def ensure_user(self, uid: int, username: str = "", full_name: str = "") -> dict:
        doc = self._users.find_one({"uid": uid})
        if doc is None:
            new_user = {
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
            try:
                self._users.insert_one(new_user)
            except DuplicateKeyError:
                doc = self._users.find_one({"uid": uid})
            else:
                return self._clean(new_user)  # type: ignore[return-value]
        update: dict[str, Any] = {}
        if username and doc.get("username") != username:
            update["username"] = username
        if full_name and doc.get("full_name") != full_name:
            update["full_name"] = full_name
        for field, default in (
            ("coins", 0),
            ("referral_code", utils.new_referral_code()),
            ("referred_by", None),
            ("referral_count", 0),
            ("bots_created", []),
        ):
            if field not in doc:
                update[field] = default
        if update:
            self._users.update_one({"uid": uid}, {"$set": update})
            doc.update(update)
        return self._clean(doc)  # type: ignore[return-value]

    def get_user(self, uid: int) -> Optional[dict]:
        return self._clean(self._users.find_one({"uid": uid}))

    def get_user_by(self, query: dict[str, Any]) -> Optional[dict]:
        return self._clean(self._users.find_one(query))

    def get_all_users(self) -> list[dict]:
        return [self._clean(u) for u in self._users.find({}, {"_id": 0})]  # type: ignore[misc]

    def update_user(self, uid: int, patch: dict[str, Any]) -> None:
        if patch:
            self._users.update_one({"uid": uid}, {"$set": patch})

    def next_web_uid(self) -> int:
        top = self._users.find_one(sort=[("uid", -1)], projection={"uid": 1})
        highest = int((top or {}).get("uid") or 0)
        return max(highest, config.WEB_ACCOUNT_UID_START - 1) + 1

    def insert_user(self, user: dict) -> None:
        try:
            self._users.insert_one(dict(user))
        except DuplicateKeyError:
            log.warning("درج کاربر تکراری رخ داد: uid=%s", user.get("uid"))

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
        bot_defaults(rec)
        self._bots.insert_one(rec)
        self._users.update_one({"uid": owner_uid}, {"$addToSet": {"bots_created": bot_id}})
        return self._clean(rec)  # type: ignore[return-value]

    def get_bot(self, bot_id: str) -> Optional[dict]:
        doc = self._clean(self._bots.find_one({"bot_id": bot_id}))
        return bot_defaults(doc) if doc else None

    def get_user_bots(self, uid: int) -> list[dict]:
        return [
            bot_defaults(self._clean(b))  # type: ignore[misc, arg-type]
            for b in self._bots.find({"owner_uid": uid}, {"_id": 0})
        ]

    def get_all_bots(self) -> list[dict]:
        return [
            bot_defaults(self._clean(b))  # type: ignore[misc, arg-type]
            for b in self._bots.find({}, {"_id": 0})
        ]

    def delete_bot(self, bot_id: str, owner_uid: int) -> bool:
        res = self._bots.delete_one({"bot_id": bot_id, "owner_uid": owner_uid})
        if not res.deleted_count:
            return False
        self._users.update_one({"uid": owner_uid}, {"$pull": {"bots_created": bot_id}})
        return True

    def update_bot(self, bot_id: str, patch: dict[str, Any]) -> None:
        if patch:
            self._bots.update_one({"bot_id": bot_id}, {"$set": patch})

    # ── کاربرانِ ربات ────────────────────────────────────────────────────
    def add_bot_user(self, bot_id: str, uid: int) -> bool:
        doc = self._bots.find_one({"bot_id": bot_id}, {"bot_users": 1})
        if not doc or uid in doc.get("bot_users", []):
            return False
        day = utils.today()
        self._bots.update_one(
            {"bot_id": bot_id},
            {
                "$addToSet": {"bot_users": uid},
                "$inc": {"stats.unique_users": 1, f"daily_stats.{day}.new_users": 1},
                "$set": {"last_activity": utils.now_iso()},
            },
        )
        return True

    def get_bot_users(self, bot_id: str) -> list[dict]:
        doc = self._bots.find_one({"bot_id": bot_id}, {"bot_users": 1, "bot_user_info": 1}) or {}
        uids: list = doc.get("bot_users", [])
        info: dict = doc.get("bot_user_info", {})
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
        key = str(uid)
        set_fields: dict[str, Any] = {f"bot_user_info.{key}.joined": utils.now_iso()}
        if full_name:
            set_fields[f"bot_user_info.{key}.name"] = full_name
        if username:
            set_fields[f"bot_user_info.{key}.username"] = username
        self._bots.update_one({"bot_id": bot_id}, {"$set": set_fields})

    def get_user_vars(self, bot_id: str, uid: int) -> dict:
        doc = self._bots.find_one({"bot_id": bot_id}, {f"bot_user_vars.{uid}": 1}) or {}
        return dict((doc.get("bot_user_vars") or {}).get(str(uid)) or {})

    def set_user_var(self, bot_id: str, uid: int, name: str, value: Any) -> None:
        name = str(name)[:40]
        if not name:
            return
        if isinstance(value, str):
            value = value[:500]
        self._bots.update_one(
            {"bot_id": bot_id}, {"$set": {f"bot_user_vars.{uid}.{name}": value}}
        )

    # ── نشست ─────────────────────────────────────────────────────────────
    def session_get(self, bot_id: str, uid: int) -> Optional[dict]:
        doc = self._bots.find_one({"bot_id": bot_id}, {f"sessions.{uid}": 1}) or {}
        s = (doc.get("sessions") or {}).get(str(uid))
        if not s or s.get("expires", 0) <= time.time():
            return None
        return s

    def session_set(
        self,
        bot_id: str,
        uid: int,
        node_id: Optional[str] = None,
        temp: Optional[dict] = None,
        ttl: int = 900,
        merge: bool = True,
    ) -> None:
        key = str(uid)
        cur = self.session_get(bot_id, uid) or {}
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
        self._bots.update_one({"bot_id": bot_id}, {"$set": {f"sessions.{key}": new}})

    def session_clear(self, bot_id: str, uid: int) -> None:
        self._bots.update_one({"bot_id": bot_id}, {"$unset": {f"sessions.{uid}": ""}})

    # ── تیکت‌ها ──────────────────────────────────────────────────────────
    def ticket_set_pending(self, bot_id: str, uid: int, node_id: str, ttl: int = 900) -> None:
        self._bots.update_one(
            {"bot_id": bot_id},
            {
                "$set": {
                    f"pending_tickets.{uid}": {
                        "node": node_id,
                        "expires": time.time() + ttl,
                    }
                }
            },
        )

    def ticket_pop_pending(self, bot_id: str, uid: int) -> Optional[dict]:
        doc = self._bots.find_one_and_update(
            {"bot_id": bot_id},
            {"$unset": {f"pending_tickets.{uid}": ""}},
            projection={f"pending_tickets.{uid}": 1},
        )
        entry = (doc or {}).get("pending_tickets", {}).get(str(uid))
        if entry and entry.get("expires", 0) > time.time():
            return entry
        return None

    def ticket_add(self, bot_id: str, tid: str, rec: dict) -> None:
        self._bots.update_one({"bot_id": bot_id}, {"$set": {f"tickets.{tid}": rec}})
        # محدود کردن اندازهٔ صندوق تیکت (مثل legacy)
        doc = self._bots.find_one({"bot_id": bot_id}, {"tickets": 1}) or {}
        tickets: dict = doc.get("tickets") or {}
        if len(tickets) > _MAX_TICKETS:
            old = sorted(tickets, key=lambda k: tickets[k].get("t", 0))[
                : len(tickets) - _MAX_TICKETS
            ]
            self._bots.update_one(
                {"bot_id": bot_id}, {"$unset": {f"tickets.{k}": "" for k in old}}
            )

    def ticket_list(self, bot_id: str, limit: int = 50) -> list[dict]:
        doc = self._bots.find_one({"bot_id": bot_id}, {"tickets": 1}) or {}
        items = list((doc.get("tickets") or {}).values())
        items.sort(key=lambda t: t.get("t", 0), reverse=True)
        return items[:limit]

    def ticket_reply(self, bot_id: str, tid: str, text: str) -> bool:
        res = self._bots.update_one(
            {"bot_id": bot_id, f"tickets.{tid}": {"$exists": True}},
            {
                "$set": {
                    f"tickets.{tid}.reply": text,
                    f"tickets.{tid}.reply_at": utils.now_iso(),
                }
            },
        )
        return res.modified_count > 0

    # ── آمار ─────────────────────────────────────────────────────────────
    def update_bot_stats(self, bot_id: str, received: int = 0, sent: int = 0) -> None:
        inc: dict[str, Any] = {}
        if received:
            inc["stats.messages_received"] = received
        if sent:
            inc["stats.messages_sent"] = sent
        if not inc:
            return
        self._bots.update_one(
            {"bot_id": bot_id},
            {"$inc": inc, "$set": {"last_activity": utils.now_iso()}},
        )

    def record_daily(self, bot_id: str, key: str, amount: int = 1) -> None:
        day = utils.today()
        self._bots.update_one(
            {"bot_id": bot_id}, {"$inc": {f"daily_stats.{day}.{key}": amount}}
        )

    def record_broadcast(self, bot_id: str, sent: int) -> None:
        self._bots.update_one(
            {"bot_id": bot_id},
            {"$inc": {"stats.broadcasts_sent": 1, "stats.messages_sent": sent}},
        )

    # ── سکه و رفرال ─────────────────────────────────────────────────────
    def add_coins(self, uid: int, amount: int) -> bool:
        res = self._users.update_one({"uid": uid}, {"$inc": {"coins": amount}})
        return res.modified_count > 0

    def inc_referral_count(self, uid: int) -> None:
        self._users.update_one({"uid": uid}, {"$inc": {"referral_count": 1}})

    # ── داده‌های موقتِ TTLدار ────────────────────────────────────────────
    def _kv_id(self, scope: str, key: str) -> str:
        return f"{scope}:{key}"

    def ttl_set(self, scope: str, key: str, value: Any, ttl: int) -> None:
        self._kv.update_one(
            {"_id": self._kv_id(scope, key)},
            {
                "$set": {
                    "scope": scope,
                    "key": key,
                    "v": value,
                    "exp": time.time() + ttl,
                }
            },
            upsert=True,
        )

    def ttl_get(self, scope: str, key: str) -> Optional[Any]:
        doc = self._kv.find_one({"_id": self._kv_id(scope, key)}, {"_id": 0, "v": 1, "exp": 1})
        if not doc:
            return None
        if doc.get("exp", 0) <= time.time():
            self._kv.delete_one({"_id": self._kv_id(scope, key)})
            return None
        return doc.get("v")

    def ttl_delete(self, scope: str, key: str) -> None:
        self._kv.delete_one({"_id": self._kv_id(scope, key)})

    def ttl_count(self, scope: str, key: str, window: int) -> int:
        doc = self._kv.find_one({"_id": self._kv_id(scope, key)}, {"_id": 0, "v": 1, "exp": 1})
        if not doc:
            return 0
        if doc.get("exp", 0) <= time.time():
            self._kv.delete_one({"_id": self._kv_id(scope, key)})
            return 0
        stamps = doc.get("v")
        if not isinstance(stamps, list):
            return 1
        cutoff = time.time() - window
        stamps = [t for t in stamps if t > cutoff]
        self._kv.update_one(
            {"_id": self._kv_id(scope, key)}, {"$set": {"v": stamps}}
        )
        return len(stamps)

    def ttl_prune(self, scope: str) -> int:
        res = self._kv.delete_many({"scope": scope, "exp": {"$lte": time.time()}})
        return res.deleted_count


def connect(uri: str) -> Storage:
    """اتصال به Mongo — در صورت شکست، به حافظهٔ موقت تنزل می‌کند.

    تنزل فقط هنگام راه‌اندازی رخ می‌دهد و یک‌بار لاگ می‌شود.
    """
    try:
        storage = MongoStorage(uri)
        storage._client.admin.command("ping")  # type: ignore[attr-defined]
        log.info("MongoDB متصل شد")
        return storage
    except PyMongoError as exc:
        log.warning("خطا در اتصال به MongoDB: %s — از حافظهٔ موقت استفاده می‌شود.", exc)
        return MemoryStorage()
