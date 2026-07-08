"\"\"\"handlers/user.py — User menus, deposit flow, referrals, leaderboard, language.\"\"\"

import logging
from datetime import datetime, timezone, timedelta

from pyrogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message,
)

from database import (
    get_user, get_balance, get_user_orders, add_transaction, utr_exists,
    is_admin, get_config, get_referral_count, get_referral_earnings,
    top_referrers, top_depositors, set_language, get_language,
)
from handlers.i18n import t

logger = logging.getLogger(__name__)

user_states: dict = {}


# ── HELPERS ──────────────────────────────────────────────────
async def _send_new(client, chat_id, prev, text, markup=None, photo=None):
    try:
        await prev.delete()
    except Exception:
        pass
    if photo:
        return await client.send_photo(chat_id, photo, caption=text, reply_markup=markup)
    return await client.send_message(chat_id, text, reply_markup=markup)


def _prev(update):
    return update.message if isinstance(update, CallbackQuery) else update


def _usr(update):
    return update.from_user


def _now_ist() -> str:
    ist = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(ist).strftime(\"%d %b %Y, %I:%M %p IST\")


def _mask_number(phone: str) -> str:
    phone = phone.strip()
    if len(phone) <= 4:
        return phone
    return f\"{phone[:3]}{'*' * (len(phone) - 4)}{phone[-1]}\"


# ── MAIN MENU ────────────────────────────────────────────────
def _main_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, \"btn_shop\"),    callback_data=\"open_shop\"),
         InlineKeyboardButton(t(lang, \"btn_deposit\"), callback_data=\"open_deposit\")],
        [InlineKeyboardButton(t(lang, \"btn_profile\"), callback_data=\"open_profile\"),
         InlineKeyboardButton(t(lang, \"btn_orders\"),  callback_data=\"open_orders\")],
        [InlineKeyboardButton(t(lang, \"btn_refer\"),       callback_data=\"open_refer\"),
         InlineKeyboardButton(t(lang, \"btn_leaderboard\"), callback_data=\"open_leaderboard\")],
        [InlineKeyboardButton(t(lang, \"btn_support\"), callback_data=\"open_support\"),
         InlineKeyboardButton(t(lang, \"btn_rules\"),   callback_data=\"open_rules\")],
        [InlineKeyboardButton(t(lang, \"btn_help\"),    callback_data=\"open_help\"),
         InlineKeyboardButton(t(lang, \"btn_balance\"), callback_data=\"open_balance\")],
        [InlineKeyboardButton(t(lang, \"btn_lang\"),    callback_data=\"open_lang\")],
    ])


async def start(client, update):
    user = _usr(update)

    # Handle referral via /start <referrer_id>
    referred_by = None
    if isinstance(update, Message) and update.text:
        parts = update.text.split(maxsplit=1)
        if len(parts) == 2 and parts[1].strip().isdigit():
            referred_by = int(parts[1].strip())

    doc = get_user(user.id, username=user.username, first_name=user.first_name,
                   referred_by=referred_by)
    lang = doc.get(\"language\", \"en\")

    # Notify referrer on first join (only if newly linked)
    if referred_by and doc.get(\"referred_by\") == referred_by and referred_by != user.id:
        try:
            await client.send_message(
                referred_by,
                f\"👥 **New Referral!**

\"
                f\"🎉 {user.first_name} joined using your link.
\"
                f\"💰 You'll earn a bonus when they make a deposit!\"
            )
        except Exception:
            pass

    text = t(lang, \"start\", name=user.first_name)
    prev = _prev(update)

    if isinstance(update, CallbackQuery):
        await _send_new(client, user.id, prev, text, markup=_main_keyboard(lang))
    else:
        await update.reply(text, reply_markup=_main_keyboard(lang))


# ── BALANCE (plain reply) ────────────────────────────────────
async def balance_cmd(client, message: Message):
    bal = get_balance(message.from_user.id)
    await message.reply(f\"💰 **Your Wallet Balance:** ₹{bal:.2f}\")


# ── PROFILE ──────────────────────────────────────────────────
async def profile_menu(client, update):
    user = _usr(update)
    doc = get_user(user.id, username=user.username, first_name=user.first_name)
    orders = get_user_orders(user.id)
    ref_count = get_referral_count(user.id)

    text = (
        f\"👤 **Your Profile**

\"
        f\"━━━━━━━━━━━━━━━━━━━━━━━━
\"
        f\"🏷️ **Name:** {user.first_name}
\"
        f\"🆔 **User ID:** `{user.id}`
\"
        f\"💰 **Wallet:** ₹{doc.get('balance', 0):.2f}
\"
        f\"💸 **Total Spent:** ₹{doc.get('total_spent', 0):.2f}
\"
        f\"💵 **Total Deposited:** ₹{doc.get('total_deposited', 0):.2f}
\"
        f\"📦 **Purchases:** {len(orders)}
\"
        f\"👥 **Referrals:** {ref_count}
\"
        f\"🎁 **Referral Earnings:** ₹{doc.get('referral_earnings', 0):.2f}
\"
        f\"━━━━━━━━━━━━━━━━━━━━━━━━\"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(\"💵 Deposit\", callback_data=\"open_deposit\"),
         InlineKeyboardButton(\"👥 Refer\",   callback_data=\"open_refer\")],
        [InlineKeyboardButton(\"🔙 Back\", callback_data=\"back_to_main\")],
    ])
    prev = _prev(update)
    if isinstance(update, CallbackQuery):
        await _send_new(client, user.id, prev, text, markup=markup)
    else:
        await update.reply(text, reply_markup=markup)


# ── DEPOSIT ──────────────────────────────────────────────────
async def deposit_menu(client, update):
    user = _usr(update)
    cfg = get_config()
    upi_id = cfg.get(\"upi_id\")
    upi_name = cfg.get(\"upi_name\")
    qr_img = cfg.get(\"upi_image_file_id\")
    prev = _prev(update)

    if not upi_id:
        markup = InlineKeyboardMarkup([[InlineKeyboardButton(\"🔙 Back\", callback_data=\"back_to_main\")]])
        text = \"⚠️ **Payment Not Configured**

Contact support to set up UPI.\"
        if isinstance(update, CallbackQuery):
            await _send_new(client, user.id, prev, text, markup=markup)
        else:
            await update.reply(text, reply_markup=markup)
        return

    text = (
        f\"💵 **Deposit Funds**

\"
        f\"━━━━━━━━━━━━━━━━━━━━━━━━
\"
        f\"💳 **UPI ID:** `{upi_id}`
\"
        f\"👤 **Name:** {upi_name or 'OTP Ocean'}
\"
        f\"━━━━━━━━━━━━━━━━━━━━━━━━

\"
        f\"📋 **Steps:**
\"
        f\"1️⃣ Pay via any UPI app to the ID above
\"
        f\"2️⃣ Enter the **amount** you paid
\"
        f\"3️⃣ Send a **screenshot** of your payment
\"
        f\"4️⃣ Enter the **UTR / Transaction ID** (12–22 digits)

\"
        f\"⏰ _Approvals usually within 5–30 min._\"
    )
    markup = InlineKeyboardMarkup([[InlineKeyboardButton(\"❌ Cancel\", callback_data=\"cancel_deposit\")]])

    user_states[user.id] = {\"step\": \"waiting_amount\"}

    if isinstance(update, CallbackQuery):
        if qr_img:
            await _send_new(client, user.id, prev, text, markup=markup, photo=qr_img)
        else:
            await _send_new(client, user.id, prev, text, markup=markup)
    else:
        if qr_img:
            await client.send_photo(user.id, qr_img, caption=text, reply_markup=markup)
        else:
            await update.reply(text, reply_markup=markup)


# ── ORDERS ───────────────────────────────────────────────────
async def orders_menu(client, update):
    user = _usr(update)
    orders = get_user_orders(user.id)
    prev = _prev(update)

    if not orders:
        text = (\"📦 **My Orders**

━━━━━━━━━━━━━━━━━━━━━━━━
\"
                \"❌ No orders yet.

👉 Head to Shop to buy your first account!\")
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(\"🛒 Shop\", callback_data=\"open_shop\")],
            [InlineKeyboardButton(\"🔙 Back\", callback_data=\"back_to_main\")],
        ])
    else:
        text = \"📦 **My Orders**

━━━━━━━━━━━━━━━━━━━━━━━━
Tap an order to fetch OTP.
✅ = Active   🔒 = Closed\"
        buttons = []
        for o in orders[:10]:
            icon = \"✅\" if o[\"status\"] == \"active\" else \"🔒\"
            label = f\"{icon} {o['country']} — {_mask_number(o['phone'])}\"
            buttons.append([InlineKeyboardButton(label, callback_data=f\"get_otp_{o['order_id']}\")])
        buttons.append([InlineKeyboardButton(\"🔙 Back\", callback_data=\"back_to_main\")])
        markup = InlineKeyboardMarkup(buttons)

    if isinstance(update, CallbackQuery):
        await _send_new(client, user.id, prev, text, markup=markup)
    else:
        await update.reply(text, reply_markup=markup)


# ── REFERRAL ─────────────────────────────────────────────────
async def refer_menu(client, update):
    user = _usr(update)
    cfg = get_config()
    percent = float(cfg.get(\"referral_percent\") or 0)
    min_dep = float(cfg.get(\"min_deposit\") or 0)
    ref_count = get_referral_count(user.id)
    earnings = get_referral_earnings(user.id)

    me = await client.get_me()
    link = f\"https://t.me/{me.username}?start={user.id}\"

    if percent <= 0:
        offer_line = \"ℹ️ _Referral program is temporarily disabled._\"
    else:
        thresh = f\" (min deposit ₹{min_dep:.0f})\" if min_dep > 0 else \"\"
        offer_line = f\"🎁 **You earn {percent}% of every deposit** your friends make{thresh}!\"

    text = (
        f\"👥 **Refer & Earn**

\"
        f\"━━━━━━━━━━━━━━━━━━━━━━━━
\"
        f\"{offer_line}
\"
        f\"━━━━━━━━━━━━━━━━━━━━━━━━

\"
        f\"🔗 **Your Referral Link:**
`{link}`

\"
        f\"📊 **Your Stats:**
\"
        f\"👥 Total Referrals: **{ref_count}**
\"
        f\"💰 Total Earnings: **₹{earnings:.2f}**

\"
        f\"━━━━━━━━━━━━━━━━━━━━━━━━
\"
        f\"💡 Share your link. When they deposit, you earn instantly!\"
    )
    share_url = f\"https://t.me/share/url?url={link}&text=Get%20premium%20Telegram%20accounts%20on%20OTP%20Ocean!\"
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(\"📤 Share Link\", url=share_url)],
        [InlineKeyboardButton(\"🔙 Back\", callback_data=\"back_to_main\")],
    ])
    prev = _prev(update)
    if isinstance(update, CallbackQuery):
        await _send_new(client, user.id, prev, text, markup=markup)
    else:
        await update.reply(text, reply_markup=markup)


# ── LEADERBOARD ──────────────────────────────────────────────
async def leaderboard_menu(client, update):
    user = _usr(update)
    refs = top_referrers(10)
    deps = top_depositors(10)

    lines = [\"🏆 **Leaderboard**

━━━━━━━━━━━━━━━━━━━━━━━━
**Top Referrers 👥**\"]
    if refs:
        for i, r in enumerate(refs, 1):
            medal = {1: \"🥇\", 2: \"🥈\", 3: \"🥉\"}.get(i, f\"{i}.\")
            name = (r[\"first_name\"] or \"User\")[:15]
            lines.append(f\"{medal} {name} — {r['count']} refs (₹{r['earnings']:.0f})\")
    else:
        lines.append(\"_No referrals yet._\")

    lines.append(\"
━━━━━━━━━━━━━━━━━━━━━━━━
**Top Depositors 💰**\")
    if deps:
        for i, d in enumerate(deps, 1):
            medal = {1: \"🥇\", 2: \"🥈\", 3: \"🥉\"}.get(i, f\"{i}.\")
            name = (d.get(\"first_name\") or \"User\")[:15]
            lines.append(f\"{medal} {name} — ₹{d.get('total_deposited', 0):.0f}\")
    else:
        lines.append(\"_No deposits yet._\")

    lines.append(\"
━━━━━━━━━━━━━━━━━━━━━━━━\")
    text = \"
\".join(lines)
    markup = InlineKeyboardMarkup([[InlineKeyboardButton(\"🔙 Back\", callback_data=\"back_to_main\")]])
    prev = _prev(update)
    if isinstance(update, CallbackQuery):
        await _send_new(client, user.id, prev, text, markup=markup)
    else:
        await update.reply(text, reply_markup=markup)


# ── LANGUAGE ─────────────────────────────────────────────────
async def language_menu(client, update):
    user = _usr(update)
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(\"🇬🇧 English\", callback_data=\"setlang_en\"),
         InlineKeyboardButton(\"🇮🇳 हिन्दी\",  callback_data=\"setlang_hi\")],
        [InlineKeyboardButton(\"🔙 Back\", callback_data=\"back_to_main\")],
    ])
    text = \"🌐 **Select Language / भाषा चुनें**\"
    prev = _prev(update)
    if isinstance(update, CallbackQuery):
        await _send_new(client, user.id, prev, text, markup=markup)
    else:
        await update.reply(text, reply_markup=markup)


async def set_language_callback(client, callback: CallbackQuery):
    lang = callback.data.replace(\"setlang_\", \"\")
    if lang not in (\"en\", \"hi\"):
        return
    set_language(callback.from_user.id, lang)
    await callback.answer(t(lang, \"lang_set\"), show_alert=False)
    await start(client, callback)


# ── HELP ─────────────────────────────────────────────────────
async def help_menu(client, update):
    user = _usr(update)
    prev = _prev(update)
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(\"👤 User Commands\", callback_data=\"help_user\")],
        [InlineKeyboardButton(\"🔐 Admin Commands\", callback_data=\"help_admin\")],
        [InlineKeyboardButton(\"🔙 Back\", callback_data=\"back_to_main\")],
    ])
    text = \"📖 **OTP Ocean — Help**

Choose a category:\"
    if isinstance(update, CallbackQuery):
        await _send_new(client, user.id, prev, text, markup=markup)
    else:
        await update.reply(text, reply_markup=markup)


USER_HELP = (
    \"👤 **User Commands**

━━━━━━━━━━━━━━━━━━━━━━━━
\"
    \"/start — 🏠 Main menu
\"
    \"/shop — 🛒 Browse accounts
\"
    \"/orders — 📦 My orders + OTP
\"
    \"/balance — 💰 Wallet balance
\"
    \"/profile — 👤 My profile
\"
    \"/refer — 👥 Referral link
\"
    \"/leaderboard — 🏆 Top users
\"
    \"/language — 🌐 Change language
\"
    \"/help — 📖 This menu
\"
    \"━━━━━━━━━━━━━━━━━━━━━━━━\"
)

ADMIN_HELP = (
    \"🔐 **Admin Commands**

━━━━━━━━━━━━━━━━━━━━━━━━
\"
    \"/stats — 📊 Bot stats
\"
    \"/addbal `<uid> <amt>` — ➕ Add balance
\"
    \"/broadcast `<text>` — 📢 Send to all
\"
    \"/addadmin `<uid>` — 👑 Promote
\"
    \"/rmadmin `<uid>` — 🚫 Demote
\"
    \"/ban `<uid>` — 🔨 Ban user
\"
    \"/unban `<uid>` — ♻️ Unban user
\"
    \"/setupi `<upi> <name>` — 💳 UPI
\"
    \"/setfsub — 📢 FSub channels
\"
    \"/addacc — ➕ Add account
\"
    \"/login — 🔑 Login + auto-setup
\"
    \"/cancellogin — ❌ Cancel login
\"
    \"/recovery `<email>` — 📧 Recovery email
\"
    \"/fa2 `<password>` — 🔐 Default 2FA
\"
    \"/setrefer `<percent>` — 👥 Referral %
\"
    \"/setmindep `<amount>` — 💵 Min deposit for referral
\"
    \"/setwelcome `<amt>` — 🎁 Signup bonus
\"
    \"/sold — 📋 Recent sales
\"
    \"━━━━━━━━━━━━━━━━━━━━━━━━\"
)


async def help_detail(client, callback: CallbackQuery):
    user_id = callback.from_user.id
    if callback.data == \"help_admin\":
        if not is_admin(user_id):
            await callback.answer(\"❌ Admin only!\", show_alert=True)
            return
        text = ADMIN_HELP
    else:
        text = USER_HELP
    markup = InlineKeyboardMarkup([[InlineKeyboardButton(\"🔙 Back\", callback_data=\"open_help\")]])
    await _send_new(client, user_id, callback.message, text, markup=markup)


# ── DEPOSIT FLOW STATE MACHINE ───────────────────────────────
async def handle_message(client, message: Message):
    user_id = message.from_user.id
    state = user_states.get(user_id)
    if not state:
        return
    step = state.get(\"step\")

    if step == \"waiting_amount\":
        try:
            amount = float((message.text or \"\").strip())
            if amount <= 0:
                raise ValueError
        except ValueError:
            await message.reply(\"❌ **Invalid amount!** Enter a positive number, e.g. `200`\")
            return
        user_states[user_id] = {\"step\": \"waiting_ss\", \"amount\": amount}
        await message.reply(f\"✅ Amount: ₹{amount:.2f}

📸 Now send the **payment screenshot** (photo).\")

    elif step == \"waiting_ss\":
        if not message.photo:
            await message.reply(\"📸 Please send a **photo** (not a file).\")
            return
        user_states[user_id].update({\"step\": \"waiting_utr\", \"ss_file_id\": message.photo.file_id})
        await message.reply(\"✅ Screenshot received.

🔢 Now send the **UTR / Transaction ID** (12–22 digits).\")

    elif step == \"waiting_utr\":
        utr = (message.text or \"\").strip()
        if not utr.isdigit() or not (12 <= len(utr) <= 22):
            await message.reply(\"⚠️ UTR must be **12–22 digits only**.\")
            return
        if utr_exists(utr):
            await message.reply(\"❌ This UTR has already been submitted.\")
            return

        amount = state[\"amount\"]
        ss = state[\"ss_file_id\"]
        add_transaction(user_id, utr, amount, ss)

        from info import LOG_GROUP
        user = message.from_user
        uname = f\"@{user.username}\" if user.username else \"_(no username)_\"
        caption = (
            f\"💸 **NEW PAYMENT REQUEST**

\"
            f\"👤 {user.first_name} ({uname})
\"
            f\"🆔 `{user_id}`
\"
            f\"💰 ₹{amount:.2f}
\"
            f\"🔢 UTR: `{utr}`
\"
            f\"📅 {_now_ist()}\"
        )
        log_markup = InlineKeyboardMarkup([[
            InlineKeyboardButton(\"✅ Approve\", callback_data=f\"approve_{utr}_{user_id}_{amount}\"),
            InlineKeyboardButton(\"❌ Reject\",  callback_data=f\"reject_{utr}_{user_id}\"),
        ]])
        try:
            await client.send_photo(LOG_GROUP, ss, caption=caption, reply_markup=log_markup)
        except Exception as e:
            logger.error(f\"❌ Log group send failed: {e}\")

        await message.reply(
            f\"✅ **Payment Submitted!**

💰 ₹{amount:.2f}
🔢 `{utr}`

⏳ You'll be notified after approval.\"
        )
        user_states.pop(user_id, None)
