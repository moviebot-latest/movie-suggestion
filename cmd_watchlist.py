# ╔══════════════════════════════════════════╗
# ║  cmd_watchlist.py — ❤️ Watchlist         ║
# ║                    🔔 Movie Alerts       ║
# ╚══════════════════════════════════════════╝
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import now_ist
from storage import load_json, save_json
from helpers import get_badge

# ═══════════════════════════════════════════════════════════════════
#           WATCHLIST
# ═══════════════════════════════════════════════════════════════════
async def watchlist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = str(update.effective_user.id)
    data = load_json("watchlist")
    wl   = data.get(uid, [])
    if not wl:
        await update.message.reply_text(
            "╔══════════════════╗\n║  ❤️  *WATCHLIST*  ║\n╚══════════════════╝\n\n"
            "📭 *Empty Watchlist!*\n\n_Movie search karo aur ❤️ tap karo_",
            parse_mode="Markdown"
        )
        return
    text = "╔══════════════════╗\n║  ❤️  *WATCHLIST*  ║\n╚══════════════════╝\n\n"
    text += f"📋 *{len(wl)} Movies Saved:*\n━━━━━━━━━━━━━━━━━━\n\n"
    for i, m in enumerate(wl, 1):
        text += f"`{i}.` 🎬 *{m['title']}* `({m['year']})` ⭐`{m['rating']}`\n"
    text += "\n_Search karo movie naam type karke_ 🔎"
    await update.message.reply_text(
        text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🗑 Clear All", callback_data="wl_clear")]])
    )

async def wl_save_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        parts  = query.data.split("|")
        title, year, rating = parts[1], parts[2], parts[3]
    except IndexError:
        await query.answer("⚠️ Error saving. Search again.", show_alert=True)
        return
    uid  = str(query.from_user.id)
    data = load_json("watchlist")
    if uid not in data: data[uid] = []
    if any(m["title"] == title for m in data[uid]):
        await query.answer("⚠️ Already in Watchlist!", show_alert=True)
        return
    data[uid].append({"title": title, "year": year, "rating": rating, "saved": now_ist().strftime("%d %b %Y")})
    save_json("watchlist", data)
    await query.answer(f"❤️ '{title}' saved!", show_alert=True)

async def wl_clear_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid   = str(query.from_user.id)
    data  = load_json("watchlist")
    data[uid] = []
    save_json("watchlist", data)
    await query.message.edit_text("🗑 *Watchlist cleared!*", parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════════
#           MOVIE ALERTS
# ═══════════════════════════════════════════════════════════════════
async def alerts_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid   = str(update.effective_user.id)
    data  = load_json("alerts")
    my_al = data.get(uid, [])
    text     = "╔══════════════════╗\n║  🔔  *MY ALERTS*  ║\n╚══════════════════╝\n\n"
    keyboard = []
    if my_al:
        text += "*Active Alerts:*\n━━━━━━━━━━━━━━━━━━\n"
        for i, m in enumerate(my_al, 1):
            text += f"`{i}.` 🎬 *{m['title']}* ({m['year']})\n"
            keyboard.append([InlineKeyboardButton(f"🗑 Remove: {m['title'][:20]}", callback_data=f"alert_del|{m['title']}")])
        text += "\n_Jab movie available hogi, notify karunga!_"
        keyboard.append([InlineKeyboardButton("🗑 Clear All Alerts", callback_data="alert_clear")])
    else:
        text += "📭 *Koi alert set nahi!*\n\n_Movie card pe 🔔 tap karo._"
    await update.message.reply_text(
        text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
    )

async def alert_add_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        parts       = query.data.split("|")
        title, year = parts[1], parts[2]
    except IndexError:
        await query.answer("⚠️ Error. Try again.", show_alert=True)
        return
    uid  = str(query.from_user.id)
    data = load_json("alerts")
    if uid not in data: data[uid] = []
    if any(m["title"] == title for m in data[uid]):
        await query.answer("⚠️ Alert already set!", show_alert=True)
        return
    data[uid].append({"title": title, "year": year})
    save_json("alerts", data)
    await query.answer(f"🔔 Alert set for '{title}'!", show_alert=True)

async def alert_del_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    title = query.data.split("|", 1)[1]
    uid   = str(query.from_user.id)
    data  = load_json("alerts")
    if uid in data:
        data[uid] = [m for m in data[uid] if m["title"] != title]
        save_json("alerts", data)
    await query.message.edit_text(f"✅ *Alert removed:* _{title}_", parse_mode="Markdown")

async def alert_clear_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid  = str(query.from_user.id)
    data = load_json("alerts")
    data[uid] = []
    save_json("alerts", data)
    await query.message.edit_text("🗑 *All alerts cleared!*", parse_mode="Markdown")
