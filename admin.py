# ╔══════════════════════════════════════════╗
# ║  admin.py — 👑 Admin Panel               ║
# ║  Edit to change admin features           ║
# ╚══════════════════════════════════════════╝
import asyncio, json, os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from config import ADMIN_ID, GROQ_API, IST, now_ist, today_ist
from storage import (load_json, save_json, is_admin, is_owner, is_maintenance,
                     load_servers, get_trending, DEFAULT_SERVERS)
from helpers import progress_bar, animate_generic, auto_delete, FRAMES
from server_checker import (srv_check_all_parallel, srv_format_status,
                             srv_format_stats, srv_ai_diagnose)

async def clean_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_admin(user.id):
        await update.message.reply_text(
            "╔═══════════════════╗\n║  🧹  *ADMIN CLEAN*  ║\n╚═══════════════════╝\n\n"
            "⚠️ Telegram only allows bots to delete their own messages.\n\n/admin",
            parse_mode="Markdown"
        )
        return
    try:
        await update.message.delete()
        confirm = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="🧹 *Your message deleted!*\n\n_Deletes in 5 seconds._",
            parse_mode="Markdown"
        )
        asyncio.create_task(auto_delete(confirm, 5))
    except Exception:
        await update.message.reply_text("❌ *Cannot delete.*", parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════════
#   MULTI-ADMIN MANAGEMENT
# ═══════════════════════════════════════════════════════════════════
async def addadmin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_owner(user.id):
        await update.message.reply_text("🚫 Sirf *Owner* ye command use kar sakta hai!", parse_mode="Markdown")
        return
    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ *Usage:*\n`/addadmin USER_ID` — Permanent\n`/addadmin USER_ID 24` — 24 ghante",
            parse_mode="Markdown"
        )
        return
    try:
        target_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ User ID sirf numbers mein!", parse_mode="Markdown")
        return
    if target_id == ADMIN_ID:
        await update.message.reply_text("⚠️ Owner ko admin banana zaroori nahi!", parse_mode="Markdown")
        return
    admins = load_json("admins")
    if len(args) >= 2:
        try:
            hours  = int(args[1])
            expiry = now_ist().timestamp() + (hours * 3600)
            admins[str(target_id)] = {
                "id": target_id, "type": "temporary", "hours": hours,
                "expiry": expiry, "added_by": user.id,
                "added_at": now_ist().strftime("%Y-%m-%d %H:%M"),
            }
            save_json("admins", admins)
            expiry_str = datetime.fromtimestamp(expiry, tz=IST).strftime("%d %b %Y, %I:%M %p IST")
            await update.message.reply_text(
                f"✅ *Temporary Admin Added!*\n\n👤 `{target_id}`\n⏱ `{hours} ghante`\n📅 Expires: `{expiry_str}`",
                parse_mode="Markdown"
            )
            try:
                await context.bot.send_message(chat_id=target_id, text=(
                    f"🎉 Aapko *CineBot* ka *Temporary Admin* banaya gaya hai!\n\n"
                    f"⏱ Duration: `{hours} ghante`\n📅 Expires: `{expiry_str}`\n\n/admin"
                ), parse_mode="Markdown")
            except Exception: pass
        except ValueError:
            await update.message.reply_text("❌ Ghante sirf numbers mein!", parse_mode="Markdown")
    else:
        admins[str(target_id)] = {
            "id": target_id, "type": "permanent",
            "added_by": user.id, "added_at": now_ist().strftime("%Y-%m-%d %H:%M"),
        }
        save_json("admins", admins)
        await update.message.reply_text(
            f"✅ *Permanent Admin Added!*\n\n👤 `{target_id}`",
            parse_mode="Markdown"
        )
        try:
            await context.bot.send_message(chat_id=target_id,
                text="🎉 Aapko *CineBot* ka *Permanent Admin* banaya gaya hai!\n\n/admin",
                parse_mode="Markdown")
        except Exception: pass

async def removeadmin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_owner(user.id):
        await update.message.reply_text("🚫 Sirf *Owner* ye command use kar sakta hai!", parse_mode="Markdown")
        return
    args = context.args
    if not args:
        await update.message.reply_text("❌ Usage: `/removeadmin USER_ID`", parse_mode="Markdown")
        return
    try:
        target_id = str(int(args[0]))
    except ValueError:
        await update.message.reply_text("❌ User ID sirf numbers mein!", parse_mode="Markdown")
        return
    admins = load_json("admins")
    if target_id not in admins:
        await update.message.reply_text(f"⚠️ User `{target_id}` admin list mein nahi hai.", parse_mode="Markdown")
        return
    del admins[target_id]
    save_json("admins", admins)
    await update.message.reply_text(f"✅ *Admin Removed!*\n\n👤 `{target_id}`", parse_mode="Markdown")

