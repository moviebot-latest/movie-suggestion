from __future__ import annotations

import asyncio

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from config import ADMIN_ID
import repository as repo
from decorators import guarded

W_BROADCAST, W_BAN_USER, W_MAINT_MSG, W_ADDADMIN = range(100, 104)


def _admin_menu_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("📢 Broadcast", callback_data="adm_broadcast"),
         InlineKeyboardButton("🚫 Ban User", callback_data="adm_ban")],
        [InlineKeyboardButton("✅ Unban User", callback_data="adm_unban"),
         InlineKeyboardButton("🔧 Maintenance", callback_data="adm_maint_toggle")],
        [InlineKeyboardButton("📊 Stats", callback_data="adm_stats"),
         InlineKeyboardButton("👥 List Admins", callback_data="adm_listadmins")],
        [InlineKeyboardButton("➕ Add Admin", callback_data="adm_addadmin"),
         InlineKeyboardButton("🤖 Groq Status", callback_data="adm_groqstatus")],
        [InlineKeyboardButton("🛑 Shutdown", callback_data="adm_shutdown_confirm"),
         InlineKeyboardButton("✅ Recover", callback_data="adm_recover")],
    ]
    return InlineKeyboardMarkup(rows)


@guarded(require_admin=True)
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.callback_query.message if update.callback_query else update.message
    if update.callback_query:
        await update.callback_query.answer()
    await target.reply_text("🛠 *Admin Panel*", parse_mode="Markdown", reply_markup=_admin_menu_keyboard())


@guarded(require_admin=True)
async def adm_stats_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    total_users = await repo.user_count()
    banned = await repo.list_banned()
    admins = await repo.list_admins()
    await query.message.reply_text(
        f"📊 *Bot Stats*\n\n"
        f"👥 Users: `{total_users}`\n"
        f"🚫 Banned: `{len(banned)}`\n"
        f"👮 Sub-admins: `{len(admins)}`",
        parse_mode="Markdown",
    )


@guarded(require_admin=True)
async def adm_listadmins_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    rows = await repo.list_admins()
    if not rows:
        await query.message.reply_text("Koi sub-admins nahi hain.")
        return
    lines = [f"• `{r['user_id']}` ({r['admin_type']})" for r in rows]
    await query.message.reply_text("👮 *Admins*\n\n" + "\n".join(lines), parse_mode="Markdown")


@guarded(require_admin=True)
async def listadmins_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = await repo.list_admins()
    lines = [f"• `{r['user_id']}` ({r['admin_type']})" for r in rows] or ["Koi sub-admins nahi hain."]
    await update.message.reply_text("👮 *Admins*\n\n" + "\n".join(lines), parse_mode="Markdown")


# ── Broadcast ────────────────────────────────────────────────────
@guarded(require_admin=True)
async def adm_broadcast_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("📢 Broadcast message bhejo:\n\n/cancel")
    return W_BROADCAST


@guarded(require_admin=True)
async def adm_do_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text.strip()
    user_ids = await repo.all_user_ids()
    loader = await update.message.reply_text(f"📢 Broadcasting to {len(user_ids)} users...")
    success = failed = 0
    for uid in user_ids:
        if uid == ADMIN_ID:
            continue
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=f"📢 *CineBot Announcement*\n━━━━━━━━━━━━━━━━━━\n\n{msg}",
                parse_mode="Markdown",
            )
            success += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)  # stay under Telegram's ~30 msg/sec limit
    try:
        await loader.delete()
    except Exception:
        pass
    await update.message.reply_text(f"✅ *Broadcast Done!*\n✅ Sent: `{success}`\n❌ Failed: `{failed}`", parse_mode="Markdown")
    return ConversationHandler.END


# ── Ban / Unban ──────────────────────────────────────────────────
@guarded(require_admin=True)
async def adm_ban_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("🚫 User ID bhejo ban karne ke liye:\n\n/cancel")
    return W_BAN_USER


@guarded(require_admin=True)
async def adm_do_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        ban_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Invalid ID. Try again or /cancel")
        return W_BAN_USER
    await repo.ban_user(ban_id)
    await update.message.reply_text(f"🚫 *User `{ban_id}` banned!*", parse_mode="Markdown")
    return ConversationHandler.END


