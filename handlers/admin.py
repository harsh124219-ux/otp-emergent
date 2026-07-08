"\"\"\"handlers/admin.py — Admin commands + interactive flows.\"\"\"

import logging
import asyncio
from datetime import datetime, timezone, timedelta

from pyrogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message,
)

from database import (
    is_admin, get_config, update_config, add_admin, remove_admin,
    add_fsub_channel, get_fsub_channels, add_balance, get_balance,
    add_account, get_all_user_ids, _col, set_banned,
)
from info import ADMIN_ID

logger = logging.getLogger(__name__)

admin_states: dict = {}


def _now_ist() -> str:
    ist = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(ist).strftime(\"%d %b %Y, %I:%M %p IST\")


# ── STATS ────────────────────────────────────────────────────
async def stats(client, message: Message):
    if not is_admin(message.from_user.id):
        return
    users_c = _col(\"users\").count_documents({})
    banned_c = _col(\"users\").count_documents({\"banned\": True})
    txns = _col(\"transactions\").count_documents({})
    pending = _col(\"transactions\").count_documents({\"status\": \"pending\"})
    approved = _col(\"transactions\").count_documents({\"status\": \"approved\"})
    rejected = _col(\"transactions\").count_documents({\"status\": \"rejected\"})
    avail = _col(\"accounts\").count_documents({\"status\": \"available\"})
    sold = _col(\"accounts\").count_documents({\"status\": \"sold\"})
    orders = _col(\"orders\").count_documents({})
    active = _col(\"orders\").count_documents({\"status\": \"active\"})

    pipe = [{\"$match\": {\"status\": \"approved\"}}, {\"$group\": {\"_id\": None, \"t\": {\"$sum\": \"$amount\"}}}]
    rev = list(_col(\"transactions\").aggregate(pipe))
    revenue = rev[0][\"t\"] if rev else 0.0

    cfg = get_config()
    await message.reply(
        f\"📊 **Bot Statistics**

\"
        f\"━━━━━━━━━━━━━━━━━━━━━━━━
\"
        f\"👥 Users: {users_c}  (🚫 banned: {banned_c})
\"
        f\"💸 Transactions: {txns}
\"
        f\"  ⏳ Pending: {pending}  ✅ Approved: {approved}  ❌ Rejected: {rejected}
\"
        f\"💰 Revenue: ₹{revenue:.2f}
\"
        f\"📱 Accounts: {avail + sold}  (✅ {avail}  💰 {sold})
\"
        f\"📦 Orders: {orders}  (🟢 active: {active})
\"
        f\"━━━━━━━━━━━━━━━━━━━━━━━━
\"
        f\"⚙️ **Settings**
\"
        f\"👥 Referral %: {cfg.get('referral_percent') or 0}
\"
        f\"💵 Min Deposit (referral): ₹{cfg.get('min_deposit') or 0}
\"
        f\"🎁 Welcome Bonus: ₹{cfg.get('welcome_bonus') or 0}
\"
        f\"━━━━━━━━━━━━━━━━━━━━━━━━
\"
        f\"🕐 {_now_ist()}\"
    )


# ── ADD BALANCE ──────────────────────────────────────────────
async def add_bal(client, message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 3:
        await message.reply(\"❌ Usage: `/addbal <user_id> <amount>`\")
        return
    try:
        uid = int(parts[1]); amt = float(parts[2])
        if amt <= 0: raise ValueError
    except ValueError:
        await message.reply(\"❌ Invalid arguments.\")
        return
    new_bal = add_balance(uid, amt)
    await message.reply(f\"✅ Added ₹{amt:.2f} to `{uid}`
New balance: ₹{new_bal:.2f}\")
    try:
        await client.send_message(uid, f\"🎁 Admin added ₹{amt:.2f} to your wallet!
💰 New balance: ₹{new_bal:.2f}\")
    except Exception:
        pass


# ── BROADCAST ────────────────────────────────────────────────
async def broadcast(client, message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split(None, 1)
    if len(parts) < 2 or not parts[1].strip():
        await message.reply(\"❌ Usage: `/broadcast <message>`\")
        return
    text = parts[1].strip()
    uids = get_all_user_ids()
    status = await message.reply(f\"📢 Broadcasting to {len(uids)} users...\")
    sent = fail = 0
    for uid in uids:
        try:
            await client.send_message(uid, f\"📢 **Announcement**

{text}\")
            sent += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)
    try:
        await status.edit_text(f\"✅ Done. Sent: {sent} | Failed: {fail}\")
    except Exception:
        await message.reply(f\"✅ Sent: {sent} | Failed: {fail}\")


# ── MANAGE ADMINS ────────────────────────────────────────────
async def manage_admins(client, message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()
    cmd = parts[0].lstrip(\"/\").lower()
    if len(parts) != 2:
        await message.reply(f\"❌ Usage: `/{cmd} <user_id>`\")
        return
    try:
        uid = int(parts[1])
    except ValueError:
        await message.reply(\"❌ User ID must be a number.\")
        return
    if cmd == \"addadmin\":
        add_admin(uid)
        await message.reply(f\"👑 `{uid}` is now an admin.\")
        try:
            await client.send_message(uid, \"🎉 You've been promoted to Admin!\")
        except Exception:
            pass
    else:
        if not remove_admin(uid):
            await message.reply(\"❌ Cannot remove primary admin.\")
        else:
            await message.reply(f\"✅ `{uid}` removed from admins.\")


# ── BAN / UNBAN ──────────────────────────────────────────────
async def ban_user(client, message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()
    cmd = parts[0].lstrip(\"/\").lower()
    if len(parts) != 2:
        await message.reply(f\"❌ Usage: `/{cmd} <user_id>`\")
        return
    try:
        uid = int(parts[1])
    except ValueError:
        await message.reply(\"❌ User ID must be a number.\")
        return
    if uid == ADMIN_ID:
        await message.reply(\"❌ Cannot ban primary admin.\")
        return
    banned = (cmd == \"ban\")
    set_banned(uid, banned)
    await message.reply(f\"{'🔨 Banned' if banned else '♻️ Unbanned'}: `{uid}`\")


# ── CONFIG COMMANDS ──────────────────────────────────────────
async def set_config_cmd(client, message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split(None, 2)
    cmd = parts[0].lstrip(\"/\").lower()

    if cmd == \"setupi\":
        if len(parts) < 3:
            await message.reply(\"❌ Usage: `/setupi <upi_id> <display_name>`\")
            return
        update_config(\"upi_id\", parts[1])
        update_config(\"upi_name\", parts[2])
        markup = InlineKeyboardMarkup([[InlineKeyboardButton(\"🖼️ Upload QR Image\", callback_data=\"set_upi_image\")]])
        await message.reply(f\"✅ UPI: `{parts[1]}` — {parts[2]}

Optionally upload QR image:\", reply_markup=markup)

    elif cmd == \"setfsub\":
        await show_fsub_manager(client, message)

    elif cmd == \"recovery\":
        if len(parts) < 2:
            await message.reply(\"❌ Usage: `/recovery <email>`\")
            return
        email = parts[1]
        if \"@\" not in email or \".\" not in email:
            await message.reply(\"❌ Invalid email.\")
            return
        update_config(\"recovery_email\", email)
        await message.reply(f\"✅ Recovery email set: `{email}`\")

    elif cmd == \"fa2\":
        if len(parts) < 2:
            await message.reply(\"❌ Usage: `/fa2 <password>`\")
            return
        pwd = parts[1]
        if len(pwd) < 6:
            await message.reply(\"❌ 2FA password must be ≥6 chars.\")
            return
        update_config(\"admin_2fa\", pwd)
        await message.reply(f\"✅ Default 2FA saved.\")

    elif cmd == \"setrefer\":
        if len(parts) < 2:
            await message.reply(\"❌ Usage: `/setrefer <percent>` (0 to disable)\")
            return
        try:
            p = float(parts[1])
            if p < 0 or p > 100:
                raise ValueError
        except ValueError:
            await message.reply(\"❌ Percent must be 0–100.\")
            return
        update_config(\"referral_percent\", p)
        state = \"DISABLED\" if p == 0 else f\"{p}%\"
        await message.reply(f\"✅ Referral: **{state}**

_Referrer earns {p}% of every referred user's deposit._\")

    elif cmd == \"setmindep\":
        if len(parts) < 2:
            await message.reply(\"❌ Usage: `/setmindep <amount>`\")
            return
        try:
            m = float(parts[1])
            if m < 0: raise ValueError
        except ValueError:
            await message.reply(\"❌ Amount must be ≥ 0.\")
            return
        update_config(\"min_deposit\", m)
        await message.reply(f\"✅ Min deposit for referral bonus: ₹{m:.2f}\")

    elif cmd == \"setwelcome\":
        if len(parts) < 2:
            await message.reply(\"❌ Usage: `/setwelcome <amount>`\")
            return
        try:
            w = float(parts[1])
            if w < 0: raise ValueError
        except ValueError:
            await message.reply(\"❌ Amount must be ≥ 0.\")
            return
        update_config(\"welcome_bonus\", w)
        await message.reply(f\"✅ Welcome bonus: ₹{w:.2f} (applied to new users)\")


# ── FSUB MANAGER ─────────────────────────────────────────────
async def show_fsub_manager(client, update):
    if isinstance(update, CallbackQuery):
        chat_id = update.from_user.id; old = update.message
    else:
        chat_id = update.from_user.id; old = None

    channels = get_fsub_channels()
    ch_text = \"
\".join([f\"  • `{c}`\" for c in channels]) if channels else \"  _(none)_\"

    text = f\"📢 **Force Subscribe Manager**

━━━━━━━━━━━━━━━━━━━━━━━━
**Current:**
{ch_text}
━━━━━━━━━━━━━━━━━━━━━━━━\"
    buttons = [[InlineKeyboardButton(\"➕ Add Channel\", callback_data=\"add_fsub_prompt\")]]
    if channels:
        buttons.append([InlineKeyboardButton(\"➖ Remove Channel\", callback_data=\"rm_fsub_menu\")])
    buttons.append([InlineKeyboardButton(\"🔙 Back\", callback_data=\"back_to_main\")])
    markup = InlineKeyboardMarkup(buttons)

    if old:
        try: await old.delete()
        except Exception: pass
        await client.send_message(chat_id, text, reply_markup=markup)
    else:
        await update.reply(text, reply_markup=markup)


async def show_rm_fsub_menu(client, callback: CallbackQuery):
    channels = get_fsub_channels()
    if not channels:
        await callback.answer(\"ℹ️ No channels.\", show_alert=True); return
    buttons = [[InlineKeyboardButton(f\"🗑️ {c}\", callback_data=f\"rm_fsub_{c}\")] for c in channels]
    buttons.append([InlineKeyboardButton(\"🔙 Back\", callback_data=\"setfsub_menu\")])
    try: await callback.message.delete()
    except Exception: pass
    await client.send_message(callback.from_user.id, \"➖ **Select to remove:**\",
                              reply_markup=InlineKeyboardMarkup(buttons))


# ── SOLD ─────────────────────────────────────────────────────
async def sold_accounts(client, message: Message):
    if not is_admin(message.from_user.id):
        return
    orders = list(_col(\"orders\").find({}).sort(\"timestamp\", -1).limit(50))
    if not orders:
        await message.reply(\"📋 No orders yet.\"); return
    lines = [\"📋 **Recent 50 Orders**
━━━━━━━━━━━━━━━━━━━━━━━━\"]
    for o in orders:
        ts = o.get(\"timestamp\")
        d = ts.strftime(\"%d/%m %H:%M\") if ts else \"N/A\"
        icon = \"🟢\" if o.get(\"status\") == \"active\" else \"🔒\"
        lines.append(f\"{icon} `{o['phone']}` | 👤 `{o['user_id']}` | ₹{o.get('price', 0):.0f} | {d}\")
    text = \"
\".join(lines)
    if len(text) > 4096:
        chunks = [lines[0]]
        for ln in lines[1:]:
            if len(\"
\".join(chunks + [ln])) > 4000:
                await message.reply(\"
\".join(chunks)); chunks = [ln]
            else:
                chunks.append(ln)
        if chunks: await message.reply(\"
\".join(chunks))
    else:
        await message.reply(text)


# ── INTERACTIVE /addacc + UPI IMAGE ──────────────────────────
async def add_acc_start(client, message: Message):
    if not is_admin(message.from_user.id):
        return
    admin_states[message.from_user.id] = {\"step\": \"phone\"}
    await message.reply(
        \"➕ **Add Account — Step 1/4**

📱 Enter phone (+country code):
Example: `+919876543210`\"
    )


async def set_upi_image_start(client, callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer(\"❌ Admin only!\", show_alert=True); return
    admin_states[callback.from_user.id] = {\"step\": \"waiting_upi_image\"}
    await callback.answer(\"📸 Send QR image now.\")
    await client.send_message(callback.from_user.id, \"📸 Send the UPI QR **photo** now.\")


async def handle_admin_msg(client, message: Message):
    admin_id = message.from_user.id
    state = admin_states.get(admin_id)
    if not state:
        return
    step = state.get(\"step\")

    if step == \"waiting_upi_image\":
        if not message.photo:
            await message.reply(\"📸 Please send a photo, not a file.\"); return
        update_config(\"upi_image_file_id\", message.photo.file_id)
        admin_states.pop(admin_id, None)
        await message.reply(\"✅ UPI QR saved!\")

    elif step == \"waiting_fsub_channel\":
        ch = (message.text or \"\").strip()
        if not ch:
            await message.reply(\"⚠️ Enter a channel ID or @username.\"); return
        add_fsub_channel(ch)
        admin_states.pop(admin_id, None)
        await message.reply(f\"✅ Added: `{ch}`\")

    elif step == \"phone\":
        phone = (message.text or \"\").strip()
        if not phone.startswith(\"+\") or len(phone) < 7:
            await message.reply(\"❌ Invalid phone.\"); return
        state.update({\"step\": \"session\", \"phone\": phone})
        await message.reply(f\"✅ Phone: `{phone}`

**Step 2/4** — Enter Pyrogram session string:\")

    elif step == \"session\":
        s = (message.text or \"\").strip()
        if len(s) < 50:
            await message.reply(\"❌ Session string too short.\"); return
        state.update({\"step\": \"country\", \"session\": s})
        await message.reply(\"✅ Saved.

**Step 3/4** — Enter country (e.g. `INDIA`):\")

    elif step == \"country\":
        c = (message.text or \"\").strip().upper()
        if not c:
            await message.reply(\"❌ Cannot be empty.\"); return
        state.update({\"step\": \"price\", \"country\": c})
        await message.reply(f\"✅ Country: `{c}`

**Step 4/4** — Enter price (₹):\")

    elif step == \"price\":
        try:
            p = float((message.text or \"\").strip())
            if p <= 0: raise ValueError
        except ValueError:
            await message.reply(\"❌ Price must be positive.\"); return
        cfg = get_config()
        pwd = cfg.get(\"admin_2fa\") or \"\"
        email = cfg.get(\"recovery_email\") or \"\"
        add_account(state[\"phone\"], state[\"session\"], state[\"country\"], p, pwd, email)
        admin_states.pop(admin_id, None)
        await message.reply(
            f\"✅ **Account Added!**

📱 `{state['phone']}`
🌍 {state['country']}
💰 ₹{p:.2f}
🔐 2FA: `{pwd or 'none'}`
📧 Email: `{email or 'none'}`\"
        )
