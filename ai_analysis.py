from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from omdb import get_omdb
from groq_ai import ai_movie_review, ai_cast_analysis, ai_trivia
from tmdb import search_by_name, get_credits, get_similar, get_movie_details
from decorators import guarded


@guarded()
async def review_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🤖 Writing review...")
    imdb_id = query.data.split("_", 1)[1]
    data = await get_omdb(imdb_id, by_id=True)
    if not data or data.get("Response") == "False":
        await query.message.reply_text("❌ Movie details fetch nahi ho payi!")
        return
    review = await ai_movie_review(
        data.get("Title", "N/A"), data.get("Year", "N/A"),
        data.get("Plot", "N/A"), data.get("imdbRating", "N/A"),
    )
    if review:
        await query.message.reply_text(f"🤖 *AI Review*\n\n🎬 *{data.get('Title')}*\n━━━━━━━━━━━━━━━━━━\n\n{review}", parse_mode="Markdown")
    else:
        await query.message.reply_text("❌ AI Review nahi aaya. Try again.")


@guarded()
async def fullreview_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = " ".join(context.args).strip() if context.args else ""
    if not title:
        await update.message.reply_text("Usage: `/fullreview Movie Name`", parse_mode="Markdown")
        return
    data = await get_omdb(title)
    if not data or data.get("Response") == "False":
        await update.message.reply_text(f"❌ *'{title}'* nahi mili.", parse_mode="Markdown")
        return
    review = await ai_movie_review(data.get("Title"), data.get("Year"), data.get("Plot"), data.get("imdbRating"))
    if review:
        await update.message.reply_text(f"📖 *Full Review — {data.get('Title')}*\n\n{review}", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ AI abhi available nahi hai.")


@guarded()
async def fullreview_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("📖 Generating...")
    imdb_id = query.data.split("_", 1)[1]
    data = await get_omdb(imdb_id, by_id=True)
    if not data or data.get("Response") == "False":
        await query.message.reply_text("❌ Fetch nahi ho paya.")
        return
    review = await ai_movie_review(data.get("Title"), data.get("Year"), data.get("Plot"), data.get("imdbRating"))
    if review:
        await query.message.reply_text(f"📖 *Full Review — {data.get('Title')}*\n\n{review}", parse_mode="Markdown")
    else:
        await query.message.reply_text("❌ AI abhi available nahi hai.")


@guarded()
async def moodmatch_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Use /mood command for mood-based suggestions.")


@guarded()
async def moodmatch_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("Use /mood command.", show_alert=True)


@guarded()
async def castinfo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = " ".join(context.args).strip() if context.args else ""
    if not title:
        await update.message.reply_text("Usage: `/castinfo Movie Name`", parse_mode="Markdown")
        return
    results = await search_by_name(title)
    if not results:
        await update.message.reply_text("❌ Movie nahi mili.")
        return
    movie_id = results[0]["id"]
    credits = await get_credits(movie_id)
    if not credits:
        await update.message.reply_text("❌ Cast info nahi mili.")
        return
    cast = credits.get("cast", [])[:6]
    cast_names = ", ".join(c["name"] for c in cast) or "N/A"
    analysis = await ai_cast_analysis(results[0]["title"], cast_names)
    text = f"🎭 *Cast — {results[0]['title']}*\n\n{cast_names}"
    if analysis:
        text += f"\n\n🤖 *Analysis*\n{analysis}"
    await update.message.reply_text(text, parse_mode="Markdown")


@guarded()
async def castanalysis_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("Use /castinfo <movie name> command.", show_alert=True)


@guarded()
async def trivia_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = " ".join(context.args).strip() if context.args else ""
    if not title:
        await update.message.reply_text("Usage: `/trivia Movie Name`", parse_mode="Markdown")
        return
    data = await get_omdb(title)
    if not data or data.get("Response") == "False":
        await update.message.reply_text(f"❌ *'{title}'* nahi mili.", parse_mode="Markdown")
        return
    trivia = await ai_trivia(data.get("Title"), data.get("Year"))
    if trivia:
        await update.message.reply_text(f"🎉 *Trivia — {data.get('Title')}*\n\n{trivia}", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ AI abhi available nahi hai.")


@guarded()
async def trivia_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("Use /trivia <movie name> command.", show_alert=True)


@guarded()
async def funfact_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🎉 Generating...")
    imdb_id = query.data.split("_", 1)[1]
    data = await get_omdb(imdb_id, by_id=True)
    if not data or data.get("Response") == "False":
        await query.message.reply_text("❌ Fetch nahi ho paya.")
        return
    trivia = await ai_trivia(data.get("Title"), data.get("Year"))
    if trivia:
        await query.message.reply_text(f"🎉 *Fun Facts — {data.get('Title')}*\n\n{trivia}", parse_mode="Markdown")
    else:
        await query.message.reply_text("❌ AI abhi available nahi hai.")


@guarded()
async def fullpackage_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("📦 Generating full package... this may take a moment")
    imdb_id = query.data.split("_", 1)[1]
    data = await get_omdb(imdb_id, by_id=True)
    if not data or data.get("Response") == "False":
        await query.message.reply_text("❌ Fetch nahi ho paya.")
        return
    review = await ai_movie_review(data.get("Title"), data.get("Year"), data.get("Plot"), data.get("imdbRating"))
    trivia = await ai_trivia(data.get("Title"), data.get("Year"))
    text = f"📦 *Full Package — {data.get('Title')}*\n\n🤖 *Review*\n{review or 'N/A'}\n\n🎉 *Trivia*\n{trivia or 'N/A'}"
    await query.message.reply_text(text, parse_mode="Markdown")


# ── Similar movies ───────────────────────────────────────────────
@guarded()
async def similar_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🎭 Finding similar movies...")
    imdb_id = query.data.split("_", 1)[1]
    data = await get_omdb(imdb_id, by_id=True)
    if not data or data.get("Response") == "False":
        await query.message.reply_text("❌ Fetch nahi ho paya.")
        return
    results = await search_by_name(data.get("Title", ""))
    if not results:
        await query.message.reply_text("❌ Similar movies nahi mili.")
        return
    movie_id = results[0]["id"]
    similar = await get_similar(movie_id)
    if not similar:
        await query.message.reply_text("❌ Similar movies nahi mili.")
        return
    lines = [f"🎬 {m.get('title', 'Unknown')} ({m.get('release_date', 'N/A')[:4]})" for m in similar]
    await query.message.reply_text("🎭 *Similar Movies*\n\n" + "\n".join(lines), parse_mode="Markdown")