@guarded(require_admin=True)
async def adm_unban_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    rows = await repo.list_banned()
    if not rows:
        await query.message.reply_text("Koi banned users nahi hain.")
        return
    kb = [[InlineKeyboardButton(f"✅ Unban {r['user_id']}", callback_data=f"dounban_{r['user_id']}")] for r in rows[:20]]
    await query.message.reply_text("🚫 *Banned Users*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


@guarded(require_admin=True)
async def do_unban_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = int(query.data.replace("dounban_", ""))
    await repo.unban_user(uid)
    await query.answer(f"✅ Unbanned {uid}", show_alert=True)


# ── Maintenance mode ─────────────────────────────────────────────
@guarded(require_admin=True)
async def adm_maint_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    maint = await repo.get_setting("maintenance", {"active": False, "message": "Maintenance chal raha hai."})
    maint["active"] = not maint.get("active", False)
    await repo.set_setting("maintenance", maint)
    status = "ON 🔧" if maint["active"] else "OFF ✅"
    await query.message.reply_text(f"Maintenance mode: *{status}*", parse_mode="Markdown")


@guarded(require_admin=True)
async def adm_maint_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("🔧 Naya maintenance message bhejo:\n\n/cancel")
    return W_MAINT_MSG


@guarded(require_admin=True)
async def adm_recv_maint_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    maint = await repo.get_setting("maintenance", {"active": False})
    maint["message"] = text
    await repo.set_setting("maintenance", maint)
    await update.message.reply_text("✅ Maintenance message updated!")
    return ConversationHandler.END


# ── Admin management (owner-only) ─────────────────────────────────
@guarded(require_owner=True)
async def addadmin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ *Usage:*\n`/addadmin USER_ID` — Permanent\n`/addadmin USER_ID 24` — 24 ghante",
            parse_mode="Markdown",
        )
        return
    try:
        target_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ User ID sirf numbers mein!")
        return
    if target_id == ADMIN_ID:
        await update.message.reply_text("⚠️ Owner ko admin banana zaroori nahi!")
        return

    hours = None
    if len(args) >= 2:
        try:
            hours = int(args[1])
        except ValueError:
            await update.message.reply_text("❌ Ghante sirf numbers mein!")
            return

    await repo.add_admin(target_id, update.effective_user.id, hours)
    label = f"Temporary ({hours}h)" if hours else "Permanent"
    await update.message.reply_text(f"✅ *{label} Admin Added!*\n\n👤 `{target_id}`", parse_mode="Markdown")
    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=f"🎉 Aapko *CineBot* ka *{label} Admin* banaya gaya!\n\n/admin",
            parse_mode="Markdown",
        )
    except Exception:
        pass


