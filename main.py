# ╔══════════════════════════════════════════════════════════════════════════╗
# ║      🎬  CineBot v9 — GROQ EDITION + FULL AI ANALYSIS (v10)           ║
# ║                                                                          ║
# ║  ✅ V9 BASE:                                                            ║
# ║     • All v9 features intact                                             ║
# ║     • Groq API (llama-3.3-70b-versatile)                               ║
# ║     • movie_info module, admin panel, watchlist, alerts etc.            ║
# ║                                                                          ║
# ║  ✅ NEW — FULL AI ANALYSIS (from movie_finder_groq):                   ║
# ║     • 📝 ai_full_review   — Review + Positives/Negatives + Verdict     ║
# ║     • 🎯 ai_similar_deep  — 5 similar movies with reasons              ║
# ║     • 🎭 ai_mood_match    — Best mood/time/with whom + snack           ║
# ║     • ❓ ai_trivia_quiz   — MCQ trivia question for this movie         ║
# ║     • 🌟 ai_cast_analysis — Director + cast performance analysis       ║
# ║     • 🔥 ai_full_package  — Sab ek saath (all 5 combined)             ║
# ║                                                                          ║
# ║  ✅ NEW BUTTONS on every movie card:                                    ║
# ║     • 📝 Full Review   • 🎭 Mood Match                                 ║
# ║     • 🌟 Cast Analysis • ❓ Trivia Quiz                                ║
# ║     • 🔥 Full Package (sab ek saath)                                   ║
# ║                                                                          ║
# ║  ✅ NEW COMMANDS:                                                       ║
# ║     • /fullreview <movie>  — Detailed AI review                        ║
# ║     • /moodmatch  <movie>  — Mood match analysis                       ║
# ║     • /castinfo   <movie>  — Cast & director analysis                  ║
# ║     • /trivia     <movie>  — MCQ trivia question                       ║
# ║                                                                          ║
# ║  APIs: BOT_TOKEN, OMDB_API, TMDB_API, GROQ_API, ADMIN_ID              ║
# ╚══════════════════════════════════════════════════════════════════════════╝

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes, ConversationHandler
)
import requests, threading, json, os, asyncio, random, re, time, logging
from datetime import datetime, date
from flask import Flask
from urllib.parse import quote
from typing import Optional
import aiohttp


# ═══════════════════════════════════════════════════════════════════
#                         ENV VARIABLES
# ═══════════════════════════════════════════════════════════════════
TOKEN      = os.getenv("BOT_TOKEN")
OMDB_API   = os.getenv("OMDB_API")
TMDB_API   = os.getenv("TMDB_API",   "")
GROQ_API   = os.getenv("GROQ_API",   "")
ADMIN_ID   = int(os.getenv("ADMIN_ID", "0"))

TMDB_API_KEY = TMDB_API
OMDB_API_KEY = OMDB_API

GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"

if not TOKEN:
    raise ValueError("❌ BOT_TOKEN environment variable is not set!")
if not OMDB_API:
    raise ValueError("❌ OMDB_API environment variable is not set!")

if GROQ_API:
    print("✅ Groq API (llama-3.3-70b-versatile) loaded")
else:
    print("⚠️ GROQ_API not set — AI features disabled")


# ═══════════════════════════════════════════════════════════════════
#                       WEB SERVER (KEEP ALIVE)
# ═══════════════════════════════════════════════════════════════════
web_app = Flask(__name__)

@web_app.route("/")
def home(): return "🎬 CineBot v9 Groq + Full Analysis Running"

@web_app.route("/health")
def health(): return {"status": "ok", "version": "9.1", "ai": "groq", "analysis": "full"}

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
    "ratings":     "ratings.json",
    "history":     "history.json",
    "votes":       "votes.json",
    "admins":      "admins.json",
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
        except Exception as e:
            print(f"⚠️ load_json error [{key}]: {e} — returning default")
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
            "lang":     "Any",
            "ref_by":   ref_id,
            "refs":     0,
            "msg_ids":  [],
        }
        if ref_id:
            refs = load_json("refers")
            refs[str(ref_id)] = refs.get(str(ref_id), 0) + 1
            save_json("refers", refs)
            if str(ref_id) in users:
                users[str(ref_id)]["points"] = users[str(ref_id)].get("points", 0) + 50
                users[str(ref_id)]["refs"]   = users[str(ref_id)].get("refs", 0) + 1
        save_json("users", users)
    return users[uid]

def add_search_points(user_id):
    users = load_json("users")
    uid   = str(user_id)
    if uid in users:
        users[uid]["searches"] = users[uid].get("searches", 0) + 1
        users[uid]["points"]   = users[uid].get("points",   0) + 10
        save_json("users", users)

def get_user_lang(user_id):
    users = load_json("users")
    return users.get(str(user_id), {}).get("lang", "Any")

def log_search(title, user_id):
    data = load_json("searches")
    data[title] = data.get(title, 0) + 1
    save_json("searches", data)
    logs  = load_json("logs")
    today = str(date.today())
    if today not in logs: logs[today] = []
    logs[today].append({"user": user_id, "movie": title, "time": datetime.now().strftime("%H:%M")})
    while len(logs) > 30:
        oldest = sorted(logs.keys())[0]
        del logs[oldest]
    save_json("logs", logs)
    history = load_json("history")
    uid     = str(user_id)
    if uid not in history: history[uid] = []
    history[uid] = [h for h in history[uid] if h["movie"] != title]
    history[uid].insert(0, {"movie": title, "time": datetime.now().strftime("%d %b %H:%M")})
    history[uid] = history[uid][:20]
    save_json("history", history)

def get_trending(n=10):
    data = load_json("searches")
    return sorted(data.items(), key=lambda x: x[1], reverse=True)[:n]

def is_banned(user_id):
    return str(user_id) in load_json("banned")

def is_owner(uid):
    return uid == ADMIN_ID

def is_admin(uid):
    if uid == ADMIN_ID:
        return True
    admins = load_json("admins")
    entry  = admins.get(str(uid))
    if not entry:
        return False
    if entry.get("type") == "permanent":
        return True
    if entry.get("type") == "temporary":
        expiry = entry.get("expiry", 0)
        if datetime.now().timestamp() < expiry:
            return True
        else:
            del admins[str(uid)]
            save_json("admins", admins)
            return False
    return False

def is_maintenance(): return load_json("maintenance", {"active": False}).get("active", False)


# ═══════════════════════════════════════════════════════════════════
#                  AUTO DELETE HELPER
# ═══════════════════════════════════════════════════════════════════
async def auto_delete(msg, delay=60, user_data=None, key=None):
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except:
        pass
    if user_data is not None and key is not None:
        user_data.pop(key, None)


# ═══════════════════════════════════════════════════════════════════
#                  ANIMATIONS
# ═══════════════════════════════════════════════════════════════════
def progress_bar(current, total, length=10):
    filled = int(length * current / total)
    bar    = "█" * filled + "·" * (length - filled)
    pct    = int(100 * current / total)
    return f"[{bar}] {pct}%"

async def animate_search(msg):
    steps = [
        (1, 6, "🎬 Searching"),
        (2, 6, "🎬 Fetching"),
        (3, 6, "🎬 Loading"),
        (4, 6, "🎬 Almost"),
        (5, 6, "🎬 Done"),
        (6, 6, "✅ Found"),
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
    "server":      ["🌐 Connecting", "🌐 Loading", "⚡ Almost", "✅ Ready"],
    "back":        ["🔄 Returning", "🔄 Loading", "✅ Back"],
    "save":        ["💾 Saving", "💾 Writing", "✅ Saved"],
    "maint_on":    ["🔧 Activating", "🔧 Processing", "🚨 Maintenance ON"],
    "maint_off":   ["🟢 Restoring", "🟢 Processing", "✅ Bot LIVE"],
    "broadcast":   ["📢 Sending", "📢 Delivering", "✅ Done"],
    "ai":          ["🤖 Thinking", "🤖 Processing", "✨ Ready"],
    "similar":     ["🔍 Analyzing", "🔍 Matching", "🎬 Found"],
    "quiz":        ["🎯 Preparing", "🎯 Loading", "✅ Ready"],
    "daily":       ["🎬 Picking", "🎬 Loading", "✅ Today's Pick"],
    "review":      ["🤖 Reading", "🤖 Analyzing", "✍️ Writing", "✅ Done"],
    "compare":     ["🔍 Loading 1st", "🔍 Loading 2nd", "⚖️ Comparing", "✅ Ready"],
    "mood":        ["🎭 Reading mood", "🤖 Thinking", "🎬 Picking", "✅ Ready"],
    "fullreview":  ["📖 Reading plot", "🤖 Analyzing", "✍️ Writing review", "✅ Done"],
    "moodmatch":   ["🎭 Sensing mood", "🤖 Matching", "🍿 Perfect pick!", "✅ Ready"],
    "castanalysis":["🎬 Loading cast", "🌟 Analyzing", "✅ Done"],
    "trivia":      ["🧠 Thinking", "❓ Creating question", "✅ Ready"],
    "fullpackage": ["📖 Review", "🎯 Similar", "🎭 Mood", "🌟 Cast", "✅ All Done!"],
}


# ═══════════════════════════════════════════════════════════════════
#                        HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════
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
            f"https://www.omdbapi.com/?{param}={quote(title)}&apikey={OMDB_API}&plot=full",
            timeout=8
        )
        return r.json()
    except: return None

def get_omdb_search(query):
    try:
        r = requests.get(
            f"https://www.omdbapi.com/?s={quote(query)}&apikey={OMDB_API}",
            timeout=8
        )
        return r.json().get("Search", [])[:5]
    except: return []

def get_tmdb_similar(title):
    if not TMDB_API: return []
    try:
        r  = requests.get(f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API}&query={quote(title)}", timeout=8)
        rs = r.json().get("results", [])
        if not rs: return []
        mid = rs[0]["id"]
        r2  = requests.get(f"https://api.themoviedb.org/3/movie/{mid}/similar?api_key={TMDB_API}", timeout=8)
        return [(m["title"], round(m["vote_average"], 1)) for m in r2.json().get("results", [])[:6]]
    except: return []

def get_tmdb_trending():
    if not TMDB_API: return []
    try:
        r = requests.get(f"https://api.themoviedb.org/3/trending/movie/week?api_key={TMDB_API}", timeout=8)
        return [(m["title"], round(m["vote_average"], 1)) for m in r.json().get("results", [])[:10]]
    except: return []

def get_tmdb_upcoming():
    if not TMDB_API: return []
    try:
        r = requests.get(f"https://api.themoviedb.org/3/movie/upcoming?api_key={TMDB_API}", timeout=8)
        results = []
        for m in r.json().get("results", [])[:8]:
            rd = m.get("release_date", "")
            if rd:
                try:
                    rdate = datetime.strptime(rd, "%Y-%m-%d")
                    days  = (rdate - datetime.now()).days
                    if days >= 0:
                        results.append((m["title"], rd, days))
                except: pass
        return results
    except: return []

def get_director_movies(director):
    if not TMDB_API: return []
    try:
        r  = requests.get(f"https://api.themoviedb.org/3/search/person?api_key={TMDB_API}&query={quote(director)}", timeout=8)
        rs = r.json().get("results", [])
        if not rs: return []
        pid = rs[0]["id"]
        r2  = requests.get(f"https://api.themoviedb.org/3/person/{pid}/movie_credits?api_key={TMDB_API}", timeout=8)
        crew = r2.json().get("crew", [])
        directed = [m for m in crew if m.get("job") == "Director"]
        directed.sort(key=lambda x: x.get("vote_average", 0), reverse=True)
        return [(m["title"], round(m.get("vote_average", 0), 1)) for m in directed[:5]]
    except: return []

def get_actor_movies(actor_name):
    if not TMDB_API: return []
    try:
        r  = requests.get(f"https://api.themoviedb.org/3/search/person?api_key={TMDB_API}&query={quote(actor_name)}", timeout=8)
        rs = r.json().get("results", [])
        if not rs: return []
        pid = rs[0]["id"]
        r2  = requests.get(f"https://api.themoviedb.org/3/person/{pid}/movie_credits?api_key={TMDB_API}", timeout=8)
        cast = r2.json().get("cast", [])
        cast.sort(key=lambda x: x.get("vote_average", 0), reverse=True)
        return [(m["title"], round(m.get("vote_average", 0), 1)) for m in cast[:6]]
    except: return []


# ═══════════════════════════════════════════════════════════════════
#          GROQ AI — CORE CALLER
# ═══════════════════════════════════════════════════════════════════
async def ai_ask(prompt: str, max_tokens: int = 1000) -> Optional[str]:
    """Core async Groq API caller."""
    if not GROQ_API:
        return None
    headers = {
        "Authorization": f"Bearer {GROQ_API}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.75,
    }
    timeout = aiohttp.ClientTimeout(total=20)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(GROQ_URL, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"].strip()
                elif resp.status == 429:
                    await asyncio.sleep(5)
                    return None
                else:
                    text = await resp.text()
                    print(f"⚠️ Groq API Error {resp.status}: {text[:200]}")
                    return None
    except asyncio.TimeoutError:
        print("⚠️ Groq API timeout")
        return None
    except Exception as e:
        print(f"⚠️ Groq API Exception: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════
#          GROQ AI — ORIGINAL FUNCTIONS (v9)
# ═══════════════════════════════════════════════════════════════════
async def ai_fix_movie_name(raw_name: str) -> str:
    if not GROQ_API:
        return raw_name
    result = await ai_ask(
        f"User typed this movie name: '{raw_name}'\n"
        "Fix spelling/Hinglish and return ONLY the correct English movie title.\n"
        "Examples: 'rrr' → 'RRR', 'kgf2' → 'KGF Chapter 2', 'andha dhun' → 'Andhadhun'\n"
        "Return ONLY the movie title, nothing else."
    )
    if result:
        fixed = result.strip().strip('"').strip("'")
        if len(fixed) < 60:
            return fixed
    return raw_name

async def ai_recommend(query: str) -> Optional[str]:
    return await ai_ask(
        f"You are a movie expert. {query}\n"
        "Give exactly 5 recommendations.\n"
        "Format: 🎬 Title (Year) — One line reason\n"
        "Be concise. Reply in same language as query."
    )

async def ai_plot_search(plot_desc: str) -> Optional[str]:
    return await ai_ask(
        f"A user describes a movie plot: '{plot_desc}'\n"
        "Identify the most likely movie(s) this refers to.\n"
        "Give top 3 guesses.\n"
        "Format: 🎬 Title (Year) — Why it matches\n"
        "Be concise."
    )

async def ai_movie_review(title: str, year: str, plot: str, rating: str) -> Optional[str]:
    return await ai_ask(
        f"Write a short, engaging movie review for '{title}' ({year}).\n"
        f"IMDb Rating: {rating}/10\nPlot summary: {plot}\n\n"
        "Write 3-4 sentences. Be honest, fun, and informative.\n"
        "End with a recommendation: Watch / Skip / Must Watch.\n"
        "Reply in Hinglish (mix of Hindi and English)."
    )

async def ai_fun_facts(title: str, year: str, director: str, actors: str) -> Optional[str]:
    return await ai_ask(
        f"Give 3 interesting behind-the-scenes fun facts about '{title}' ({year}).\n"
        f"Director: {director}, Cast: {actors}\n"
        "Format: 💡 Fact\nBe interesting and surprising. Keep each fact 1-2 lines.\n"
        "Reply in Hinglish (mix of Hindi and English)."
    )

async def ai_mood_recommend(mood: str) -> Optional[str]:
    return await ai_ask(
        f"User ka mood hai: '{mood}'\n"
        "Is mood ke hisaab se 5 perfect movies recommend karo.\n"
        "Format: 🎬 Title (Year) — Why perfect for this mood\n"
        "Be empathetic and fun. Reply in Hinglish."
    )

async def ai_compare_movies(movie1: str, movie2: str) -> Optional[str]:
    return await ai_ask(
        f"Compare these two movies in detail:\nMovie 1: {movie1}\nMovie 2: {movie2}\n\n"
        "Compare on: Story, Acting, Direction, Entertainment, Overall\n"
        "Format each point clearly. End with a winner recommendation.\n"
        "Reply in Hinglish (mix of Hindi and English). Be fun and opinionated."
    )


# ═══════════════════════════════════════════════════════════════════
#    ✅ NEW — FULL AI ANALYSIS FUNCTIONS (from movie_finder_groq)
# ═══════════════════════════════════════════════════════════════════
async def ai_full_review(title: str, year: str, genre: str, plot: str,
                         rating: str, director: str, actors: str, awards: str) -> Optional[str]:
    """Comprehensive review — positives, negatives, verdict, AI rating."""
    return await ai_ask(
        f"""Tum ek expert movie critic ho. Is movie ki detailed review likho:

Movie   : {title} ({year})
Genre   : {genre}
Rating  : {rating}/10
Director: {director}
Cast    : {actors}
Awards  : {awards}
Plot    : {plot[:400]}

BILKUL is format mein likho:

📝 *REVIEW:*
[3-4 lines, engaging aur honest]

✅ *POSITIVES:*
• [point 1]
• [point 2]
• [point 3]

❌ *NEGATIVES:*
• [point 1]
• [point 2]

🎯 *VERDICT:* [Watch / Skip / Must Watch / Wait for OTT]
⭐ *AI RATING:* [X/10]

Hinglish mein likho. Fun aur opinionated raho.""",
        max_tokens=900
    )

async def ai_similar_deep(title: str, year: str, genre: str) -> Optional[str]:
    """5 similar movies with solid reasons — deeper than basic similar."""
    return await ai_ask(
        f"""'{title}' ({year}) — Genre: {genre}

Is movie jaisi 5 movies recommend karo. Ek solid reason do kyun similar hai.

Format:
🎬 1. Title (Year) — [reason, 1 line]
🎬 2. Title (Year) — [reason, 1 line]
🎬 3. Title (Year) — [reason, 1 line]
🎬 4. Title (Year) — [reason, 1 line]
🎬 5. Title (Year) — [reason, 1 line]

Hinglish mein. Hindi aur English movies mix karo.""",
        max_tokens=450
    )

async def ai_mood_match(title: str, genre: str, plot: str) -> Optional[str]:
    """Perfect mood, time, company aur snack suggestion."""
    return await ai_ask(
        f"""Movie: '{title}'
Genre: {genre}
Plot: {plot[:300]}

Batao:
🎭 *Best Mood*     : [kaunsi feeling mein dekhni chahiye]
👥 *Best With*     : [akele / dost / family / couple]
🕐 *Best Time*     : [din / raat / weekend / rainy day]
🍿 *Snack Suggest* : [kya khana chahiye saath mein — fun answer]
💬 *One-Line Pitch*: [ek zabardast line jis se dost convince ho jaye]

Hinglish mein likho, creative aur fun raho.""",
        max_tokens=350
    )

async def ai_cast_analysis(title: str, actors: str, director: str) -> Optional[str]:
    """Director + cast ki performance analysis."""
    return await ai_ask(
        f"""Movie '{title}' mein in logon ki performance ke baare mein analysis karo:

Director : {director}
Cast     : {actors}

Har ek ke liye:
🎬 [Naam] — [1-2 line performance analysis ya career highlight]

End mein:
🏆 *Standout Performance:* [sabse acha kaun tha aur kyun — 2 lines]

Hinglish mein. Honest aur specific raho.""",
        max_tokens=600
    )

async def ai_trivia_quiz_movie(title: str, year: str, director: str, actors: str) -> Optional[str]:
    """Ek MCQ trivia question for this specific movie."""
    return await ai_ask(
        f"""Movie '{title}' ({year}) ke baare mein ek interesting MCQ trivia question banao.
Director: {director}, Cast: {actors}

EXACTLY is format mein:
❓ *Question:* [question]

   A) [option]
   B) [option]
   C) [option]
   D) [option]

✅ *Answer:* [correct option letter] — [correct answer]
💡 *Fact:* [ek interesting related fact, 1-2 lines]

Hinglish mein. Lesser-known fact pe based question banana.""",
        max_tokens=400
    )


# ═══════════════════════════════════════════════════════════════════
#         MOVIE INFO MODULE (TMDB-based)
# ═══════════════════════════════════════════════════════════════════
_mi_logger = logging.getLogger("movie_info")
_mi_logger.setLevel(logging.DEBUG)

TMDB_BASE      = "https://api.themoviedb.org/3"
TMDB_IMG_BASE  = "https://image.tmdb.org/t/p/w500"
OMDB_BASE      = "https://www.omdbapi.com"
MI_TIMEOUT     = aiohttp.ClientTimeout(total=8)
RETRY_ATTEMPTS = 3
RETRY_DELAY    = 1.5
CACHE_TTL      = 3600

_mi_cache: dict = {}

def _mi_cache_get(key: str) -> Optional[dict]:
    if key in _mi_cache:
        ts, data = _mi_cache[key]
        if time.time() - ts < CACHE_TTL:
            return data
        else:
            del _mi_cache[key]
    return None

def _mi_cache_set(key: str, data: dict):
    _mi_cache[key] = (time.time(), data)

def _mi_sanitize(text: str) -> str:
    text = text.strip()
    text = re.sub(r"[^\w\s\-\(\)\.,:&']", "", text)
    text = re.sub(r"\s+", " ", text)
    return text

async def _mi_fetch_json(session: aiohttp.ClientSession, url: str, params: dict = None) -> Optional[dict]:
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            async with session.get(url, params=params, timeout=MI_TIMEOUT) as resp:
                if resp.status == 200:
                    return await resp.json()
                elif resp.status == 429:
                    await asyncio.sleep(RETRY_DELAY * 2)
                elif resp.status == 404:
                    return None
        except asyncio.TimeoutError:
            pass
        except aiohttp.ClientConnectorError:
            pass
        except Exception as e:
            _mi_logger.error(f"[MI ERROR] {url} — {e}")
        if attempt < RETRY_ATTEMPTS:
            await asyncio.sleep(RETRY_DELAY)
    return None

async def _mi_tmdb_search(session, title):
    data = await _mi_fetch_json(session, f"{TMDB_BASE}/search/movie", params={
        "api_key": TMDB_API_KEY, "query": title, "language": "en-US", "page": 1,
    })
    if not data: return None
    results = data.get("results", [])
    return results[0] if results else None

async def _mi_tmdb_detail(session, tmdb_id):
    return await _mi_fetch_json(session, f"{TMDB_BASE}/movie/{tmdb_id}", params={
        "api_key": TMDB_API_KEY, "language": "en-US",
    })

async def _mi_tmdb_credits(session, tmdb_id):
    return await _mi_fetch_json(session, f"{TMDB_BASE}/movie/{tmdb_id}/credits", params={
        "api_key": TMDB_API_KEY,
    })

async def _mi_omdb_poster(session, imdb_id):
    if not imdb_id: return None
    data = await _mi_fetch_json(session, OMDB_BASE, params={"i": imdb_id, "apikey": OMDB_API_KEY})
    if not data: return None
    poster = data.get("Poster", "")
    if poster and poster != "N/A" and poster.startswith("http"):
        return poster
    return None

async def get_movie_info(title: str) -> Optional[dict]:
    title = _mi_sanitize(title)
    if not title:
        return None
    cache_key = title.lower()
    cached = _mi_cache_get(cache_key)
    if cached:
        return cached
    async with aiohttp.ClientSession() as session:
        movie = await _mi_tmdb_search(session, title)
        if not movie:
            return None
        tmdb_id = movie.get("id")
        if not tmdb_id:
            return None
        tmdb_poster = None
        if movie.get("poster_path"):
            tmdb_poster = f"{TMDB_IMG_BASE}{movie['poster_path']}"
        detail_task  = asyncio.create_task(_mi_tmdb_detail(session, tmdb_id))
        credits_task = asyncio.create_task(_mi_tmdb_credits(session, tmdb_id))
        detail, credits = await asyncio.gather(detail_task, credits_task)
        if not detail:
            detail = movie
        genres      = ", ".join(g["name"] for g in detail.get("genres", []))
        runtime_raw = detail.get("runtime", 0) or 0
        runtime_str = f"{runtime_raw // 60}h {runtime_raw % 60}m" if runtime_raw else "N/A"
        imdb_id     = detail.get("imdb_id", "") or ""
        rating      = round(float(detail.get("vote_average") or 0), 1)
        votes       = detail.get("vote_count", 0)
        overview    = detail.get("overview") or "No description available."
        tagline     = detail.get("tagline") or ""
        language    = (detail.get("original_language") or "en").upper()
        budget      = detail.get("budget", 0) or 0
        revenue     = detail.get("revenue", 0) or 0
        year        = (detail.get("release_date") or movie.get("release_date") or "")[:4]
        director = "N/A"
        cast_str = "N/A"
        if credits:
            crew = credits.get("crew", [])
            directors = [p["name"] for p in crew if p.get("job") == "Director"]
            director  = ", ".join(directors) if directors else "N/A"
            cast_list = credits.get("cast", [])[:5]
            cast_str  = ", ".join(p["name"] for p in cast_list) if cast_list else "N/A"
        poster = await _mi_omdb_poster(session, imdb_id)
        if not poster:
            poster = tmdb_poster
        result = {
            "title":    detail.get("title") or movie.get("title") or title,
            "year":     year,
            "genres":   genres or "N/A",
            "runtime":  runtime_str,
            "rating":   rating,
            "votes":    votes,
            "overview": overview,
            "poster":   poster,
            "imdb_id":  imdb_id,
            "tmdb_id":  tmdb_id,
            "director": director,
            "cast":     cast_str,
            "tagline":  tagline,
            "language": language,
            "budget":   f"${budget:,}" if budget else "N/A",
            "revenue":  f"${revenue:,}" if revenue else "N/A",
        }
        _mi_cache_set(cache_key, result)
        return result

def _mi_format_stars(rating: float) -> str:
    filled = round(rating / 2)
    return "⭐" * filled + "☆" * (5 - filled)

async def send_movie_card(update: Update, context: ContextTypes.DEFAULT_TYPE,
                          title: str, extra_buttons: list = None):
    loading_msg = await update.effective_message.reply_text("🎬 Fetching detailed info...")
    try:
        info = await get_movie_info(title)
    except Exception as e:
        _mi_logger.error(f"[send_movie_card] {e}")
        info = None
    try:
        await loading_msg.delete()
    except Exception:
        pass
    if not info:
        await update.effective_message.reply_text(
            f"❌ *'{title}'* nahi mila!\n\n_Spelling check karo ya English title try karo._",
            parse_mode="Markdown"
        )
        return
    stars = _mi_format_stars(info["rating"])
    caption = (
        f"🎬 *{info['title']}*"
        + (f" _({info['year']})_" if info["year"] else "") + "\n"
    )
    if info["tagline"]:
        caption += f"_{info['tagline']}_\n"
    caption += (
        f"\n{stars}\n"
        f"⭐ *Rating:* `{info['rating']}/10` ({info['votes']:,} votes)\n"
        f"🎭 *Genres:* {info['genres']}\n"
        f"⏱ *Runtime:* `{info['runtime']}`\n"
        f"🌐 *Language:* `{info['language']}`\n"
        f"🎥 *Director:* {info['director']}\n"
        f"🎭 *Cast:* {info['cast']}\n"
    )
    if info["budget"] != "N/A":
        caption += f"💰 *Budget:* {info['budget']}\n"
    if info["revenue"] != "N/A":
        caption += f"🏆 *Revenue:* {info['revenue']}\n"
    caption += f"\n📖 *Overview:*\n{info['overview'][:800]}"
    if len(info["overview"]) > 800:
        caption += "..."
    keyboard = []
    if info["imdb_id"]:
        keyboard.append([InlineKeyboardButton(
            "🔗 View on IMDb",
            url=f"https://www.imdb.com/title/{info['imdb_id']}/"
        )])
    if extra_buttons:
        keyboard.extend(extra_buttons)
    markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    try:
        if info["poster"]:
            await update.effective_message.reply_photo(
                photo=info["poster"], caption=caption[:1024],
                parse_mode="Markdown", reply_markup=markup,
            )
        else:
            await update.effective_message.reply_text(
                caption, parse_mode="Markdown", reply_markup=markup,
                disable_web_page_preview=False,
            )
    except Exception as e:
        _mi_logger.error(f"[send_movie_card SEND ERROR] {e}")
        try:
            plain = (
                f"{info['title']} ({info['year']})\n"
                f"Rating: {info['rating']}/10\n"
                f"Genres: {info['genres']}\n\n"
                f"{info['overview'][:500]}"
            )
            await update.effective_message.reply_text(plain)
        except Exception as e2:
            _mi_logger.critical(f"[send_movie_card TOTAL FAIL] {e2}")

def mi_cache_clear():
    _mi_cache.clear()

def mi_cache_size() -> int:
    return len(_mi_cache)


# ═══════════════════════════════════════════════════════════════════
#                    CONVERSATION STATES
# ═══════════════════════════════════════════════════════════════════
(
    W_URL, W_NAME, W_MAINT_MSG, W_BROADCAST,
    W_AI_QUERY, W_PLOT_SEARCH, W_LANG_FILTER,
    W_ALERT_MOVIE, W_BAN_USER, W_QUIZ,
    W_MOOD, W_COMPARE_1, W_COMPARE_2, W_RATE_MOVIE,
    W_ADDADMIN,
) = range(15)


# ═══════════════════════════════════════════════════════════════════
#                    /start
# ═══════════════════════════════════════════════════════════════════
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
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
    users  = load_json("users")
    uid    = str(user.id)
    udata  = users.get(uid, {})
    points = udata.get("points", 0)
    refs   = udata.get("refs",   0)
    badge  = get_badge(points)
    ai_status = "✅ Groq AI" if GROQ_API else "⚠️ No AI"
    admin_btn = []
    if is_admin(user.id):
        admin_btn = [[InlineKeyboardButton("👑 Admin Panel", callback_data="open_admin")]]
    keyboard = [
        [InlineKeyboardButton("🔥 Trending",    callback_data="cmd_trending"),
         InlineKeyboardButton("🎲 Random",      callback_data="cmd_random")],
        [InlineKeyboardButton("📅 Upcoming",    callback_data="cmd_upcoming"),
         InlineKeyboardButton("🎯 Daily Pick",  callback_data="cmd_daily")],
        [InlineKeyboardButton("❤️ Watchlist",   callback_data="cmd_watchlist"),
         InlineKeyboardButton("📊 My Stats",    callback_data="cmd_mystats")],
        [InlineKeyboardButton("🤖 AI Suggest",  callback_data="cmd_suggest"),
         InlineKeyboardButton("🔍 Plot Search", callback_data="cmd_plotsearch")],
        [InlineKeyboardButton("🎭 Mood Pick",   callback_data="cmd_mood"),
         InlineKeyboardButton("⚖️ Compare",     callback_data="cmd_compare")],
        [InlineKeyboardButton("🎮 Quiz",        callback_data="cmd_quiz"),
         InlineKeyboardButton("🏆 Leaderboard", callback_data="cmd_leaderboard")],
        [InlineKeyboardButton("📜 History",     callback_data="cmd_history"),
         InlineKeyboardButton("👥 Refer",       callback_data="cmd_refer")],
    ] + admin_btn
    await update.message.reply_text(
        f"╔═══════════════════════╗\n"
        f"║   🎬  *C I N E B O T*  v9   ║\n"
        f"╚═══════════════════════╝\n\n"
        f"✨ *Welcome, {user.first_name}!*\n\n"
        f"┌─────────────────────┐\n"
        f"│  {badge}\n"
        f"│  ⭐ `{points}` Points  •  👥 `{refs}` Refers\n"
        f"│  🤖 {ai_status}\n"
        f"└─────────────────────┘\n\n"
        f"🔎 *Movie dhundhna ho?*\n"
        f"_Seedha movie ka naam type karo!_\n\n"
        f"🤖 *Groq AI Powered Search*\n"
        f"_Galat naam, Hinglish — sab samjha jayega!_\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ═══════════════════════════════════════════════════════════════════
#              START BUTTON CALLBACKS
# ═══════════════════════════════════════════════════════════════════
async def start_btn_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cmd = query.data.replace("cmd_", "")
    fake_update = type('obj', (object,), {
        'effective_user': query.from_user,
        'message':        query.message,
        'effective_chat': query.message.chat,
    })()
    if   cmd == "trending":     await trending_cmd(fake_update, context)
    elif cmd == "random":       await random_cmd(fake_update, context)
    elif cmd == "upcoming":     await upcoming_cmd(fake_update, context)
    elif cmd == "daily":        await daily_cmd(fake_update, context)
    elif cmd == "watchlist":    await watchlist_cmd(fake_update, context)
    elif cmd == "mystats":      await mystats_cmd(fake_update, context)
    elif cmd == "refer":        await refer_cmd(fake_update, context)
    elif cmd == "leaderboard":  await leaderboard_cmd(fake_update, context)
    elif cmd == "history":      await history_cmd(fake_update, context)
    elif cmd == "quiz":         await quiz_cmd(fake_update, context)
    elif cmd == "open_admin":   await admin_panel(fake_update, context)
    elif cmd in ("suggest", "plotsearch", "mood", "compare"):
        pass


# ═══════════════════════════════════════════════════════════════════
#   MOVIE CARD (OMDB) — ✅ 2 naye rows added: Mood/Cast + Trivia/Package
# ═══════════════════════════════════════════════════════════════════
async def _send_movie_card(update, context, data, reply_to=None, is_search=False):
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
    imdb_id  = data.get("imdbID",     "")

    rt_score = "N/A"
    for r in data.get("Ratings", []):
        if "Rotten Tomatoes" in r.get("Source", ""):
            rt_score = r["Value"]

    if not poster or poster == "N/A":
        poster = None
        if TMDB_API:
            try:
                r = requests.get(
                    f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API}&query={quote(title)}",
                    timeout=5
                )
                results = r.json().get("results", [])
                if results and results[0].get("poster_path"):
                    poster = f"https://image.tmdb.org/t/p/w500{results[0]['poster_path']}"
            except Exception:
                poster = None

    ratings_db  = load_json("ratings")
    movie_rates = ratings_db.get(title, {})
    if movie_rates:
        avg_rate = sum(movie_rates.values()) / len(movie_rates)
        comm_rat = f"⭐ `{avg_rate:.1f}/5` ({len(movie_rates)} votes)"
    else:
        comm_rat = "_No ratings yet_"

    star_bar     = build_star_bar(rating)
    search_query = quote(title)
    servers      = load_servers()
    urls         = [servers[f"s{i}"]["url"] + search_query for i in range(1, 7)]
    names        = [servers[f"s{i}"]["name"]               for i in range(1, 7)]
    trailer      = f"https://www.youtube.com/results?search_query={quote(title + ' trailer')}"
    subs_url     = f"https://subscene.com/subtitles/searchbytitle?query={search_query}"

    try:
        uid = str(update.effective_user.id)
    except:
        uid = "0"

    log_search(title, uid)
    if is_search:
        add_search_points(uid)

    caption = (
        f"🎬 *{title}*  `{year}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{star_bar}\n"
        f"⭐ *IMDb:* `{rating}/10`   🍅 *RT:* `{rt_score}`\n"
        f"👥 *Community:* {comm_rat}\n"
        f"🗳 *Votes:* `{votes}`   🔞 *Rated:* `{rated}`\n\n"
        f"🎭 *Genre:*    `{genre}`\n"
        f"⏱ *Runtime:* `{runtime}`\n"
        f"🌍 *Lang:*     `{language}`\n"
        f"🎥 *Director:* `{director}`\n"
        f"👥 *Cast:*     `{actors}`\n"
        f"💰 *Box Office:* `{boxoff}`\n"
        f"🏆 *Awards:* `{awards}`\n\n"
        f"📖 *Story:*\n_{plot}_\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ 6 Servers  •  🦁 Brave = No Ads"
    )

    msg_obj = reply_to if reply_to else update.message

    # Temp keyboard (before msg_id is known)
    temp_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 Trailer",   url=trailer),
         InlineKeyboardButton("📝 Subtitles", url=subs_url)],
        [InlineKeyboardButton("❤️ Watchlist", callback_data=f"wl_save|{title}|{year}|{rating}"),
         InlineKeyboardButton("🔔 Alert",     callback_data=f"alert_add|{title}|{year}")],
        [InlineKeyboardButton(f"⬇️ {names[0]}", url=urls[0])],
        [InlineKeyboardButton("🌐 All 6 Servers",    callback_data="s_tmp"),
         InlineKeyboardButton("🎯 Similar",          callback_data="sim_tmp")],
        [InlineKeyboardButton("🤖 AI Review",        callback_data="rev_tmp"),
         InlineKeyboardButton("💡 Fun Facts",        callback_data="fun_tmp")],
        [InlineKeyboardButton("⭐ Rate Movie",       callback_data="rate_tmp"),
         InlineKeyboardButton("🎥 Director Top 5",  callback_data=f"dir_{quote(director, safe='')}")],
        # ✅ NEW ROW 1 — Full Analysis
        [InlineKeyboardButton("📝 Full Review",      callback_data="frev_tmp"),
         InlineKeyboardButton("🎭 Mood Match",       callback_data="mood_match_tmp")],
        # ✅ NEW ROW 2
        [InlineKeyboardButton("🌟 Cast Analysis",    callback_data="cast_tmp"),
         InlineKeyboardButton("❓ Trivia Quiz",      callback_data="trivia_tmp")],
        # ✅ NEW ROW 3
        [InlineKeyboardButton("🔥 Full AI Package",  callback_data="pkg_tmp")],
    ])

    if poster:
        try:
            sent = await msg_obj.reply_photo(
                photo=poster, caption=caption,
                parse_mode="Markdown", reply_markup=temp_keyboard
            )
        except Exception:
            sent = await msg_obj.reply_text(
                f"⚠️ _Poster load nahi hua_\n\n{caption}",
                parse_mode="Markdown", reply_markup=temp_keyboard
            )
    else:
        sent = await msg_obj.reply_text(
            caption, parse_mode="Markdown", reply_markup=temp_keyboard
        )

    msg_id = str(sent.message_id)
    # ✅ Store genre, awards too for new AI functions
    context.user_data[msg_id] = {
        "servers":  urls,
        "names":    names,
        "trailer":  trailer,
        "title":    title,
        "year":     year,
        "rating":   rating,
        "director": director,
        "actors":   actors,
        "plot":     plot,
        "imdb_id":  imdb_id,
        "genre":    genre,
        "awards":   awards,
    }

    # Real keyboard with msg_id
    real_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 Trailer",   url=trailer),
         InlineKeyboardButton("📝 Subtitles", url=subs_url)],
        [InlineKeyboardButton("❤️ Watchlist", callback_data=f"wl_save|{title}|{year}|{rating}"),
         InlineKeyboardButton("🔔 Alert",     callback_data=f"alert_add|{title}|{year}")],
        [InlineKeyboardButton(f"⬇️ {names[0]}", url=urls[0])],
        [InlineKeyboardButton("🌐 All 6 Servers",    callback_data=f"srv_{msg_id}"),
         InlineKeyboardButton("🎯 Similar",          callback_data=f"sim_{msg_id}")],
        [InlineKeyboardButton("🤖 AI Review",        callback_data=f"rev_{imdb_id}"),
         InlineKeyboardButton("💡 Fun Facts",        callback_data=f"fun_{imdb_id}")],
        [InlineKeyboardButton("⭐ Rate Movie",       callback_data=f"rate_{msg_id}"),
         InlineKeyboardButton("🎥 Director Top 5",  callback_data=f"dir_{quote(director, safe='')}")],
        # ✅ NEW ROWS with real msg_id
        [InlineKeyboardButton("📝 Full Review",      callback_data=f"frev_{msg_id}"),
         InlineKeyboardButton("🎭 Mood Match",       callback_data=f"mood_match_{msg_id}")],
        [InlineKeyboardButton("🌟 Cast Analysis",    callback_data=f"cast_{msg_id}"),
         InlineKeyboardButton("❓ Trivia Quiz",      callback_data=f"trivia_{msg_id}")],
        [InlineKeyboardButton("🔥 Full AI Package",  callback_data=f"pkg_{msg_id}")],
    ])
    try:
        await sent.edit_reply_markup(reply_markup=real_keyboard)
    except Exception as e:
        print(f"⚠️ edit_reply_markup failed (msg_id={msg_id}): {e}")

    asyncio.create_task(auto_delete(sent, 7200, user_data=context.user_data, key=msg_id))


# ═══════════════════════════════════════════════════════════════════
#   ✅ NEW CALLBACKS — Full Analysis (from movie_finder_groq)
# ═══════════════════════════════════════════════════════════════════

# --- 📝 Full Review ---
async def fullreview_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer("📝 Writing full review...")
    msg_id = query.data.split("_", 1)[1]
    md     = context.user_data.get(msg_id)
    if not md:
        await query.message.reply_text("⚠️ Session expired. Movie dobara search karo.")
        return
    loader = await query.message.reply_text("📝 Full review likh raha hai...\n" + progress_bar(0, 4))
    await animate_generic(loader, FRAMES["fullreview"])
    result = await ai_full_review(
        md["title"], md["year"], md.get("genre", "N/A"),
        md["plot"], md["rating"], md["director"],
        md["actors"], md.get("awards", "N/A")
    )
    try: await loader.delete()
    except: pass
    if result:
        await query.message.reply_text(
            f"╔══════════════════════════╗\n║  📝  *FULL AI REVIEW*  ║\n╚══════════════════════════╝\n\n"
            f"🎬 *{md['title']}* ({md['year']})\n━━━━━━━━━━━━━━━━━━\n\n"
            f"{result}\n\n_Powered by Groq AI (Llama 3.3)_ 🤖",
            parse_mode="Markdown"
        )
    else:
        await query.message.reply_text(
            "❌ AI review nahi likh paya.\n_GROQ_API check karo._",
            parse_mode="Markdown"
        )

