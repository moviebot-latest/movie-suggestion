from __future__ import annotations

import random as _random

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import repository as repo
from omdb import get_omdb
from decorators import guarded

QUIZ_QUESTIONS = [
    {"q": "Which movie won Best Picture at the 2020 Oscars?", "options": ["Parasite", "1917", "Joker", "Ford v Ferrari"], "answer": 0},
    {"q": "Who directed 'Inception'?", "options": ["Christopher Nolan", "Steven Spielberg", "James Cameron", "Denis Villeneuve"], "answer": 0},
    {"q": "Which movie features the character 'Jai' and 'Veeru'?", "options": ["Sholay", "Deewar", "Zanjeer", "Don"], "answer": 0},
    {"q": "What year did 'The Matrix' release?", "options": ["1997", "1999", "2001", "2003"], "answer": 1},
    {"q": "Which actor played the Joker in 'The Dark Knight'?", "options": ["Jared Leto", "Joaquin Phoenix", "Heath Ledger", "Jack Nicholson"], "answer": 2},
]


@guarded()
async def quiz_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = _random.choice(QUIZ_QUESTIONS)
    context.user_data["quiz_answer"] = q["answer"]
    kb = [[InlineKeyboardButton(opt, callback_data=f"quiz_ans_{i}")] for i, opt in enumerate(q["options"])]
    await update.message.reply_text(
        f"🧠 *QUIZ TIME!*\n━━━━━━━━━━━━━━━━━━\n\n❓ {q['q']}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb),
    )


@guarded()
async def quiz_answer_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chosen = int(query.data.split("_")[2])
    correct_idx = context.user_data.get("quiz_answer")
    if correct_idx is None:
        await query.answer("Quiz expired, /quiz phir se try karo.", show_alert=True)
        return
    is_correct = chosen == correct_idx
    await repo.quiz_record(query.from_user.id, is_correct)
    if is_correct:
        await repo.add_points(query.from_user.id, 5)
        await query.answer("✅ Correct! +5 points", show_alert=True)
    else:
        await query.answer("❌ Wrong answer!", show_alert=True)


@guarded()
async def trending_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    seeds = ["Dune Part Two", "Oppenheimer", "Deadpool & Wolverine", "Animal", "Jawan"]
    lines = []
    for title in seeds:
        data = await get_omdb(title)
        if data and data.get("Response") == "True":
            lines.append(f"🎬 *{data.get('Title')}* ({data.get('Year')}) — ⭐ {data.get('imdbRating', 'N/A')}/10")
    if not lines:
        await update.message.reply_text("❌ Trending fetch nahi ho paya.")
        return
    await update.message.reply_text(
        "🔥 *TRENDING NOW*\n━━━━━━━━━━━━━━━━━━\n\n" + "\n".join(lines), parse_mode="Markdown"
    )


@guarded()
async def daily_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from formatting import today_ist
    seeds = ["Inception", "Interstellar", "Parasite", "RRR", "The Dark Knight",
             "3 Idiots", "Dangal", "Gladiator", "Pulp Fiction", "The Matrix"]
    day_index = today_ist().toordinal() % len(seeds)
    title = seeds[day_index]
    data = await get_omdb(title)
    if data and data.get("Response") == "True":
        from formatting import movie_card_text
        await update.message.reply_text(
            f"📅 *MOVIE OF THE DAY*\n━━━━━━━━━━━━━━━━━━\n\n{movie_card_text(data)}", parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("❌ Kuch error aa gaya.")


@guarded(require_admin=True)
async def clean_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin utility: clears the caller's own conversation state."""
    context.user_data.clear()
    await update.message.reply_text("🧹 Session data cleared.")


@guarded()
async def back_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    from keyboards import main_menu_keyboard
    await query.message.reply_text(
        "╔══════════════════╗\n     🎬 *MAIN MENU*\n╚══════════════════╝",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )
