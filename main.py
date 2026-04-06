# ╔══════════════════════════════════════════════════════════════════╗
# ║              🎬 CineBot v2 — All Phases Complete                ║
# ║                                                                  ║
# ║  Phase 1: Movie Info + Rotten Tomatoes + Subtitles + Countdown  ║
# ║  Phase 2: AI Suggest + Similar + Plot Search + Lang Filter      ║
# ║  Phase 3: Typewriter + Progress Bar + Color Themes              ║
# ║  Phase 4: Admin Stats + Broadcast + Ban + Logs + Alerts         ║
# ║  Phase 5: Watchlist + Points + Badges + Alerts + Lang Switch    ║
# ║  Phase 6: Trending + Random + Refer + Daily + Quiz              ║
# ║                                                                  ║
# ║  APIs (all FREE):                                                ║
# ║  • BOT_TOKEN   → @BotFather                                     ║
# ║  • OMDB_API    → omdbapi.com                                    ║
# ║  • TMDB_API    → themoviedb.org                                 ║
# ║  • GEMINI_API  → aistudio.google.com                            ║
# ║  • ADMIN_ID    → @userinfobot                                   ║
# ║                                                                  ║
# ║  Deploy: Koyeb (free, no sleep) + MongoDB Atlas (free)          ║
# ║  pip install python-telegram-bot requests flask                  ║
# ║           google-generativeai                                    ║
# ╚══════════════════════════════════════════════════════════════════╝

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes, ConversationHandler
)
import requests, threading, json, os, asyncio, random
from datetime import datetime, date
from flask import Flask

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

# ═══════════════════════════════════════════════════════════════════
#                         ENV VARIABLES
# ═══════════════════════════════════════════════════════════════════
TOKEN      = os.getenv("BOT_TOKEN")
OMDB_API   = os.getenv("OMDB_API")
TMDB_API   = os.getenv("TMDB_API",   "")
GEMINI_API = os.getenv("GEMINI_API", "")
ADMIN_ID   = int(os.getenv("ADMIN_ID", "0"))

if GEMINI_AVAILABLE and GEMINI_API:
    genai.configure(api_key=GEMINI_API)
    ai_model = genai.GenerativeModel("gemini-1.5-flash")
else:
    ai_model = None

# ═══════════════════════════════════════════════════════════════════
#                       WEB SERVER (KEEP ALIVE)
# ═══════════════════════════════════════════════════════════════════
web_app = Flask(__name__)

@web_app.route("/")
def home(): return "🎬 CineBot v2 Running"

def run_web():
    web_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

threading.Thread(target=run_web, daemon=True).start()


# ═══════════════════════════════════════════════════════════════════
#                      PERSISTENT STORAGE
# ═══════════════════════════════════════════════════════════════════
FILES = {
    "servers":     "servers.json",
    "maintenance": "maintenance.json",
    "users":       "users.json",
    "watchlist":   "watchlist.json",
    "searches":    "searches.json",
    "banned":      "banned.json",
    "logs":        "logs.json",
    "daily":       "daily.json",
    "quiz":        "quiz.json",
    "alerts":      "alerts.json",
    "refers":      "refers.json",
}

DEFAULT_SERVERS = {
    "s1": {"name": "HdHub4u",     "url": "https://new4.hdhub4u.fo/?s="},
    "s2": {"name": "123Mkv",      "url": "https://123mkv.bar/?s="},
    "s3": {"name": "MkvCinemas",  "url": "https://mkvcinemas.sb/?s="},
    "s4": {"name": "WorldFree4u", "url": "https://worldfree4u.ist/?s="},
    "s5": {"name": "Bolly4u",     "url": "https://bolly4u.gifts/?s="},
    "s6": {"name": "FilmyZilla",  "url": "https://filmyzilla.com.ph/?s="},
}

def load_json(key, default=None):
    fp = FILES[key]
    if default is None: default = {}
    if os.path.exists(fp):
        try:
            with open(fp) as f: return json.load(f)
        except: pass
    save_json(key, default)
    return default.copy() if isinstance(default, dict) else default

def save_json(key, data):
    with open(FILES[key], "w") as f: json.dump(data, f, indent=2)

def load_servers():
    data = load_json("servers", {k: v.copy() for k, v in DEFAULT_SERVERS.items()})
    for k, v in DEFAULT_SERVERS.items():
        if k not in data: data[k] = v.copy()
    return data

bot_servers = load_servers()

def register_user(user, ref_id=None):
    users = load_json("users")
    uid   = str(user.id)
    if uid not in users:
        users[uid] = {
            "id":       user.id,
            "name":     user.full_name,
            "username": user.username or "N/A",
            "joined":   datetime.now().strftime("%Y-%m-%d %H:%M"),
            "searches": 0,
            "points":   0,
            "lang":     "hi",
            "ref_by":   ref_id,
            "refs":     0,
        }
        # Refer bonus
        if ref_id:
            refs = load_json("refers")
            refs[str(ref_id)] = refs.get(str(ref_id), 0) + 1
            save_json("refers", refs)
            # Give referrer bonus points
            if str(ref_id) in users:
                users[str(ref_id)]["points"] = users[str(ref_id)].get("points", 0) + 50
                users[str(ref_id)]["refs"]   = users[str(ref_id)].get("refs", 0) + 1
    else:
        users[uid]["searches"] = users[uid].get("searches", 0) + 1
        users[uid]["points"]   = users[uid].get("points",   0) + 10
    save_json("users", users)

def get_user_lang(user_id):
    users = load_json("users")
    return users.get(str(user_id), {}).get("lang", "hi")

def log_search(title, user_id):
    # Search trending
    data = load_json("searches")
    data[title] = data.get(title, 0) + 1
    save_json("searches", data)
    # Activity log
    logs = load_json("logs")
    today = str(date.today())
    if today not in logs: logs[today] = []
    logs[today].append({"user": user_id, "movie": title, "time": datetime.now().strftime("%H:%M")})
    if len(logs) > 30:  # Keep 30 days only
        oldest = sorted(logs.keys())[0]
        del logs[oldest]
    save_json("logs", logs)

def get_trending(n=10):
    data = load_json("searches")
    return sorted(data.items(), key=lambda x: x[1], reverse=True)[:n]

def is_banned(user_id):
    return str(user_id) in load_json("banned")


# ═══════════════════════════════════════════════════════════════════
#                  PHASE 3 — ANIMATIONS (Upgraded)
# ═══════════════════════════════════════════════════════════════════

# Typewriter effect
async def typewriter(msg, text, delay=0.05):
    current = ""
    for char in text:
        current += char
        try:
            await msg.edit_text(current)
            await asyncio.sleep(delay)
        except: pass

# Progress bar builder
def progress_bar(current, total, length=10):
    filled = int(length * current / total)
    bar    = "█" * filled + "·" * (length - filled)
    pct    = int(100 * current / total)
    return f"[{bar}] {pct}%"

# Animated progress search
async def animate_search(msg):
    steps = [
        (1,  6, "🎬 Searching"),
        (2,  6, "🎬 Fetching"),
        (3,  6, "🎬 Loading"),
        (4,  6, "🎬 Almost"),
        (5,  6, "🎬 Done"),
        (6,  6, "✅ Found"),
    ]
    for cur, total, label in steps:
        bar = progress_bar(cur, total)
        try:
            await msg.edit_text(f"{label}...\n{bar}")
            await asyncio.sleep(0.35)
        except: pass

async def animate_generic(msg, frames, delay=0.45):
    for i, frame in enumerate(frames):
        bar = progress_bar(i + 1, len(frames))
        try:
            await msg.edit_text(f"{frame}\n{bar}")
            await asyncio.sleep(delay)
        except: pass