# --- 🎭 Mood Match ---
async def moodmatch_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer("🎭 Mood match kar raha hai...")
    msg_id = query.data.split("_", 2)[2]   # mood_match_MSGID
    md     = context.user_data.get(msg_id)
    if not md:
        await query.message.reply_text("⚠️ Session expired. Movie dobara search karo.")
        return
    loader = await query.message.reply_text("🎭 Mood analyze ho raha hai...\n" + progress_bar(0, 4))
    await animate_generic(loader, FRAMES["moodmatch"])
    result = await ai_mood_match(
        md["title"], md.get("genre", "N/A"), md["plot"]
    )
    try: await loader.delete()
    except: pass
    if result:
        await query.message.reply_text(
            f"╔══════════════════════════╗\n║  🎭  *MOOD MATCH*  ║\n╚══════════════════════════╝\n\n"
            f"🎬 *{md['title']}* ({md['year']})\n━━━━━━━━━━━━━━━━━━\n\n"
            f"{result}\n\n_Powered by Groq AI (Llama 3.3)_ 🤖",
            parse_mode="Markdown"
        )
    else:
        await query.message.reply_text("❌ Mood match nahi hua. GROQ_API check karo.", parse_mode="Markdown")

# --- 🌟 Cast Analysis ---
async def castanalysis_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer("🌟 Cast analyze ho raha hai...")
    msg_id = query.data.split("_", 1)[1]
    md     = context.user_data.get(msg_id)
    if not md:
        await query.message.reply_text("⚠️ Session expired. Movie dobara search karo.")
        return
    loader = await query.message.reply_text("🌟 Cast analysis chal raha hai...\n" + progress_bar(0, 3))
    await animate_generic(loader, FRAMES["castanalysis"])
    result = await ai_cast_analysis(md["title"], md["actors"], md["director"])
    try: await loader.delete()
    except: pass
    if result:
        await query.message.reply_text(
            f"╔══════════════════════════╗\n║  🌟  *CAST ANALYSIS*  ║\n╚══════════════════════════╝\n\n"
            f"🎬 *{md['title']}* ({md['year']})\n━━━━━━━━━━━━━━━━━━\n\n"
            f"{result}\n\n_Powered by Groq AI (Llama 3.3)_ 🤖",
            parse_mode="Markdown"
        )
    else:
        await query.message.reply_text("❌ Cast analysis nahi hua. GROQ_API check karo.", parse_mode="Markdown")

# --- ❓ Trivia Quiz (per movie) ---
async def trivia_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer("❓ Trivia question bana raha hai...")
    msg_id = query.data.split("_", 1)[1]
    md     = context.user_data.get(msg_id)
    if not md:
        await query.message.reply_text("⚠️ Session expired. Movie dobara search karo.")
        return
    loader = await query.message.reply_text("❓ Trivia bana raha hai...\n" + progress_bar(0, 3))
    await animate_generic(loader, FRAMES["trivia"])
    result = await ai_trivia_quiz_movie(
        md["title"], md["year"], md["director"], md["actors"]
    )
    try: await loader.delete()
    except: pass
    if result:
        await query.message.reply_text(
            f"╔══════════════════════════╗\n║  ❓  *MOVIE TRIVIA*  ║\n╚══════════════════════════╝\n\n"
            f"🎬 *{md['title']}* ({md['year']})\n━━━━━━━━━━━━━━━━━━\n\n"
            f"{result}\n\n_Powered by Groq AI (Llama 3.3)_ 🤖",
            parse_mode="Markdown"
        )
    else:
        await query.message.reply_text("❌ Trivia nahi bana. GROQ_API check karo.", parse_mode="Markdown")

