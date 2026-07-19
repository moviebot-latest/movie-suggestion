from __future__ import annotations

import re
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import repository as repo
from tmdb import get_movies_for_month, get_trailer, search_by_name
from decorators import guarded
from formatting import now_ist, today_ist


def _nav_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Prev", callback_data="upcom_prev"),
         InlineKeyboardButton("➡️ Next", callback_data="upcom_next")],
    ])


async def _send_movie_card(chat_id: int, m: dict, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎥 Trailer", callback_data=f"upcom_ai_{m['id']}"),
         InlineKeyboardButton("🔔 Remind Me", callback_data=f"upcom_rm_{m['id']}_{m['release']}")],
        [InlineKeyboardButton("➕ Add to My List", callback_data=f"upcom_add_{m['id']}")],
    ])
    caption = (
        f"🎬 *{m['title']}*\n📅 {m['release']}\n⭐ {m['rating']}/10 ({m['votes']} votes)\n🎭 {m['genres']}\n\n"
        f"{m['overview'][:400]}"
    )
    try:
        await context.bot.send_photo(chat_id, photo=m["poster"], caption=caption, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        await context.bot.send_message(
            chat_id, f"🖼️ _Poster load nahi hua_\n\n{caption}", parse_mode="Markdown", reply_markup=kb
        )


def _extract_name_and_year(args: list[str]) -> tuple[str, int | None]:
    """
    /upcoming Avengers 2027        -> ("Avengers", 2027)
    /upcoming Avengers Doomsday    -> ("Avengers Doomsday", None)
    /upcoming Don 2028             -> ("Don", 2028)
    A trailing 4-digit number in a sane year range is treated as the year;
    otherwise the whole thing is treated as the title.
    """
    if not args:
        return "", None
    if len(args) >= 2 and re.fullmatch(r"(19|20)\d{2}", args[-1]):
        year = int(args[-1])
        if 1900 <= year <= 2100:
            return " ".join(args[:-1]), year
    return " ".join(args), None


@guarded()
async def upcoming_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # `/upcoming` with no args -> browse this month's releases (old behavior).
    if not context.args:
        today = today_ist()
        month, year = today.month, today.year
        movies = await get_movies_for_month(month, year)
        if not movies:
            await update.message.reply_text("📅 Koi upcoming movies nahi mili is mahine.")
            return
        context.user_data["upcom_movies"] = movies
        context.user_data["upcom_page"] = 0
        chunk = movies[:5]
        await update.message.reply_text(f"📅 *Upcoming — {today.strftime('%B %Y')}*", parse_mode="Markdown")
        for m in chunk:
            await _send_movie_card(update.effective_chat.id, m, context)
        if len(movies) > 5:
            await update.message.reply_text("👇 Navigate karo:", reply_markup=_nav_keyboard())
        return

    # `/upcoming <movie name> [year]` -> search for that specific movie.
    name, year = _extract_name_and_year(context.args)
    loader = await update.message.reply_text(f"🔍 Searching for *{name}*{f' ({year})' if year else ''}...", parse_mode="Markdown")
    results = await search_by_name(name, year)
    try:
        await loader.delete()
    except Exception:
        pass

    if not results:
        hint = f" *({year})*" if year else ""
        await update.message.reply_text(
            f"❌ *'{name}'*{hint} nahi mili.\n\n"
            "💡 Tip: `/upcoming Movie Name 2027` — saal bhi likhoge to sahi movie milne ke chances zyada hain "
            "(kai movies ke sequel/remake same naam se hote hain).",
            parse_mode="Markdown",
        )
        return

    if len(results) == 1:
        context.user_data["upcom_movies"] = results
        await _send_movie_card(update.effective_chat.id, results[0], context)
        return

    # Multiple matches — let the user pick the correct one (this is exactly the
    # case where a bare title search shows the wrong movie; picking by year
    # disambiguates it).
    context.user_data["upcom_movies"] = results
    keyboard = [
        [InlineKeyboardButton(
            f"🎬 {m['title']} ({m['release'][:4] if m['release'] != 'N/A' else '?'})",
            callback_data=f"upcom_pick_{m['id']}",
        )]
        for m in results
    ]
    await update.message.reply_text(
        f"🔍 *Multiple results for '{name}'*\n\nSahi wali choose karo 👇",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


@guarded()
async def upcom_pick_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🎬 Loading...")
    movie_id = int(query.data.replace("upcom_pick_", ""))
    movies = context.user_data.get("upcom_movies", [])
    m = next((mv for mv in movies if mv["id"] == movie_id), None)
    if not m:
        await query.message.reply_text("❌ Session expired, `/upcoming` phir se try karo.", parse_mode="Markdown")
        return
    await _send_movie_card(query.message.chat_id, m, context)


@guarded()
async def upcom_paginate_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    movies = context.user_data.get("upcom_movies", [])
    page = context.user_data.get("upcom_page", 0)
    if query.data == "upcom_next":
        page += 1
    elif query.data == "upcom_prev":
        page = max(0, page - 1)
    context.user_data["upcom_page"] = page
    chunk = movies[page * 5:(page + 1) * 5]
    if not chunk:
        await query.answer("Aur movies nahi hain.", show_alert=True)
        return
    await query.answer(f"Page {page + 1}")
    for m in chunk:
        await _send_movie_card(query.message.chat_id, m, context)


@guarded()
async def upcom_ai_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🎥 Loading trailer...")
    movie_id = int(query.data.split("_")[2])
    trailer = await get_trailer(movie_id)
    if trailer:
        await query.message.reply_text(f"🎥 Trailer: {trailer}")
    else:
        await query.message.reply_text("❌ Trailer nahi mila.")


@guarded()
async def upcom_remind_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = query.data.split("_")
    movie_id = int(parts[2])
    release = parts[3]
    try:
        rel_date = datetime.strptime(release, "%Y-%m-%d").date()
        if rel_date <= today_ist():
            await query.answer("⚠️ Ye movie already release ho chuki hai!", show_alert=True)
            return
    except ValueError:
        await query.answer("⚠️ Release date unknown.", show_alert=True)
        return

    movies = context.user_data.get("upcom_movies", [])
    title = next((m["title"] for m in movies if m["id"] == movie_id), "Movie")
    await repo.upcoming_reminder_add(query.from_user.id, movie_id, title, release)
    await query.answer(f"🔔 Reminder set! Release: {release}", show_alert=True)


@guarded()
async def upcom_add_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Adding...")
    movie_id = int(query.data.split("_")[2])
    movies = context.user_data.get("upcom_movies", [])
    title = next((m["title"] for m in movies if m["id"] == movie_id), "Movie")
    await repo.upcoming_mylist_add(query.from_user.id, movie_id, title)
    await query.message.reply_text(f"➕ Added to your list: *{title}*", parse_mode="Markdown")


@guarded()
async def upcom_remove_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/upcom_remove <movie_id>`", parse_mode="Markdown")
        return
    try:
        movie_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid movie ID.")
        return
    removed = await repo.upcoming_mylist_remove(update.effective_user.id, movie_id)
    if removed:
        await update.message.reply_text("✅ Removed from your list.")
    else:
        await update.message.reply_text("Ye movie aapki list mein nahi hai.")
