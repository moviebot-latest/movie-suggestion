from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from groq_ai import ai_recommend, ai_plot_search
from omdb import get_omdb
from decorators import guarded
from formatting import movie_card_text

W_AI_QUERY, W_PLOT_SEARCH, W_MOOD, W_COMPARE_1, W_COMPARE_2 = range(5)


# ── /suggest ─────────────────────────────────────────────────────
@guarded()
async def suggest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.callback_query.message if update.callback_query else update.message
    if update.callback_query:
        await update.callback_query.answer()
    await target.reply_text(
        "🎬 *AI Suggest*\n\nMujhe bata do kya dekhna chahte ho — genre, mood, ya kisi movie jaisi vibe.\n\n/cancel",
        parse_mode="Markdown",
    )
    return W_AI_QUERY


async def suggest_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    loader = await update.message.reply_text("🤖 Thinking...")
    result = await ai_recommend(query)
    try:
        await loader.delete()
    except Exception:
        pass
    if result:
        await update.message.reply_text(f"🎬 *AI Suggestions*\n━━━━━━━━━━━━━━━━━━\n\n{result}", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ AI abhi available nahi hai. Try /random instead.")
    return ConversationHandler.END


# ── /plotsearch ──────────────────────────────────────────────────
@guarded()
async def plotsearch_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.callback_query.message if update.callback_query else update.message
    if update.callback_query:
        await update.callback_query.answer()
    await target.reply_text(
        "🔍 *Plot Search*\n\nMovie ka plot/story describe karo, main guess karunga kaunsi movie hai.\n\n/cancel",
        parse_mode="Markdown",
    )
    return W_PLOT_SEARCH


async def plotsearch_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plot = update.message.text.strip()
    loader = await update.message.reply_text("🤖 Analyzing plot...")
    result = await ai_plot_search(plot)
    try:
        await loader.delete()
    except Exception:
        pass
    if result:
        await update.message.reply_text(f"🔍 *Possible Matches*\n━━━━━━━━━━━━━━━━━━\n\n{result}", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Guess nahi kar paya. Thoda aur detail do?")
    return ConversationHandler.END


# ── /mood ────────────────────────────────────────────────────────
@guarded()
async def mood_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.callback_query.message if update.callback_query else update.message
    if update.callback_query:
        await update.callback_query.answer()
    await target.reply_text(
        "😊 *Mood Match*\n\nAbhi kaisa feel kar rahe ho? (e.g. \"sad\", \"excited\", \"bored\")\n\n/cancel",
        parse_mode="Markdown",
    )
    return W_MOOD


async def mood_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from groq_ai import ai_mood_match
    mood = update.message.text.strip()
    loader = await update.message.reply_text("🤖 Finding movies for your mood...")
    result = await ai_mood_match(mood)
    try:
        await loader.delete()
    except Exception:
        pass
    if result:
        await update.message.reply_text(f"😊 *Mood Matches*\n━━━━━━━━━━━━━━━━━━\n\n{result}", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ AI abhi available nahi hai.")
    return ConversationHandler.END


# ── /compare ─────────────────────────────────────────────────────
@guarded()
async def compare_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.callback_query.message if update.callback_query else update.message
    if update.callback_query:
        await update.callback_query.answer()
    await target.reply_text("⚖️ *Compare Movies*\n\nPehli movie ka naam bhejo:\n\n/cancel", parse_mode="Markdown")
    return W_COMPARE_1


async def compare_recv1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["compare_movie1"] = update.message.text.strip()
    await update.message.reply_text("Ab dusri movie ka naam bhejo:")
    return W_COMPARE_2


async def compare_recv2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title1 = context.user_data.pop("compare_movie1", None)
    title2 = update.message.text.strip()
    if not title1:
        await update.message.reply_text("❌ Kuch error aa gaya, /compare phir se try karo.")
        return ConversationHandler.END

    loader = await update.message.reply_text("🎬 Comparing...")
    data1 = await get_omdb(title1)
    data2 = await get_omdb(title2)
    try:
        await loader.delete()
    except Exception:
        pass

    if not data1 or data1.get("Response") == "False":
        await update.message.reply_text(f"❌ *'{title1}'* nahi mili.", parse_mode="Markdown")
        return ConversationHandler.END
    if not data2 or data2.get("Response") == "False":
        await update.message.reply_text(f"❌ *'{title2}'* nahi mili.", parse_mode="Markdown")
        return ConversationHandler.END

    text = (
        f"⚖️ *Comparison*\n\n"
        f"{movie_card_text(data1)}\n\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"{movie_card_text(data2)}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END