FRAMES = {
    "server":    ["🌐 Connecting", "🌐 Loading", "⚡ Almost", "✅ Ready"],
    "back":      ["🔄 Returning", "🔄 Loading", "✅ Back"],
    "save":      ["💾 Saving", "💾 Writing", "✅ Saved"],
    "maint_on":  ["🔧 Activating", "🔧 Processing", "🚨 Maintenance ON"],
    "maint_off": ["🟢 Restoring", "🟢 Processing", "✅ Bot LIVE"],
    "broadcast": ["📢 Sending", "📢 Delivering", "✅ Done"],
    "ai":        ["🤖 Thinking", "🤖 Processing", "✨ Ready"],
    "similar":   ["🔍 Analyzing", "🔍 Matching", "🎬 Found"],
    "quiz":      ["🎯 Preparing", "🎯 Loading", "✅ Ready"],
    "daily":     ["🎬 Picking", "🎬 Loading", "✅ Today's Pick"],
}


# ═══════════════════════════════════════════════════════════════════
#                        HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════
def is_admin(uid):    return uid == ADMIN_ID
def is_maintenance(): return load_json("maintenance", {"active": False}).get("active", False)

def get_badge(points):
    if points >= 1000: return "💎 Diamond"
    if points >= 500:  return "🥇 Gold"
    if points >= 200:  return "🥈 Silver"
    if points >= 100:  return "🥉 Bronze"
    return "🌱 Newbie"

def build_star_bar(rating):
    try:
        s = int(float(rating))
        return "⭐" * s + "☆" * (10 - s)
    except: return "☆☆☆☆☆☆☆☆☆☆"

def get_omdb(title, by_id=False):
    try:
        param = "i" if by_id else "t"
        r = requests.get(
            f"http://www.omdbapi.com/?{param}={title}&apikey={OMDB_API}&plot=full",
            timeout=5
        )
        return r.json()
    except: return None

def get_omdb_search(query):
    """Search multiple results"""
    try:
        r = requests.get(
            f"http://www.omdbapi.com/?s={query}&apikey={OMDB_API}",
            timeout=5
        )
        return r.json().get("Search", [])[:5]
    except: return []

def get_tmdb_similar(title):
    if not TMDB_API: return []
    try:
        r  = requests.get(f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API}&query={title}", timeout=5)
        rs = r.json().get("results", [])
        if not rs: return []
        mid = rs[0]["id"]
        r2  = requests.get(f"https://api.themoviedb.org/3/movie/{mid}/similar?api_key={TMDB_API}", timeout=5)
        return [(m["title"], round(m["vote_average"], 1)) for m in r2.json().get("results", [])[:6]]
    except: return []

def get_tmdb_trending():
    if not TMDB_API: return []
    try:
        r = requests.get(f"https://api.themoviedb.org/3/trending/movie/week?api_key={TMDB_API}", timeout=5)
        return [(m["title"], round(m["vote_average"], 1)) for m in r.json().get("results", [])[:10]]
    except: return []

def get_tmdb_upcoming():
    if not TMDB_API: return []
    try:
        r = requests.get(f"https://api.themoviedb.org/3/movie/upcoming?api_key={TMDB_API}", timeout=5)
        results = []
        for m in r.json().get("results", [])[:5]:
            rd = m.get("release_date", "")
            if rd:
                try:
                    rdate = datetime.strptime(rd, "%Y-%m-%d")
                    days  = (rdate - datetime.now()).days
                    if days > 0:
                        results.append((m["title"], rd, days))
                except: pass
        return results
    except: return []

def get_rt_score(title):
    """Rotten Tomatoes score from OMDB Ratings field"""
    data = get_omdb(title)
    if not data: return "N/A"
    for r in data.get("Ratings", []):
        if "Rotten Tomatoes" in r.get("Source", ""):
            return r["Value"]
    return "N/A"

async def ai_ask(prompt):
    if not ai_model: return None
    try:
        r = ai_model.generate_content(prompt)
        return r.text
    except: return None

async def ai_recommend(query):
    return await ai_ask(
        f"You are a movie expert. {query}\n"
        "Give exactly 5 recommendations.\n"
        "Format: 🎬 Title (Year) — One line reason\n"
        "Be concise. Reply in same language as query."
    )

async def ai_plot_search(plot_desc):
    return await ai_ask(
        f"A user describes a movie plot: '{plot_desc}'\n"
        "Identify the most likely movie(s) this refers to.\n"
        "Give top 3 guesses.\n"
        "Format: 🎬 Title (Year) — Why it matches\n"
        "Be concise."
    )

async def get_subtitle_link(title, year):
    search = title.replace(" ", "+")
    return f"https://subscene.com/subtitles/searchbytitle?query={search}"

def get_director_movies(director):
    if not TMDB_API: return []
    try:
        r  = requests.get(f"https://api.themoviedb.org/3/search/person?api_key={TMDB_API}&query={director}", timeout=5)
        rs = r.json().get("results", [])
        if not rs: return []
        pid = rs[0]["id"]
        r2  = requests.get(f"https://api.themoviedb.org/3/person/{pid}/movie_credits?api_key={TMDB_API}", timeout=5)
        crew = r2.json().get("crew", [])
        directed = [m for m in crew if m.get("job") == "Director"]
        directed.sort(key=lambda x: x.get("vote_average", 0), reverse=True)
        return [(m["title"], round(m.get("vote_average", 0), 1)) for m in directed[:5]]
    except: return []


# ═══════════════════════════════════════════════════════════════════
#                    CONVERSATION STATES
# ═══════════════════════════════════════════════════════════════════
(
    W_URL, W_NAME, W_MAINT_MSG, W_BROADCAST,
    W_AI_QUERY, W_PLOT_SEARCH, W_LANG_FILTER,
    W_ALERT_MOVIE, W_BAN_USER, W_QUIZ,
) = range(10)


# ═══════════════════════════════════════════════════════════════════
#                         /start
# ═══════════════════════════════════════════════════════════════════
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # Refer link check
    ref_id = None
    if context.args:
        try: ref_id = int(context.args[0])
        except: pass

    register_user(user, ref_id)

    if is_banned(user.id):
        await update.message.reply_text("🚫 You are banned.")
        return

    if is_maintenance() and not is_admin(user.id):
        maint = load_json("maintenance", {"active": False, "message": "🔧 Maintenance..."})
        await update.message.reply_text(
            f"🚧 *CineBot — Maintenance*\n\n{maint.get('message', '')}",
            parse_mode="Markdown"
        )
        return

    users   = load_json("users")
    uid     = str(user.id)
    udata   = users.get(uid, {})
    points  = udata.get("points",   0)
    refs    = udata.get("refs",     0)
    badge   = get_badge(points)
    admin_n = "\n\n👑 *Admin:* /admin" if is_admin(user.id) else ""

    await update.message.reply_text(
        f"🎬 *CineBot v2 — Welcome, {user.first_name}!*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{badge}  •  ⭐ `{points}` pts  •  👥 `{refs}` refers\n\n"
        f"📋 *Commands:*\n"
        f"🔎 Type movie name to search\n"
        f"🤖 /suggest — AI Recommendations\n"
        f"🔍 /plotsearch — Search by plot\n"
        f"🔥 /trending — This week's trending\n"
        f"📅 /upcoming — Coming soon movies\n"
        f"🎲 /random — Random movie\n"
        f"🎯 /daily — Today's featured movie\n"
        f"❤️ /watchlist — My saved movies\n"
        f"🔔 /alerts — Movie release alerts\n"
        f"🎮 /quiz — Movie trivia game\n"
        f"👥 /refer — Refer & earn points\n"
        f"🌐 /lang — Language preference\n"
        f"📊 /mystats — My stats\n"
        f"ℹ️ /help — Help"
        f"{admin_n}",
        parse_mode="Markdown"
    )


