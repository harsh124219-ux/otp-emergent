"""
main.py — OTP Ocean Bot entry point (fixed silent-fail bug).

🔧 THE BUG THAT WAS FIXED
─────────────────────────
In the previous version, `@app.on_message()` (global debug logger) was in the
same handler group (default group=0) as all other message handlers.
In Pyrogram, only ONE handler per group fires per update — so the debug logger
consumed every incoming message and no command/state handler ever ran.

FIX: The global debug logger is now in group=-1 (a separate group), so it runs
alongside — not instead of — the real handlers.
"""

import asyncio
import logging
import os
import sys
import time
import traceback
from collections import defaultdict, deque

import aiohttp
import aiohttp.web
from pyrogram import Client, filters, idle
from pyrogram.types import CallbackQuery, Message

# ── LOGGING ────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    stream=sys.stdout,
    force=True,
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logger = logging.getLogger("main")


# ── IMPORTS with startup diagnostics ───────────────────────
def _import_or_die(module_path: str, label: str):
    import importlib
    try:
        mod = importlib.import_module(module_path)
        logger.info(f"✅ Imported: {label}")
        return mod
    except Exception as e:
        logger.critical(f"❌ IMPORT FAILED [{label}]: {e}")
        traceback.print_exc()
        sys.exit(1)


_import_or_die("info", "info")
_import_or_die("database", "database")
_import_or_die("handlers.user", "handlers.user")
_import_or_die("handlers.shop", "handlers.shop")
_import_or_die("handlers.admin", "handlers.admin")
_import_or_die("handlers.payment", "handlers.payment")
_import_or_die("handlers.session", "handlers.session")
_import_or_die("handlers.fsub", "handlers.fsub")

from info import BOT_TOKEN, API_ID, API_HASH, ADMIN_ID, LOG_GROUP, PORT
from database import init_db, is_admin, is_banned

from handlers.user import (
    start, balance_cmd, profile_menu, deposit_menu, orders_menu,
    help_menu, help_detail, handle_message, user_states,
    refer_menu, leaderboard_menu, language_menu, set_language_callback,
)
from handlers.shop import (
    shop_menu, sort_options_menu, view_country_accounts,
    buy_account, get_otp_logic, logout_acc_logic,
)
from handlers.admin import (
    stats, add_bal, broadcast, manage_admins, set_config_cmd,
    show_fsub_manager, show_rm_fsub_menu, sold_accounts,
    add_acc_start, set_upi_image_start, handle_admin_msg,
    admin_states, ban_user,
)
from handlers.payment import (
    payment_callback, handle_admin_rejection_reason, payment_admin_states,
)
from handlers.session import (
    login_command, cancel_login_command, handle_session_message,
    handle_automation_callback, check_incomplete_sessions, session_states,
)
from handlers.fsub import check_fsub, recheck_fsub_callback
from keep_alive import self_ping_loop


# ── BOT CLIENT ─────────────────────────────────────────────
app = Client(
    name="otp_ocean_main",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=(BOT_TOKEN or "").strip(),
    max_concurrent_transmissions=3,
)


# ── RATE LIMITER (anti-spam) ───────────────────────────────
_MAX_REQS = 20            # max messages per window
_WINDOW   = 30            # seconds
_rl_hits: dict = defaultdict(lambda: deque(maxlen=_MAX_REQS))


def _rate_limited(user_id: int) -> bool:
    now = time.time()
    q = _rl_hits[user_id]
    # drop old
    while q and now - q[0] > _WINDOW:
        q.popleft()
    if len(q) >= _MAX_REQS:
        return True
    q.append(now)
    return False


# ── ROUTING CONSTANTS ──────────────────────────────────────
_FSUB_GUARDED = {"open_shop", "open_deposit", "open_orders", "open_profile", "open_refer"}
_USER_CMDS = ["start", "help", "shop", "orders", "balance", "profile",
              "refer", "leaderboard", "language"]
_ADMIN_CMDS = [
    "stats", "addbal", "broadcast", "addadmin", "rmadmin",
    "ban", "unban", "setfsub", "setupi", "addacc", "recovery",
    "fa2", "sold", "login", "cancellogin",
    "setrefer", "setmindep", "setwelcome",
]
_ALL_CMDS = _USER_CMDS + _ADMIN_CMDS