@guarded(require_owner=True)
async def removeadmin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("❌ Usage: `/removeadmin USER_ID`", parse_mode="Markdown")
        return
    try:
        target_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ User ID sirf numbers mein!")
        return
    removed = await repo.remove_admin(target_id)
    if removed:
        await update.message.reply_text(f"✅ Admin `{target_id}` removed.", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Ye user admin nahi hai.")


# ── Groq key status & live rotation ───────────────────────────────
def _format_groq_status(status: dict | None) -> str:
    from datetime import datetime
    if not status:
        return "🤖 *Groq AI Status*\n\n⚪ Never checked yet. Run `/groqstatus` to check now."
    icon = "🟢" if status["active"] else "🔴"
    label = "ACTIVE" if status["active"] else "INACTIVE / EXPIRED"
    checked = datetime.fromtimestamp(status["checked_at"]).strftime("%d %b %Y, %I:%M %p")
    return (
        f"🤖 *Groq AI Status*\n\n"
        f"{icon} *{label}*\n"
        f"📝 {status['detail']}\n"
        f"🕐 Last checked: `{checked}`\n\n"
        f"_Groq doesn't expose a key expiry date via API — this is a live test call, "
        f"so \"active\" only means the key worked just now._"
    )


@guarded(require_admin=True)
async def groqstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from groq_ai import check_groq_status
    loader = await update.message.reply_text("🤖 Checking Groq key...")
    status = await check_groq_status()
    try:
        await loader.delete()
    except Exception:
        pass
    text = _format_groq_status(status)
    if not status["active"]:
        text += "\n\n⚠️ Update it with:\n`/setgroqkey <new_key>`"
    await update.message.reply_text(text, parse_mode="Markdown")


@guarded(require_admin=True)
async def adm_groqstatus_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🤖 Checking...")
    from groq_ai import check_groq_status
    status = await check_groq_status()
    text = _format_groq_status(status)
    if not status["active"]:
        text += "\n\n⚠️ Update it with:\n`/setgroqkey <new_key>`"
    await query.message.reply_text(text, parse_mode="Markdown")


@guarded(require_owner=True)
async def setgroqkey_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner-only: rotate the Groq API key live, no redeploy needed."""
    if not context.args:
        await update.message.reply_text(
            "❌ *Usage:* `/setgroqkey YOUR_NEW_GROQ_KEY`\n\n"
            "⚠️ Ye command apna message turant delete kar dega taaki key kisi aur ko chat mein na dikhe.",
            parse_mode="Markdown",
        )
        return

    new_key = context.args[0].strip()

    # Delete the message containing the raw key ASAP — it's a secret.
    delete_failed = False
    try:
        await update.message.delete()
    except Exception:
        delete_failed = True

    from groq_ai import set_groq_key, check_groq_status
    await set_groq_key(new_key)
    loader = await context.bot.send_message(update.effective_chat.id, "🔄 Key saved. Verifying it works...")
    status = await check_groq_status()
    try:
        await loader.delete()
    except Exception:
        pass

    if status["active"]:
        msg = "✅ *New Groq key saved & verified working!*\n\nNo redeploy needed — it's active immediately."
        if delete_failed:
            msg += "\n\n⚠️ Couldn't auto-delete your message with the raw key — please delete it manually."
        await context.bot.send_message(update.effective_chat.id, msg, parse_mode="Markdown")
    else:
        await context.bot.send_message(
            update.effective_chat.id,
            f"⚠️ *Key saved but the test call failed:*\n{status['detail']}\n\n"
            "Double-check the key and try `/setgroqkey` again.",
            parse_mode="Markdown",
        )


# ── Shutdown / Recover (maintenance-mode shortcuts) ────────────────
@guarded(require_admin=True)
async def shutdown_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reason = " ".join(context.args) if context.args else "Bot temporarily down for maintenance."
    await repo.set_setting("maintenance", {"active": True, "message": reason})
    await update.message.reply_text(
        f"🛑 *Bot Shutdown*\n\nSaare users ke liye bot band ho gaya hai (sirf admins use kar sakte hain).\n\n"
        f"📝 Reason: {reason}\n\nWapas on karne ke liye: `/recover`",
        parse_mode="Markdown",
    )


@guarded(require_admin=True)
async def recover_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await repo.set_setting("maintenance", {"active": False, "message": ""})
    await update.message.reply_text("✅ *Bot Recovered!*\n\nSab users ke liye wapas se available hai.", parse_mode="Markdown")


@guarded(require_admin=True)
async def adm_shutdown_confirm_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛑 Yes, Shutdown Now", callback_data="adm_shutdown_do"),
         InlineKeyboardButton("❌ Cancel", callback_data="adm_back")],
    ])
    await query.message.reply_text(
        "⚠️ *Confirm Shutdown*\n\nYe saare users ke liye bot ko turant band kar dega.\nPakka?",
        parse_mode="Markdown", reply_markup=kb,
    )


@guarded(require_admin=True)
async def adm_shutdown_do_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🛑 Shutting down...", show_alert=True)
    await repo.set_setting("maintenance", {"active": True, "message": "Bot temporarily down for maintenance."})
    await query.message.reply_text("🛑 *Bot Shutdown.*\n\nWapas on karne ke liye `/recover` bhejo.", parse_mode="Markdown")


@guarded(require_admin=True)
async def adm_recover_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("✅ Recovering...", show_alert=True)
    await repo.set_setting("maintenance", {"active": False, "message": ""})
    await query.message.reply_text("✅ *Bot Recovered!*\n\nSab users ke liye wapas se available hai.", parse_mode="Markdown")