# ═══════════════════════════════════════════════════════════════════
#                   PHASE 1 — MOVIE CARD (Full)
# ═══════════════════════════════════════════════════════════════════
async def _send_movie_card(update_or_msg, context, data, is_msg=True):
    title    = data.get("Title",      "N/A")
    year     = data.get("Year",       "N/A")
    rating   = data.get("imdbRating", "N/A")
    genre    = data.get("Genre",      "N/A")
    runtime  = data.get("Runtime",    "N/A")
    director = data.get("Director",   "N/A")
    actors   = data.get("Actors",     "N/A")
    plot     = data.get("Plot",       "N/A")
    language = data.get("Language",   "N/A")
    poster   = data.get("Poster",     "N/A")
    votes    = data.get("imdbVotes",  "N/A")
    awards   = data.get("Awards",     "N/A")
    rated    = data.get("Rated",      "N/A")
    boxoff   = data.get("BoxOffice",  "N/A")

    # Rotten Tomatoes from Ratings array
    rt_score = "N/A"
    for r in data.get("Ratings", []):
        if "Rotten Tomatoes" in r.get("Source", ""):
            rt_score = r["Value"]

    if poster == "N/A" or not poster:
        poster = "https://i.imgur.com/8qH7Z8L.jpeg"

    star_bar = build_star_bar(rating)
    search   = title.replace(" ", "+")
    servers  = load_servers()
    urls     = [servers[f"s{i}"]["url"] + search for i in range(1, 7)]
    names    = [servers[f"s{i}"]["name"]          for i in range(1, 7)]
    trailer  = f"https://www.youtube.com/results?search_query={search}+trailer"
    subs_url = f"https://subscene.com/subtitles/searchbytitle?query={search}"

    uid = str(update_or_msg.effective_user.id if is_msg else update_or_msg.from_user.id)
    log_search(title, uid)

    caption = (
        f"🎬 *{title}* `({year})`\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{star_bar}\n"
        f"⭐ *IMDb:* `{rating}/10`  🍅 *RT:* `{rt_score}`\n"
        f"🗳 *Votes:* `{votes}`  •  🔞 `{rated}`\n\n"
        f"🎭 *Genre:* `{genre}`\n"
        f"⏱ *Runtime:* `{runtime}`\n"
        f"🌍 *Language:* `{language}`\n"
        f"🎥 *Director:* `{director}`\n"
        f"👥 *Cast:* `{actors}`\n"
        f"💰 *Box Office:* `{boxoff}`\n"
        f"🏆 *Awards:* `{awards}`\n\n"
        f"📖 *Plot:*\n_{plot}_\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ 6 Servers  •  🦁 Brave = No Ads"
    )

    reply_fn = update_or_msg.message.reply_photo if is_msg else update_or_msg.message.reply_photo

    sent = await reply_fn(
        photo=poster,
        caption=caption,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎬 Trailer",   url=trailer),
             InlineKeyboardButton("📝 Subtitles", url=subs_url)],
            [InlineKeyboardButton("❤️ Watchlist", callback_data=f"wl_save|{title}|{year}|{rating}"),
             InlineKeyboardButton("🔔 Alert",     callback_data=f"alert_add|{title}|{year}")],
            [InlineKeyboardButton(f"⬇️ {names[0]}", url=urls[0])],
            [InlineKeyboardButton("🌐 All 6 Servers",    callback_data="s_tmp"),
             InlineKeyboardButton("🎯 Similar",          callback_data="sim_tmp")],
            [InlineKeyboardButton("🎥 Director's Top 5", callback_data=f"dir_{director.replace(' ', '_')}")]
        ])
    )

    msg_id = str(sent.message_id)
    context.user_data[msg_id] = {
        "servers": urls, "names": names,
        "trailer": trailer, "title": title,
        "year": year, "rating": rating,
        "director": director,
    }

    await sent.edit_reply_markup(reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 Trailer",   url=trailer),
         InlineKeyboardButton("📝 Subtitles", url=subs_url)],
        [InlineKeyboardButton("❤️ Watchlist", callback_data=f"wl_save|{title}|{year}|{rating}"),
         InlineKeyboardButton("🔔 Alert",     callback_data=f"alert_add|{title}|{year}")],
        [InlineKeyboardButton(f"⬇️ {names[0]}", url=urls[0])],
        [InlineKeyboardButton("🌐 All 6 Servers",    callback_data=f"srv_{msg_id}"),
         InlineKeyboardButton("🎯 Similar",          callback_data=f"sim_{msg_id}")],
        [InlineKeyboardButton("🎥 Director's Top 5", callback_data=f"dir_{director.replace(' ', '_')}")]
    ]))


# ═══════════════════════════════════════════════════════════════════
#                       MOVIE SEARCH
# ═══════════════════════════════════════════════════════════════════
async def movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_banned(user.id):
        await update.message.reply_text("🚫 You are banned.")
        return
    register_user(user)

    if is_maintenance() and not is_admin(user.id):
        maint = load_json("maintenance", {"active": False, "message": "Maintenance..."})
        await update.message.reply_text(f"🚧 *Maintenance*\n\n{maint.get('message', '')}", parse_mode="Markdown")
        return

    name   = update.message.text.strip()
    loader = await update.message.reply_text("🎬 Searching...\n" + progress_bar(0, 6))
    await animate_search(loader)

    data = get_omdb(name)
    if not data:
        await loader.edit_text("⚠️ Server busy, try again.")
        return
    if data.get("Response") == "False":
        await loader.edit_text(
            "❌ *Movie not found!*\n\n"
            "_Try /plotsearch to search by plot description_\n"
            "_Try /suggest for AI recommendations_",
            parse_mode="Markdown"
        )
        return

    await loader.delete()
    await _send_movie_card(update, context, data)


