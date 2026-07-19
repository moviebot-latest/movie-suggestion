from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.db import repository as repo
from bot.db.database import get_pool
from bot.utils.decorators import guarded

LANGUAGES = ["Hindi", "English", "Tamil", "Telugu", "Punjabi", "Any"]


@guarded()
async def lang_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton(l, callback_data=f"setlang_{l}")] for l in LANGUAGES]
    await update.message.reply_text(
        "🌐 *Choose your preferred language:*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb)
    )


@guarded()
async def setlang_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    lang = query.data.replace("setlang_", "")
    await repo.set_lang(query.from_user.id, lang)
    await query.answer(f"✅ Language set to {lang}", show_alert=True)


@guarded(require_admin=True)
async def lang_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pool = await get_pool()
    rows = await pool.fetch("SELECT lang, COUNT(*) as cnt FROM users GROUP BY lang ORDER BY cnt DESC")
    if not rows:
        await update.message.reply_text("Koi data nahi hai.")
        return
    lines = [f"• {r['lang']}: {r['cnt']}" for r in rows]
    await update.message.reply_text("🌐 *Language Stats*\n\n" + "\n".join(lines), parse_mode="Markdown")


@guarded(require_owner=True)
async def lang_bulk_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pool = await get_pool()
    await pool.execute("UPDATE users SET lang = 'Any'")
    await update.message.reply_text("✅ All users' language preference reset to 'Any'.")


@guarded(require_admin=True)
async def adminlang_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("Use /lang command.", show_alert=True)


@guarded(require_admin=True)
async def adminpanel_lang_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("Use /langstats or /langreset command.", show_alert=True)


async def lang_cancel_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Cancelled.")