async def listadmins_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_owner(user.id):
        await update.message.reply_text("🚫 Sirf *Owner* ye dekh sakta hai!", parse_mode="Markdown")
        return
    admins = load_json("admins")
    now    = now_ist().timestamp()
    if not admins:
        await update.message.reply_text(
            f"📋 *Admin List*\n\n_Koi extra admin nahi._\n\n👑 Owner: `{ADMIN_ID}`",
            parse_mode="Markdown"
        )
        return
    lines = [f"╔══════════════════════╗\n║  👑  *ADMIN LIST*  ║\n╚══════════════════════╝\n"]
    lines.append(f"👑 *Owner:* `{ADMIN_ID}` _(permanent)_\n")
    lines.append("━━━━━━━━━━━━━━━━━━━━━\n")
    active_count = 0
    expired_list = []
    for uid, info in admins.items():
        if info.get("type") == "permanent":
            lines.append(f"🔑 `{uid}` — *Permanent*\n   Added: `{info.get('added_at','?')}`")
            active_count += 1
        elif info.get("type") == "temporary":
            expiry = info.get("expiry", 0)
            if now < expiry:
                remaining = int((expiry - now) / 3600)
                exp_str   = datetime.fromtimestamp(expiry, tz=IST).strftime("%d %b, %I:%M %p IST")
                lines.append(f"⏱ `{uid}` — *Temp* ({remaining}h left)\n   Expires: `{exp_str}`")
                active_count += 1
            else:
                expired_list.append(uid)
    if expired_list:
        for uid in expired_list:
            del admins[uid]
        save_json("admins", admins)
    lines.append(f"\n✅ Active Admins: `{active_count}`")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def adm_addadmin_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_owner(query.from_user.id):
        await query.answer("🚫 Sirf Owner ye kar sakta hai!", show_alert=True)
        return ConversationHandler.END
    await query.answer()
    sent = await query.message.reply_text(
        "╔═══════════════════════╗\n║  👑  *ADD NEW ADMIN*  ║\n╚═══════════════════════╝\n\n"
        "`USER_ID` — Permanent\n`USER_ID GHANTE` — Temporary\n\n❌ /cancel",
        parse_mode="Markdown"
    )
    asyncio.create_task(auto_delete(sent, 120))
    return W_ADDADMIN

async def adm_addadmin_recv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return ConversationHandler.END
    text  = update.message.text.strip()
    parts = text.split()
    try:
        target_id = int(parts[0])
    except ValueError:
        await update.message.reply_text("❌ User ID numbers mein likhein.\n/cancel", parse_mode="Markdown")
        return W_ADDADMIN
    if target_id == ADMIN_ID:
        await update.message.reply_text("⚠️ Owner ko admin banana zaroori nahi!", parse_mode="Markdown")
        return ConversationHandler.END
    admins = load_json("admins")
    loader = await update.message.reply_text("⚙️ Processing...\n" + progress_bar(1, 3))
    if len(parts) >= 2:
        try:
            hours  = int(parts[1])
            expiry = now_ist().timestamp() + (hours * 3600)
            admins[str(target_id)] = {
                "id": target_id, "type": "temporary", "hours": hours,
                "expiry": expiry, "added_by": update.effective_user.id,
                "added_at": now_ist().strftime("%Y-%m-%d %H:%M"),
            }
            save_json("admins", admins)
            expiry_str = datetime.fromtimestamp(expiry, tz=IST).strftime("%d %b %Y, %I:%M %p IST")
            try: await loader.delete()
            except: pass
            sent = await update.message.reply_text(
                f"✅ *Admin Added!*\n\n👤 `{target_id}`\n🔑 Temporary — {hours}h\n📅 Expires: `{expiry_str}`",
                parse_mode="Markdown"
            )
            asyncio.create_task(auto_delete(sent, 60))
            try:
                await context.bot.send_message(chat_id=target_id, text=(
                    f"🎉 Aapko *CineBot* ka *Temporary Admin* banaya gaya!\n\n"
                    f"⏱ Duration: `{hours}h`\n📅 Expires: `{expiry_str}`\n\n/admin"
                ), parse_mode="Markdown")
            except Exception: pass
        except ValueError:
            try: await loader.delete()
            except: pass
            await update.message.reply_text("❌ Ghante galat hain!\nExample: `123456 24`\n/cancel", parse_mode="Markdown")
            return W_ADDADMIN
    else:
        admins[str(target_id)] = {
            "id": target_id, "type": "permanent",
            "added_by": update.effective_user.id,
            "added_at": now_ist().strftime("%Y-%m-%d %H:%M"),
        }
        save_json("admins", admins)
        try: await loader.delete()
        except: pass
        sent = await update.message.reply_text(
            f"✅ *Admin Added!*\n\n👤 `{target_id}`\n🔑 Permanent",
            parse_mode="Markdown"
        )
        asyncio.create_task(auto_delete(sent, 60))
        try:
            await context.bot.send_message(chat_id=target_id,
                text="🎉 Aapko *CineBot* ka *Permanent Admin* banaya gaya!\n\n/admin",
                parse_mode="Markdown")
        except Exception: pass
    return ConversationHandler.END