# --- 🔥 Full AI Package (sab ek saath) ---
async def fullpackage_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer("🔥 Full package prepare ho raha hai...")
    msg_id = query.data.split("_", 1)[1]
    md     = context.user_data.get(msg_id)
    if not md:
        await query.message.reply_text("⚠️ Session expired. Movie dobara search karo.")
        return

    loader = await query.message.reply_text("🔥 Full AI Package loading...\n" + progress_bar(0, 5))
    await animate_generic(loader, FRAMES["fullpackage"])
    try: await loader.delete()
    except: pass

    t  = md["title"];  y  = md["year"]
    g  = md.get("genre","N/A");  p  = md["plot"]
    r  = md["rating"]; d  = md["director"]
    a  = md["actors"]; aw = md.get("awards","N/A")

    sections = [
        ("📝 FULL REVIEW",    ai_full_review(t, y, g, p, r, d, a, aw)),
        ("🎯 SIMILAR MOVIES", ai_similar_deep(t, y, g)),
        ("🎭 MOOD MATCH",     ai_mood_match(t, g, p)),
        ("🌟 CAST ANALYSIS",  ai_cast_analysis(t, a, d)),
        ("❓ TRIVIA QUIZ",    ai_trivia_quiz_movie(t, y, d, a)),
    ]

    # Run all concurrently
    results = await asyncio.gather(*[coro for _, coro in sections], return_exceptions=True)

    full_text = (
        f"╔══════════════════════════╗\n"
        f"║  🔥  *FULL AI PACKAGE*  ║\n"
        f"╚══════════════════════════╝\n\n"
        f"🎬 *{t}* ({y})\n━━━━━━━━━━━━━━━━━━\n"
    )

    for i, (label, _) in enumerate(sections):
        res = results[i]
        full_text += f"\n\n*━━ {label} ━━*\n"
        if isinstance(res, Exception) or not res:
            full_text += "_AI response nahi aaya._"
        else:
            full_text += res
        # Telegram 4096 char limit — send in chunks
        if len(full_text) > 3800:
            await query.message.reply_text(full_text, parse_mode="Markdown")
            full_text = f"🎬 *{t}* — continued...\n"

    full_text += "\n\n_Powered by Groq AI (Llama 3.3)_ 🤖"
    if full_text.strip():
        await query.message.reply_text(full_text, parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════════
#   ✅ NEW COMMANDS — /fullreview /moodmatch /castinfo /trivia
# ═══════════════════════════════════════════════════════════════════
async def fullreview_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/fullreview Inception"""
    title = " ".join(context.args).strip() if context.args else ""
    if not title:
        await update.message.reply_text(
            "❌ *Usage:* `/fullreview Movie Name`\nExample: `/fullreview Inception`",
            parse_mode="Markdown"
        )
        return
    if not GROQ_API:
        await update.message.reply_text("⚠️ GROQ_API set nahi hai!", parse_mode="Markdown")
        return
    loader = await update.message.reply_text("📝 Movie info fetch ho rahi hai...\n" + progress_bar(1, 4))
    data = await asyncio.to_thread(get_omdb, title)
    if not data or data.get("Response") == "False":
        await loader.edit_text(f"❌ *'{title}'* nahi mili!", parse_mode="Markdown")
        return
    await animate_generic(loader, FRAMES["fullreview"])
    result = await ai_full_review(
        data.get("Title","N/A"), data.get("Year","N/A"),
        data.get("Genre","N/A"), data.get("Plot","N/A"),
        data.get("imdbRating","N/A"), data.get("Director","N/A"),
        data.get("Actors","N/A"), data.get("Awards","N/A")
    )
    try: await loader.delete()
    except: pass
    if result:
        await update.message.reply_text(
            f"╔══════════════════════════╗\n║  📝  *FULL AI REVIEW*  ║\n╚══════════════════════════╝\n\n"
            f"🎬 *{data['Title']}* ({data['Year']})\n━━━━━━━━━━━━━━━━━━\n\n"
            f"{result}\n\n_Powered by Groq AI_ 🤖",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("❌ Review nahi likh paya. Try again.", parse_mode="Markdown")

async def moodmatch_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/moodmatch Inception"""
    title = " ".join(context.args).strip() if context.args else ""
    if not title:
        await update.message.reply_text(
            "❌ *Usage:* `/moodmatch Movie Name`\nExample: `/moodmatch Inception`",
            parse_mode="Markdown"
        )
        return
    if not GROQ_API:
        await update.message.reply_text("⚠️ GROQ_API set nahi hai!", parse_mode="Markdown")
        return
    loader = await update.message.reply_text("🎭 Mood analyze ho raha hai...\n" + progress_bar(1, 4))
    data = await asyncio.to_thread(get_omdb, title)
    if not data or data.get("Response") == "False":
        await loader.edit_text(f"❌ *'{title}'* nahi mili!", parse_mode="Markdown")
        return
    await animate_generic(loader, FRAMES["moodmatch"])
    result = await ai_mood_match(
        data.get("Title","N/A"), data.get("Genre","N/A"), data.get("Plot","N/A")
    )
    try: await loader.delete()
    except: pass
    if result:
        await update.message.reply_text(
            f"╔══════════════════════╗\n║  🎭  *MOOD MATCH*  ║\n╚══════════════════════╝\n\n"
            f"🎬 *{data['Title']}* ({data['Year']})\n━━━━━━━━━━━━━━━━━━\n\n"
            f"{result}\n\n_Powered by Groq AI_ 🤖",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("❌ Mood match nahi hua. Try again.", parse_mode="Markdown")

async def castinfo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/castinfo Inception"""
    title = " ".join(context.args).strip() if context.args else ""
    if not title:
        await update.message.reply_text(
            "❌ *Usage:* `/castinfo Movie Name`\nExample: `/castinfo Inception`",
            parse_mode="Markdown"
        )
        return
    if not GROQ_API:
        await update.message.reply_text("⚠️ GROQ_API set nahi hai!", parse_mode="Markdown")
        return
    loader = await update.message.reply_text("🌟 Cast analyze ho raha hai...\n" + progress_bar(1, 3))
    data = await asyncio.to_thread(get_omdb, title)
    if not data or data.get("Response") == "False":
        await loader.edit_text(f"❌ *'{title}'* nahi mili!", parse_mode="Markdown")
        return
    await animate_generic(loader, FRAMES["castanalysis"])
    result = await ai_cast_analysis(
        data.get("Title","N/A"), data.get("Actors","N/A"), data.get("Director","N/A")
    )
    try: await loader.delete()
    except: pass
    if result:
        await update.message.reply_text(
            f"╔══════════════════════════╗\n║  🌟  *CAST ANALYSIS*  ║\n╚══════════════════════════╝\n\n"
            f"🎬 *{data['Title']}* ({data['Year']})\n━━━━━━━━━━━━━━━━━━\n\n"
            f"{result}\n\n_Powered by Groq AI_ 🤖",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("❌ Cast info nahi aaya. Try again.", parse_mode="Markdown")

async def trivia_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/trivia Inception"""
    title = " ".join(context.args).strip() if context.args else ""
    if not title:
        await update.message.reply_text(
            "❌ *Usage:* `/trivia Movie Name`\nExample: `/trivia Inception`",
            parse_mode="Markdown"
        )
        return
    if not GROQ_API:
        await update.message.reply_text("⚠️ GROQ_API set nahi hai!", parse_mode="Markdown")
        return
    loader = await update.message.reply_text("❓ Trivia bana raha hai...\n" + progress_bar(1, 3))
    data = await asyncio.to_thread(get_omdb, title)
    if not data or data.get("Response") == "False":
        await loader.edit_text(f"❌ *'{title}'* nahi mili!", parse_mode="Markdown")
        return
    await animate_generic(loader, FRAMES["trivia"])
    result = await ai_trivia_quiz_movie(
        data.get("Title","N/A"), data.get("Year","N/A"),
        data.get("Director","N/A"), data.get("Actors","N/A")
    )
    try: await loader.delete()
    except: pass
    if result:
        await update.message.reply_text(
            f"╔══════════════════════════╗\n║  ❓  *MOVIE TRIVIA*  ║\n╚══════════════════════════╝\n\n"
            f"🎬 *{data['Title']}* ({data['Year']})\n━━━━━━━━━━━━━━━━━━\n\n"
            f"{result}\n\n_Powered by Groq AI_ 🤖",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("❌ Trivia nahi bana. Try again.", parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════════
#       MOVIE SEARCH (OMDB)
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
    raw_name = update.message.text.strip()
    loader   = await update.message.reply_text("🎬 Searching...\n" + progress_bar(0, 6))
    await animate_search(loader)
    data = await asyncio.to_thread(get_omdb, raw_name)
    if not data or data.get("Response") == "False":
        try:
            await loader.edit_text("🤖 AI fixing name...\n" + progress_bar(4, 6))
        except: pass
        fixed_name = await ai_fix_movie_name(raw_name)
        if fixed_name.lower() != raw_name.lower():
            data = await asyncio.to_thread(get_omdb, fixed_name)
    if not data or data.get("Response") == "False":
        results = await asyncio.to_thread(get_omdb_search, raw_name)
        if results:
            if len(results) == 1:
                data = await asyncio.to_thread(get_omdb, results[0].get("imdbID", ""), True)
            else:
                try: await loader.delete()
                except: pass
                keyboard = [
                    [InlineKeyboardButton(
                        f"🎬 {r.get('Title','?')} ({r.get('Year','?')})",
                        callback_data=f"pick_{r.get('imdbID','')}"
                    )]
                    for r in results if r.get("imdbID")
                ]
                await update.message.reply_text(
                    f"╔══════════════════════╗\n║  🔍  *Multiple Results*  ║\n╚══════════════════════╝\n\n"
                    f"*'{raw_name}'* ke liye kaunsi movie chahiye?\n\nChoose karo 👇",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return
    if not data or data.get("Response") == "False":
        try:
            await loader.edit_text(
                f"╔═══════════════════╗\n║  ❌  Movie Not Found  ║\n╚═══════════════════╝\n\n"
                f"🔍 *'{raw_name}'* nahi mili\n\n"
                f"💡 *Try karo:*\n"
                f"• /plotsearch — Plot describe karo\n"
                f"• /suggest — AI recommendations\n"
                f"• /mood — Mood se movie\n"
                f"• /random — Random movie\n\n"
                f"_Aur clearly likhke try karo_ 📝",
                parse_mode="Markdown"
            )
        except: pass
        return
    try: await loader.delete()
    except: pass
    await _send_movie_card(update, context, data, is_search=True)


# /movieinfo command
async def movieinfo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_maintenance() and not is_admin(update.effective_user.id):
        await update.message.reply_text("🚧 Maintenance mode.")
        return
    if not TMDB_API:
        await update.message.reply_text(
            "⚠️ *TMDB_API not set!*", parse_mode="Markdown"
        )
        return
    title = " ".join(context.args).strip() if context.args else ""
    if not title:
        await update.message.reply_text(
            "❌ *Usage:* `/movieinfo Movie Name`", parse_mode="Markdown"
        )
        return
    await send_movie_card(update, context, title)

# Multi-result pick callback
async def pick_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    await query.answer("🎬 Loading...")
    imdb_id = query.data.replace("pick_", "")
    loader  = await query.message.reply_text("🎬 Loading...\n" + progress_bar(2, 6))
    await animate_search(loader)
    data = await asyncio.to_thread(get_omdb, imdb_id, True)
    try: await loader.delete()
    except: pass
    if data and data.get("Response") == "True":
        await _send_movie_card(update, context, data, reply_to=query.message, is_search=True)
    else:
        await query.message.reply_text("❌ Load nahi hua. Try again.")


# ═══════════════════════════════════════════════════════════════════
#         AI REVIEW CALLBACK (original — short review)
# ═══════════════════════════════════════════════════════════════════
async def review_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🤖 Writing review...")
    imdb_id    = query.data.split("_", 1)[1]
    movie_data = await asyncio.to_thread(get_omdb, imdb_id, True)
    if not movie_data or movie_data.get("Response") == "False":
        await query.message.reply_text("❌ Movie details fetch nahi ho payi!")
        return
    loader = await query.message.reply_text("🤖 Writing AI Review...\n" + progress_bar(0, 4))
    await animate_generic(loader, FRAMES["review"])
    review = await ai_movie_review(
        movie_data.get("Title", "N/A"), movie_data.get("Year", "N/A"),
        movie_data.get("Plot", "N/A"), movie_data.get("imdbRating", "N/A")
    )
    try: await loader.delete()
    except: pass
    if review:
        await query.message.reply_text(
            f"╔══════════════════════╗\n║  🤖  *AI REVIEW* ║\n╚══════════════════════╝\n\n"
            f"🎬 *{movie_data['Title']}* ({movie_data['Year']})\n━━━━━━━━━━━━━━━━━━\n\n"
            f"{review}\n\n_Powered by Groq AI (Llama 3.3)_ 🤖",
            parse_mode="Markdown"
        )
    else:
        await query.message.reply_text("❌ Groq API ne response nahi diya. GROQ_API check karo.")


# ═══════════════════════════════════════════════════════════════════
#         FUN FACTS CALLBACK
# ═══════════════════════════════════════════════════════════════════
async def funfact_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("💡 Finding fun facts...")
    try:
        imdb_id = query.data.split("_", 1)[1]
    except IndexError:
        await query.message.reply_text("⚠️ Error: Movie ID nahi mili.")
        return
    movie_data = await asyncio.to_thread(get_omdb, imdb_id, True)
    if not movie_data or movie_data.get("Response") == "False":
        await query.message.reply_text("❌ Movie details fetch nahi ho payi!")
        return
    loader = await query.message.reply_text("💡 Finding Fun Facts...\n" + progress_bar(0, 3))
    await animate_generic(loader, FRAMES["ai"])
    facts = await ai_fun_facts(
        movie_data.get("Title", "N/A"), movie_data.get("Year", "N/A"),
        movie_data.get("Director", "N/A"), movie_data.get("Actors", "N/A")
    )
    try: await loader.delete()
    except: pass
    if facts:
        await query.message.reply_text(
            f"╔══════════════════════╗\n║  💡  *FUN FACTS* ║\n╚══════════════════════╝\n\n"
            f"🎬 *{movie_data.get('Title')}* ({movie_data.get('Year')})\n━━━━━━━━━━━━━━━━━━\n\n"
            f"{facts}\n\n_Powered by Groq AI (Llama 3.3)_ 🤖",
            parse_mode="Markdown"
        )
    else:
        await query.message.reply_text("❌ Groq API ne response nahi diya. GROQ_API check karo.")


# ═══════════════════════════════════════════════════════════════════
#         RATE MOVIE CALLBACK
# ═══════════════════════════════════════════════════════════════════
async def rate_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query      = update.callback_query
    await query.answer()
    msg_id     = query.data.split("_", 1)[1]
    movie_data = context.user_data.get(msg_id)
    if not movie_data:
        await query.message.reply_text("⚠️ Session expired. Search again.")
        return
    title = movie_data["title"]
    keyboard = [
        [InlineKeyboardButton(f"{'⭐' * i}  {i}/5", callback_data=f"dorat_{msg_id}_{i}")]
        for i in range(1, 6)
    ]
    await query.message.reply_text(
        f"⭐ *Rate:* _{title}_\n\n_Apni rating do:_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def dorat_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer()
    parts  = query.data.split("_")
    score  = int(parts[-1])
    msg_id = "_".join(parts[1:-1])
    movie_data = context.user_data.get(msg_id)
    if not movie_data:
        await query.message.edit_text("⚠️ Session expired.")
        return
    title   = movie_data["title"]
    uid     = str(query.from_user.id)
    ratings = load_json("ratings")
    if title not in ratings: ratings[title] = {}
    ratings[title][uid] = score
    save_json("ratings", ratings)
    avg = sum(ratings[title].values()) / len(ratings[title])
    await query.message.edit_text(
        f"✅ *Rating saved!*\n\n🎬 *{title}*\n⭐ Your rating: `{score}/5`\n"
        f"👥 Community avg: `{avg:.1f}/5` ({len(ratings[title])} votes)\n\n_Shukriya!_ 🙏",
        parse_mode="Markdown"
    )
    users = load_json("users")
    if uid in users:
        users[uid]["points"] = users[uid].get("points", 0) + 5
        save_json("users", users)


# ═══════════════════════════════════════════════════════════════════
#         MOOD-BASED RECOMMENDATION (existing)
# ═══════════════════════════════════════════════════════════════════
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
async def director_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query    = update.callback_query
    await query.answer("🎥 Loading director films...")
    from urllib.parse import unquote
    director = unquote(query.data.replace("dir_", ""))
    loader = await query.message.reply_text("🎥 Loading...\n" + progress_bar(0, 3))
    await animate_generic(loader, FRAMES["similar"])
    movies = get_director_movies(director)
    try: await loader.delete()
    except: pass
    if movies:
        text = f"🎥 *Top 5 by {director}:*\n━━━━━━━━━━━━━━━━━━\n\n"
        medals = ["🥇", "🥈", "🥉", "🏅", "🎖"]
        for i, (t, r) in enumerate(movies):
            text += f"{medals[i]} *{t}* — ⭐`{r}`\n"
        text += "\n_Type naam to search_ 🔎"
    else:
        text = f"🎥 *{director}* ki movies:\n\nTMDB API add karo for results."
    await query.message.reply_text(text, parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════════
#              UPCOMING MOVIES
# ═══════════════════════════════════════════════════════════════════
async def upcoming_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_maintenance() and not is_admin(update.effective_user.id):
        await update.message.reply_text("🚧 Maintenance mode.")
        return
    loader = await update.message.reply_text("📅 Loading upcoming...\n" + progress_bar(1, 3))
    await asyncio.sleep(0.8)
    movies = get_tmdb_upcoming()
    try: await loader.delete()
    except: pass
    if movies:
        text = "╔═══════════════════════╗\n║  📅  *UPCOMING MOVIES*  ║\n╚═══════════════════════╝\n\n"
        for item in movies:
            if len(item) == 3:
                title, release, days = item
            else:
                title, days = item[0], item[1]
                release = "TBA"
            bar = "🟩" * min(10, max(1, 10 - days // 10)) + "⬜" * max(0, 10 - min(10, max(1, 10 - days // 10)))
            countdown = "🔴 *TODAY!*" if days == 0 else (f"🟡 `{days}` days" if days <= 7 else f"🟢 `{days}` days")
            text += f"🎬 *{title}*\n📅 `{release}`  ⏳ {countdown}\n{bar}\n\n"
        text += "_Type naam to search_ 🔎"
    else:
        text = (
            "╔═══════════════════════╗\n║  📅  *UPCOMING MOVIES*  ║\n╚═══════════════════════╝\n\n"
            "⚠️ *TMDB API needed!*\n\n_Set TMDB_API in Render Environment Variables_\n\n🆓 Free at: themoviedb.org"
        )
    await update.message.reply_text(text, parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════════
#           AI SUGGEST
# ═══════════════════════════════════════════════════════════════════
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
        "🌐 *Language Preference*\n━━━━━━━━━━━━━━━━━━\n\nDefault language filter select karo 👇",
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
        f"✅ *Language set:* `{lang}`\n\n_Ab tumhari AI suggestions {lang} prefer karengi._",
        parse_mode="Markdown"
    )


# ═══════════════════════════════════════════════════════════════════
#          SIMILAR MOVIES
# ═══════════════════════════════════════════════════════════════════
async def similar_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query      = update.callback_query
    await query.answer("🎯 Finding similar...")
    msg_id     = query.data.split("_", 1)[1]
    movie_data = context.user_data.get(msg_id)
    if not movie_data:
        await query.message.reply_text("⚠️ Session expired. Search again.")
        return
    loader = await query.message.reply_text("🎯 Loading...\n" + progress_bar(0, 3))
    await animate_generic(loader, FRAMES["similar"])
    title   = movie_data["title"]
    similar = get_tmdb_similar(title)
    try: await loader.delete()
    except: pass
    if similar:
        text = f"╔══════════════════════╗\n║  🎯  *SIMILAR MOVIES*  ║\n╚══════════════════════╝\n\n"
        text += f"_Similar to_ *{title}:*\n━━━━━━━━━━━━━━━━━━\n\n"
        medals = ["🥇", "🥈", "🥉", "🏅", "🎖", "🌟"]
        for i, (t, r) in enumerate(similar):
            text += f"{medals[i]} *{t}* ⭐`{r}`\n"
        text += "\n_Type naam to search_ 🔎"
    elif GROQ_API:
        result = await ai_similar_deep(title, movie_data.get("year",""), movie_data.get("genre",""))
        text = f"🤖 *AI Similar to {title}:*\n━━━━━━━━━━━━━━━━━━\n\n{result or 'Not found'}"
    else:
        text = "_TMDB/Groq API add karo for similar movies_"
    await query.message.reply_text(text, parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════════
#            TRENDING
# ═══════════════════════════════════════════════════════════════════
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

async def daily_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_maintenance() and not is_admin(update.effective_user.id):
        await update.message.reply_text("🚧 Maintenance.")
        return
    today = str(date.today())
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
async def watchlist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = str(update.effective_user.id)
    data = load_json("watchlist")
    wl   = data.get(uid, [])
    if not wl:
        await update.message.reply_text(
            "╔══════════════════╗\n║  ❤️  *WATCHLIST*  ║\n╚══════════════════╝\n\n"
            "📭 *Empty Watchlist!*\n\n_Movie search karo aur ❤️ tap karo_",
            parse_mode="Markdown"
        )
        return
    text = f"╔══════════════════╗\n║  ❤️  *WATCHLIST*  ║\n╚══════════════════╝\n\n"
    text += f"📋 *{len(wl)} Movies Saved:*\n━━━━━━━━━━━━━━━━━━\n\n"
    for i, m in enumerate(wl, 1):
        text += f"`{i}.` 🎬 *{m['title']}* `({m['year']})` ⭐`{m['rating']}`\n"
    text += "\n_Search karo movie naam type karke_ 🔎"
    await update.message.reply_text(
        text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🗑 Clear All", callback_data="wl_clear")]])
    )

async def wl_save_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        parts  = query.data.split("|")
        title, year, rating = parts[1], parts[2], parts[3]
    except IndexError:
        await query.answer("⚠️ Error saving. Search again.", show_alert=True)
        return
    uid  = str(query.from_user.id)
    data = load_json("watchlist")
    if uid not in data: data[uid] = []
    if any(m["title"] == title for m in data[uid]):
        await query.answer("⚠️ Already in Watchlist!", show_alert=True)
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
#           MOVIE ALERTS
# ═══════════════════════════════════════════════════════════════════
async def alerts_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid   = str(update.effective_user.id)
    data  = load_json("alerts")
    my_al = data.get(uid, [])
    text     = "╔══════════════════╗\n║  🔔  *MY ALERTS*  ║\n╚══════════════════╝\n\n"
    keyboard = []
    if my_al:
        text += "*Active Alerts:*\n━━━━━━━━━━━━━━━━━━\n"
        for i, m in enumerate(my_al, 1):
            text += f"`{i}.` 🎬 *{m['title']}* ({m['year']})\n"
            keyboard.append([InlineKeyboardButton(f"🗑 Remove: {m['title'][:20]}", callback_data=f"alert_del|{m['title']}")])
        text += "\n_Jab movie available hogi, notify karunga!_"
        keyboard.append([InlineKeyboardButton("🗑 Clear All Alerts", callback_data="alert_clear")])
    else:
        text += "📭 *Koi alert set nahi!*\n\n_Movie card pe 🔔 tap karo._"
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None)

async def alert_add_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        parts       = query.data.split("|")
        title, year = parts[1], parts[2]
    except IndexError:
        await query.answer("⚠️ Error. Try again.", show_alert=True)
        return
    uid  = str(query.from_user.id)
    data = load_json("alerts")
    if uid not in data: data[uid] = []
    if any(m["title"] == title for m in data[uid]):
        await query.answer("⚠️ Alert already set!", show_alert=True)
        return
    data[uid].append({"title": title, "year": year})
    save_json("alerts", data)
    await query.answer(f"🔔 Alert set for '{title}'!", show_alert=True)

async def alert_del_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    title = query.data.split("|", 1)[1]
    uid   = str(query.from_user.id)
    data  = load_json("alerts")
    if uid in data:
        data[uid] = [m for m in data[uid] if m["title"] != title]
        save_json("alerts", data)
    await query.message.edit_text(f"✅ *Alert removed:* _{title}_", parse_mode="Markdown")

async def alert_clear_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid  = str(query.from_user.id)
    data = load_json("alerts")
    data[uid] = []
    save_json("alerts", data)
    await query.message.edit_text("🗑 *All alerts cleared!*", parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════════
#            MYSTATS
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
# ═══════════════════════════════════════════════════════════════════
QUIZ_QUESTIONS = [
    {"q": "🎬 'Inception' ka director kaun hai?",
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
    {"q": "🎬 'Pushpa' main character ka naam kya hai?",
     "opts": ["Pushpa Raj", "Pushpa Kumar", "Pushpa Vikram", "Pushpa Singh"], "ans": 0},
    {"q": "🎬 'Tumbbad' konse genre ki movie hai?",
     "opts": ["Action", "Comedy", "Horror/Fantasy", "Romance"], "ans": 2},
    {"q": "🎬 'Andhadhun' mein main actor kaun hai?",
     "opts": ["Ayushmann Khurrana", "Rajkummar Rao", "Vicky Kaushal", "Irrfan Khan"], "ans": 0},
    {"q": "🎬 'Pathaan' mein SRK ka character naam kya hai?",
     "opts": ["Tiger", "Pathaan", "Kabir", "Arjun"], "ans": 1},
]

async def quiz_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_maintenance() and not is_admin(update.effective_user.id):
        await update.message.reply_text("🚧 Maintenance.")
        return
    loader = await update.message.reply_text("🎯 Loading quiz...\n" + progress_bar(0, 3))
    await animate_generic(loader, FRAMES["quiz"])
    try: await loader.delete()
    except: pass
    q = random.choice(QUIZ_QUESTIONS)
    context.user_data["quiz_ans"] = q["ans"]
    context.user_data["quiz_q"]   = q["q"]
    keyboard = [
        [InlineKeyboardButton(f"{['A','B','C','D'][i]}. {opt}", callback_data=f"quiz_ans_{i}")]
        for i, opt in enumerate(q["opts"])
    ]
    await update.message.reply_text(
        f"╔══════════════════╗\n║  🎮  *MOVIE QUIZ*  ║\n╚══════════════════╝\n\n"
        f"{q['q']}\n\n_Sahi jawab = +20 points_ ⭐\n\nChoose your answer 👇",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def quiz_answer_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    await query.answer()
    ans_idx = int(query.data.replace("quiz_ans_", ""))
    correct = context.user_data.get("quiz_ans", -1)
    uid     = str(query.from_user.id)
    if ans_idx == correct:
        users = load_json("users")
        if uid in users:
            users[uid]["points"] = users[uid].get("points", 0) + 20
            save_json("users", users)
        await query.message.edit_text(
            f"✅ *SAHI JAWAB!* 🎉\n\n+20 points added! ⭐\n\n"
            f"_{context.user_data.get('quiz_q', '')}_\n\n_/quiz — Ek aur try karo_ 🎯",
            parse_mode="Markdown"
        )
    else:
        q_text   = context.user_data.get("quiz_q", "")
        opts_key = next((qitem for qitem in QUIZ_QUESTIONS if qitem["q"] == q_text), None)
        correct_text = opts_key["opts"][correct] if opts_key and 0 <= correct < len(opts_key["opts"]) else "N/A"
        await query.message.edit_text(
            f"❌ *GALAT JAWAB!*\n\n✅ Sahi: *{correct_text}*\n\n_/quiz — Try again_ 🎯",
            parse_mode="Markdown"
        )


# ═══════════════════════════════════════════════════════════════════
#    ALL 6 SERVERS
# ═══════════════════════════════════════════════════════════════════
async def servers_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query      = update.callback_query
    await query.answer("🌐 Loading servers...")
    msg_id     = query.data.split("_", 1)[1]
    movie_data = context.user_data.get(msg_id)
    if not movie_data:
        await query.message.reply_text("⚠️ Session expired. Search again.")
        return
    loader = await query.message.reply_text("🌐 Loading servers...\n" + progress_bar(0, 4))
    await animate_generic(loader, FRAMES["server"])
    try: await loader.delete()
    except: pass
    urls   = movie_data["servers"]
    names  = movie_data["names"]
    title  = movie_data["title"]
    medals = ["🥇","🥈","🥉","🏅","🎖","🌟"]
    keyboard = [[InlineKeyboardButton(f"{medals[i]} {names[i]}", url=urls[i])] for i in range(6)]
    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data=f"bk_{msg_id}")])
    sent = await query.message.reply_text(
        f"╔═══════════════════════╗\n║  🌐  *6 DOWNLOAD SERVERS*  ║\n╚═══════════════════════╝\n\n"
        f"🎬 *{title}*\n━━━━━━━━━━━━━━━━━━\nPick any server 👇\n\n🦁 *Brave Browser = No Ads!*\n⏱ _Deletes in 1 min_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    asyncio.create_task(auto_delete(sent, 60))

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
    try: await loader.delete()
    except: pass
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
             InlineKeyboardButton("🎯 Similar", callback_data=f"sim_{msg_id}")]
        ])
    )


# ═══════════════════════════════════════════════════════════════════
#   /clean
# ═══════════════════════════════════════════════════════════════════
async def clean_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_admin(user.id):
        await update.message.reply_text(
            "╔═══════════════════╗\n║  🧹  *ADMIN CLEAN*  ║\n╚═══════════════════╝\n\n"
            "⚠️ Telegram only allows bots to delete their own messages.\n\n/admin",
            parse_mode="Markdown"
        )
        return
    try:
        await update.message.delete()
        confirm = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="🧹 *Your message deleted!*\n\n_Deletes in 5 seconds._",
            parse_mode="Markdown"
        )
        asyncio.create_task(auto_delete(confirm, 5))
    except Exception:
        await update.message.reply_text("❌ *Cannot delete.*", parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════════
#   MULTI-ADMIN MANAGEMENT
# ═══════════════════════════════════════════════════════════════════
async def addadmin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_owner(user.id):
        await update.message.reply_text("🚫 Sirf *Owner* ye command use kar sakta hai!", parse_mode="Markdown")
        return
    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ *Usage:*\n`/addadmin USER_ID` — Permanent\n`/addadmin USER_ID 24` — 24 ghante",
            parse_mode="Markdown"
        )
        return
    try:
        target_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ User ID sirf numbers mein!", parse_mode="Markdown")
        return
    if target_id == ADMIN_ID:
        await update.message.reply_text("⚠️ Owner ko admin banana zaroori nahi!", parse_mode="Markdown")
        return
    admins = load_json("admins")
    if len(args) >= 2:
        try:
            hours  = int(args[1])
            expiry = datetime.now().timestamp() + (hours * 3600)
            admins[str(target_id)] = {
                "id": target_id, "type": "temporary", "hours": hours,
                "expiry": expiry, "added_by": user.id,
                "added_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
            save_json("admins", admins)
            expiry_str = datetime.fromtimestamp(expiry).strftime("%d %b %Y, %I:%M %p")
            await update.message.reply_text(
                f"✅ *Temporary Admin Added!*\n\n👤 `{target_id}`\n⏱ `{hours} ghante`\n📅 Expires: `{expiry_str}`",
                parse_mode="Markdown"
            )
            try:
                await context.bot.send_message(chat_id=target_id, text=(
                    f"🎉 Aapko *CineBot* ka *Temporary Admin* banaya gaya hai!\n\n"
                    f"⏱ Duration: `{hours} ghante`\n📅 Expires: `{expiry_str}`\n\n/admin"
                ), parse_mode="Markdown")
            except Exception: pass
        except ValueError:
            await update.message.reply_text("❌ Ghante sirf numbers mein!", parse_mode="Markdown")
    else:
        admins[str(target_id)] = {
            "id": target_id, "type": "permanent",
            "added_by": user.id, "added_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        save_json("admins", admins)
        await update.message.reply_text(
            f"✅ *Permanent Admin Added!*\n\n👤 `{target_id}`",
            parse_mode="Markdown"
        )
        try:
            await context.bot.send_message(chat_id=target_id,
                text="🎉 Aapko *CineBot* ka *Permanent Admin* banaya gaya hai!\n\n/admin",
                parse_mode="Markdown")
        except Exception: pass

async def removeadmin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_owner(user.id):
        await update.message.reply_text("🚫 Sirf *Owner* ye command use kar sakta hai!", parse_mode="Markdown")
        return
    args = context.args
    if not args:
        await update.message.reply_text("❌ Usage: `/removeadmin USER_ID`", parse_mode="Markdown")
        return
    try:
        target_id = str(int(args[0]))
    except ValueError:
        await update.message.reply_text("❌ User ID sirf numbers mein!", parse_mode="Markdown")
        return
    admins = load_json("admins")
    if target_id not in admins:
        await update.message.reply_text(f"⚠️ User `{target_id}` admin list mein nahi hai.", parse_mode="Markdown")
        return
    del admins[target_id]
    save_json("admins", admins)
    await update.message.reply_text(f"✅ *Admin Removed!*\n\n👤 `{target_id}`", parse_mode="Markdown")

async def listadmins_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_owner(user.id):
        await update.message.reply_text("🚫 Sirf *Owner* ye dekh sakta hai!", parse_mode="Markdown")
        return
    admins = load_json("admins")
    now    = datetime.now().timestamp()
    if not admins:
        await update.message.reply_text(
            f"📋 *Admin List*\n\n_Koi extra admin nahi._\n\n👑 Owner: `{ADMIN_ID}`",
            parse_mode="Markdown"
        )
        return
    lines = [f"╔══════════════════════╗\n║  👑  *ADMIN LIST*  ║\n╚══════════════════════╝\n"]
    lines.append(f"👑 *Owner:* `{ADMIN_ID}` _(permanent)_\n")
    lines.append("━━━━━━━━━━━━━━━━━━━━━\n")
    active_count = 0
    expired_list = []
    for uid, info in admins.items():
        if info.get("type") == "permanent":
            lines.append(f"🔑 `{uid}` — *Permanent*\n   Added: `{info.get('added_at','?')}`")
            active_count += 1
        elif info.get("type") == "temporary":
            expiry = info.get("expiry", 0)
            if now < expiry:
                remaining = int((expiry - now) / 3600)
                exp_str   = datetime.fromtimestamp(expiry).strftime("%d %b, %I:%M %p")
                lines.append(f"⏱ `{uid}` — *Temp* ({remaining}h left)\n   Expires: `{exp_str}`")
                active_count += 1
            else:
                expired_list.append(uid)
    if expired_list:
        for uid in expired_list:
            del admins[uid]
        save_json("admins", admins)
    lines.append(f"\n✅ Active Admins: `{active_count}`")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def adm_addadmin_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_owner(query.from_user.id):
        await query.answer("🚫 Sirf Owner ye kar sakta hai!", show_alert=True)
        return ConversationHandler.END
    await query.answer()
    sent = await query.message.reply_text(
        "╔═══════════════════════╗\n║  👑  *ADD NEW ADMIN*  ║\n╚═══════════════════════╝\n\n"
        "`USER_ID` — Permanent\n`USER_ID GHANTE` — Temporary\n\n❌ /cancel",
        parse_mode="Markdown"
    )
    asyncio.create_task(auto_delete(sent, 120))
    return W_ADDADMIN

async def adm_addadmin_recv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return ConversationHandler.END
    text  = update.message.text.strip()
    parts = text.split()
    try:
        target_id = int(parts[0])
    except ValueError:
        await update.message.reply_text("❌ User ID numbers mein likhein.\n/cancel", parse_mode="Markdown")
        return W_ADDADMIN
    if target_id == ADMIN_ID:
        await update.message.reply_text("⚠️ Owner ko admin banana zaroori nahi!", parse_mode="Markdown")
        return ConversationHandler.END
    admins = load_json("admins")
    loader = await update.message.reply_text("⚙️ Processing...\n" + progress_bar(1, 3))
    if len(parts) >= 2:
        try:
            hours  = int(parts[1])
            expiry = datetime.now().timestamp() + (hours * 3600)
            admins[str(target_id)] = {
                "id": target_id, "type": "temporary", "hours": hours,
                "expiry": expiry, "added_by": update.effective_user.id,
                "added_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
            save_json("admins", admins)
            expiry_str = datetime.fromtimestamp(expiry).strftime("%d %b %Y, %I:%M %p")
            try: await loader.delete()
            except: pass
            sent = await update.message.reply_text(
                f"✅ *Admin Added!*\n\n👤 `{target_id}`\n🔑 Temporary — {hours}h\n📅 Expires: `{expiry_str}`",
                parse_mode="Markdown"
            )
            asyncio.create_task(auto_delete(sent, 60))
            try:
                await context.bot.send_message(chat_id=target_id, text=(
                    f"🎉 Aapko *CineBot* ka *Temporary Admin* banaya gaya!\n\n"
                    f"⏱ Duration: `{hours}h`\n📅 Expires: `{expiry_str}`\n\n/admin"
                ), parse_mode="Markdown")
            except Exception: pass
        except ValueError:
            try: await loader.delete()
            except: pass
            await update.message.reply_text("❌ Ghante galat hain!\nExample: `123456 24`\n/cancel", parse_mode="Markdown")
            return W_ADDADMIN
    else:
        admins[str(target_id)] = {
            "id": target_id, "type": "permanent",
            "added_by": update.effective_user.id,
            "added_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        save_json("admins", admins)
        try: await loader.delete()
        except: pass
        sent = await update.message.reply_text(
            f"✅ *Admin Added!*\n\n👤 `{target_id}`\n🔑 Permanent",
            parse_mode="Markdown"
        )
        asyncio.create_task(auto_delete(sent, 60))
        try:
            await context.bot.send_message(chat_id=target_id,
                text="🎉 Aapko *CineBot* ka *Permanent Admin* banaya gaya!\n\n/admin",
                parse_mode="Markdown")
        except Exception: pass
    return ConversationHandler.END

async def adm_listadmins_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_owner(query.from_user.id):
        await query.answer("🚫 Sirf Owner ye dekh sakta hai!", show_alert=True)
        return
    await query.answer()
    admins = load_json("admins")
    now    = datetime.now().timestamp()
    if not admins:
        sent = await query.message.reply_text(
            f"╔══════════════════════╗\n║  👑  *ADMIN LIST*  ║\n╚══════════════════════╝\n\n"
            f"_Koi extra admin nahi._\n\n👑 Owner: `{ADMIN_ID}`",
            parse_mode="Markdown"
        )
        asyncio.create_task(auto_delete(sent, 60))
        return
    lines = [f"╔══════════════════════╗\n║  👑  *ADMIN LIST*  ║\n╚══════════════════════╝\n"]
    lines.append(f"👑 *Owner:* `{ADMIN_ID}`\n")
    active_count = 0
    expired_list = []
    remove_btns  = []
    for uid, info in admins.items():
        if info.get("type") == "permanent":
            lines.append(f"🔑 `{uid}` — *Permanent*  Added: `{info.get('added_at','?')}`")
            active_count += 1
            remove_btns.append([InlineKeyboardButton(f"🗑 Remove {uid}", callback_data=f"adm_rmadmin_{uid}")])
        elif info.get("type") == "temporary":
            expiry = info.get("expiry", 0)
            if now < expiry:
                remaining = int((expiry - now) / 3600)
                exp_str   = datetime.fromtimestamp(expiry).strftime("%d %b, %I:%M %p")
                lines.append(f"⏱ `{uid}` — *Temp* ({remaining}h left)  Expires: `{exp_str}`")
                active_count += 1
                remove_btns.append([InlineKeyboardButton(f"🗑 Remove {uid}", callback_data=f"adm_rmadmin_{uid}")])
            else:
                expired_list.append(uid)
    if expired_list:
        for uid in expired_list:
            del admins[uid]
        save_json("admins", admins)
    lines.append(f"\n✅ Active Admins: `{active_count}`")
    remove_btns.append([InlineKeyboardButton("⬅️ Back", callback_data="adm_back")])
    sent = await query.message.reply_text(
        "\n".join(lines), parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(remove_btns) if remove_btns else None
    )
    asyncio.create_task(auto_delete(sent, 60))

async def adm_rmadmin_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_owner(query.from_user.id):
        await query.answer("🚫 Sirf Owner!", show_alert=True)
        return
    await query.answer()
    target_id = query.data.replace("adm_rmadmin_", "")
    admins    = load_json("admins")
    if target_id in admins:
        del admins[target_id]
        save_json("admins", admins)
        await query.message.edit_text(
            f"✅ *Admin Removed!*\n\n👤 `{target_id}`", parse_mode="Markdown"
        )
    else:
        await query.message.edit_text(f"⚠️ User `{target_id}` list mein nahi tha.", parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════════
#   ADMIN PANEL
# ═══════════════════════════════════════════════════════════════════
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 *Access Denied!*", parse_mode="Markdown")
        return
    loader = await update.message.reply_text("🔐 Authenticating...\n" + progress_bar(1, 4))
    await asyncio.sleep(0.4)
    try: await loader.edit_text("🗄 Loading data...\n" + progress_bar(2, 4))
    except: pass
    await asyncio.sleep(0.35)
    try: await loader.edit_text("📊 Building panel...\n" + progress_bar(3, 4))
    except: pass
    await asyncio.sleep(0.35)
    try: await loader.edit_text("✅ Ready!\n" + progress_bar(4, 4))
    except: pass
    await asyncio.sleep(0.25)
    try: await loader.delete()
    except: pass

    maint    = load_json("maintenance", {"active": False})
    users    = load_json("users")
    banned   = load_json("banned")
    admins   = load_json("admins")
    servers  = load_servers()
    ratings  = load_json("ratings")
    searches = sum(u.get("searches", 0) for u in users.values())
    status   = "🔴 ON" if maint.get("active") else "🟢 OFF"
    ai_stat  = "✅ Groq" if GROQ_API else "❌ No API"
    now      = datetime.now().timestamp()
    active_admins = sum(
        1 for v in admins.values()
        if v.get("type") == "permanent" or
           (v.get("type") == "temporary" and now < v.get("expiry", 0))
    )
    text = (
        f"╔════════════════════════════╗\n"
        f"║  👑  *ADMIN PANEL v9.1*  🎬  ║\n"
        f"╚════════════════════════════╝\n\n"
        f"━━━━━  📊 LIVE STATS  ━━━━━\n"
        f"👥 *Total Users:*    `{len(users)}`\n"
        f"🔎 *Total Searches:* `{searches}`\n"
        f"🚫 *Banned Users:*   `{len(banned)}`\n"
        f"⭐ *Rated Movies:*   `{len(ratings)}`\n"
        f"👑 *Active Admins:*  `{active_admins + 1}` (incl. owner)\n"
        f"🚧 *Maintenance:*    {status}\n"
        f"🤖 *AI Engine:*      {ai_stat}\n\n"
        f"━━━━━  📡 SERVERS  ━━━━━\n"
    )
    for i in range(1, 7):
        text += f"  `{i}.` _{servers[f's{i}']['name']}_\n"
    mb = "🔴 Turn Maintenance OFF" if maint.get("active") else "🟢 Turn Maintenance ON"
    keyboard = [
        [InlineKeyboardButton("📡 Manage Servers",       callback_data="adm_servers")],
        [InlineKeyboardButton(mb,                         callback_data="adm_maint_toggle")],
        [InlineKeyboardButton("✏️ Maintenance Message",  callback_data="adm_maint_msg")],
        [InlineKeyboardButton("📢 Broadcast",            callback_data="adm_broadcast")],
        [InlineKeyboardButton("🚫 Ban User",             callback_data="adm_ban"),
         InlineKeyboardButton("✅ Unban User",           callback_data="adm_unban")],
        [InlineKeyboardButton("📋 Activity Logs",        callback_data="adm_logs")],
        [InlineKeyboardButton("📊 Full Stats",           callback_data="adm_stats")],
        [InlineKeyboardButton("🔔 Send Alerts",          callback_data="adm_send_alerts")],
        [InlineKeyboardButton("📤 Export Users",         callback_data="adm_export")],
        [InlineKeyboardButton("👑 Add Admin",            callback_data="adm_addadmin"),
         InlineKeyboardButton("📋 Admin List",           callback_data="adm_listadmins")],
        [InlineKeyboardButton("🗑 Remove Admin",         callback_data="adm_listadmins")],
    ]
    sent = await update.message.reply_text(
        text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    asyncio.create_task(auto_delete(sent, 60))

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
    sent = await query.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    asyncio.create_task(auto_delete(sent, 60))

async def adm_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return ConversationHandler.END
    sk = query.data.replace("adm_edit_", "")
    context.user_data["editing_server"] = sk
    servers = load_servers()
    await query.message.reply_text(
        f"✏️ *Editing Server {sk[1]}*\n\nCurrent URL:\n`{servers[sk]['url']}`\n\n📝 Naya URL:\n/cancel",
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
        f"✅ URL saved!\n\n📝 Display name bhejo (current: `{load_servers()[sk]['name']}`):\n/cancel",
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
    try: await loader.delete()
    except: pass
    sent = await update.message.reply_text(
        f"✅ *Server {sk[1]} Updated!*\n\n🏷 `{name}`\n🔗 `{url}`", parse_mode="Markdown"
    )
    asyncio.create_task(auto_delete(sent, 60))
    return ConversationHandler.END

async def adm_maint_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    maint = load_json("maintenance", {"active": False, "message": "🔧 Maintenance..."})
    maint["active"] = not maint["active"]
    save_json("maintenance", maint)
    frames = FRAMES["maint_on"] if maint["active"] else FRAMES["maint_off"]
    loader = await query.message.reply_text(frames[0] + "\n" + progress_bar(0, len(frames)))
    await animate_generic(loader, frames)
    try: await loader.delete()
    except: pass
    if maint["active"]:
        users   = load_json("users")
        success = failed = 0
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
        sent = await query.message.reply_text(
            f"🚨 *Maintenance ON!*\n✅ `{success}` sent | ❌ `{failed}` failed", parse_mode="Markdown"
        )
    else:
        sent = await query.message.reply_text("✅ *Maintenance OFF! Bot LIVE!*", parse_mode="Markdown")
    asyncio.create_task(auto_delete(sent, 60))

async def adm_maint_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return ConversationHandler.END
    maint = load_json("maintenance", {"active": False, "message": ""})
    await query.message.reply_text(
        f"✏️ Current message:\n_{maint.get('message', '')}_\n\n📝 Naya message:\n/cancel",
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
    try: await loader.delete()
    except: pass
    sent = await update.message.reply_text(f"✅ *Updated!*\n\n_{maint['message']}_", parse_mode="Markdown")
    asyncio.create_task(auto_delete(sent, 60))
    return ConversationHandler.END

async def adm_broadcast_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return ConversationHandler.END
    await query.message.reply_text(
        "📢 *Broadcast Message*\n\nSabhi users ko message:\n\n/cancel", parse_mode="Markdown"
    )
    return W_BROADCAST

async def adm_do_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    msg     = update.message.text.strip()
    users   = load_json("users")
    success = failed = 0
    loader  = await update.message.reply_text("📢 Broadcasting...\n" + progress_bar(0, 3))
    await animate_generic(loader, FRAMES["broadcast"])
    try: await loader.delete()
    except: pass
    for uid in list(users.keys()):
        if int(uid) == ADMIN_ID: continue
        try:
            await context.bot.send_message(
                chat_id=int(uid),
                text=f"📢 *CineBot Announcement*\n━━━━━━━━━━━━━━━━━━\n\n{msg}",
                parse_mode="Markdown"
            )
            success += 1
        except: failed += 1
        await asyncio.sleep(0.05)
    sent = await update.message.reply_text(
        f"✅ *Broadcast Done!*\n✅ Sent: `{success}`\n❌ Failed: `{failed}`", parse_mode="Markdown"
    )
    asyncio.create_task(auto_delete(sent, 60))
    return ConversationHandler.END

async def adm_ban_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return ConversationHandler.END
    await query.message.reply_text("🚫 *Ban User*\n\nUser ID bhejo:\n/cancel", parse_mode="Markdown")
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
    sent = await update.message.reply_text(f"🚫 *User `{ban_id}` banned!*", parse_mode="Markdown")
    asyncio.create_task(auto_delete(sent, 60))
    return ConversationHandler.END

async def adm_unban_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    banned = load_json("banned")
    if not banned:
        await query.message.reply_text("✅ *No banned users!*", parse_mode="Markdown")
        return
    text = "🔓 *Banned Users:*\n━━━━━━━━━━━━━━━━━━\n\n"
    keyboard = []
    for uid, dt in list(banned.items())[:10]:
        text += f"• `{uid}` — {dt}\n"
        keyboard.append([InlineKeyboardButton(f"✅ Unban {uid}", callback_data=f"dounban_{uid}")])
    sent = await query.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    asyncio.create_task(auto_delete(sent, 60))

async def do_unban_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    uid    = query.data.replace("dounban_", "")
    banned = load_json("banned")
    if uid in banned:
        del banned[uid]
        save_json("banned", banned)
        await query.message.edit_text(f"✅ *User `{uid}` unbanned!*", parse_mode="Markdown")
    else:
        await query.message.edit_text(f"⚠️ User `{uid}` not in banned list.", parse_mode="Markdown")

async def adm_export_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    users = load_json("users")
    lines = ["ID,Name,Username,Joined,Searches,Points,Refs"]
    for u in users.values():
        lines.append(f"{u.get('id','')},{u.get('name','')},{u.get('username','')},{u.get('joined','')},{u.get('searches',0)},{u.get('points',0)},{u.get('refs',0)}")
    export_path = "users_export.txt"
    with open(export_path, "w") as f:
        f.write("\n".join(lines))
    with open(export_path, "rb") as doc_file:
        await context.bot.send_document(
            chat_id=query.from_user.id, document=doc_file,
            caption=f"📤 *Users Export*\n`{len(users)}` total users",
            parse_mode="Markdown"
        )
    sent = await query.message.reply_text("✅ *Export sent to your DM!*", parse_mode="Markdown")
    asyncio.create_task(auto_delete(sent, 30))

async def adm_logs_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    logs  = load_json("logs")
    today = str(date.today())
    t_logs = logs.get(today, [])
    text  = f"╔═════════════════════════╗\n║  📋  *ACTIVITY LOGS*  ║\n╚═════════════════════════╝\n\n"
    text += f"📊 Today: `{len(t_logs)}` searches\n━━━━━━━━━━━━━━━━━━\n\n"
    for entry in t_logs[-10:]:
        text += f"`{entry['time']}` — {entry['movie']} by `{entry['user']}`\n"
    if not t_logs:
        text += "_No activity today_"
    sent = await query.message.reply_text(text, parse_mode="Markdown")
    asyncio.create_task(auto_delete(sent, 60))

async def adm_stats_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    users    = load_json("users")
    maint    = load_json("maintenance", {"active": False})
    banned   = load_json("banned")
    trending = get_trending(5)
    searches = sum(u.get("searches", 0) for u in users.values())
    ratings  = load_json("ratings")
    status   = "🔴 ON" if maint.get("active") else "🟢 OFF"
    ai_stat  = "✅ Groq (Llama 3.3)" if GROQ_API else "❌ GROQ_API not set"
    text  = f"╔══════════════════╗\n║  📊  *FULL STATS*  ║\n╚══════════════════╝\n\n"
    text += f"👥 Users: `{len(users)}`\n🔎 Searches: `{searches}`\n🚫 Banned: `{len(banned)}`\n"
    text += f"⭐ Rated: `{len(ratings)}`\n🚧 Maintenance: {status}\n🤖 AI: {ai_stat}\n\n"
    if trending:
        text += "🔥 *Top Searched:*\n"
        for i, (t, c) in enumerate(trending, 1):
            text += f"  `{i}.` {t} — `{c}x`\n"
    sent = await query.message.reply_text(text, parse_mode="Markdown")
    asyncio.create_task(auto_delete(sent, 60))

async def adm_send_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    alerts = load_json("alerts")
    sent_c = 0
    for uid, movies in alerts.items():
        for movie_item in movies:
            try:
                await context.bot.send_message(
                    chat_id=int(uid),
                    text=f"🔔 *Movie Alert!*\n\n🎬 *{movie_item['title']}* ({movie_item['year']})\n\nSearch karo!",
                    parse_mode="Markdown"
                )
                sent_c += 1
            except: pass
            await asyncio.sleep(0.05)
    sent = await query.message.reply_text(f"🔔 *Alerts sent:* `{sent_c}`", parse_mode="Markdown")
    asyncio.create_task(auto_delete(sent, 60))

async def adm_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    global bot_servers
    bot_servers = {k: v.copy() for k, v in DEFAULT_SERVERS.items()}
    save_json("servers", bot_servers)
    sent = await query.message.reply_text("🔄 *All 6 Servers Reset!* ✅", parse_mode="Markdown")
    asyncio.create_task(auto_delete(sent, 60))

async def adm_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    maint    = load_json("maintenance", {"active": False})
    users    = load_json("users")
    banned   = load_json("banned")
    admins   = load_json("admins")
    ratings  = load_json("ratings")
    searches = sum(u.get("searches", 0) for u in users.values())
    status   = "🔴 ON" if maint.get("active") else "🟢 OFF"
    ai_stat  = "✅ Groq" if GROQ_API else "❌ No API"
    now      = datetime.now().timestamp()
    active_admins = sum(
        1 for v in admins.values()
        if v.get("type") == "permanent" or
           (v.get("type") == "temporary" and now < v.get("expiry", 0))
    )
    mb = "🔴 Turn Maintenance OFF" if maint.get("active") else "🟢 Turn Maintenance ON"
    text = (
        f"╔════════════════════════════╗\n"
        f"║  👑  *ADMIN PANEL v9.1*  🎬  ║\n"
        f"╚════════════════════════════╝\n\n"
        f"👥 Users: `{len(users)}`  🔎 Searches: `{searches}`\n"
        f"🚫 Banned: `{len(banned)}`  ⭐ Rated: `{len(ratings)}`\n"
        f"👑 Admins: `{active_admins + 1}`  🚧 Maintenance: {status}\n"
        f"🤖 AI: {ai_stat}\n"
    )
    keyboard = [
        [InlineKeyboardButton("📡 Manage Servers",       callback_data="adm_servers")],
        [InlineKeyboardButton(mb,                         callback_data="adm_maint_toggle")],
        [InlineKeyboardButton("✏️ Maintenance Message",  callback_data="adm_maint_msg")],
        [InlineKeyboardButton("📢 Broadcast",            callback_data="adm_broadcast")],
        [InlineKeyboardButton("🚫 Ban User",             callback_data="adm_ban"),
         InlineKeyboardButton("✅ Unban User",           callback_data="adm_unban")],
        [InlineKeyboardButton("📋 Activity Logs",        callback_data="adm_logs")],
        [InlineKeyboardButton("📊 Full Stats",           callback_data="adm_stats")],
        [InlineKeyboardButton("🔔 Send Alerts",          callback_data="adm_send_alerts")],
        [InlineKeyboardButton("📤 Export Users",         callback_data="adm_export")],
        [InlineKeyboardButton("👑 Add Admin",            callback_data="adm_addadmin"),
         InlineKeyboardButton("📋 Admin List",           callback_data="adm_listadmins")],
        [InlineKeyboardButton("🗑 Remove Admin",         callback_data="adm_listadmins")],
    ]
    sent = await query.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    asyncio.create_task(auto_delete(sent, 60))


# Cancel
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ *Cancelled.*", parse_mode="Markdown")
    return ConversationHandler.END

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ai_status = "✅ Groq AI Active" if GROQ_API else "⚠️ Set GROQ_API for AI features"
    await update.message.reply_text(
        "╔═══════════════════╗\n║  ℹ️  *CINEBOT HELP*  ║\n╚═══════════════════╝\n\n"
        f"🤖 *AI Status:* {ai_status}\n\n"
        "🔎 *Movie Search:* Seedha naam type karo\n\n"
        "📋 *Commands:*\n"
        "🎬 /movieinfo    — TMDB rich movie info\n"
        "📝 /fullreview   — Detailed AI review ✅NEW\n"
        "🎭 /moodmatch    — Mood match analysis ✅NEW\n"
        "🌟 /castinfo     — Cast & director info ✅NEW\n"
        "❓ /trivia       — MCQ trivia question ✅NEW\n"
        "🤖 /suggest      — AI recommendations\n"
        "🔍 /plotsearch   — Search by plot\n"
        "🎭 /mood         — Mood-based picks\n"
        "⚖️ /compare      — Compare 2 movies\n"
        "🔥 /trending     — Weekly trending\n"
        "📅 /upcoming     — Coming soon\n"
        "🎲 /random       — Random movie\n"
        "🎯 /daily        — Today's featured\n"
        "❤️ /watchlist    — Saved movies\n"
        "🔔 /alerts       — Release alerts\n"
        "🎮 /quiz         — Movie trivia\n"
        "🏆 /leaderboard  — Top users\n"
        "📜 /history      — Search history\n"
        "👥 /refer        — Refer & earn\n"
        "🌐 /lang         — Language filter\n"
        "📊 /mystats      — Points & badge\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🎯 *Movie card pe naye buttons:*\n"
        "📝 Full Review • 🎭 Mood Match\n"
        "🌟 Cast Analysis • ❓ Trivia Quiz\n"
        "🔥 Full AI Package (sab ek saath)\n\n"
        "🦁 *Brave Browser = No Ads!*",
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
        CallbackQueryHandler(adm_addadmin_cb,      pattern="^adm_addadmin$"),
        CallbackQueryHandler(suggest_cmd,          pattern="^cmd_suggest$"),
        CallbackQueryHandler(plotsearch_cmd,       pattern="^cmd_plotsearch$"),
        CallbackQueryHandler(mood_cmd,             pattern="^cmd_mood$"),
        CallbackQueryHandler(compare_cmd,          pattern="^cmd_compare$"),
        CommandHandler("suggest",    suggest_cmd),
        CommandHandler("plotsearch", plotsearch_cmd),
        CommandHandler("mood",       mood_cmd),
        CommandHandler("compare",    compare_cmd),
    ],
    states={
        W_URL:         [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_recv_url)],
        W_NAME:        [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_recv_name)],
        W_MAINT_MSG:   [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_recv_maint_msg)],
        W_BROADCAST:   [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_do_broadcast)],
        W_BAN_USER:    [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_do_ban)],
        W_AI_QUERY:    [MessageHandler(filters.TEXT & ~filters.COMMAND, suggest_receive)],
        W_PLOT_SEARCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, plotsearch_receive)],
        W_MOOD:        [MessageHandler(filters.TEXT & ~filters.COMMAND, mood_receive)],
        W_COMPARE_1:   [MessageHandler(filters.TEXT & ~filters.COMMAND, compare_recv1)],
        W_COMPARE_2:   [MessageHandler(filters.TEXT & ~filters.COMMAND, compare_recv2)],
        W_ADDADMIN:    [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_addadmin_recv)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)

# Commands
application.add_handler(CommandHandler("start",       start))
application.add_handler(CommandHandler("help",        help_cmd))
application.add_handler(CommandHandler("trending",    trending_cmd))
application.add_handler(CommandHandler("random",      random_cmd))
application.add_handler(CommandHandler("daily",       daily_cmd))
application.add_handler(CommandHandler("upcoming",    upcoming_cmd))
application.add_handler(CommandHandler("watchlist",   watchlist_cmd))
application.add_handler(CommandHandler("alerts",      alerts_cmd))
application.add_handler(CommandHandler("quiz",        quiz_cmd))
application.add_handler(CommandHandler("refer",       refer_cmd))
application.add_handler(CommandHandler("lang",        lang_cmd))
application.add_handler(CommandHandler("mystats",     mystats_cmd))
application.add_handler(CommandHandler("admin",       admin_panel))
application.add_handler(CommandHandler("clean",       clean_cmd))
application.add_handler(CommandHandler("leaderboard", leaderboard_cmd))
application.add_handler(CommandHandler("history",     history_cmd))
application.add_handler(CommandHandler("movieinfo",   movieinfo_cmd))
application.add_handler(CommandHandler("addadmin",    addadmin_cmd))
application.add_handler(CommandHandler("removeadmin", removeadmin_cmd))
application.add_handler(CommandHandler("admins",      listadmins_cmd))
# ✅ NEW commands
application.add_handler(CommandHandler("fullreview",  fullreview_cmd))
application.add_handler(CommandHandler("moodmatch",   moodmatch_cmd))
application.add_handler(CommandHandler("castinfo",    castinfo_cmd))
application.add_handler(CommandHandler("trivia",      trivia_cmd))

# Admin callbacks
application.add_handler(CallbackQueryHandler(adm_servers_cb,    pattern="^adm_servers$"))
application.add_handler(CallbackQueryHandler(adm_maint_toggle,  pattern="^adm_maint_toggle$"))
application.add_handler(CallbackQueryHandler(adm_reset,         pattern="^adm_reset$"))
application.add_handler(CallbackQueryHandler(adm_stats_cb,      pattern="^adm_stats$"))
application.add_handler(CallbackQueryHandler(adm_back,          pattern="^adm_back$"))
application.add_handler(CallbackQueryHandler(adm_logs_cb,       pattern="^adm_logs$"))
application.add_handler(CallbackQueryHandler(adm_send_alerts,   pattern="^adm_send_alerts$"))
application.add_handler(CallbackQueryHandler(adm_unban_prompt,  pattern="^adm_unban$"))
application.add_handler(CallbackQueryHandler(do_unban_cb,       pattern="^dounban_"))
application.add_handler(CallbackQueryHandler(adm_export_cb,     pattern="^adm_export$"))
application.add_handler(CallbackQueryHandler(adm_listadmins_cb, pattern="^adm_listadmins$"))
application.add_handler(CallbackQueryHandler(adm_rmadmin_cb,    pattern="^adm_rmadmin_"))

# ✅ NEW analysis callbacks
application.add_handler(CallbackQueryHandler(fullreview_cb,   pattern="^frev_"))
application.add_handler(CallbackQueryHandler(moodmatch_cb,    pattern="^mood_match_"))
application.add_handler(CallbackQueryHandler(castanalysis_cb, pattern="^cast_"))
application.add_handler(CallbackQueryHandler(trivia_cb,       pattern="^trivia_"))
application.add_handler(CallbackQueryHandler(fullpackage_cb,  pattern="^pkg_"))

# User callbacks
application.add_handler(master_conv)
application.add_handler(CallbackQueryHandler(start_btn_cb,   pattern="^cmd_(?!suggest|plotsearch|mood|compare)"))
application.add_handler(CallbackQueryHandler(start_btn_cb,   pattern="^open_admin$"))
application.add_handler(CallbackQueryHandler(wl_save_cb,     pattern="^wl_save\\|"))
application.add_handler(CallbackQueryHandler(wl_clear_cb,    pattern="^wl_clear$"))
application.add_handler(CallbackQueryHandler(alert_add_cb,   pattern="^alert_add\\|"))
application.add_handler(CallbackQueryHandler(alert_del_cb,   pattern="^alert_del\\|"))
application.add_handler(CallbackQueryHandler(alert_clear_cb, pattern="^alert_clear$"))
application.add_handler(CallbackQueryHandler(similar_cb,     pattern="^sim_"))
application.add_handler(CallbackQueryHandler(servers_cb,     pattern="^srv_"))
application.add_handler(CallbackQueryHandler(back_cb,        pattern="^bk_"))
application.add_handler(CallbackQueryHandler(director_cb,    pattern="^dir_"))
application.add_handler(CallbackQueryHandler(quiz_answer_cb, pattern="^quiz_ans_"))
application.add_handler(CallbackQueryHandler(setlang_cb,     pattern="^setlang_"))
application.add_handler(CallbackQueryHandler(pick_cb,        pattern="^pick_"))
application.add_handler(CallbackQueryHandler(review_cb,      pattern="^rev_"))
application.add_handler(CallbackQueryHandler(funfact_cb,     pattern="^fun_"))
application.add_handler(CallbackQueryHandler(rate_cb,        pattern="^rate_"))
application.add_handler(CallbackQueryHandler(dorat_cb,       pattern="^dorat_"))

# Movie search (last)
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, movie))

print("✅ CineBot v9.1 — Groq AI + Full Analysis Package integrated!")
application.run_polling()
