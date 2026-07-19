"""
Inline mode — lets users type `@YourBot movie name` in ANY chat (not just
with the bot) and get a movie card to share. New feature vs the old bot.
"""
from __future__ import annotations

import uuid

from telegram import (
    InlineQueryResultArticle, InlineQueryResultPhoto,
    InputTextMessageContent, Update,
)
from telegram.ext import ContextTypes

from bot.services.omdb import get_omdb_search
from bot.utils.keyboards import movie_card_keyboard


async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query.strip()
    if not query or len(query) < 2:
        return

    results = await get_omdb_search(query)
    items = []
    for r in results[:10]:
        title = r.get("Title", "Unknown")
        year = r.get("Year", "")
        imdb_id = r.get("imdbID", "")
        poster = r.get("Poster")
        caption = f"🎬 *{title}* ({year})"
        kb = movie_card_keyboard(imdb_id) if imdb_id else None

        if poster and poster != "N/A":
            items.append(
                InlineQueryResultPhoto(
                    id=str(uuid.uuid4()),
                    photo_url=poster,
                    thumbnail_url=poster,
                    title=f"{title} ({year})",
                    caption=caption,
                    parse_mode="Markdown",
                    reply_markup=kb,
                )
            )
        else:
            items.append(
                InlineQueryResultArticle(
                    id=str(uuid.uuid4()),
                    title=f"{title} ({year})",
                    description="No poster available",
                    input_message_content=InputTextMessageContent(caption, parse_mode="Markdown"),
                    reply_markup=kb,
                )
            )

    await update.inline_query.answer(items, cache_time=300, is_personal=False)
