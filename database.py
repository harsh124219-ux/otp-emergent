"""database.py — MongoDB layer for OTP Ocean.

Collections:
  users        — {user_id, username, first_name, balance, total_spent, joined,
                  language, referred_by, referral_earnings, banned}
  config       — settings singleton
  transactions — payment requests
  accounts     — shop inventory
  orders       — user purchases
"""

import logging
from datetime import datetime, timezone
from pymongo import MongoClient, ASCENDING, DESCENDING

logger = logging.getLogger(__name__)

_mongo_client = None
db = None


def init_db():
    """Connect to MongoDB. Call once in main() before bot starts."""
    global _mongo_client, db
    from info import MONGO_URL
    _mongo_client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
    db = _mongo_client["otpbot"]
    _mongo_client.admin.command("ping")
    logger.info("✅ MongoDB connected successfully.")

    try:
        db["users"].create_index("user_id", unique=True)
        db["users"].create_index("referred_by")
        db["transactions"].create_index("utr", unique=True)
        db["accounts"].create_index("phone", unique=True)
        db["orders"].create_index("order_id", unique=True)
        db["orders"].create_index("user_id")
        db["accounts"].create_index([("status", ASCENDING), ("country", ASCENDING)])
        logger.info("✅ DB indexes ensured.")
    except Exception as e:
        logger.warning(f"⚠️ Index warning: {e}")


def _col(name: str):
    return db[name] if db is not None else None


# ── CONFIG ────────────────────────────────────────────────────
def get_config() -> dict:
    from info import ADMIN_ID
    col = _col("config")
    doc = col.find_one({"type": "settings"})
    if doc is None:
        default = {
            "type": "settings",
            "admins": [ADMIN_ID] if ADMIN_ID else [],
            "fsub_channels": [],
            "upi_id": None,
            "upi_name": None,
            "upi_image_file_id": None,
            "recovery_email": None,
            "admin_2fa": None,
            "referral_percent": 0,   # 0 = referral OFF
            "daily_bonus": 0,        # 0 = daily bonus OFF
            "min_deposit": 0,        # minimum deposit for referral to trigger
            "welcome_bonus": 0,      # signup bonus
            "updated_at": datetime.now(timezone.utc),
        }
        col.insert_one(default)
        doc = col.find_one({"type": "settings"})
    return doc


def update_config(key: str, value) -> None:
    _col("config").update_one(
        {"type": "settings"},
        {"$set": {key: value, "updated_at": datetime.now(timezone.utc)}},
        upsert=True,
    )


def is_admin(user_id: int) -> bool:
    return user_id in get_config().get("admins", [])


def add_admin(user_id: int):
    _col("config").update_one({"type": "settings"}, {"$addToSet": {"admins": user_id}}, upsert=True)


def remove_admin(user_id: int) -> bool:
    from info import ADMIN_ID
    if user_id == ADMIN_ID:
        return False
    _col("config").update_one({"type": "settings"}, {"$pull": {"admins": user_id}})
    return True


def get_fsub_channels() -> list:
    return get_config().get("fsub_channels", [])


def add_fsub_channel(ch: str):
    _col("config").update_one({"type": "settings"}, {"$addToSet": {"fsub_channels": ch}}, upsert=True)


def remove_fsub_channel(ch: str):
    _col("config").update_one({"type": "settings"}, {"$pull": {"fsub_channels": ch}})


# ── USERS ─────────────────────────────────────────────────────
def get_user(user_id: int, username: str = None, first_name: str = None,
             referred_by: int = None) -> dict:
    col = _col("users")
    doc = col.find_one({"user_id": user_id})
    if doc is None:
        cfg = get_config()
        welcome = float(cfg.get("welcome_bonus") or 0)
        doc = {
            "user_id": user_id,
            "username": username,
            "first_name": first_name or "User",
            "balance": welcome,
            "total_spent": 0.0,
            "total_deposited": 0.0,
            "joined": datetime.now(timezone.utc),
            "language": "en",
            "referred_by": referred_by if referred_by and referred_by != user_id else None,
            "referral_earnings": 0.0,
            "banned": False,
            "last_bonus": None,
        }
        col.insert_one(doc)
        doc = col.find_one({"user_id": user_id})
    else:
        updates = {}
        if username is not None:
            updates["username"] = username
        if first_name is not None:
            updates["first_name"] = first_name
        # Only set referred_by if user doesn't already have one AND it's valid
        if referred_by and not doc.get("referred_by") and referred_by != user_id:
            updates["referred_by"] = referred_by
        if updates:
            col.update_one({"user_id": user_id}, {"$set": updates})
            doc.update(updates)
    return doc


def get_balance(user_id: int) -> float:
    return get_user(user_id).get("balance", 0.0)


def add_balance(user_id: int, amount: float) -> float:
    get_user(user_id)
    _col("users").update_one({"user_id": user_id}, {"$inc": {"balance": amount}})
    return get_balance(user_id)


def deduct_balance(user_id: int, amount: float) -> bool:
    doc = get_user(user_id)
    if doc.get("balance", 0.0) < amount:
        return False
    _col("users").update_one(
        {"user_id": user_id},
        {"$inc": {"balance": -amount, "total_spent": amount}},
    )
    return True


def add_deposit(user_id: int, amount: float):
    """Track total lifetime deposits (for leaderboard/analytics)."""
    _col("users").update_one({"user_id": user_id}, {"$inc": {"total_deposited": amount}})


def set_language(user_id: int, lang: str):
    _col("users").update_one({"user_id": user_id}, {"$set": {"language": lang}})


def get_language(user_id: int) -> str:
    doc = _col("users").find_one({"user_id": user_id}, {"language": 1})
    return (doc or {}).get("language") or "en"