# ══════════════════════════════════════════════════════════
#  DEBUG LOGGER — group=-1 (SEPARATE GROUP, so real handlers still run)
# ══════════════════════════════════════════════════════════
@app.on_message(group=-1)
async def global_debug_logger(client, message: Message):
    uid = message.from_user.id if message.from_user else "?"
    text = (message.text or "[non-text]")[:60]
    ct = message.chat.type.value if message.chat else "?"
    logger.info(f"📨 MSG from {uid} [{ct}]: {text}")


# ══════════════════════════════════════════════════════════
#  USER COMMANDS — group=0 (default)
# ══════════════════════════════════════════════════════════
@app.on_message(filters.command(_USER_CMDS) & filters.private)
async def user_commands_handler(client, message: Message):
    uid = message.from_user.id if message.from_user else 0
    if is_banned(uid):
        try: await message.reply("🚫 You are banned.")
        except Exception: pass
        return
    if _rate_limited(uid):
        try: await message.reply("⏳ Slow down.")
        except Exception: pass
        return

    cmd = message.command[0].lower()
    routes = {
        "start":       start,
        "help":        help_menu,
        "shop":        shop_menu,
        "orders":      orders_menu,
        "balance":     balance_cmd,
        "profile":     profile_menu,
        "refer":       refer_menu,
        "leaderboard": leaderboard_menu,
        "language":    language_menu,
    }
    handler = routes.get(cmd)
    if handler:
        try:
            await handler(client, message)
        except Exception as e:
            logger.exception(f"Error in /{cmd}: {e}")
            try: await message.reply(f"⚠️ Error running /{cmd}. Please try again.")
            except Exception: pass


# ══════════════════════════════════════════════════════════
#  ADMIN COMMANDS
# ══════════════════════════════════════════════════════════
@app.on_message(filters.command(_ADMIN_CMDS) & filters.private)
async def admin_commands_handler(client, message: Message):
    uid = message.from_user.id if message.from_user else 0
    if not is_admin(uid):
        await message.reply("❌ **Access Denied.** Admins only.")
        return

    cmd = message.command[0].lower()
    try:
        if cmd == "stats":            await stats(client, message)
        elif cmd == "addbal":         await add_bal(client, message)
        elif cmd == "broadcast":      await broadcast(client, message)
        elif cmd in ("addadmin", "rmadmin"):  await manage_admins(client, message)
        elif cmd in ("ban", "unban"): await ban_user(client, message)
        elif cmd in ("setupi", "setfsub", "recovery", "fa2",
                     "setrefer", "setmindep", "setwelcome"):
            await set_config_cmd(client, message)
        elif cmd == "addacc":         await add_acc_start(client, message)
        elif cmd == "sold":           await sold_accounts(client, message)
        elif cmd == "login":          await login_command(client, message)
        elif cmd == "cancellogin":    await cancel_login_command(client, message)
    except Exception as e:
        logger.exception(f"Admin cmd /{cmd}: {e}")
        try: await message.reply(f"⚠️ Error running /{cmd}: `{str(e)[:200]}`")
        except Exception: pass


# ══════════════════════════════════════════════════════════
#  GENERIC MESSAGE HANDLER (state machines)
# ══════════════════════════════════════════════════════════
@app.on_message(~filters.command(_ALL_CMDS) & filters.private)
async def generic_message_handler(client, message: Message):
    if not message.from_user:
        return
    uid = message.from_user.id
    if is_banned(uid):
        return
    if _rate_limited(uid):
        try: await message.reply("⏳ Slow down.")
        except Exception: pass
        return

    try:
        # Priority: payment_admin > session > admin > user
        if uid in payment_admin_states:
            await handle_admin_rejection_reason(client, message); return
        if uid in session_states:
            await handle_session_message(client, message); return
        if is_admin(uid) and uid in admin_states:
            await handle_admin_msg(client, message); return
        await handle_message(client, message)
    except Exception as e:
        logger.exception(f"Generic handler: {e}")


