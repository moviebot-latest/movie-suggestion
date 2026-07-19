from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from bot.db import repository as repo
from bot.services.omdb import get_omdb
from bot.utils.decorators import guarded
from bot.utils.keyboards import rating_keyboard


# ── Watchlist ────────────────────────────────────────────────────
@guarded()
async def watchlist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    rows = await repo.watchlist_get(user_id)
    if not rows:
        await update.message.reply_text("📋 Watchlist khali hai. Kisi movie card se '💾 Watchlist' dabao.")
        return
    lines = [f"• {r['title']}" for r in rows]
    await update.message.reply_text(
        "📋 *Your Watchlist*\n━━━━━━━━━━━━━━━━━━\n\n" + "\n".join(lines), parse_mode="Markdown"
    )


@guarded()
async def wl_save_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    imdb_id = query.data.split("|", 1)[1]
    data = await get_omdb(imdb_id, by_id=True)
    title = data.get("Title", imdb_id) if data else imdb_id
    await repo.watchlist_add(query.from_user.id, imdb_id, title)
    await query.answer(f"💾 Saved: {title}", show_alert=True)


@guarded()
async def wl_clear_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await repo.watchlist_clear(query.from_user.id)
    await query.answer("🗑 Watchlist cleared!", show_alert=True)


# ── Ratings ──────────────────────────────────────────────────────
@guarded()
async def rate_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    imdb_id = query.data.split("_", 1)[1]
    await query.message.reply_text("⭐ Rate this movie (1-10):", reply_markup=rating_keyboard(imdb_id))


@guarded()
async def dorat_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, imdb_id, rating_str = query.data.split("_", 2)
    rating = int(rating_str)
    data = await get_omdb(imdb_id, by_id=True)
    title = data.get("Title", imdb_id) if data else imdb_id
    await repo.rate_movie(query.from_user.id, imdb_id, title, rating)
    await repo.add_points(query.from_user.id, 2)
    await query.answer(f"⭐ Rated {title}: {rating}/10", show_alert=True)


# ── Alerts ───────────────────────────────────────────────────────
@guarded()
async def alerts_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    user_id = update.effective_user.id
    if context.args:
        keyword = " ".join(context.args)
        await repo.alert_add(user_id, keyword)
        await update.message.reply_text(f"🔔 Alert set for keyword: *{keyword}*", parse_mode="Markdown")
        return
    rows = await repo.alert_list(user_id)
    if not rows:
        await update.message.reply_text("🔔 Koi alerts nahi hain.\nUsage: `/alerts <keyword>`", parse_mode="Markdown")
        return
    kb = [[InlineKeyboardButton(f"🗑 {r['keyword']}", callback_data=f"alert_del|{r['keyword']}")] for r in rows]
    kb.append([InlineKeyboardButton("🗑 Clear All", callback_data="alert_clear")])
    await update.message.reply_text(
        "🔔 *Your Alerts* (tap to remove)", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb)
    )


@guarded()
async def alert_add_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    keyword = query.data.split("|", 1)[1]
    await repo.alert_add(query.from_user.id, keyword)
    await query.answer(f"🔔 Alert added: {keyword}", show_alert=True)


@guarded()
async def alert_del_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    keyword = query.data.split("|", 1)[1]
    await repo.alert_del(query.from_user.id, keyword)
    await query.answer(f"🗑 Removed: {keyword}", show_alert=True)


@guarded()
async def alert_clear_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await repo.alert_clear(query.from_user.id)
    await query.answer("🗑 All alerts cleared!", show_alert=True)


# ── History & Stats ──────────────────────────────────────────────
@guarded()
async def history_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = await repo.get_history(update.effective_user.id, limit=20)
    if not rows:
        await update.message.reply_text("📜 Koi search history nahi hai abhi tak.")
        return
    lines = [f"• {r['query']}" for r in rows]
    await update.message.reply_text("📜 *Recent Searches*\n\n" + "\n".join(lines), parse_mode="Markdown")


@guarded()
async def mystats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await repo.get_user(update.effective_user.id)
    if not user:
        await update.message.reply_text("Stats nahi mile. Try /start first.")
        return
    points = user["points"]
    badge = (
        "💎 Diamond" if points >= 1000 else
        "🥇 Gold" if points >= 500 else
        "🥈 Silver" if points >= 200 else
        "🥉 Bronze" if points >= 100 else
        "🌱 Newbie"
    )
    await update.message.reply_text(
        f"📊 *Your Stats*\n\n"
        f"🔍 Searches: `{user['searches']}`\n"
        f"⭐ Points: `{points}`\n"
        f"🏅 Badge: {badge}\n"
        f"📅 Joined: `{user['joined_at'].strftime('%d %b %Y')}`",
        parse_mode="Markdown",
    )


@guarded()
async def leaderboard_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = await repo.leaderboard(10)
    if not rows:
        await update.message.reply_text("Leaderboard khali hai.")
        return
    lines = [f"{i+1}. {r['name']} — {r['points']} pts" for i, r in enumerate(rows)]
    await update.message.reply_text("🏆 *Leaderboard*\n\n" + "\n".join(lines), parse_mode="Markdown")


@guarded()
async def refer_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_username = (await context.bot.get_me()).username
    user_id = update.effective_user.id
    link = f"https://t.me/{bot_username}?start={user_id}"
    await update.message.reply_text(
        f"🎁 *Refer & Earn*\n\nApna link share karo:\n{link}\n\n"
        "Jab koi is link se join karega, tumhe points milenge!",
        parse_mode="Markdown",
    )