def is_banned(user_id: int) -> bool:
    doc = _col("users").find_one({"user_id": user_id}, {"banned": 1})
    return bool((doc or {}).get("banned"))


def set_banned(user_id: int, banned: bool):
    _col("users").update_one({"user_id": user_id}, {"$set": {"banned": banned}}, upsert=True)


def get_all_users() -> list:
    return list(_col("users").find({}))


def get_all_user_ids() -> list:
    return [d["user_id"] for d in _col("users").find({}, {"user_id": 1})]


# ── REFERRALS ─────────────────────────────────────────────────
def apply_referral_bonus(user_id: int, deposit_amount: float) -> tuple:
    """
    Called when a deposit is APPROVED.
    Returns (referrer_id, bonus_amount) or (None, 0) if no referral.
    """
    cfg = get_config()
    percent = float(cfg.get("referral_percent") or 0)
    min_dep = float(cfg.get("min_deposit") or 0)

    if percent <= 0 or deposit_amount < min_dep:
        return None, 0.0

    user = _col("users").find_one({"user_id": user_id})
    if not user:
        return None, 0.0
    referrer_id = user.get("referred_by")
    if not referrer_id:
        return None, 0.0

    bonus = round(deposit_amount * percent / 100.0, 2)
    if bonus <= 0:
        return None, 0.0

    _col("users").update_one(
        {"user_id": referrer_id},
        {"$inc": {"balance": bonus, "referral_earnings": bonus}},
    )
    return referrer_id, bonus


def get_referral_count(user_id: int) -> int:
    return _col("users").count_documents({"referred_by": user_id})


def get_referral_earnings(user_id: int) -> float:
    doc = _col("users").find_one({"user_id": user_id}, {"referral_earnings": 1})
    return float((doc or {}).get("referral_earnings") or 0.0)


def top_referrers(limit: int = 10) -> list:
    pipe = [
        {"$match": {"referred_by": {"$ne": None}}},
        {"$group": {"_id": "$referred_by", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": limit},
    ]
    rows = list(_col("users").aggregate(pipe))
    out = []
    for r in rows:
        u = _col("users").find_one({"user_id": r["_id"]}, {"first_name": 1, "referral_earnings": 1})
        if u:
            out.append({
                "user_id": r["_id"],
                "first_name": u.get("first_name", "User"),
                "count": r["count"],
                "earnings": float(u.get("referral_earnings") or 0.0),
            })
    return out


def top_depositors(limit: int = 10) -> list:
    return list(_col("users").find(
        {"total_deposited": {"$gt": 0}},
        {"user_id": 1, "first_name": 1, "total_deposited": 1},
    ).sort("total_deposited", DESCENDING).limit(limit))


# ── TRANSACTIONS ──────────────────────────────────────────────
def add_transaction(user_id: int, utr: str, amount: float, ss_file_id: str):
    _col("transactions").insert_one({
        "user_id": user_id, "utr": utr, "amount": amount,
        "ss_file_id": ss_file_id, "status": "pending",
        "timestamp": datetime.now(timezone.utc),
    })


def get_transaction(utr: str):
    return _col("transactions").find_one({"utr": utr})


def update_transaction_status(utr: str, status: str):
    _col("transactions").update_one({"utr": utr}, {"$set": {"status": status}})


def utr_exists(utr: str) -> bool:
    return _col("transactions").count_documents({"utr": utr}) > 0


# ── ACCOUNTS ──────────────────────────────────────────────────
def add_account(phone, session_string, country, price, password="", recovery_email=""):
    _col("accounts").update_one(
        {"phone": phone},
        {"$set": {
            "phone": phone, "session_string": session_string,
            "country": country.upper().strip(), "price": price,
            "status": "available", "password": password,
            "recovery_email": recovery_email,
            "added_at": datetime.now(timezone.utc),
        }},
        upsert=True,
    )


def get_available_accounts(country=None):
    q = {"status": "available"}
    if country:
        q["country"] = country.upper().strip()
    return list(_col("accounts").find(q).sort("price", ASCENDING))


def get_accounts_by_country_sorted(country, sort_order):
    d = ASCENDING if sort_order == "low_to_high" else DESCENDING
    return list(_col("accounts").find(
        {"status": "available", "country": country.upper().strip()}
    ).sort("price", d))


def update_account_status(phone, status):
    _col("accounts").update_one({"phone": phone}, {"$set": {"status": status}})


def clear_account_session(phone):
    _col("accounts").update_one({"phone": phone}, {"$set": {"session_string": ""}})


def get_all_countries() -> list:
    return sorted(_col("accounts").distinct("country"))


def get_account(phone):
    return _col("accounts").find_one({"phone": phone})


# ── ORDERS ────────────────────────────────────────────────────
def create_order(user_id, phone, session_string, country, price) -> str:
    order_id = f"ORD{int(datetime.now(timezone.utc).timestamp())}"
    _col("orders").insert_one({
        "order_id": order_id, "user_id": user_id, "phone": phone,
        "session_string": session_string, "country": country,
        "price": price, "status": "active",
        "timestamp": datetime.now(timezone.utc),
    })
    return order_id


def get_user_orders(user_id: int):
    return list(_col("orders").find({"user_id": user_id}).sort("timestamp", DESCENDING))


def get_order(order_id: str):
    return _col("orders").find_one({"order_id": order_id})


def close_order(order_id: str):
    o = get_order(order_id)
    if o:
        _col("orders").update_one(
            {"order_id": order_id},
            {"$set": {"status": "closed", "session_string": ""}},
        )
        clear_account_session(o["phone"])
