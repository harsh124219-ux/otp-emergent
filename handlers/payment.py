"""handlers/payment.py — Admin payment approval/rejection + referral bonus trigger."""

import logging
from pyrogram.types import CallbackQuery

from database import (
    get_transaction, update_transaction_status, add_balance,
    is_admin, apply_referral_bonus, add_deposit,
)

logger = logging.getLogger(__name__)

payment_admin_states: dict = {}


async def payment_callback(client, callback: CallbackQuery):
    admin_id = callback.from_user.id
    if not is_admin(admin_id):
        await callback.answer("❌ Not an admin!", show_alert=True)
        return

    data = callback.data

    # ── APPROVE ─────────────────────────────────
    if data.startswith("approve_"):
        parts = data.split("_")
        utr = parts[1]
        user_id = int(parts[2])
        amount = float(parts[3])

        txn = get_transaction(utr)
        if not txn:
            await callback.answer("❌ Not found!", show_alert=True); return
        if txn["status"] == "approved":
            await callback.answer("⚠️ Already approved!", show_alert=True); return
        if txn["status"] == "rejected":
            await callback.answer("⚠️ Already rejected!", show_alert=True); return

        new_balance = add_balance(user_id, amount)
        add_deposit(user_id, amount)
        update_transaction_status(utr, "approved")

        # 🎁 Referral bonus (fires only if configured & user has a referrer)
        ref_id, bonus = apply_referral_bonus(user_id, amount)

        try:
            cap = callback.message.caption or ""
            note = f"\n\n✅ **APPROVED** by {callback.from_user.first_name} (`{admin_id}`)"
            if ref_id and bonus > 0:
                note += f"\n👥 Referral bonus: ₹{bonus:.2f} → `{ref_id}`"
            await callback.message.edit_caption(cap + note)
        except Exception as e:
            logger.warning(f"⚠️ edit caption: {e}")

        try:
            await client.send_message(
                user_id,
                f"✅ **Payment Approved!**\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💰 Added: ₹{amount:.2f}\n"
                f"🔢 UTR: `{utr}`\n"
                f"💳 Balance: ₹{new_balance:.2f}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🛒 Head to Shop to buy accounts!"
            )
        except Exception as e:
            logger.error(f"❌ Notify user {user_id}: {e}")

        # Notify referrer
        if ref_id and bonus > 0:
            try:
                await client.send_message(
                    ref_id,
                    f"🎉 **Referral Bonus Earned!**\n\n"
                    f"👤 Your friend `{user_id}` just deposited ₹{amount:.2f}\n"
                    f"💰 You earned: **₹{bonus:.2f}**\n\n"
                    f"_Keep sharing your link to earn more!_"
                )
            except Exception:
                pass

        await callback.answer("✅ Approved!", show_alert=False)

    # ── REJECT ──────────────────────────────────
    elif data.startswith("reject_"):
        parts = data.split("_")
        utr = parts[1]
        user_id = int(parts[2])

        txn = get_transaction(utr)
        if not txn:
            await callback.answer("❌ Not found!", show_alert=True); return
        if txn["status"] == "rejected":
            await callback.answer("⚠️ Already rejected!", show_alert=True); return
        if txn["status"] == "approved":
            await callback.answer("⚠️ Already approved!", show_alert=True); return

        payment_admin_states[admin_id] = {
            "utr": utr, "user_id": user_id, "log_message": callback.message,
        }
        await callback.answer("📝 Type rejection reason.", show_alert=False)
        try:
            await client.send_message(
                admin_id,
                f"💬 **Enter rejection reason for UTR** `{utr}`:\n\n_Your next message becomes the reason._"
            )
        except Exception as e:
            logger.error(f"❌ Msg admin {admin_id}: {e}")
            payment_admin_states.pop(admin_id, None)


async def handle_admin_rejection_reason(client, message):
    admin_id = message.from_user.id
    state = payment_admin_states.get(admin_id)
    if not state:
        return
    reason = (message.text or "").strip()
    if not reason:
        await message.reply("⚠️ Reason cannot be empty."); return

    utr = state["utr"]; user_id = state["user_id"]; log_msg = state["log_message"]
    update_transaction_status(utr, "rejected")

    try:
        cap = log_msg.caption or ""
        await log_msg.edit_caption(
            cap + f"\n\n❌ **REJECTED** by {message.from_user.first_name} (`{admin_id}`)\n📝 Reason: {reason}"
        )
    except Exception:
        pass

    txn = get_transaction(utr)
    caption = (
        f"❌ **Payment Rejected**\n\n"
        f"🔢 UTR: `{utr}`\n"
        f"⚠️ Reason: {reason}\n\n"
        f"Please resubmit with correct proof."
    )
    if txn and txn.get("ss_file_id"):
        try:
            await client.send_photo(user_id, txn["ss_file_id"], caption=caption)
        except Exception:
            try:
                await client.send_message(user_id, caption)
            except Exception as e:
                logger.error(f"❌ Notify user {user_id}: {e}")
    else:
        try:
            await client.send_message(user_id, caption)
        except Exception as e:
            logger.error(f"❌ Notify user {user_id}: {e}")

    await message.reply(f"✅ Rejection sent to `{user_id}` — UTR `{utr}`.")
    payment_admin_states.pop(admin_id, None)