# ═══════════════════════════════════════════════════════════════════
#                 PHASE 1 — DIRECTOR TOP 5
# ═══════════════════════════════════════════════════════════════════
async def director_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query    = update.callback_query
    await query.answer("🎥 Loading director films...")
    director = query.data.replace("dir_", "").replace("_", " ")

    loader = await query.message.reply_text("🎥 Loading...\n" + progress_bar(0, 3))
    await animate_generic(loader, FRAMES["similar"])
    await loader.delete()

    movies = get_director_movies(director)

    if movies:
        text = f"🎥 *Top 5 by {director}:*\n━━━━━━━━━━━━━━━━━━\n\n"
        medals = ["🥇", "🥈", "🥉", "🏅", "🎖"]
        for i, (t, r) in enumerate(movies):
            text += f"{medals[i]} *{t}* — ⭐`{r}`\n"
        text += "\n_Type movie name to search_ 🔎"
    else:
        text = f"🎥 *{director}* ki movies:\n\nSearch manually on bot."

    await query.message.reply_text(text, parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════════
#             PHASE 1 — UPCOMING MOVIES + COUNTDOWN
# ═══════════════════════════════════════════════════════════════════
async def upcoming_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_maintenance() and not is_admin(update.effective_user.id):
        await update.message.reply_text("🚧 Maintenance mode.")
        return

    loader = await update.message.reply_text("📅 Loading...\n" + progress_bar(1, 3))
    await asyncio.sleep(0.5)
    movies = get_tmdb_upcoming()
    await loader.delete()

    if movies:
        text = "📅 *Upcoming Movies — Countdown*\n━━━━━━━━━━━━━━━━━━\n\n"
        for title, release, days in movies:
            bar = "🟩" * min(10, max(1, 10 - days // 10)) + "⬜" * max(0, 10 - min(10, max(1, 10 - days // 10)))
            text += f"🎬 *{title}*\n"
            text += f"📅 `{release}` — ⏳ `{days} days`\n"
            text += f"{bar}\n\n"
    else:
        text = "📅 *Upcoming Movies*\n\nTMDB API add karo for live data!\n\n_Set TMDB_API in .env_"

    await update.message.reply_text(text, parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════════
#              PHASE 2 — AI SUGGEST
# ═══════════════════════════════════════════════════════════════════
async def suggest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_maintenance() and not is_admin(update.effective_user.id):
        await update.message.reply_text("🚧 Maintenance.")
        return
    await update.message.reply_text(
        "🤖 *AI Movie Suggest*\n━━━━━━━━━━━━━━━━━━\n\n"
        "📝 *Batao kya chahiye:*\n\n"
        "Examples:\n"
        "_• Mujhe action movie chahiye_\n"
        "_• RRR jaisi movie_\n"
        "_• Best 2023 thriller_\n"
        "_• Sad romantic Hindi movie_\n\n"
        "/cancel",
        parse_mode="Markdown"
    )
    return W_AI_QUERY

async def suggest_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.message.text.strip()
    loader = await update.message.reply_text("🤖 Thinking...\n" + progress_bar(0, 4))
    await animate_generic(loader, FRAMES["ai"])
    result = await ai_recommend(query)
    await loader.delete()

    if result:
        await update.message.reply_text(
            f"🤖 *AI Recommendations*\n━━━━━━━━━━━━━━━━━━\n\n{result}\n\n"
            "_Movie naam type karo to search_ 🔎",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "🎬 *Top Picks:*\n\n"
            "🎬 RRR (2022)\n🎬 KGF 2 (2022)\n🎬 Pushpa (2021)\n"
            "🎬 Pathaan (2023)\n🎬 Animal (2023)\n\n"
            "_Type naam to search_ 🔎",
            parse_mode="Markdown"
        )
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════════════
#           PHASE 2 — PLOT SEARCH (Describe → Find Movie)
# ═══════════════════════════════════════════════════════════════════
async def plotsearch_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔍 *Search by Plot*\n━━━━━━━━━━━━━━━━━━\n\n"
        "📝 *Movie ka plot/scene describe karo:*\n\n"
        "Examples:\n"
        "_• Wo movie jisme train crash hoti hai_\n"
        "_• Ek ladka matrix world mein jaata hai_\n"
        "_• Two brothers fight for gold mine_\n\n"
        "/cancel",
        parse_mode="Markdown"
    )
    return W_PLOT_SEARCH

async def plotsearch_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    desc   = update.message.text.strip()
    loader = await update.message.reply_text("🔍 Searching...\n" + progress_bar(0, 4))
    await animate_generic(loader, FRAMES["ai"])
    result = await ai_plot_search(desc)
    await loader.delete()

    if result:
        await update.message.reply_text(
            f"🔍 *Plot Match Results:*\n━━━━━━━━━━━━━━━━━━\n\n{result}\n\n"
            "_Movie naam type karo to search_ 🔎",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "❌ Match nahi mila.\n\nAI API add karo for best results.",
            parse_mode="Markdown"
        )
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════════════
#          PHASE 2 — LANGUAGE FILTER
# ═══════════════════════════════════════════════════════════════════
async def lang_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🇮🇳 Hindi",   callback_data="setlang_Hindi"),
         InlineKeyboardButton("🇺🇸 English", callback_data="setlang_English")],
        [InlineKeyboardButton("🎬 Tamil",    callback_data="setlang_Tamil"),
         InlineKeyboardButton("🎬 Telugu",   callback_data="setlang_Telugu")],
        [InlineKeyboardButton("🎬 Punjabi",  callback_data="setlang_Punjabi"),
         InlineKeyboardButton("🌍 Any",      callback_data="setlang_Any")],
    ]
    await update.message.reply_text(
        "🌐 *Language Preference*\n\nDefault language filter select karo 👇",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def setlang_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang  = query.data.replace("setlang_", "")
    uid   = str(query.from_user.id)
    users = load_json("users")
    if uid in users:
        users[uid]["lang"] = lang
        save_json("users", users)
    await query.message.edit_text(
        f"✅ *Language set to: {lang}*\n\nAb tumhari searches {lang} prefer karengi.",
        parse_mode="Markdown"
    )


# ═══════════════════════════════════════════════════════════════════
#          PHASE 2 — SIMILAR MOVIES
# ═══════════════════════════════════════════════════════════════════
async def similar_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query      = update.callback_query
    await query.answer("🎯 Finding...")
    msg_id     = query.data.split("_", 1)[1]
    movie_data = context.user_data.get(msg_id)

    if not movie_data:
        await query.message.reply_text("⚠️ Session expired. Search again.")
        return

    loader = await query.message.reply_text("🎯 Loading...\n" + progress_bar(0, 3))
    await animate_generic(loader, FRAMES["similar"])
    await loader.delete()

    title   = movie_data["title"]
    similar = get_tmdb_similar(title)

    if similar:
        text = f"🎯 *Similar to {title}:*\n━━━━━━━━━━━━━━━━━━\n\n"
        medals = ["🥇", "🥈", "🥉", "🏅", "🎖", "🌟"]
        for i, (t, r) in enumerate(similar):
            text += f"{medals[i]} *{t}* ⭐`{r}`\n"
        text += "\n_Type naam to search_ 🔎"
    elif ai_model:
        result = await ai_recommend(f"Movies similar to {title}")
        text = f"🎯 *AI Similar to {title}:*\n━━━━━━━━━━━━━━━━━━\n\n{result or 'Not found'}"
    else:
        text = f"_TMDB/Gemini API add karo for similar movies_"

    await query.message.reply_text(text, parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════════
#            PHASE 3 — TRENDING
# ═══════════════════════════════════════════════════════════════════
async def trending_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_maintenance() and not is_admin(update.effective_user.id):
        await update.message.reply_text("🚧 Maintenance.")
        return

    loader = await update.message.reply_text("🔥 Loading...\n" + progress_bar(1, 3))
    await asyncio.sleep(0.8)
    tmdb_t  = get_tmdb_trending()
    bot_t   = get_trending(5)
    await loader.delete()

    text = "🔥 *Trending Movies*\n━━━━━━━━━━━━━━━━━━\n\n"
    if tmdb_t:
        text += "🌍 *Worldwide This Week:*\n"
        medals = ["🥇","🥈","🥉","🏅","🎖","⭐","🌟","💫","✨","🎬"]
        for i, (t, r) in enumerate(tmdb_t):
            text += f"{medals[i]} `{t}` ⭐{r}\n"
        text += "\n"
    if bot_t:
        text += "📊 *Most Searched Here:*\n"
        for i, (t, c) in enumerate(bot_t, 1):
            text += f"`{i}.` {t} — `{c}x`\n"
    text += "\n_Type naam to search_ 🔎"

    await update.message.reply_text(text, parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════════
#            PHASE 3 — RANDOM MOVIE
# ═══════════════════════════════════════════════════════════════════
RANDOM_POOL = [
    "Inception","Interstellar","The Dark Knight","Avengers Endgame",
    "RRR","KGF","Pushpa","Pathaan","Animal","Jawan","Dune",
    "Oppenheimer","Top Gun Maverick","Avatar","Spider-Man No Way Home",
    "Bahubali","Dangal","3 Idiots","PK","Andhadhun","Tumbbad",
    "Article 15","Uri","Shershaah","Brahmastra","Vikram"
]

async def random_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_maintenance() and not is_admin(update.effective_user.id):
        await update.message.reply_text("🚧 Maintenance.")
        return

    loader = await update.message.reply_text("🎲 Picking random...\n" + progress_bar(3, 6))
    await asyncio.sleep(1.2)

    pick = random.choice(RANDOM_POOL)
    data = get_omdb(pick)
    await loader.delete()

    if data and data.get("Response") == "True":
        await _send_movie_card(update, context, data)
    else:
        await update.message.reply_text(
            f"🎲 *Random Pick:* _{pick}_\n\nType to search! 🔎",
            parse_mode="Markdown"
        )


# ═══════════════════════════════════════════════════════════════════
#          PHASE 3 — DAILY FEATURED MOVIE
# ═══════════════════════════════════════════════════════════════════
DAILY_MOVIES = [
    "Inception", "The Dark Knight", "Interstellar", "RRR", "KGF",
    "Bahubali 2", "3 Idiots", "Dangal", "Andhadhun", "Tumbbad",
    "Dune", "Oppenheimer", "Pathaan", "Animal", "Jawan",
]

async def daily_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_maintenance() and not is_admin(update.effective_user.id):
        await update.message.reply_text("🚧 Maintenance.")
        return

    today = str(date.today())
    daily = load_json("daily")

    loader = await update.message.reply_text("🎬 Loading...\n" + progress_bar(0, 3))
    await animate_generic(loader, FRAMES["daily"])

    # Same movie all day for everyone
    if daily.get("date") != today:
        pick = DAILY_MOVIES[hash(today) % len(DAILY_MOVIES)]
        daily = {"date": today, "movie": pick}
        save_json("daily", daily)
    else:
        pick = daily["movie"]

    data = get_omdb(pick)
    await loader.delete()

    if data and data.get("Response") == "True":
        await update.message.reply_text(
            f"🎯 *Today's Featured Movie:*\n📅 `{today}`",
            parse_mode="Markdown"
        )
        await _send_movie_card(update, context, data)
    else:
        await update.message.reply_text(f"🎬 *Today's Pick:* _{pick}_", parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════════
#            PHASE 5 — WATCHLIST
# ═══════════════════════════════════════════════════════════════════
async def watchlist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = str(update.effective_user.id)
    data = load_json("watchlist")
    wl   = data.get(uid, [])

    if not wl:
        await update.message.reply_text(
            "❤️ *Watchlist Empty!*\n\nMovie search karo aur ❤️ tap karo.",
            parse_mode="Markdown"
        )
        return

    text = f"❤️ *Watchlist* — `{len(wl)} movies`\n━━━━━━━━━━━━━━━━━━\n\n"
    for i, m in enumerate(wl, 1):
        text += f"`{i}.` 🎬 *{m['title']}* `({m['year']})` ⭐`{m['rating']}`\n"
    text += "\n_Search karo movie naam type karke_ 🔎"

    await update.message.reply_text(
        text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🗑 Clear All", callback_data="wl_clear")]
        ])
    )

async def wl_save_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    parts  = query.data.split("|")
    title, year, rating = parts[1], parts[2], parts[3]
    uid    = str(query.from_user.id)
    data   = load_json("watchlist")
    if uid not in data: data[uid] = []
    if any(m["title"] == title for m in data[uid]):
        await query.answer("⚠️ Already saved!", show_alert=True)
        return
    data[uid].append({"title": title, "year": year, "rating": rating, "saved": datetime.now().strftime("%d %b %Y")})
    save_json("watchlist", data)
    await query.answer(f"❤️ '{title}' saved!", show_alert=True)

async def wl_clear_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid   = str(query.from_user.id)
    data  = load_json("watchlist")
    data[uid] = []
    save_json("watchlist", data)
    await query.message.edit_text("🗑 *Watchlist cleared!*", parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════════
#           PHASE 5 — MOVIE ALERTS
# ═══════════════════════════════════════════════════════════════════
async def alerts_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid   = str(update.effective_user.id)
    data  = load_json("alerts")
    my_al = data.get(uid, [])

    text = "🔔 *Movie Alerts*\n━━━━━━━━━━━━━━━━━━\n\n"
    if my_al:
        text += "*Active Alerts:*\n"
        for m in my_al:
            text += f"• 🎬 {m['title']} ({m['year']})\n"
        text += "\n"
    text += "_Jab movie available hogi, notify karunga!_\n\n"
    text += "Movie card pe 🔔 Alert button tap karo."

    await update.message.reply_text(text, parse_mode="Markdown")

async def alert_add_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    parts  = query.data.split("|")
    title, year = parts[1], parts[2]
    uid    = str(query.from_user.id)
    data   = load_json("alerts")
    if uid not in data: data[uid] = []
    if any(m["title"] == title for m in data[uid]):
        await query.answer("⚠️ Alert already set!", show_alert=True)
        return
    data[uid].append({"title": title, "year": year})
    save_json("alerts", data)
    await query.answer(f"🔔 Alert set for '{title}'!", show_alert=True)


# ═══════════════════════════════════════════════════════════════════
#            PHASE 5 — MYSTATS
# ═══════════════════════════════════════════════════════════════════
async def mystats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid   = str(update.effective_user.id)
    users = load_json("users")
    udata = users.get(uid, {})
    wl    = load_json("watchlist").get(uid, [])
    pts   = udata.get("points",   0)
    srch  = udata.get("searches", 0)
    refs  = udata.get("refs",     0)
    badge = get_badge(pts)

    next_badge = ""
    if pts < 100:   next_badge = f"🥉 Bronze at 100 pts — need `{100-pts}` more"
    elif pts < 200: next_badge = f"🥈 Silver at 200 pts — need `{200-pts}` more"
    elif pts < 500: next_badge = f"🥇 Gold at 500 pts — need `{500-pts}` more"
    elif pts < 1000:next_badge = f"💎 Diamond at 1000 pts — need `{1000-pts}` more"
    else:           next_badge = "💎 Max Badge Achieved!"

    await update.message.reply_text(
        f"📊 *My Stats*\n━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 *{update.effective_user.full_name}*\n"
        f"🏆 *Badge:* {badge}\n"
        f"⭐ *Points:* `{pts}`\n"
        f"🔎 *Searches:* `{srch}`\n"
        f"❤️ *Watchlist:* `{len(wl)}`\n"
        f"👥 *Refers:* `{refs}`\n\n"
        f"📈 *Next:* {next_badge}\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"_Har search = +10 pts | Refer = +50 pts_ 🎯",
        parse_mode="Markdown"
    )


# ═══════════════════════════════════════════════════════════════════
#           PHASE 6 — REFER & EARN
# ═══════════════════════════════════════════════════════════════════
async def refer_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user  = update.effective_user
    uid   = str(user.id)
    users = load_json("users")
    refs  = users.get(uid, {}).get("refs", 0)
    pts   = users.get(uid, {}).get("points", 0)

    bot_info = await context.bot.get_me()
    link     = f"https://t.me/{bot_info.username}?start={user.id}"

    await update.message.reply_text(
        f"👥 *Refer & Earn*\n━━━━━━━━━━━━━━━━━━\n\n"
        f"*Your Refer Link:*\n`{link}`\n\n"
        f"📊 *Stats:*\n"
        f"👥 Referred: `{refs}` users\n"
        f"⭐ Points: `{pts}`\n\n"
        f"💰 *Rewards:*\n"
        f"• Har refer = +50 points\n"
        f"• 10 refers = 🥇 Gold Badge\n\n"
        f"_Share karo aur points kamao!_ 🚀",
        parse_mode="Markdown"
    )


# ═══════════════════════════════════════════════════════════════════
#           PHASE 6 — MOVIE QUIZ
# ═══════════════════════════════════════════════════════════════════
QUIZ_QUESTIONS = [
    {"q": "🎬 Is movie mein 'Inception' ka director kaun hai?",
     "opts": ["Christopher Nolan", "Steven Spielberg", "James Cameron", "Ridley Scott"], "ans": 0},
    {"q": "🎬 'RRR' movie kab release hui?",
     "opts": ["2021", "2022", "2023", "2020"], "ans": 1},
    {"q": "🎬 'Bahubali' ka villain kaun hai?",
     "opts": ["Bhallaladeva", "Kattappa", "Bijjaladeva", "Inkoshi"], "ans": 0},
    {"q": "🎬 '3 Idiots' mein Rancho ka asli naam kya hai?",
     "opts": ["Farhan", "Raju", "Phunsukh Wangdu", "Virus"], "ans": 2},
    {"q": "🎬 'KGF Chapter 2' mein villain kaun hai?",
     "opts": ["Rocky", "Adheera", "Garuda", "Andrews"], "ans": 1},
    {"q": "🎬 'Dangal' kis par based hai?",
     "opts": ["Saina Nehwal", "Mahavir Singh Phogat", "MS Dhoni", "Milkha Singh"], "ans": 1},
    {"q": "🎬 'Pushpa' main character ka poora naam kya hai?",
     "opts": ["Pushpa Raj", "Pushpa Kumar", "Pushpa Vikram", "Pushpa Singh"], "ans": 0},
    {"q": "🎬 'Tumbbad' konse genre ki movie hai?",
     "opts": ["Action", "Comedy", "Horror/Fantasy", "Romance"], "ans": 2},
    {"q": "🎬 'Andhadhun' mein main actor kaun hai?",
     "opts": ["Ayushmann Khurrana", "Rajkummar Rao", "Vicky Kaushal", "Irrfan Khan"], "ans": 0},
    {"q": "🎬 'Pathaan' mein Shah Rukh Khan ka character naam kya hai?",
     "opts": ["Tiger", "Pathaan", "Kabir", "Arjun"], "ans": 1},
]

async def quiz_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_maintenance() and not is_admin(update.effective_user.id):
        await update.message.reply_text("🚧 Maintenance.")
        return

    loader = await update.message.reply_text("🎯 Loading quiz...\n" + progress_bar(0, 3))
    await animate_generic(loader, FRAMES["quiz"])
    await loader.delete()

    q    = random.choice(QUIZ_QUESTIONS)
    context.user_data["quiz_ans"] = q["ans"]
    context.user_data["quiz_q"]   = q["q"]

    keyboard = [
        [InlineKeyboardButton(f"{['A','B','C','D'][i]}. {opt}", callback_data=f"quiz_ans_{i}")]
        for i, opt in enumerate(q["opts"])
    ]

    await update.message.reply_text(
        f"🎮 *Movie Quiz!*\n━━━━━━━━━━━━━━━━━━\n\n"
        f"{q['q']}\n\n"
        f"_Sahi jawab = +20 points_ ⭐",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def quiz_answer_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query    = update.callback_query
    await query.answer()
    ans_idx  = int(query.data.replace("quiz_ans_", ""))
    correct  = context.user_data.get("quiz_ans", -1)
    uid      = str(query.from_user.id)

    if ans_idx == correct:
        # Give points
        users = load_json("users")
        if uid in users:
            users[uid]["points"] = users[uid].get("points", 0) + 20
            save_json("users", users)
        await query.message.edit_text(
            f"✅ *Sahi Jawab!* +20 points! 🎉\n\n"
            f"_{context.user_data.get('quiz_q', '')}_\n\n"
            f"_/quiz — Ek aur question_ 🎯",
            parse_mode="Markdown"
        )
    else:
        q_text   = context.user_data.get("quiz_q", "")
        opts_key = next((q for q in QUIZ_QUESTIONS if q["q"] == q_text), None)
        correct_text = ""
        if opts_key:
            correct_text = opts_key["opts"][correct]

        await query.message.edit_text(
            f"❌ *Galat Jawab!*\n\n"
            f"✅ Sahi jawab: *{correct_text}*\n\n"
            f"_/quiz — Try again_ 🎯",
            parse_mode="Markdown"
        )


# ═══════════════════════════════════════════════════════════════════
#              ALL 6 SERVERS CALLBACK
# ═══════════════════════════════════════════════════════════════════
async def servers_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query      = update.callback_query
    await query.answer("🌐 Loading...")
    msg_id     = query.data.split("_", 1)[1]
    movie_data = context.user_data.get(msg_id)

    if not movie_data:
        await query.message.reply_text("⚠️ Session expired. Search again.")
        return

    loader = await query.message.reply_text("🌐 Loading...\n" + progress_bar(0, 4))
    await animate_generic(loader, FRAMES["server"])
    await loader.delete()

    urls   = movie_data["servers"]
    names  = movie_data["names"]
    title  = movie_data["title"]
    medals = ["🥇","🥈","🥉","🏅","🎖","🌟"]

    keyboard = [[InlineKeyboardButton(f"{medals[i]} {names[i]}", url=urls[i])] for i in range(6)]
    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data=f"bk_{msg_id}")])

    await query.message.reply_text(
        f"🌐 *6 Servers — {title}*\n━━━━━━━━━━━━━━━━━━\n"
        f"Pick any server 👇\n🦁 *Brave = No Ads*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def back_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query      = update.callback_query
    await query.answer()
    msg_id     = query.data.split("_", 1)[1]
    movie_data = context.user_data.get(msg_id)

    if not movie_data:
        await query.message.reply_text("⚠️ Expired. Search again.")
        return

    loader = await query.message.reply_text("🔄 Loading...\n" + progress_bar(0, 3))
    await animate_generic(loader, FRAMES["back"])
    await loader.delete()

    urls  = movie_data["servers"]
    names = movie_data["names"]

    await query.message.reply_text(
        f"🎬 *Back to:* _{movie_data['title']}_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎬 Trailer", url=movie_data["trailer"]),
             InlineKeyboardButton("❤️ Watchlist", callback_data=f"wl_save|{movie_data['title']}|{movie_data['year']}|{movie_data['rating']}")],
            [InlineKeyboardButton(f"⬇️ {names[0]}", url=urls[0])],
            [InlineKeyboardButton("🌐 All 6 Servers", callback_data=f"srv_{msg_id}"),
             InlineKeyboardButton("🎯 Similar",       callback_data=f"sim_{msg_id}")]
        ])
    )