# ══════════════════════════════════════════════════════════
#  CALLBACK QUERY HANDLER
# ══════════════════════════════════════════════════════════
@app.on_callback_query()
async def callback_handler(client, callback: CallbackQuery):
    data = callback.data or ""
    uid = callback.from_user.id

    if is_banned(uid):
        try: await callback.answer("🚫 You are banned.", show_alert=True)
        except Exception: pass
        return

    is_payment_cb = data.startswith("approve_") or data.startswith("reject_")
    if not is_payment_cb:
        try: await callback.answer()
        except Exception: pass

    if data in _FSUB_GUARDED:
        if not await check_fsub(client, callback):
            return

    try:
        if data == "back_to_main":
            await start(client, callback)
        elif data == "cancel_deposit":
            user_states.pop(uid, None)
            try: await callback.message.delete()
            except Exception: pass
            await start(client, callback)
        elif data == "check_fsub_again":
            await recheck_fsub_callback(client, callback)

        elif data == "open_shop":         await shop_menu(client, callback)
        elif data == "open_deposit":      await deposit_menu(client, callback)
        elif data == "open_profile":      await profile_menu(client, callback)
        elif data == "open_orders":       await orders_menu(client, callback)
        elif data == "open_refer":        await refer_menu(client, callback)
        elif data == "open_leaderboard":  await leaderboard_menu(client, callback)
        elif data == "open_lang":         await language_menu(client, callback)
        elif data.startswith("setlang_"): await set_language_callback(client, callback)

        elif data == "open_help":         await help_menu(client, callback)
        elif data in ("help_user", "help_admin"): await help_detail(client, callback)

        elif data == "open_rules":
            from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            rules = (
                "📋 **OTP Ocean — Rules**\n\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "🔐 Change 2FA immediately after purchase.\n"
                "🚫 No spam / scam / illegal use.\n"
                "💸 Refund only if account non-functional on delivery.\n"
                "📞 Support: contact via bot menu.\n\n"
                "⚠️ Violation = permanent ban."
            )
            markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]])
            try: await callback.message.delete()
            except Exception: pass
            await client.send_message(uid, rules, reply_markup=markup)

        elif data == "open_support":
            from info import SUPPORT_USERNAME
            from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            support = (
                f"🛟 **Support Center**\n\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📬 Contact: {SUPPORT_USERNAME}\n\n"
                f"❓ OTP not showing? → Trigger login, then 🔄 Refresh\n"
                f"❓ Payment issue? → Check UTR (12–22 digits)\n"
                f"❓ Account broken? → Support within 24h with Order ID\n\n"
                f"⏰ Hours: 9 AM – 11 PM IST"
            )
            markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]])
            try: await callback.message.delete()
            except Exception: pass
            await client.send_message(uid, support, reply_markup=markup)

        elif data == "open_balance":
            from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            from database import get_balance
            bal = get_balance(uid)
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("💵 Deposit", callback_data="open_deposit")],
                [InlineKeyboardButton("🔙 Back",    callback_data="back_to_main")],
            ])
            try: await callback.message.delete()
            except Exception: pass
            await client.send_message(uid, f"💰 **Balance: ₹{bal:.2f}**", reply_markup=markup)

        elif data.startswith("sort_opts_"):    await sort_options_menu(client, callback)
        elif data.startswith("view_country_"): await view_country_accounts(client, callback)
        elif data.startswith("buy_acc_"):      await buy_account(client, callback)
        elif data.startswith("get_otp_"):      await get_otp_logic(client, callback)
        elif data.startswith("logout_confirm_") or data.startswith("logout_acc_"):
            await logout_acc_logic(client, callback)

        elif is_payment_cb:
            await payment_callback(client, callback)

        elif data in ("setup_all", "setup_clean", "setup_sec", "setup_skip"):
            await handle_automation_callback(client, callback)

        elif data == "set_upi_image":
            await set_upi_image_start(client, callback)

        elif data in ("setfsub_menu", "open_setfsub"):
            if is_admin(uid):
                await show_fsub_manager(client, callback)
            else:
                await callback.answer("❌ Admin only!", show_alert=True)

        elif data == "add_fsub_prompt":
            if not is_admin(uid):
                await callback.answer("❌ Admin only!", show_alert=True); return
            admin_states[uid] = {"step": "waiting_fsub_channel"}
            try: await callback.message.delete()
            except Exception: pass
            await client.send_message(uid,
                "📢 **Add FSub Channel**\n\nEnter channel ID or @username:\n\n• `@MyChannel`\n• `-1001234567890`")

        elif data == "rm_fsub_menu":
            if not is_admin(uid):
                await callback.answer("❌ Admin only!", show_alert=True); return
            await show_rm_fsub_menu(client, callback)

        elif data.startswith("rm_fsub_"):
            if not is_admin(uid):
                await callback.answer("❌ Admin only!", show_alert=True); return
            from database import remove_fsub_channel
            ch = data.replace("rm_fsub_", "")
            remove_fsub_channel(ch)
            await callback.answer(f"✅ Removed: {ch}")
            await show_fsub_manager(client, callback)

        else:
            logger.warning(f"⚠️ Unhandled callback: {data!r} from {uid}")
            await callback.answer("⚠️ Unknown action.", show_alert=True)
    except Exception as e:
        logger.exception(f"Callback error [{data}]: {e}")


