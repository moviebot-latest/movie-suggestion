# ╔══════════════════════════════════════════╗
# ║  ai_features.py — 🤖 AI Suggest          ║
# ║   🔍 Plot Search  🎭 Mood  ⚖️ Compare    ║
# ║  Edit prompts to improve AI responses    ║
# ╚══════════════════════════════════════════╝
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from config import now_ist
from storage import is_maintenance
from helpers import progress_bar, animate_generic, FRAMES
from ai_engine import ai_recommend, ai_plot_search, ai_mood_recommend, ai_compare_movies

import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from config import now_ist
from storage import is_maintenance
from helpers import progress_bar, animate_generic, FRAMES
from ai_engine import ai_recommend

async def suggest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        msg = update.callback_query.message
    else:
        msg = update.message
    if is_maintenance() and not is_admin(update.effective_user.id):
        await msg.reply_text("🚧 Maintenance.")
        return
    await msg.reply_text(
        "╔═══════════════════╗\n║  🤖  *AI SUGGEST*  ║\n╚═══════════════════╝\n\n"
        "📝 *Batao kya chahiye:*\n\n"
        "┌─ Examples ─────────────┐\n"
        "│ • Mujhe action movie chahiye\n│ • RRR jaisi movie\n"
        "│ • Best 2023 thriller\n"
        "└────────────────────────┘\n\n/cancel to exit",
        parse_mode="Markdown"
    )
    return W_AI_QUERY

async def suggest_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.message.text.strip()
    loader = await update.message.reply_text("🤖 Thinking...\n" + progress_bar(0, 4))
    await animate_generic(loader, FRAMES["ai"])
    result = await ai_recommend(query)
    try: await loader.delete()
    except: pass
    if result:
        await update.message.reply_text(
            f"╔══════════════════════╗\n║  🤖  *AI PICKS FOR YOU*  ║\n╚══════════════════════╝\n\n"
            f"{result}\n\n━━━━━━━━━━━━━━━━━━\n_Movie naam type karo to search_ 🔎",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "🥇 RRR (2022)\n🥈 KGF 2 (2022)\n🥉 Pushpa (2021)\n"
            "🏅 Pathaan (2023)\n🎖 Animal (2023)\n\n_Type naam to search_ 🔎\n\n"
            "_GROQ_API add karo better results ke liye!_ 🤖",
            parse_mode="Markdown"
        )
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════════════
#           PLOT SEARCH
# ═══════════════════════════════════════════════════════════════════

import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from config import now_ist
from storage import is_maintenance
from helpers import progress_bar, animate_generic, FRAMES
from ai_engine import ai_plot_search

async def plotsearch_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        msg = update.callback_query.message
    else:
        msg = update.message
    if is_maintenance() and not is_admin(update.effective_user.id):
        await msg.reply_text("🚧 Maintenance.")
        return
    await msg.reply_text(
        "╔═══════════════════╗\n║  🔍  *PLOT SEARCH*  ║\n╚═══════════════════╝\n\n"
        "📝 *Movie ka scene/plot describe karo:*\n\n"
        "┌─ Examples ─────────────┐\n"
        "│ • Train crash wali movie\n│ • Ladka matrix world mein jaata\n"
        "│ • Two brothers fight for gold\n└────────────────────────┘\n\n/cancel to exit",
        parse_mode="Markdown"
    )
    return W_PLOT_SEARCH