# ═══════════════════════════════════════════════════════════════════
#                   ADMIN PANEL — Full
# ═══════════════════════════════════════════════════════════════════
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 *Access Denied!*", parse_mode="Markdown")
        return

    maint   = load_json("maintenance", {"active": False})
    users   = load_json("users")
    servers = load_servers()
    searches = sum(u.get("searches", 0) for u in users.values())
    status  = "🔴 ON" if maint.get("active") else "🟢 OFF"

    text  = f"👑 *Admin Panel — CineBot v2*\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    text += f"🚧 *Maintenance:* {status}\n"
    text += f"👥 *Users:* `{len(users)}`\n"
    text += f"🔎 *Searches:* `{searches}`\n\n"
    text += "📡 *Servers:*\n"
    for i in range(1, 7):
        text += f"  `{i}.` _{servers[f's{i}']['name']}_\n"

    mb = "🔴 Maintenance OFF" if maint.get("active") else "🟢 Maintenance ON"

    keyboard = [
        [InlineKeyboardButton("📡 Manage Servers",        callback_data="adm_servers")],
        [InlineKeyboardButton(mb,                          callback_data="adm_maint_toggle")],
        [InlineKeyboardButton("✏️ Maintenance Message",   callback_data="adm_maint_msg")],
        [InlineKeyboardButton("📢 Broadcast",             callback_data="adm_broadcast")],
        [InlineKeyboardButton("🚫 Ban User",              callback_data="adm_ban")],
        [InlineKeyboardButton("📋 Activity Logs",         callback_data="adm_logs")],
        [InlineKeyboardButton("📊 Full Stats",            callback_data="adm_stats")],
        [InlineKeyboardButton("🔔 Send Alerts",           callback_data="adm_send_alerts")],
    ]

    await update.message.reply_text(
        text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ── Admin: Servers ──
async def adm_servers_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    servers = load_servers()
    text = "📡 *Server Manager*\n━━━━━━━━━━━━━━━━━━\n\n"
    for i in range(1, 7):
        text += f"*{i}.* _{servers[f's{i}']['name']}_\n`{servers[f's{i}']['url']}`\n\n"
    keyboard = [
        [InlineKeyboardButton(f"✏️ S{i} — {servers[f's{i}']['name']}", callback_data=f"adm_edit_s{i}")]
        for i in range(1, 7)
    ]
    keyboard.append([InlineKeyboardButton("🔄 Reset Default", callback_data="adm_reset")])
    keyboard.append([InlineKeyboardButton("⬅️ Back",          callback_data="adm_back")])
    await query.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

# ── Admin: Edit Server ──
async def adm_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return ConversationHandler.END
    sk = query.data.replace("adm_edit_", "")
    context.user_data["editing_server"] = sk
    servers = load_servers()
    await query.message.reply_text(
        f"✏️ *Editing Server {sk[1]} — {servers[sk]['name']}*\n\n"
        f"Current:\n`{servers[sk]['url']}`\n\n📝 Naya URL bhejo:\n/cancel",
        parse_mode="Markdown"
    )
    return W_URL

async def adm_recv_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    url = update.message.text.strip()
    if not url.startswith("http"):
        await update.message.reply_text("❌ Invalid URL. Try again or /cancel")
        return W_URL
    context.user_data["new_url"] = url
    sk = context.user_data["editing_server"]
    await update.message.reply_text(
        f"✅ `{url}`\n\n📝 Display name bhejo (current: `{load_servers()[sk]['name']}`):\n/cancel",
        parse_mode="Markdown"
    )
    return W_NAME

async def adm_recv_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    global bot_servers
    name = update.message.text.strip()
    url  = context.user_data["new_url"]
    sk   = context.user_data["editing_server"]
    loader = await update.message.reply_text("💾 Saving...\n" + progress_bar(0, 3))
    await animate_generic(loader, FRAMES["save"])
    bot_servers[sk]["url"]  = url
    bot_servers[sk]["name"] = name
    save_json("servers", bot_servers)
    await loader.delete()
    await update.message.reply_text(
        f"✅ *Server {sk[1]} Updated!*\n\n🏷 `{name}`\n🔗 `{url}`\n\n/admin",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

# ── Admin: Maintenance Toggle ──
async def adm_maint_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    maint = load_json("maintenance", {"active": False, "message": "🔧 Maintenance..."})
    maint["active"] = not maint["active"]
    save_json("maintenance", maint)

    frames = FRAMES["maint_on"] if maint["active"] else FRAMES["maint_off"]
    loader = await query.message.reply_text(frames[0] + "\n" + progress_bar(0, 3))
    await animate_generic(loader, frames[1:])
    await loader.delete()

    if maint["active"]:
        users   = load_json("users")
        success = failed = 0
        b_loader = await query.message.reply_text("📢 Sending...\n" + progress_bar(0, 3))
        await animate_generic(b_loader, FRAMES["broadcast"])
        await b_loader.delete()
        for uid in users:
            if int(uid) == ADMIN_ID: continue
            try:
                await context.bot.send_message(
                    chat_id=int(uid),
                    text=f"🚧 *CineBot — Maintenance*\n\n{maint['message']}\n\n🙏 Sorry!",
                    parse_mode="Markdown"
                )
                success += 1
            except: failed += 1
            await asyncio.sleep(0.05)
        await query.message.reply_text(
            f"🚨 *Maintenance ON!*\n✅ `{success}` sent | ❌ `{failed}` failed\n\n/admin",
            parse_mode="Markdown"
        )
    else:
        await query.message.reply_text("✅ *Maintenance OFF! Bot LIVE!*\n\n/admin", parse_mode="Markdown")

# ── Admin: Edit Maint Msg ──
async def adm_maint_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return ConversationHandler.END
    maint = load_json("maintenance", {"active": False, "message": ""})
    await query.message.reply_text(
        f"✏️ Current:\n_{maint.get('message', '')}_\n\n📝 Naya message:\n/cancel",
        parse_mode="Markdown"
    )
    return W_MAINT_MSG

async def adm_recv_maint_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    maint = load_json("maintenance", {"active": False})
    maint["message"] = update.message.text.strip()
    save_json("maintenance", maint)
    loader = await update.message.reply_text("💾 Saving...\n" + progress_bar(0, 3))
    await animate_generic(loader, FRAMES["save"])
    await loader.delete()
    await update.message.reply_text(f"✅ *Updated!*\n\n_{maint['message']}_\n\n/admin", parse_mode="Markdown")
    return ConversationHandler.END

# ── Admin: Broadcast ──
async def adm_broadcast_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return ConversationHandler.END
    await query.message.reply_text("📢 *Broadcast*\n\nMessage bhejo:\n\n/cancel", parse_mode="Markdown")
    return W_BROADCAST

async def adm_do_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    msg     = update.message.text.strip()
    users   = load_json("users")
    success = failed = 0
    loader  = await update.message.reply_text("📢 Sending...\n" + progress_bar(0, 3))
    await animate_generic(loader, FRAMES["broadcast"])
    await loader.delete()
    for uid in users:
        if int(uid) == ADMIN_ID: continue
        try:
            await context.bot.send_message(
                chat_id=int(uid),
                text=f"📢 *CineBot Announcement*\n\n{msg}",
                parse_mode="Markdown"
            )
            success += 1
        except: failed += 1
        await asyncio.sleep(0.05)
    await update.message.reply_text(
        f"✅ *Done!* ✅`{success}` | ❌`{failed}`\n\n/admin",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

# ── Admin: Ban User ──
async def adm_ban_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return ConversationHandler.END
    await query.message.reply_text(
        "🚫 *Ban User*\n\nUser ID bhejo ban karne ke liye:\n\n/cancel",
        parse_mode="Markdown"
    )
    return W_BAN_USER

async def adm_do_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    try:
        ban_id = int(update.message.text.strip())
    except:
        await update.message.reply_text("❌ Invalid ID. Try again or /cancel")
        return W_BAN_USER
    banned = load_json("banned")
    banned[str(ban_id)] = datetime.now().strftime("%Y-%m-%d %H:%M")
    save_json("banned", banned)
    await update.message.reply_text(f"🚫 *User `{ban_id}` banned!*\n\n/admin", parse_mode="Markdown")
    return ConversationHandler.END

# ── Admin: Logs ──
async def adm_logs_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    logs  = load_json("logs")
    today = str(date.today())
    t_logs = logs.get(today, [])
    text  = f"📋 *Activity Logs — Today*\n━━━━━━━━━━━━━━━━━━\n\n"
    text += f"📊 Total today: `{len(t_logs)}`\n\n"
    for entry in t_logs[-10:]:
        text += f"`{entry['time']}` — {entry['movie']} by `{entry['user']}`\n"
    if not t_logs:
        text += "_No activity today_"
    await query.message.reply_text(text, parse_mode="Markdown")

# ── Admin: Stats ──
async def adm_stats_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    users    = load_json("users")
    maint    = load_json("maintenance", {"active": False})
    banned   = load_json("banned")
    trending = get_trending(5)
    searches = sum(u.get("searches", 0) for u in users.values())
    status   = "🔴 ON" if maint.get("active") else "🟢 OFF"
    text  = f"📊 *Full Stats*\n━━━━━━━━━━━━━━━━━━\n\n"
    text += f"👥 Users: `{len(users)}`\n"
    text += f"🔎 Searches: `{searches}`\n"
    text += f"🚫 Banned: `{len(banned)}`\n"
    text += f"🚧 Maintenance: {status}\n\n"
    if trending:
        text += "🔥 *Top Searched:*\n"
        for i, (t, c) in enumerate(trending, 1):
            text += f"  `{i}.` {t} — `{c}x`\n"
    await query.message.reply_text(text, parse_mode="Markdown")

# ── Admin: Send Movie Alerts ──
async def adm_send_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    alerts  = load_json("alerts")
    sent_c  = 0
    for uid, movies in alerts.items():
        for movie in movies:
            try:
                await context.bot.send_message(
                    chat_id=int(uid),
                    text=f"🔔 *Movie Alert!*\n\n🎬 *{movie['title']}* ({movie['year']}) search karo!\nType naam to get servers.",
                    parse_mode="Markdown"
                )
                sent_c += 1
            except: pass
            await asyncio.sleep(0.05)
    await query.message.reply_text(f"🔔 *Alerts sent:* `{sent_c}`\n\n/admin", parse_mode="Markdown")

# ── Admin: Reset + Back ──
async def adm_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    global bot_servers
    bot_servers = {k: v.copy() for k, v in DEFAULT_SERVERS.items()}
    save_json("servers", bot_servers)
    await query.message.reply_text("🔄 *All 6 Servers Reset!* ✅\n\n/admin", parse_mode="Markdown")

async def adm_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    maint   = load_json("maintenance", {"active": False})
    users   = load_json("users")
    servers = load_servers()
    status  = "🔴 ON" if maint.get("active") else "🟢 OFF"
    mb = "🔴 Maintenance OFF" if maint.get("active") else "🟢 Maintenance ON"
    text = (f"👑 *Admin Panel*\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🚧 Maintenance: {status}\n👥 Users: `{len(users)}`\n")
    keyboard = [
        [InlineKeyboardButton("📡 Manage Servers",        callback_data="adm_servers")],
        [InlineKeyboardButton(mb,                          callback_data="adm_maint_toggle")],
        [InlineKeyboardButton("✏️ Maintenance Message",   callback_data="adm_maint_msg")],
        [InlineKeyboardButton("📢 Broadcast",             callback_data="adm_broadcast")],
        [InlineKeyboardButton("🚫 Ban User",              callback_data="adm_ban")],
        [InlineKeyboardButton("📋 Activity Logs",         callback_data="adm_logs")],
        [InlineKeyboardButton("📊 Full Stats",            callback_data="adm_stats")],
        [InlineKeyboardButton("🔔 Send Alerts",           callback_data="adm_send_alerts")],
    ]
    await query.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))


# ── Cancel ──
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ *Cancelled.*\n\n/admin", parse_mode="Markdown")
    return ConversationHandler.END

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ *CineBot v2 — Help*\n━━━━━━━━━━━━━━━━━━\n\n"
        "🔎 Movie naam type karo to search\n"
        "🤖 /suggest — AI recommendations\n"
        "🔍 /plotsearch — Describe plot, find movie\n"
        "🔥 /trending — Weekly trending\n"
        "📅 /upcoming — Coming soon + countdown\n"
        "🎲 /random — Random movie\n"
        "🎯 /daily — Today's featured\n"
        "❤️ /watchlist — Saved movies\n"
        "🔔 /alerts — Release notifications\n"
        "🎮 /quiz — Movie trivia +20pts\n"
        "👥 /refer — Refer link +50pts each\n"
        "🌐 /lang — Language filter\n"
        "📊 /mystats — Points & badge\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🦁 Brave Browser = No Ads!",
        parse_mode="Markdown"
    )


