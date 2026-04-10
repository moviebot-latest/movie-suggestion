# ╔══════════════════════════════════════════╗
# ║  discovery.py — 🔥 Trending  🎲 Random  ║
# ║                 🎯 Daily Pick            ║
# ║  Edit to change movies / pool           ║
# ╚══════════════════════════════════════════╝
import asyncio, random
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from config import TMDB_API, now_ist, today_ist
from storage import is_maintenance, load_json, save_json
from movie_info import get_tmdb_trending

import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import TMDB_API, now_ist
from storage import is_maintenance
from movie_info import get_tmdb_trending

async def trending_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_maintenance() and not is_admin(update.effective_user.id):
        await update.message.reply_text("🚧 Maintenance.")
        return
    loader = await update.message.reply_text("🔥 Loading trending...\n" + progress_bar(1, 3))
    await asyncio.sleep(0.8)
    tmdb_t = get_tmdb_trending()
    bot_t  = get_trending(5)
    try: await loader.delete()
    except: pass
    text = "╔════════════════════╗\n║  🔥  *TRENDING NOW*  ║\n╚════════════════════╝\n\n"
    if tmdb_t:
        text += "🌍 *Worldwide This Week:*\n━━━━━━━━━━━━━━━━━━\n"
        medals = ["🥇","🥈","🥉","🏅","🎖","⭐","🌟","💫","✨","🎬"]
        for i, (t, r) in enumerate(tmdb_t):
            text += f"{medals[i]} `{t}` ⭐{r}\n"
        text += "\n"
    if bot_t:
        text += "📊 *Most Searched Here:*\n━━━━━━━━━━━━━━━━━━\n"
        for i, (t, c) in enumerate(bot_t, 1):
            text += f"`{i}.` {t} — `{c}x`\n"
    text += "\n_Type naam to search_ 🔎"
    await update.message.reply_text(text, parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════════
#            RANDOM MOVIE
# ═══════════════════════════════════════════════════════════════════
RANDOM_POOL = [
    "Inception","Interstellar","The Dark Knight","Avengers Endgame",
    "Dune","Oppenheimer","Top Gun Maverick","Avatar","Spider-Man No Way Home",
    "The Godfather","Forrest Gump","The Shawshank Redemption","Joker",
    "Fight Club","Gladiator","The Matrix","Parasite","Whiplash",
    "La La Land","Get Out","1917","Tenet","Arrival","Hereditary",
    "Everything Everywhere All at Once","Doctor Strange","Thor Ragnarok",
    "RRR","KGF","Pushpa","Pathaan","Animal","Jawan","Brahmastra",
    "Bahubali","Bahubali 2","Dangal","3 Idiots","PK","Andhadhun","Tumbbad",
    "Article 15","Uri","Shershaah","Vikram","Drishyam","Drishyam 2",
    "Laal Singh Chaddha","Sanju","Gully Boy","Zindagi Na Milegi Dobara",
    "Dil Chahta Hai","Swades","Lagaan","Rang De Basanti","Taare Zameen Par",
    "Queen","Piku","Masaan","Newton","Stree","Bhediya","Chhichhore",
    "Vikram Vedha","Master","Beast","Varisu","Leo","Jailer",
    "Pushpa 2","Salaar","HanuMan","Kalki 2898 AD","Devara",
]


import asyncio, random
from telegram import Update
from telegram.ext import ContextTypes
from config import now_ist
from storage import is_maintenance

async def random_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_maintenance() and not is_admin(update.effective_user.id):
        await update.message.reply_text("🚧 Maintenance.")
        return
    loader = await update.message.reply_text("🎲 Picking random...\n" + progress_bar(3, 6))
    await asyncio.sleep(1.2)
    seen = context.user_data.get("random_seen", [])
    pool = [m for m in RANDOM_POOL if m not in seen]
    if not pool:
        seen = []
        pool = RANDOM_POOL.copy()
        context.user_data["random_seen"] = []
    pick = random.choice(pool)
    seen.append(pick)
    context.user_data["random_seen"] = seen
    data = await asyncio.to_thread(get_omdb, pick)
    try: await loader.delete()
    except: pass
    if data and data.get("Response") == "True":
        remaining = len(RANDOM_POOL) - len(seen)
        await update.message.reply_text(
            f"🎲 *Random Pick* | _{remaining} more unseen_",
            parse_mode="Markdown"
        )
        await _send_movie_card(update, context, data)
    else:
        await update.message.reply_text(f"🎲 *Random Pick:* _{pick}_\n\nType to search! 🔎", parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════════
#          DAILY FEATURED MOVIE
# ═══════════════════════════════════════════════════════════════════
DAILY_MOVIES = [
    "Inception", "The Dark Knight", "Interstellar", "RRR", "KGF",
    "Bahubali 2", "3 Idiots", "Dangal", "Andhadhun", "Tumbbad",
    "Dune", "Oppenheimer", "Pathaan", "Animal", "Jawan",
]


import asyncio
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from config import now_ist, today_ist
from storage import is_maintenance, load_json, save_json

async def daily_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_maintenance() and not is_admin(update.effective_user.id):
        await update.message.reply_text("🚧 Maintenance.")
        return
    today = str(today_ist())
    daily = load_json("daily")
    loader = await update.message.reply_text("🎬 Loading daily pick...\n" + progress_bar(0, 3))
    await animate_generic(loader, FRAMES["daily"])
    if daily.get("date") != today:
        pick = DAILY_MOVIES[hash(today) % len(DAILY_MOVIES)]
        daily = {"date": today, "movie": pick}
        save_json("daily", daily)
    else:
        pick = daily["movie"]
    data = await asyncio.to_thread(get_omdb, pick)
    try: await loader.delete()
    except: pass
    if data and data.get("Response") == "True":
        await update.message.reply_text(f"🎯 *Today's Featured Movie*\n📅 `{today}`", parse_mode="Markdown")
        await _send_movie_card(update, context, data)
    else:
        await update.message.reply_text(f"🎬 *Today's Pick:* _{pick}_", parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════════
#            WATCHLIST
# ═══════════════════════════════════════════════════════════════════