async def adm_listadmins_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_owner(query.from_user.id):
        await query.answer("🚫 Sirf Owner ye dekh sakta hai!", show_alert=True)
        return
    await query.answer()
    admins = load_json("admins")
    now    = now_ist().timestamp()
    if not admins:
        sent = await query.message.reply_text(
            f"╔══════════════════════╗\n║  👑  *ADMIN LIST*  ║\n╚══════════════════════╝\n\n"
            f"_Koi extra admin nahi._\n\n👑 Owner: `{ADMIN_ID}`",
            parse_mode="Markdown"
        )
        asyncio.create_task(auto_delete(sent, 60))
        return
    lines = [f"╔══════════════════════╗\n║  👑  *ADMIN LIST*  ║\n╚══════════════════════╝\n"]
    lines.append(f"👑 *Owner:* `{ADMIN_ID}`\n")
    active_count = 0
    expired_list = []
    remove_btns  = []
    for uid, info in admins.items():
        if info.get("type") == "permanent":
            lines.append(f"🔑 `{uid}` — *Permanent*  Added: `{info.get('added_at','?')}`")
            active_count += 1
            remove_btns.append([InlineKeyboardButton(f"🗑 Remove {uid}", callback_data=f"adm_rmadmin_{uid}")])
        elif info.get("type") == "temporary":
            expiry = info.get("expiry", 0)
            if now < expiry:
                remaining = int((expiry - now) / 3600)
                exp_str   = datetime.fromtimestamp(expiry, tz=IST).strftime("%d %b, %I:%M %p IST")
                lines.append(f"⏱ `{uid}` — *Temp* ({remaining}h left)  Expires: `{exp_str}`")
                active_count += 1
                remove_btns.append([InlineKeyboardButton(f"🗑 Remove {uid}", callback_data=f"adm_rmadmin_{uid}")])
            else:
                expired_list.append(uid)
    if expired_list:
        for uid in expired_list:
            del admins[uid]
        save_json("admins", admins)
    lines.append(f"\n✅ Active Admins: `{active_count}`")
    remove_btns.append([InlineKeyboardButton("⬅️ Back", callback_data="adm_back")])
    sent = await query.message.reply_text(
        "\n".join(lines), parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(remove_btns) if remove_btns else None
    )
    asyncio.create_task(auto_delete(sent, 60))