# ══════════════════════════════════════════════════════════
#  KEEP-ALIVE WEB SERVER
# ══════════════════════════════════════════════════════════
async def start_web_server():
    web_app = aiohttp.web.Application()
    web_app.router.add_get("/",       lambda r: aiohttp.web.Response(text="🌊 OTP Ocean is alive!"))
    web_app.router.add_get("/health", lambda r: aiohttp.web.Response(text="OK"))
    runner = aiohttp.web.AppRunner(web_app)
    await runner.setup()
    site = aiohttp.web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"🌐 Web server on port {PORT}")
    return runner


# ══════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════
def _now_ist():
    from datetime import datetime, timezone, timedelta
    ist = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(ist).strftime("%d %b %Y, %I:%M %p IST")


async def main():
    logger.info("🌊 ─── OTP Ocean Bot Starting ───")

    # Validate env
    missing = [k for k, v in [
        ("BOT_TOKEN", BOT_TOKEN), ("API_ID", API_ID), ("API_HASH", API_HASH),
        ("ADMIN_ID", ADMIN_ID), ("LOG_GROUP", LOG_GROUP),
    ] if not v]
    if missing:
        logger.critical(f"❌ Missing env vars: {', '.join(missing)}")
        logger.critical("👉 Set them on Heroku/Railway or in .env — see info.py for details.")
        sys.exit(1)

    # DB
    logger.info("🍃 Connecting to MongoDB...")
    try:
        init_db()
    except Exception as e:
        logger.critical(f"❌ MongoDB connection failed: {e}")
        traceback.print_exc()
        sys.exit(1)

    # Clear stale updates
    try:
        async with aiohttp.ClientSession() as s:
            await s.get(f"https://api.telegram.org/bot{BOT_TOKEN.strip()}/deleteWebhook?drop_pending_updates=true",
                        timeout=aiohttp.ClientTimeout(total=10))
        logger.info("✅ Cleared any pending webhook/updates.")
    except Exception as e:
        logger.warning(f"⚠️ Update clear (non-fatal): {e}")

    web_runner = None
    async with app:
        me = await app.get_me()
        logger.info(f"🤖 Bot started: @{me.username} (ID: {me.id})")

        try:
            web_runner = await start_web_server()
        except Exception as e:
            logger.warning(f"⚠️ Web server: {e}")

        try:
            await app.send_message(
                ADMIN_ID,
                f"🌊 **OTP Ocean is Online!**\n\n🤖 @{me.username}\n📅 {_now_ist()}\n\n✅ All systems operational."
            )
        except Exception as e:
            logger.warning(f"⚠️ Startup admin msg: {e}")

        loop = asyncio.get_running_loop()
        loop.create_task(check_incomplete_sessions(app))
        loop.create_task(self_ping_loop())

        logger.info("🟢 Bot ready & polling!")
        await idle()

    if web_runner:
        await web_runner.cleanup()
    logger.info("🔴 Bot stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Stopped by user.")
    except Exception as e:
        logger.critical(f"💥 Critical error: {e}")
        traceback.print_exc()
        sys.exit(1)
