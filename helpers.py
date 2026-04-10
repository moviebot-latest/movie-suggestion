# ╔══════════════════════════════════════════╗
# ║  helpers.py — Progress bars, animations  ║
# ║  Edit to change UI / badge system        ║
# ╚══════════════════════════════════════════╝
import asyncio, requests
from urllib.parse import quote
from config import TMDB_API
from config import now_ist

async def auto_delete(msg, delay=60, user_data=None, key=None):
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except Exception:
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
                    days  = (rdate.date() - today_ist()).days
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