async def adm_rmadmin_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_owner(query.from_user.id):
        await query.answer("🚫 Sirf Owner!", show_alert=True)
        return
    await query.answer()
    target_id = query.data.replace("adm_rmadmin_", "")
    admins    = load_json("admins")
    if target_id in admins:
        del admins[target_id]
        save_json("admins", admins)
        await query.message.edit_text(
            f"✅ *Admin Removed!*\n\n👤 `{target_id}`", parse_mode="Markdown"
        )
    else:
        await query.message.edit_text(f"⚠️ User `{target_id}` list mein nahi tha.", parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════════
#   ADMIN PANEL
# ═══════════════════════════════════════════════════════════════════
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 *Access Denied!*", parse_mode="Markdown")
        return
    loader = await update.message.reply_text("🔐 Authenticating...\n" + progress_bar(1, 4))
    await asyncio.sleep(0.4)
    try: await loader.edit_text("🗄 Loading data...\n" + progress_bar(2, 4))
    except: pass
    await asyncio.sleep(0.35)
    try: await loader.edit_text("📊 Building panel...\n" + progress_bar(3, 4))
    except: pass
    await asyncio.sleep(0.35)
    try: await loader.edit_text("✅ Ready!\n" + progress_bar(4, 4))
    except: pass
    await asyncio.sleep(0.25)
    try: await loader.delete()
    except: pass

    maint    = load_json("maintenance", {"active": False})
    users    = load_json("users")
    banned   = load_json("banned")
    admins   = load_json("admins")
    servers  = load_servers()
    ratings  = load_json("ratings")
    searches = sum(u.get("searches", 0) for u in users.values())
    status   = "🔴 ON" if maint.get("active") else "🟢 OFF"
    ai_stat  = "✅ Groq" if GROQ_API else "❌ No API"
    now      = now_ist().timestamp()
    active_admins = sum(
        1 for v in admins.values()
        if v.get("type") == "permanent" or
           (v.get("type") == "temporary" and now < v.get("expiry", 0))
    )
    text = (
        f"╔════════════════════════════╗\n"
        f"║  👑  *ADMIN PANEL v9.1*  🎬  ║\n"
        f"╚════════════════════════════╝\n\n"
        f"━━━━━  📊 LIVE STATS  ━━━━━\n"
        f"👥 *Total Users:*    `{len(users)}`\n"
        f"🔎 *Total Searches:* `{searches}`\n"
        f"🚫 *Banned Users:*   `{len(banned)}`\n"
        f"⭐ *Rated Movies:*   `{len(ratings)}`\n"
        f"👑 *Active Admins:*  `{active_admins + 1}` (incl. owner)\n"
        f"🚧 *Maintenance:*    {status}\n"
        f"🤖 *AI Engine:*      {ai_stat}\n\n"
        f"━━━━━  📡 SERVERS  ━━━━━\n"
    )
    for i in range(1, 7):
        text += f"  `{i}.` _{servers[f's{i}']['name']}_\n"
    mb = "🔴 Turn Maintenance OFF" if maint.get("active") else "🟢 Turn Maintenance ON"
    keyboard = [
        [InlineKeyboardButton("📡 Manage Servers",       callback_data="adm_servers")],
        [InlineKeyboardButton(mb,                         callback_data="adm_maint_toggle")],
        [InlineKeyboardButton("✏️ Maintenance Message",  callback_data="adm_maint_msg")],
        [InlineKeyboardButton("📢 Broadcast",            callback_data="adm_broadcast")],
        [InlineKeyboardButton("🚫 Ban User",             callback_data="adm_ban"),
         InlineKeyboardButton("✅ Unban User",           callback_data="adm_unban")],
        [InlineKeyboardButton("📋 Activity Logs",        callback_data="adm_logs")],
        [InlineKeyboardButton("📊 Full Stats",           callback_data="adm_stats")],
        [InlineKeyboardButton("🔔 Send Alerts",          callback_data="adm_send_alerts")],
        [InlineKeyboardButton("📤 Export Users",         callback_data="adm_export")],
        [InlineKeyboardButton("👑 Add Admin",            callback_data="adm_addadmin"),
         InlineKeyboardButton("📋 Admin List",           callback_data="adm_listadmins")],
        [InlineKeyboardButton("🗑 Remove Admin",         callback_data="adm_listadmins")],
        [InlineKeyboardButton("📡 Server Status",        callback_data="adm_srv_status")],
    ]
    sent = await update.message.reply_text(
        text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    asyncio.create_task(auto_delete(sent, 60))

async def adm_servers_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    servers = load_servers()
    text = "📡 *Server Manager*\n━━━━━━━━━━━━━━━━━━\n\n"
    for i in range(1, 7):
        text += f"*{i}.* _{servers[f's{i}']['name']}_\n`{servers[f's{i}']['url']}`\n\n"
    keyboard = [
        [InlineKeyboardButton(f"✏️ S{i} — {servers[f's{i}']['name']}", callback_data=f"adm_edit_s{i}")]
        for i in range(1, 7)
    ]
    keyboard.append([InlineKeyboardButton("🔄 Reset Default", callback_data="adm_reset")])
    keyboard.append([InlineKeyboardButton("⬅️ Back",          callback_data="adm_back")])
    sent = await query.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    asyncio.create_task(auto_delete(sent, 60))

async def adm_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return ConversationHandler.END
    sk = query.data.replace("adm_edit_", "")
    context.user_data["editing_server"] = sk
    servers = load_servers()
    await query.message.reply_text(
        f"✏️ *Editing Server {sk[1]}*\n\nCurrent URL:\n`{servers[sk]['url']}`\n\n📝 Naya URL:\n/cancel",
        parse_mode="Markdown"
    )
    return W_URL

async def adm_recv_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    url = update.message.text.strip()
    if not url.startswith("http"):
        await update.message.reply_text("❌ Invalid URL. Try again or /cancel")
        return W_URL
    context.user_data["new_url"] = url
    sk = context.user_data["editing_server"]
    await update.message.reply_text(
        f"✅ URL saved!\n\n📝 Display name bhejo (current: `{load_servers()[sk]['name']}`):\n/cancel",
        parse_mode="Markdown"
    )
    return W_NAME

async def adm_recv_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    global bot_servers
    name = update.message.text.strip()
    url  = context.user_data["new_url"]
    sk   = context.user_data["editing_server"]
    loader = await update.message.reply_text("💾 Saving...\n" + progress_bar(0, 3))
    await animate_generic(loader, FRAMES["save"])
    bot_servers[sk]["url"]  = url
    bot_servers[sk]["name"] = name
    save_json("servers", bot_servers)
    try: await loader.delete()
    except: pass
    sent = await update.message.reply_text(
        f"✅ *Server {sk[1]} Updated!*\n\n🏷 `{name}`\n🔗 `{url}`", parse_mode="Markdown"
    )
    asyncio.create_task(auto_delete(sent, 60))
    return ConversationHandler.END

async def adm_maint_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    maint = load_json("maintenance", {"active": False, "message": "🔧 Maintenance..."})
    maint["active"] = not maint["active"]
    save_json("maintenance", maint)
    frames = FRAMES["maint_on"] if maint["active"] else FRAMES["maint_off"]
    loader = await query.message.reply_text(frames[0] + "\n" + progress_bar(0, len(frames)))
    await animate_generic(loader, frames)
    try: await loader.delete()
    except: pass
    if maint["active"]:
        users   = load_json("users")
        success = failed = 0
        for uid in users:
            if int(uid) == ADMIN_ID: continue
            try:
                await context.bot.send_message(
                    chat_id=int(uid),
                    text=f"🚧 *CineBot — Maintenance*\n\n{maint['message']}\n\n🙏 Sorry!",
                    parse_mode="Markdown"
                )
                success += 1
            except: failed += 1
            await asyncio.sleep(0.05)
        sent = await query.message.reply_text(
            f"🚨 *Maintenance ON!*\n✅ `{success}` sent | ❌ `{failed}` failed", parse_mode="Markdown"
        )
    else:
        sent = await query.message.reply_text("✅ *Maintenance OFF! Bot LIVE!*", parse_mode="Markdown")
    asyncio.create_task(auto_delete(sent, 60))

async def adm_maint_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return ConversationHandler.END
    maint = load_json("maintenance", {"active": False, "message": ""})
    await query.message.reply_text(
        f"✏️ Current message:\n_{maint.get('message', '')}_\n\n📝 Naya message:\n/cancel",
        parse_mode="Markdown"
    )
    return W_MAINT_MSG

async def adm_recv_maint_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    maint = load_json("maintenance", {"active": False})
    maint["message"] = update.message.text.strip()
    save_json("maintenance", maint)
    loader = await update.message.reply_text("💾 Saving...\n" + progress_bar(0, 3))
    await animate_generic(loader, FRAMES["save"])
    try: await loader.delete()
    except: pass
    sent = await update.message.reply_text(f"✅ *Updated!*\n\n_{maint['message']}_", parse_mode="Markdown")
    asyncio.create_task(auto_delete(sent, 60))
    return ConversationHandler.END

async def adm_broadcast_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return ConversationHandler.END
    await query.message.reply_text(
        "📢 *Broadcast Message*\n\nSabhi users ko message:\n\n/cancel", parse_mode="Markdown"
    )
    return W_BROADCAST

async def adm_do_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    msg     = update.message.text.strip()
    users   = load_json("users")
    success = failed = 0
    loader  = await update.message.reply_text("📢 Broadcasting...\n" + progress_bar(0, 3))
    await animate_generic(loader, FRAMES["broadcast"])
    try: await loader.delete()
    except: pass
    for uid in list(users.keys()):
        if int(uid) == ADMIN_ID: continue
        try:
            await context.bot.send_message(
                chat_id=int(uid),
                text=f"📢 *CineBot Announcement*\n━━━━━━━━━━━━━━━━━━\n\n{msg}",
                parse_mode="Markdown"
            )
            success += 1
        except: failed += 1
        await asyncio.sleep(0.05)
    sent = await update.message.reply_text(
        f"✅ *Broadcast Done!*\n✅ Sent: `{success}`\n❌ Failed: `{failed}`", parse_mode="Markdown"
    )
    asyncio.create_task(auto_delete(sent, 60))
    return ConversationHandler.END

async def adm_ban_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return ConversationHandler.END
    await query.message.reply_text("🚫 *Ban User*\n\nUser ID bhejo:\n/cancel", parse_mode="Markdown")
    return W_BAN_USER

async def adm_do_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    try:
        ban_id = int(update.message.text.strip())
    except Exception:
        await update.message.reply_text("❌ Invalid ID. Try again or /cancel")
        return W_BAN_USER
    banned = load_json("banned")
    banned[str(ban_id)] = now_ist().strftime("%Y-%m-%d %H:%M")
    save_json("banned", banned)
    sent = await update.message.reply_text(f"🚫 *User `{ban_id}` banned!*", parse_mode="Markdown")
    asyncio.create_task(auto_delete(sent, 60))
    return ConversationHandler.END

async def adm_unban_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    banned = load_json("banned")
    if not banned:
        await query.message.reply_text("✅ *No banned users!*", parse_mode="Markdown")
        return
    text = "🔓 *Banned Users:*\n━━━━━━━━━━━━━━━━━━\n\n"
    keyboard = []
    for uid, dt in list(banned.items())[:10]:
        text += f"• `{uid}` — {dt}\n"
        keyboard.append([InlineKeyboardButton(f"✅ Unban {uid}", callback_data=f"dounban_{uid}")])
    sent = await query.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    asyncio.create_task(auto_delete(sent, 60))

async def do_unban_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    uid    = query.data.replace("dounban_", "")
    banned = load_json("banned")
    if uid in banned:
        del banned[uid]
        save_json("banned", banned)
        await query.message.edit_text(f"✅ *User `{uid}` unbanned!*", parse_mode="Markdown")
    else:
        await query.message.edit_text(f"⚠️ User `{uid}` not in banned list.", parse_mode="Markdown")

async def adm_export_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    users = load_json("users")
    lines = ["ID,Name,Username,Joined,Searches,Points,Refs"]
    for u in users.values():
        lines.append(f"{u.get('id','')},{u.get('name','')},{u.get('username','')},{u.get('joined','')},{u.get('searches',0)},{u.get('points',0)},{u.get('refs',0)}")
    export_path = "users_export.txt"
    with open(export_path, "w") as f:
        f.write("\n".join(lines))
    with open(export_path, "rb") as doc_file:
        await context.bot.send_document(
            chat_id=query.from_user.id, document=doc_file,
            caption=f"📤 *Users Export*\n`{len(users)}` total users",
            parse_mode="Markdown"
        )
    sent = await query.message.reply_text("✅ *Export sent to your DM!*", parse_mode="Markdown")
    asyncio.create_task(auto_delete(sent, 30))

async def adm_logs_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    logs  = load_json("logs")
    today = str(today_ist())
    t_logs = logs.get(today, [])
    text  = f"╔═════════════════════════╗\n║  📋  *ACTIVITY LOGS*  ║\n╚═════════════════════════╝\n\n"
    text += f"📊 Today: `{len(t_logs)}` searches\n━━━━━━━━━━━━━━━━━━\n\n"
    for entry in t_logs[-10:]:
        text += f"`{entry['time']}` — {entry['movie']} by `{entry['user']}`\n"
    if not t_logs:
        text += "_No activity today_"
    sent = await query.message.reply_text(text, parse_mode="Markdown")
    asyncio.create_task(auto_delete(sent, 60))

async def adm_stats_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    users    = load_json("users")
    maint    = load_json("maintenance", {"active": False})
    banned   = load_json("banned")
    trending = get_trending(5)
    searches = sum(u.get("searches", 0) for u in users.values())
    ratings  = load_json("ratings")
    status   = "🔴 ON" if maint.get("active") else "🟢 OFF"
    ai_stat  = "✅ Groq (Llama 3.3)" if GROQ_API else "❌ GROQ_API not set"
    text  = f"╔══════════════════╗\n║  📊  *FULL STATS*  ║\n╚══════════════════╝\n\n"
    text += f"👥 Users: `{len(users)}`\n🔎 Searches: `{searches}`\n🚫 Banned: `{len(banned)}`\n"
    text += f"⭐ Rated: `{len(ratings)}`\n🚧 Maintenance: {status}\n🤖 AI: {ai_stat}\n\n"
    if trending:
        text += "🔥 *Top Searched:*\n"
        for i, (t, c) in enumerate(trending, 1):
            text += f"  `{i}.` {t} — `{c}x`\n"
    sent = await query.message.reply_text(text, parse_mode="Markdown")
    asyncio.create_task(auto_delete(sent, 60))

async def adm_send_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    alerts = load_json("alerts")
    sent_c = 0
    for uid, movies in alerts.items():
        for movie_item in movies:
            try:
                await context.bot.send_message(
                    chat_id=int(uid),
                    text=f"🔔 *Movie Alert!*\n\n🎬 *{movie_item['title']}* ({movie_item['year']})\n\nSearch karo!",
                    parse_mode="Markdown"
                )
                sent_c += 1
            except: pass
            await asyncio.sleep(0.05)
    sent = await query.message.reply_text(f"🔔 *Alerts sent:* `{sent_c}`", parse_mode="Markdown")
    asyncio.create_task(auto_delete(sent, 60))

async def sendalert_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /sendalert <message>
    Admin-only: Har user ko custom alert message bhejta hai.
    """
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("🚫 *Sirf Admins ye command use kar sakte hain!*", parse_mode="Markdown")
        return

    if not context.args:
        await update.message.reply_text(
            "╔══════════════════════════╗\n"
            "║  🔔  *SEND ALERT*  ║\n"
            "╚══════════════════════════╝\n\n"
            "❌ *Usage:*\n`/sendalert Aapka message yahan`\n\n"
            "_Example:_ `/sendalert 🎬 Naya movie add ho gaya!`",
            parse_mode="Markdown"
        )
        return

    alert_msg = " ".join(context.args).strip()
    users     = load_json("users")
    success   = failed = 0

    loader = await update.message.reply_text("🔔 Sending alerts...\n" + progress_bar(0, 3))
    await asyncio.sleep(0.3)
    try: await loader.edit_text("🔔 Sending alerts...\n" + progress_bar(1, 3))
    except: pass
    await asyncio.sleep(0.3)
    try: await loader.edit_text("🔔 Sending alerts...\n" + progress_bar(2, 3))
    except: pass

    for uid in list(users.keys()):
        if int(uid) == ADMIN_ID:
            continue
        try:
            await context.bot.send_message(
                chat_id=int(uid),
                text=(
                    f"🔔 *CineBot Alert!*\n"
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    f"{alert_msg}"
                ),
                parse_mode="Markdown"
            )
            success += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)

    try: await loader.delete()
    except: pass

    sent = await update.message.reply_text(
        f"✅ *Alert Sent!*\n\n"
        f"📨 *Message:* _{alert_msg}_\n\n"
        f"✅ Delivered: `{success}`\n"
        f"❌ Failed:    `{failed}`\n"
        f"👥 Total:     `{success + failed}`",
        parse_mode="Markdown"
    )
    asyncio.create_task(auto_delete(sent, 60))


async def adm_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    global bot_servers
    bot_servers = {k: v.copy() for k, v in DEFAULT_SERVERS.items()}
    save_json("servers", bot_servers)
    sent = await query.message.reply_text("🔄 *All 6 Servers Reset!* ✅", parse_mode="Markdown")
    asyncio.create_task(auto_delete(sent, 60))

async def adm_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    maint    = load_json("maintenance", {"active": False})
    users    = load_json("users")
    banned   = load_json("banned")
    admins   = load_json("admins")
    ratings  = load_json("ratings")
    searches = sum(u.get("searches", 0) for u in users.values())
    status   = "🔴 ON" if maint.get("active") else "🟢 OFF"
    ai_stat  = "✅ Groq" if GROQ_API else "❌ No API"
    now      = now_ist().timestamp()
    active_admins = sum(
        1 for v in admins.values()
        if v.get("type") == "permanent" or
           (v.get("type") == "temporary" and now < v.get("expiry", 0))
    )
    mb = "🔴 Turn Maintenance OFF" if maint.get("active") else "🟢 Turn Maintenance ON"
    text = (
        f"╔════════════════════════════╗\n"
        f"║  👑  *ADMIN PANEL v9.1*  🎬  ║\n"
        f"╚════════════════════════════╝\n\n"
        f"👥 Users: `{len(users)}`  🔎 Searches: `{searches}`\n"
        f"🚫 Banned: `{len(banned)}`  ⭐ Rated: `{len(ratings)}`\n"
        f"👑 Admins: `{active_admins + 1}`  🚧 Maintenance: {status}\n"
        f"🤖 AI: {ai_stat}\n"
    )
    keyboard = [
        [InlineKeyboardButton("📡 Manage Servers",       callback_data="adm_servers")],
        [InlineKeyboardButton(mb,                         callback_data="adm_maint_toggle")],
        [InlineKeyboardButton("✏️ Maintenance Message",  callback_data="adm_maint_msg")],
        [InlineKeyboardButton("📢 Broadcast",            callback_data="adm_broadcast")],
        [InlineKeyboardButton("🚫 Ban User",             callback_data="adm_ban"),
         InlineKeyboardButton("✅ Unban User",           callback_data="adm_unban")],
        [InlineKeyboardButton("📋 Activity Logs",        callback_data="adm_logs")],
        [InlineKeyboardButton("📊 Full Stats",           callback_data="adm_stats")],
        [InlineKeyboardButton("🔔 Send Alerts",          callback_data="adm_send_alerts")],
        [InlineKeyboardButton("📤 Export Users",         callback_data="adm_export")],
        [InlineKeyboardButton("👑 Add Admin",            callback_data="adm_addadmin"),
         InlineKeyboardButton("📋 Admin List",           callback_data="adm_listadmins")],
        [InlineKeyboardButton("🗑 Remove Admin",         callback_data="adm_listadmins")],
        [InlineKeyboardButton("📡 Server Status",        callback_data="adm_srv_status")],
    ]
    sent = await query.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    asyncio.create_task(auto_delete(sent, 60))


# Cancel
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ *Cancelled.*", parse_mode="Markdown")
    return ConversationHandler.END

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ai_status = "✅ Groq AI Active" if GROQ_API else "⚠️ Set GROQ_API for AI features"
    await update.message.reply_text(
        "╔═══════════════════╗\n║  ℹ️  *CINEBOT HELP*  ║\n╚═══════════════════╝\n\n"
        f"🤖 *AI Status:* {ai_status}\n\n"
        "🔎 *Movie Search:* Seedha naam type karo\n\n"
        "📋 *Commands:*\n"
        "🎬 /movieinfo    — TMDB rich movie info\n"
        "📝 /fullreview   — Detailed AI review ✅NEW\n"
        "🎭 /moodmatch    — Mood match analysis ✅NEW\n"
        "🌟 /castinfo     — Cast & director info ✅NEW\n"
        "❓ /trivia       — MCQ trivia question ✅NEW\n"
        "📡 /checkservers — Server health (Admin) ✅NEW\n"
        "📊 /serverstats  — Uptime % stats (Admin) ✅v4\n"
        "🤖 /suggest      — AI recommendations\n"
        "🔍 /plotsearch   — Search by plot\n"
        "🎭 /mood         — Mood-based picks\n"
        "⚖️ /compare      — Compare 2 movies\n"
        "🔥 /trending     — Weekly trending\n"
        "📅 /upcoming     — Coming soon\n"
        "🎲 /random       — Random movie\n"
        "🎯 /daily        — Today's featured\n"
        "❤️ /watchlist    — Saved movies\n"
        "🔔 /alerts       — Release alerts\n"
        "🎮 /quiz         — Movie trivia\n"
        "🏆 /leaderboard  — Top users\n"
        "📜 /history      — Search history\n"
        "👥 /refer        — Refer & earn\n"
        "🌐 /lang         — Language filter\n"
        "📊 /mystats      — Points & badge\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🎯 *Movie card pe naye buttons:*\n"
        "📝 Full Review • 🎭 Mood Match\n"
        "🌟 Cast Analysis • ❓ Trivia Quiz\n"
        "🔥 Full AI Package (sab ek saath)\n\n"
        "🦁 *Brave Browser = No Ads!*",
        parse_mode="Markdown"
    )


# ═══════════════════════════════════════════════════════════════════
#                        BOT START
# ═══════════════════════════════════════════════════════════════════
# ── post_init: inject bot_data + start auto checker ──
