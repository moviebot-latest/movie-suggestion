from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import repository as repo
from omdb import get_omdb, get_omdb_search
from groq_ai import ai_fix_movie_name
from decorators import guarded
from formatting import movie_card_text
from keyboards import movie_card_keyboard


async def _send_movie_card(update: Update, context: ContextTypes.DEFAULT_TYPE, data: dict, reply_to=None):
    imdb_id = data.get("imdbID", "")
    title = data.get("Title", "")
    text = movie_card_text(data)
    poster = data.get("Poster")
    kb = movie_card_keyboard(imdb_id, title)

    target = reply_to or update.effective_message

    if not poster or poster == "N/A":
        # OMDB itself has no poster for this title — nothing to retry, just send text.
        await target.reply_text(text, parse_mode="Markdown", reply_markup=kb)
        return

    try:
        await target.reply_photo(photo=poster, caption=text, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        # Poster URL OMDB gave us is dead/expired/unreachable — fall back to text-only,
        # but let the user know a poster existed and just failed to load (not that
        # this movie simply has no poster at all).
        await target.reply_text(
            f"🖼️ _Poster load nahi hua (link expired/unreachable)_\n\n{text}",
            parse_mode="Markdown",
            reply_markup=kb,
        )


@guarded()
async def movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Catch-all text handler — treats any free text as a movie search query."""
    user = update.effective_user
    raw_name = update.message.text.strip()
    if not raw_name:
        return

    await repo.register_user(user.id, user.full_name, user.username)
    await repo.increment_search_count(user.id)
    await repo.log_search(user.id, raw_name)

    loader = await update.message.reply_text("🎬 Searching...")

    data = await get_omdb(raw_name)

    if not data or data.get("Response") == "False":
        try:
            await loader.edit_text("🤖 AI fixing name...")
        except Exception:
            pass
        fixed_name = await ai_fix_movie_name(raw_name)
        if fixed_name.lower() != raw_name.lower():
            data = await get_omdb(fixed_name)

    if not data or data.get("Response") == "False":
        results = await get_omdb_search(raw_name)
        if results:
            if len(results) == 1:
                data = await get_omdb(results[0].get("imdbID", ""), by_id=True)
            else:
                try:
                    await loader.delete()
                except Exception:
                    pass
                keyboard = [
                    [InlineKeyboardButton(
                        f"🎬 {r.get('Title', '?')} ({r.get('Year', '?')})",
                        callback_data=f"pick_{r.get('imdbID', '')}",
                    )]
                    for r in results if r.get("imdbID")
                ]
                await update.message.reply_text(
                    f"🔍 *MULTIPLE RESULTS* for _'{raw_name}'_\n━━━━━━━━━━━━━━━━━━\n\nSahi wali choose karo 👇",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
                return

    if not data or data.get("Response") == "False":
        try:
            await loader.edit_text(
                f"❌ *'{raw_name}'* nahi mili\n\n💡 Try: /plotsearch /suggest /mood /random",
                parse_mode="Markdown",
            )
        except Exception:
            pass
        return

    try:
        await loader.delete()
    except Exception:
        pass
    await _send_movie_card(update, context, data)


@guarded()
async def pick_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🎬 Loading...")
    imdb_id = query.data.replace("pick_", "")
    data = await get_omdb(imdb_id, by_id=True)
    if data and data.get("Response") == "True":
        await _send_movie_card(update, context, data, reply_to=query.message)
    else:
        await query.message.reply_text("❌ Load nahi hua. Try again.")


@guarded()
async def movieinfo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = " ".join(context.args).strip() if context.args else ""
    if not title:
        await update.message.reply_text("❌ *Usage:* `/movieinfo Movie Name`", parse_mode="Markdown")
        return
    data = await get_omdb(title)
    if not data or data.get("Response") == "False":
        await update.message.reply_text(f"❌ *'{title}'* nahi mili.", parse_mode="Markdown")
        return
    await _send_movie_card(update, context, data)


@guarded()
async def random_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import random as _random
    seeds = ["Inception", "The Dark Knight", "Interstellar", "Parasite", "RRR",
             "Dangal", "The Matrix", "Pulp Fiction", "3 Idiots", "Gladiator"]
    title = _random.choice(seeds)
    data = await get_omdb(title)
    if data and data.get("Response") == "True":
        await _send_movie_card(update, context, data)
    else:
        await update.message.reply_text("❌ Kuch error aa gaya, phir try karo.")