# ═══════════════════════════════════════════════════════════════════
#                        BOT START
# ═══════════════════════════════════════════════════════════════════
application = ApplicationBuilder().token(TOKEN).build()

master_conv = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(adm_edit,             pattern="^adm_edit_s"),
        CallbackQueryHandler(adm_maint_msg,        pattern="^adm_maint_msg$"),
        CallbackQueryHandler(adm_broadcast_prompt, pattern="^adm_broadcast$"),
        CallbackQueryHandler(adm_ban_prompt,       pattern="^adm_ban$"),
        CommandHandler("suggest",    suggest_cmd),
        CommandHandler("plotsearch", plotsearch_cmd),
    ],
    states={
        W_URL:         [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_recv_url)],
        W_NAME:        [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_recv_name)],
        W_MAINT_MSG:   [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_recv_maint_msg)],
        W_BROADCAST:   [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_do_broadcast)],
        W_BAN_USER:    [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_do_ban)],
        W_AI_QUERY:    [MessageHandler(filters.TEXT & ~filters.COMMAND, suggest_receive)],
        W_PLOT_SEARCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, plotsearch_receive)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)

# Commands
application.add_handler(CommandHandler("start",      start))
application.add_handler(CommandHandler("help",       help_cmd))
application.add_handler(CommandHandler("trending",   trending_cmd))
application.add_handler(CommandHandler("random",     random_cmd))
application.add_handler(CommandHandler("daily",      daily_cmd))
application.add_handler(CommandHandler("upcoming",   upcoming_cmd))
application.add_handler(CommandHandler("watchlist",  watchlist_cmd))
application.add_handler(CommandHandler("alerts",     alerts_cmd))
application.add_handler(CommandHandler("quiz",       quiz_cmd))
application.add_handler(CommandHandler("refer",      refer_cmd))
application.add_handler(CommandHandler("lang",       lang_cmd))
application.add_handler(CommandHandler("mystats",    mystats_cmd))
application.add_handler(CommandHandler("admin",      admin_panel))
application.add_handler(master_conv)