async def plotsearch_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    desc   = update.message.text.strip()
    loader = await update.message.reply_text("🔍 Searching...\n" + progress_bar(0, 4))
    await animate_generic(loader, FRAMES["ai"])
    result = await ai_plot_search(desc)
    try: await loader.delete()
    except: pass
    if result:
        await update.message.reply_text(
            f"╔═══════════════════════╗\n║  🔍  *PLOT MATCH RESULTS*  ║\n╚═══════════════════════╝\n\n"
            f"{result}\n\n━━━━━━━━━━━━━━━━━━\n_Movie naam type karo to search_ 🔎",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("❌ *Match nahi mila.*\n\n_GROQ_API add karo._", parse_mode="Markdown")
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════════════
#          LANGUAGE FILTER
# ═══════════════════════════════════════════════════════════════════

import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from config import now_ist
from storage import is_maintenance
from helpers import progress_bar, animate_generic, FRAMES
from ai_engine import ai_mood_recommend

async def mood_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        msg = update.callback_query.message
    else:
        msg = update.message
    if is_maintenance() and not is_admin(update.effective_user.id):
        await msg.reply_text("🚧 Maintenance.")
        return
    await msg.reply_text(
        "╔══════════════════════╗\n║  🎭  *MOOD PICKER*  ║\n╚══════════════════════╝\n\n"
        "📝 *Apna mood batao:*\n\n"
        "┌─ Examples ─────────────┐\n"
        "│ • Sad hoon\n│ • Bored hoon comedy chahiye\n"
        "│ • Family ke saath dekhni\n│ • Late night thriller\n"
        "└────────────────────────┘\n\n/cancel to exit",
        parse_mode="Markdown"
    )
    return W_MOOD

async def mood_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mood   = update.message.text.strip()
    loader = await update.message.reply_text("🎭 Mood samajh raha hun...\n" + progress_bar(0, 4))
    await animate_generic(loader, FRAMES["mood"])
    result = await ai_mood_recommend(mood)
    try: await loader.delete()
    except: pass
    if result:
        await update.message.reply_text(
            f"╔═══════════════════════╗\n║  🎭  *MOOD PICKS FOR YOU*  ║\n╚═══════════════════════╝\n\n"
            f"*Tumhara mood:* _{mood}_\n━━━━━━━━━━━━━━━━━━\n\n"
            f"{result}\n\n_Type naam to search_ 🔎",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("❌ *Kuch nahi mila.*\n\n_GROQ_API add karo._", parse_mode="Markdown")
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════════════
#         MOVIE COMPARISON
# ═══════════════════════════════════════════════════════════════════

import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from config import now_ist
from storage import is_maintenance
from helpers import progress_bar, animate_generic, FRAMES
from ai_engine import ai_compare_movies

async def compare_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        msg = update.callback_query.message
    else:
        msg = update.message
    if is_maintenance() and not is_admin(update.effective_user.id):
        await msg.reply_text("🚧 Maintenance.")
        return
    await msg.reply_text(
        "╔══════════════════════╗\n║  ⚖️  *COMPARE MOVIES*  ║\n╚══════════════════════╝\n\n"
        "📝 *Pehli movie ka naam bhejo:*\n\n/cancel",
        parse_mode="Markdown"
    )
    return W_COMPARE_1

async def compare_recv1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["compare_m1"] = update.message.text.strip()
    await update.message.reply_text(
        f"✅ *Movie 1:* _{context.user_data['compare_m1']}_\n\n"
        f"📝 *Ab doosri movie ka naam bhejo:*\n\n/cancel",
        parse_mode="Markdown"
    )
    return W_COMPARE_2

async def compare_recv2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m1 = context.user_data.get("compare_m1", "")
    m2 = update.message.text.strip()
    loader = await update.message.reply_text("⚖️ Comparing...\n" + progress_bar(0, 4))
    await animate_generic(loader, FRAMES["compare"])
    result = await ai_compare_movies(m1, m2)
    try: await loader.delete()
    except: pass
    if result:
        await update.message.reply_text(
            f"╔════════════════════════╗\n║  ⚖️  *MOVIE COMPARISON*  ║\n╚════════════════════════╝\n\n"
            f"🎬 *{m1}*  vs  🎬 *{m2}*\n━━━━━━━━━━━━━━━━━━\n\n"
            f"{result}\n\n_Powered by Groq AI (Llama 3.3)_ 🤖",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("❌ Comparison nahi hua. GROQ_API check karo.", parse_mode="Markdown")
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════════════
#         LEADERBOARD
# ═══════════════════════════════════════════════════════════════════