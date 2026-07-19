from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from bot.db import repository as repo
from bot.utils.decorators import guarded
from bot.utils.keyboards import main_menu_keyboard


@guarded()
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ref_id = None
    if context.args:
        try:
            candidate = int(context.args[0])
            if candidate != user.id:
                ref_id = candidate
        except ValueError:
            pass

    await repo.register_user(user.id, user.full_name, user.username, ref_id)

    await update.message.reply_text(
        f"🎬 *Welcome to CineBot, {user.first_name}!*\n\n"
        "Movie ka naam type karo ya neeche se koi feature choose karo 👇",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )


@guarded()
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🎬 *CineBot — Commands*\n\n"
        "*Search & Discover*\n"
        "`/suggest` — AI movie recommendations\n"
        "`/plotsearch` — Find a movie by describing its plot\n"
        "`/mood` — Get suggestions based on your mood\n"
        "`/compare` — Compare two movies\n"
        "`/trending` — Trending movies right now\n"
        "`/random` — Random movie pick\n"
        "`/upcoming` — This month's releases (or `/upcoming Movie Name 2027` to search a specific one)\n\n"
        "*Your Stuff*\n"
        "`/watchlist` — Your saved movies\n"
        "`/alerts` — Get notified for keyword releases\n"
        "`/history` — Your search history\n"
        "`/mystats` — Your stats & badge\n"
        "`/leaderboard` — Top users\n\n"
        "*Fun*\n"
        "`/quiz` — Movie trivia quiz\n"
        "`/refer` — Your referral link\n\n"
        "Bas kisi movie ka naam type karo search karne ke liye!"
    )
    if await repo.is_admin(update.effective_user.id):
        text += (
            "\n\n━━━━━━━━━━━━━━━━━━\n"
            "🛠 *Admin Commands*\n\n"
            "`/admin` — Admin panel\n"
            "`/groqstatus` — Check if Groq AI key is active\n"
            "`/setgroqkey <key>` — Rotate Groq key live (owner only)\n"
            "`/shutdown [reason]` — Block all users, maintenance mode ON\n"
            "`/recover` — Turn maintenance mode OFF\n"
            "`/addadmin <id> [hours]`, `/removeadmin <id>` (owner only)\n"
            "`/checkservers`, `/serverstats`, `/failoverlog`"
        )
    await update.message.reply_text(text, parse_mode="Markdown")


@guarded()
async def start_btn_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the generic main-menu buttons that don't have their own conversation entry point."""
    query = update.callback_query
    await query.answer()
    data = query.data

    routes = {
        "cmd_trending": "trending",
        "cmd_random": "random",
        "cmd_upcoming": "upcoming",
        "cmd_watchlist": "watchlist",
        "cmd_quiz": "quiz",
        "cmd_mystats": "mystats",
    }
    if data in routes:
        await query.message.reply_text(f"👉 Use /{routes[data]} command.")
    elif data == "open_admin":
        from bot.handlers.admin import admin_panel
        await admin_panel(update, context)