# Admin callbacks
application.add_handler(CallbackQueryHandler(adm_servers_cb,    pattern="^adm_servers$"))
application.add_handler(CallbackQueryHandler(adm_maint_toggle,  pattern="^adm_maint_toggle$"))
application.add_handler(CallbackQueryHandler(adm_reset,         pattern="^adm_reset$"))
application.add_handler(CallbackQueryHandler(adm_stats_cb,      pattern="^adm_stats$"))
application.add_handler(CallbackQueryHandler(adm_back,          pattern="^adm_back$"))
application.add_handler(CallbackQueryHandler(adm_logs_cb,       pattern="^adm_logs$"))
application.add_handler(CallbackQueryHandler(adm_send_alerts,   pattern="^adm_send_alerts$"))

# User callbacks
application.add_handler(CallbackQueryHandler(wl_save_cb,     pattern="^wl_save\\|"))
application.add_handler(CallbackQueryHandler(wl_clear_cb,    pattern="^wl_clear$"))
application.add_handler(CallbackQueryHandler(alert_add_cb,   pattern="^alert_add\\|"))
application.add_handler(CallbackQueryHandler(similar_cb,     pattern="^sim_"))
application.add_handler(CallbackQueryHandler(servers_cb,     pattern="^srv_"))
application.add_handler(CallbackQueryHandler(back_cb,        pattern="^bk_"))
application.add_handler(CallbackQueryHandler(director_cb,    pattern="^dir_"))
application.add_handler(CallbackQueryHandler(quiz_answer_cb, pattern="^quiz_ans_"))
application.add_handler(CallbackQueryHandler(setlang_cb,     pattern="^setlang_"))

# Movie search (last)
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, movie))

print("✅ CineBot v2 Running — All Phases Active!")
application.run_polling()
