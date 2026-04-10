# ╔══════════════════════════════════════════╗
# ║  social.py — 🏆 Leaderboard  📜 History  ║
# ║              👥 Refer  📊 My Stats        ║
# ║  Edit to change social features          ║
# ╚══════════════════════════════════════════╝
import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from config import now_ist
from storage import load_json, save_json, is_maintenance
from helpers import get_badge

import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from storage import load_json, is_maintenance
from helpers import get_badge

async def leaderboard_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = load_json("users")
    sorted_users = sorted(users.values(), key=lambda x: x.get("points", 0), reverse=True)[:10]
    medals = ["🥇", "🥈", "🥉", "🏅", "🎖", "⭐", "🌟", "💫", "✨", "🎬"]
    text = "╔══════════════════════╗\n║  🏆  *LEADERBOARD*  ║\n╚══════════════════════╝\n\n"
    text += "*Top 10 CineBot Users:*\n━━━━━━━━━━━━━━━━━━\n\n"
    for i, u in enumerate(sorted_users):
        badge = get_badge(u.get("points", 0))
        name  = u.get("name", "Unknown")[:15]
        pts   = u.get("points", 0)
        medal = medals[i] if i < len(medals) else "🎬"
        text += f"{medal} *{name}* — `{pts}` pts {badge}\n"
    text += "\n_Search=+10 | Refer=+50 | Rate=+5_ 🎯"
    await update.message.reply_text(text, parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════════
#         SEARCH HISTORY
# ═══════════════════════════════════════════════════════════════════

import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from storage import load_json, is_maintenance

async def history_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid     = str(update.effective_user.id)
    history = load_json("history")
    my_hist = history.get(uid, [])
    if not my_hist:
        await update.message.reply_text(
            "╔══════════════════╗\n║  📜  *HISTORY*  ║\n╚══════════════════╝\n\n"
            "📭 *Koi history nahi!*\n\n_Movies search karo_ 🔎",
            parse_mode="Markdown"
        )
        return
    text = "╔══════════════════╗\n║  📜  *MY HISTORY*  ║\n╚══════════════════╝\n\n"
    text += f"*Last {len(my_hist)} Searches:*\n━━━━━━━━━━━━━━━━━━\n\n"
    for i, h in enumerate(my_hist, 1):
        text += f"`{i}.` 🎬 *{h['movie']}* — `{h['time']}`\n"
    text += "\n_Type naam to search again_ 🔎"
    await update.message.reply_text(text, parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════════
#              DIRECTOR TOP 5
# ═══════════════════════════════════════════════════════════════════

import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from storage import load_json, is_maintenance

async def refer_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user     = update.effective_user
    uid      = str(user.id)
    users    = load_json("users")
    refs     = users.get(uid, {}).get("refs",   0)
    pts      = users.get(uid, {}).get("points", 0)
    bot_info = await context.bot.get_me()
    link     = f"https://t.me/{bot_info.username}?start={user.id}"
    await update.message.reply_text(
        f"╔══════════════════════╗\n║  👥  *REFER & EARN*  ║\n╚══════════════════════╝\n\n"
        f"🔗 *Your Link:*\n`{link}`\n\n"
        f"┌─────────────────────┐\n│  👥 Referred: `{refs}` users\n│  ⭐ Points: `{pts}`\n└─────────────────────┘\n\n"
        f"💰 *Rewards:*\n• Har refer = +50 points 🎁\n• 10 refers = 🥇 Gold Badge\n\n_Share karo aur points kamao!_ 🚀",
        parse_mode="Markdown"
    )


# ═══════════════════════════════════════════════════════════════════
#           MOVIE QUIZ (general random)

import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from config import now_ist
from storage import load_json, is_maintenance
from helpers import get_badge

async def mystats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid   = str(update.effective_user.id)
    users = load_json("users")
    udata = users.get(uid, {})
    wl    = load_json("watchlist").get(uid, [])
    pts   = udata.get("points",   0)
    srch  = udata.get("searches", 0)
    refs  = udata.get("refs",     0)
    badge = get_badge(pts)
    hist  = len(load_json("history").get(uid, []))
    if pts < 100:    next_badge = f"🥉 Bronze needs `{100-pts}` more pts"
    elif pts < 200:  next_badge = f"🥈 Silver needs `{200-pts}` more pts"
    elif pts < 500:  next_badge = f"🥇 Gold needs `{500-pts}` more pts"
    elif pts < 1000: next_badge = f"💎 Diamond needs `{1000-pts}` more pts"
    else:            next_badge = "💎 *MAX BADGE!* 🎉"
    await update.message.reply_text(
        f"╔═══════════════════╗\n║  📊  *MY STATS*  ║\n╚═══════════════════╝\n\n"
        f"👤 *{update.effective_user.full_name}*\n\n"
        f"┌─────────────────────┐\n│  🏆 Badge: {badge}\n│  ⭐ Points: `{pts}`\n"
        f"│  🔎 Searches: `{srch}`\n│  ❤️ Watchlist: `{len(wl)}`\n"
        f"│  📜 History: `{hist}` movies\n│  👥 Refers: `{refs}`\n└─────────────────────┘\n\n"
        f"📈 *Next:* {next_badge}\n\n━━━━━━━━━━━━━━━━━━\n_Search=+10 • Refer=+50 • Rate=+5_ 🎯",
        parse_mode="Markdown"
    )


# ═══════════════════════════════════════════════════════════════════
#           REFER & EARN
# ═══════════════════════════════════════════════════════════════════
