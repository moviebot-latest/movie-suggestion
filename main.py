import os
import json
import re
import time
import random
import logging
import sqlite3
import threading
import asyncio
import traceback
import calendar
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any, Tuple
from urllib.parse import urlparse, quote

import requests
import aiohttp
from bs4 import BeautifulSoup

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    filters,
)

logging.basicConfig(level=logging.INFO)

# ═══════════════════════════════════════════════════════════════════
#                      CONFIG / ENV VARIABLES
# ═══════════════════════════════════════════════════════════════════
TOKEN = os.getenv("TOKEN") or os.getenv("BOT_TOKEN")
GROQ_API = os.getenv("GROQ_API") or os.getenv("GROQ_API_KEY")
TMDB_API = os.getenv("TMDB_API") or os.getenv("TMDB_API_KEY")
OMDB_API = os.getenv("OMDB_API") or os.getenv("OMDB_API_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or 0)

# Aliases used elsewhere in the file with the "_KEY" suffix
TMDB_API_KEY = TMDB_API
OMDB_API_KEY = OMDB_API

# Timezone: Indian Standard Time (UTC+5:30), used for all display timestamps
IST = timezone(timedelta(hours=5, minutes=30))

# Groq REST API config (used by the lightweight HTTP-based AI calls)
GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

def now_ist() -> datetime:
    """Current time as an IST-aware datetime."""
    return datetime.now(IST)

def today_ist():
    """Current date (no time component) in IST."""
    return datetime.now(IST).date()

if not TOKEN:
    raise RuntimeError("TOKEN env variable is not set. Set it in Render's Environment tab.")

# Optional: Groq Python SDK client (used by HealerV4 for AI-assisted domain
# recovery). Falls back to None if the `groq` package isn't installed or no
# API key is set — the bot still runs fine, just without SDK-based healing.
_groq_sdk_client = None
if GROQ_API:
    try:
        from groq import Groq as _GroqSDK
        _groq_sdk_client = _GroqSDK(api_key=GROQ_API)
    except Exception as _e:
        print(f"⚠️ Groq SDK not available ({_e}); falling back to REST calls only.")
        _groq_sdk_client = None

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
    "s1": {"name": "HdHub4u",     "url": os.getenv("SERVER_S1_URL", "https://new6.hdhub4u.fo/search.html?q=")},
    "s2": {"name": "123Mkv",      "url": os.getenv("SERVER_S2_URL", "https://123mkv.stream/?s=")},
    "s3": {"name": "MkvCinemas",  "url": os.getenv("SERVER_S3_URL", "https://mkvcinemas.sb/?s=")},
    "s4": {"name": "WorldFree4u", "url": os.getenv("SERVER_S4_URL", "https://worldfree4u.earth/?s=")},
    "s5": {"name": "Bolly4u",     "url": os.getenv("SERVER_S5_URL", "https://bolly4u.camera/?s=")},
    "s6": {"name": "FilmyZilla",  "url": os.getenv("SERVER_S6_URL", "https://1filmyfly.mov/site-1.html?to-search=")},
}

def load_json(key, default=None):
    fp = FILES[key]
    if default is None: default = {}
    if os.path.exists(fp):
        try:
            with open(fp) as f: return json.load(f)
        except Exception as e:
            print(f"⚠️ load_json error [{key}]: {e}")
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


# ═══════════════════════════════════════════════════════════════════
#  SMART SEARCH URL BUILDER
# ═══════════════════════════════════════════════════════════════════
def build_search_url(base_url: str, movie_title: str) -> str:
    title         = movie_title.strip()
    encoded_smart = quote(title, safe="").replace("%20", "+")
    if re.search(r'\?[a-z\-_]+=\s*$', base_url, re.IGNORECASE):
        return base_url + encoded_smart
    if base_url.endswith("/"):
        return base_url + f"?s={encoded_smart}"
    if "?" not in base_url:
        return base_url + f"/?s={encoded_smart}"
    if "?" in base_url and not base_url.endswith("="):
        return base_url + f"&s={encoded_smart}"
    return base_url + encoded_smart


# ═══════════════════════════════════════════════════════════════════
#  DIRECT MOVIE LINK SCRAPER
# ═══════════════════════════════════════════════════════════════════
_MOVIE_LINK_SELECTORS = [
    "h2.entry-title a", "h3.entry-title a", "h1.entry-title a", ".entry-title a",
    "article h2 a", "article h3 a", ".post-title a", ".item-title a",
    ".recent-movies .name a", ".gridlove-post-title a",
    ".film-detail .film-name a", ".flw-item .film-name a",
    ".movie-title a", ".title a",
    "h2 a[href*='download']", "h2 a[href*='movie']",
    "h3 a[href*='download']", ".search-results a", "#content a[href]",
]

def _title_match_score(link_text: str, movie_title: str) -> int:
    if not link_text or not movie_title: return 0
    lt    = link_text.lower().strip()
    mt    = re.sub(r'\b(19|20)\d{2}\b', '', movie_title.lower()).strip()
    words = [w for w in mt.split() if len(w) > 1]
    if mt in lt or movie_title.lower() in lt: return 100
    if words and all(w in lt for w in words): return 85
    matched = sum(1 for w in words if w in lt)
    if words and matched >= max(1, len(words) // 2): return 50 + matched * 5
    return 0

async def _scrape_direct_link(search_url: str, movie_title: str, timeout_sec: int = 10) -> Optional[str]:
    if not _BS4_AVAILABLE: return None
    try:
        timeout = aiohttp.ClientTimeout(sock_connect=6, sock_read=timeout_sec, total=timeout_sec + 4)
        async with aiohttp.ClientSession(timeout=timeout) as sess:
            async with sess.get(search_url, headers=_get_srv_headers(), allow_redirects=True, ssl=False) as resp:
                if resp.status not in SRV_UP_CODES: return None
                html = await resp.text(errors="ignore")
        soup = BeautifulSoup(html, "html.parser")
        base = f"{urlparse(search_url).scheme}://{urlparse(search_url).netloc}"
        best_url, best_score = None, 0
        for selector in _MOVIE_LINK_SELECTORS:
            try: links = soup.select(selector)
            except Exception: continue
            for tag in links[:8]:
                href = tag.get("href", "")
                text = tag.get_text(strip=True)
                if not href or href in ("#", "/", "javascript:void(0)"): continue
                skip_keywords = ["home","contact","about","privacy","dmca","login","register","category","tag","page"]
                if any(k in href.lower() for k in skip_keywords): continue
                if href.startswith("//"): href = "https:" + href
                elif href.startswith("/"): href = base + href
                elif not href.startswith("http"): href = base + "/" + href
                score = _title_match_score(text, movie_title)
                if score > best_score:
                    best_score = score
                    best_url   = href
            if best_score >= 80: break
        return best_url if best_score >= 40 else None
    except asyncio.TimeoutError: return None
    except Exception as e:
        print(f"⚠️ Scrape error ({urlparse(search_url).netloc}): {e}")
        return None

async def resolve_server_urls(search_urls: list, movie_title: str) -> list:
    tasks        = [_scrape_direct_link(url, movie_title) for url in search_urls]
    direct_links = await asyncio.gather(*tasks, return_exceptions=True)
    final_urls   = []
    for i, (search_url, direct) in enumerate(zip(search_urls, direct_links)):
        if isinstance(direct, Exception) or not direct:
            final_urls.append(search_url)
        else:
            final_urls.append(direct)
    return final_urls


# ═══════════════════════════════════════════════════════════════════
#                    USER MANAGEMENT
# ═══════════════════════════════════════════════════════════════════
def register_user(user, ref_id=None):
    users = load_json("users")
    uid   = str(user.id)
    if uid not in users:
        users[uid] = {
            "id": user.id, "name": user.full_name,
            "username": user.username or "N/A",
            "joined": now_ist().strftime("%Y-%m-%d %H:%M"),
            "searches": 0, "points": 0, "lang": "Any",
            "ref_by": ref_id, "refs": 0, "msg_ids": [],
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
    today = str(today_ist())
    if today not in logs: logs[today] = []
    logs[today].append({"user": user_id, "movie": title, "time": now_ist().strftime("%I:%M %p")})
    while len(logs) > 30:
        oldest = sorted(logs.keys())[0]
        del logs[oldest]
    save_json("logs", logs)
    history = load_json("history")
    uid     = str(user_id)
    if uid not in history: history[uid] = []
    history[uid] = [h for h in history[uid] if h["movie"] != title]
    history[uid].insert(0, {"movie": title, "time": now_ist().strftime("%d %b %I:%M %p")})
    history[uid] = history[uid][:20]
    save_json("history", history)

def get_trending(n=10):
    data = load_json("searches")
    return sorted(data.items(), key=lambda x: x[1], reverse=True)[:n]

def is_banned(user_id):   return str(user_id) in load_json("banned")
def is_owner(uid):        return uid == ADMIN_ID

def is_admin(uid):
    if uid == ADMIN_ID: return True
    admins = load_json("admins")
    entry  = admins.get(str(uid))
    if not entry: return False
    if entry.get("type") == "permanent": return True
    if entry.get("type") == "temporary":
        expiry = entry.get("expiry", 0)
        if now_ist().timestamp() < expiry: return True
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
    try: await msg.delete()
    except Exception: pass
    if user_data is not None and key is not None:
        user_data.pop(key, None)


# ═══════════════════════════════════════════════════════════════════
#                  ANIMATIONS
# ═══════════════════════════════════════════════════════════════════
def progress_bar(current, total, length=10):
    if total == 0: return "[··········] 0%"
    filled = int(length * current / total)
    bar    = "█" * filled + "·" * (length - filled)
    pct    = int(100 * current / total)
    return f"[{bar}] {pct}%"

async def animate_search(msg):
    steps = [(1,6,"🎬 Searching"),(2,6,"🎬 Fetching"),(3,6,"🎬 Loading"),
             (4,6,"🎬 Almost"),(5,6,"🎬 Done"),(6,6,"✅ Found")]
    for cur, total, label in steps:
        bar = progress_bar(cur, total)
        try:
            await msg.edit_text(f"{label}...\n{bar}", parse_mode="Markdown")
            await asyncio.sleep(0.35)
        except: pass

async def animate_generic(msg, frames, delay=0.45):
    for i, frame in enumerate(frames):
        bar = progress_bar(i + 1, len(frames))
        try:
            await msg.edit_text(f"{frame}\n{bar}", parse_mode="Markdown")
            await asyncio.sleep(delay)
        except: pass

FRAMES = {
    "server":       ["🌐 Connecting","🌐 Loading","⚡ Almost","✅ Ready"],
    "back":         ["🔄 Returning","🔄 Loading","✅ Back"],
    "save":         ["💾 Saving","💾 Writing","✅ Saved"],
    "maint_on":     ["🔧 Activating","🔧 Processing","🚨 Maintenance ON"],
    "maint_off":    ["🟢 Restoring","🟢 Processing","✅ Bot LIVE"],
    "broadcast":    ["📢 Sending","📢 Delivering","✅ Done"],
    "ai":           ["🤖 Thinking","🤖 Processing","✨ Ready"],
    "similar":      ["🔍 Analyzing","🔍 Matching","🎬 Found"],
    "quiz":         ["🎯 Preparing","🎯 Loading","✅ Ready"],
    "daily":        ["🎬 Picking","🎬 Loading","✅ Today's Pick"],
    "review":       ["🤖 Reading","🤖 Analyzing","✍️ Writing","✅ Done"],
    "compare":      ["🔍 Loading 1st","🔍 Loading 2nd","⚖️ Comparing","✅ Ready"],
    "mood":         ["🎭 Reading mood","🤖 Thinking","🎬 Picking","✅ Ready"],
    "fullreview":   ["📖 Reading plot","🤖 Analyzing","✍️ Writing review","✅ Done"],
    "moodmatch":    ["🎭 Sensing mood","🤖 Matching","🍿 Perfect pick!","✅ Ready"],
    "castanalysis": ["🎬 Loading cast","🌟 Analyzing","✅ Done"],
    "trivia":       ["🧠 Thinking","❓ Creating question","✅ Ready"],
    "fullpackage":  ["📖 Review","🎯 Similar","🎭 Mood","🌟 Cast","✅ All Done!"],
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
                    if days >= 0: results.append((m["title"], rd, days))
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
        crew     = r2.json().get("crew", [])
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
    if not GROQ_API: return None
    headers = {"Authorization": f"Bearer {GROQ_API}", "Content-Type": "application/json"}
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
#          GROQ AI — MOVIE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════
async def ai_fix_movie_name(raw_name: str) -> str:
    if not GROQ_API: return raw_name
    result = await ai_ask(
        f"User typed this movie name: '{raw_name}'\n"
        "Fix spelling/Hinglish and return ONLY the correct English movie title.\n"
        "Examples: 'rrr' → 'RRR', 'kgf2' → 'KGF Chapter 2', 'andha dhun' → 'Andhadhun'\n"
        "Return ONLY the movie title, nothing else."
    )
    if result:
        fixed = result.strip().strip('"').strip("'")
        if len(fixed) < 60: return fixed
    return raw_name

async def ai_recommend(query: str) -> Optional[str]:
    return await ai_ask(
        f"You are a movie expert. {query}\nGive exactly 5 recommendations.\n"
        "Format: 🎬 Title (Year) — One line reason\nBe concise. Reply in same language as query."
    )

async def ai_plot_search(plot_desc: str) -> Optional[str]:
    return await ai_ask(
        f"A user describes a movie plot: '{plot_desc}'\n"
        "Identify the most likely movie(s). Give top 3 guesses.\n"
        "Format: 🎬 Title (Year) — Why it matches\nBe concise."
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
        "Reply in Hinglish."
    )

async def ai_mood_recommend(mood: str) -> Optional[str]:
    return await ai_ask(
        f"User ka mood hai: '{mood}'\n"
        "Is mood ke hisaab se 5 perfect movies recommend karo.\n"
        "Format: 🎬 Title (Year) — Why perfect for this mood\nBe empathetic and fun. Reply in Hinglish."
    )

async def ai_compare_movies(movie1: str, movie2: str) -> Optional[str]:
    return await ai_ask(
        f"Compare these two movies:\nMovie 1: {movie1}\nMovie 2: {movie2}\n\n"
        "Compare on: Story, Acting, Direction, Entertainment, Overall\n"
        "End with a winner recommendation.\nReply in Hinglish. Be fun and opinionated."
    )

async def ai_full_review(title: str, year: str, genre: str, plot: str,
                         rating: str, director: str, actors: str, awards: str) -> Optional[str]:
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
    return await ai_ask(
        f"'{title}' ({year}) — Genre: {genre}\n\n"
        "Is movie jaisi 5 movies recommend karo. Ek solid reason do kyun similar hai.\n\n"
        "Format:\n🎬 1. Title (Year) — [reason, 1 line]\n🎬 2. Title (Year) — [reason]\n"
        "🎬 3. Title (Year) — [reason]\n🎬 4. Title (Year) — [reason]\n🎬 5. Title (Year) — [reason]\n\n"
        "Hinglish mein. Hindi aur English movies mix karo.",
        max_tokens=450
    )

async def ai_mood_match(title: str, genre: str, plot: str) -> Optional[str]:
    return await ai_ask(
        f"Movie: '{title}'\nGenre: {genre}\nPlot: {plot[:300]}\n\n"
        "Batao:\n🎭 *Best Mood*     : [kaunsi feeling mein dekhni chahiye]\n"
        "👥 *Best With*     : [akele / dost / family / couple]\n"
        "🕐 *Best Time*     : [din / raat / weekend / rainy day]\n"
        "🍿 *Snack Suggest* : [kya khana chahiye saath mein]\n"
        "💬 *One-Line Pitch*: [ek zabardast line]\n\n"
        "Hinglish mein likho, creative aur fun raho.",
        max_tokens=350
    )

async def ai_cast_analysis(title: str, actors: str, director: str) -> Optional[str]:
    return await ai_ask(
        f"Movie '{title}' mein in logon ki performance ke baare mein analysis karo:\n\n"
        f"Director : {director}\nCast     : {actors}\n\n"
        "Har ek ke liye:\n🎬 [Naam] — [1-2 line performance analysis]\n\n"
        "End mein:\n🏆 *Standout Performance:* [sabse acha kaun tha aur kyun]\n\n"
        "Hinglish mein. Honest aur specific raho.",
        max_tokens=600
    )

async def ai_trivia_quiz_movie(title: str, year: str, director: str, actors: str) -> Optional[str]:
    return await ai_ask(
        f"Movie '{title}' ({year}) ke baare mein ek interesting MCQ trivia question banao.\n"
        f"Director: {director}, Cast: {actors}\n\n"
        "EXACTLY is format mein:\n❓ *Question:* [question]\n\n"
        "   A) [option]\n   B) [option]\n   C) [option]\n   D) [option]\n\n"
        "✅ *Answer:* [correct option letter] — [correct answer]\n"
        "💡 *Fact:* [ek interesting related fact, 1-2 lines]\n\n"
        "Hinglish mein. Lesser-known fact pe based question banana.",
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
        if time.time() - ts < CACHE_TTL: return data
        else: del _mi_cache[key]
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
                if resp.status == 200: return await resp.json()
                elif resp.status == 429: await asyncio.sleep(RETRY_DELAY * 2)
                elif resp.status == 404: return None
        except asyncio.TimeoutError: pass
        except aiohttp.ClientConnectorError: pass
        except Exception as e: _mi_logger.error(f"[MI ERROR] {url} — {e}")
        if attempt < RETRY_ATTEMPTS: await asyncio.sleep(RETRY_DELAY)
    return None

async def _mi_tmdb_search(session, title):
    data = await _mi_fetch_json(session, f"{TMDB_BASE}/search/movie",
                                params={"api_key": TMDB_API_KEY, "query": title, "language": "en-US", "page": 1})
    if not data: return None
    results = data.get("results", [])
    return results[0] if results else None

async def _mi_tmdb_detail(session, tmdb_id):
    return await _mi_fetch_json(session, f"{TMDB_BASE}/movie/{tmdb_id}",
                                params={"api_key": TMDB_API_KEY, "language": "en-US"})

async def _mi_tmdb_credits(session, tmdb_id):
    return await _mi_fetch_json(session, f"{TMDB_BASE}/movie/{tmdb_id}/credits",
                                params={"api_key": TMDB_API_KEY})

async def _mi_omdb_poster(session, imdb_id):
    if not imdb_id: return None
    data = await _mi_fetch_json(session, OMDB_BASE, params={"i": imdb_id, "apikey": OMDB_API_KEY})
    if not data: return None
    poster = data.get("Poster", "")
    if poster and poster != "N/A" and poster.startswith("http"): return poster
    return None

async def get_movie_info(title: str) -> Optional[dict]:
    title = _mi_sanitize(title)
    if not title: return None
    cache_key = title.lower()
    cached = _mi_cache_get(cache_key)
    if cached: return cached
    async with aiohttp.ClientSession() as session:
        movie = await _mi_tmdb_search(session, title)
        if not movie: return None
        tmdb_id = movie.get("id")
        if not tmdb_id: return None
        tmdb_poster = None
        if movie.get("poster_path"):
            tmdb_poster = f"{TMDB_IMG_BASE}{movie['poster_path']}"
        detail_task  = asyncio.create_task(_mi_tmdb_detail(session, tmdb_id))
        credits_task = asyncio.create_task(_mi_tmdb_credits(session, tmdb_id))
        detail, credits = await asyncio.gather(detail_task, credits_task)
        if not detail: detail = movie
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
            crew      = credits.get("crew", [])
            directors = [p["name"] for p in crew if p.get("job") == "Director"]
            director  = ", ".join(directors) if directors else "N/A"
            cast_list = credits.get("cast", [])[:5]
            cast_str  = ", ".join(p["name"] for p in cast_list) if cast_list else "N/A"
        poster = await _mi_omdb_poster(session, imdb_id)
        if not poster: poster = tmdb_poster
        result = {
            "title": detail.get("title") or movie.get("title") or title,
            "year": year, "genres": genres or "N/A", "runtime": runtime_str,
            "rating": rating, "votes": votes, "overview": overview, "poster": poster,
            "imdb_id": imdb_id, "tmdb_id": tmdb_id, "director": director, "cast": cast_str,
            "tagline": tagline, "language": language,
            "budget":  f"${budget:,}" if budget else "N/A",
            "revenue": f"${revenue:,}" if revenue else "N/A",
        }
        _mi_cache_set(cache_key, result)
        return result

def _mi_format_stars(rating: float) -> str:
    filled = round(rating / 2)
    return "⭐" * filled + "☆" * (5 - filled)

async def send_movie_card(update: Update, context: ContextTypes.DEFAULT_TYPE,
                          title: str, extra_buttons: list = None):
    loading_msg = await update.effective_message.reply_text("🎬 Fetching detailed info...", parse_mode="Markdown")
    try:
        info = await get_movie_info(title)
    except Exception as e:
        _mi_logger.error(f"[send_movie_card] {e}")
        info = None
    try: await loading_msg.delete()
    except Exception: pass
    if not info:
        await update.effective_message.reply_text(
            f"❌ *'{title}'* nahi mila!\n\n_Spelling check karo ya English title try karo._",
            parse_mode="Markdown"
        )
        return
    stars   = _mi_format_stars(info["rating"])
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
    if info["budget"] != "N/A": caption += f"💰 *Budget:* {info['budget']}\n"
    if info["revenue"] != "N/A": caption += f"🏆 *Revenue:* {info['revenue']}\n"
    caption += f"\n📖 *Overview:*\n{info['overview'][:800]}"
    if len(info["overview"]) > 800: caption += "..."
    keyboard = []
    if info["imdb_id"]:
        keyboard.append([InlineKeyboardButton("🔗 View on IMDb", url=f"https://www.imdb.com/title/{info['imdb_id']}/")])
    if extra_buttons: keyboard.extend(extra_buttons)
    markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    try:
        if info["poster"]:
            await update.effective_message.reply_photo(
                photo=info["poster"], caption=caption[:1024],
                parse_mode="Markdown", reply_markup=markup)
        else:
            await update.effective_message.reply_text(
                caption, parse_mode="Markdown", reply_markup=markup,
                disable_web_page_preview=False)
    except Exception as e:
        _mi_logger.error(f"[send_movie_card SEND ERROR] {e}")
        try:
            plain = f"{info['title']} ({info['year']})\nRating: {info['rating']}/10\n\n{info['overview'][:500]}"
            await update.effective_message.reply_text(plain, parse_mode="Markdown")
        except Exception as e2:
            _mi_logger.critical(f"[send_movie_card TOTAL FAIL] {e2}")

def mi_cache_clear(): _mi_cache.clear()
def mi_cache_size() -> int: return len(_mi_cache)


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
        f"║   🎬  *C I N E B O T*  v10  ║\n"
        f"╚═══════════════════════╝\n\n"
        f"✨ *Welcome, {user.first_name}!*\n\n"
        f"┌─────────────────────┐\n"
        f"│  {badge}\n"
        f"│  ⭐ `{points}` Points  •  👥 `{refs}` Refers\n"
        f"│  🤖 {ai_status}\n"
        f"└─────────────────────┘\n\n"
        f"🔎 *Movie dhundhna ho?*\n"
        f"_Seedha movie ka naam type karo!_\n\n"
        f"🔧 *Domain Healer v4 Active*\n"
        f"_Sites auto-heal hoti hain!_\n\n"
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
    if   cmd == "trending":    await trending_cmd(fake_update, context)
    elif cmd == "random":      await random_cmd(fake_update, context)
    elif cmd == "upcoming":    await upcoming_cmd(fake_update, context)
    elif cmd == "daily":       await daily_cmd(fake_update, context)
    elif cmd == "watchlist":   await watchlist_cmd(fake_update, context)
    elif cmd == "mystats":     await mystats_cmd(fake_update, context)
    elif cmd == "refer":       await refer_cmd(fake_update, context)
    elif cmd == "leaderboard": await leaderboard_cmd(fake_update, context)
    elif cmd == "history":     await history_cmd(fake_update, context)
    elif cmd == "quiz":        await quiz_cmd(fake_update, context)
    elif cmd == "open_admin":  await admin_panel(fake_update, context)
    elif cmd in ("suggest", "plotsearch", "mood", "compare"):
        pass


# ═══════════════════════════════════════════════════════════════════
#   MOVIE CARD
# ═══════════════════════════════════════════════════════════════════
_GENRE_EMOJI = {
    "action": "💥", "comedy": "😂", "drama": "🎭", "horror": "👻",
    "thriller": "🔪", "romance": "💕", "sci-fi": "🚀", "science fiction": "🚀",
    "animation": "🎨", "documentary": "📽️", "crime": "🕵️", "mystery": "🕵️",
    "fantasy": "🧙", "adventure": "🗺️", "family": "👨‍👩‍👧", "musical": "🎵",
    "war": "⚔️", "biography": "📖", "sport": "🏆", "history": "🏛️",
}

def _genre_emoji_row(genre: str) -> str:
    """Pick up to 3 emoji matching the movie's genres for a punchy header."""
    found = []
    for g in genre.lower().split(","):
        g = g.strip()
        for key, emo in _GENRE_EMOJI.items():
            if key in g and emo not in found:
                found.append(emo)
                break
    return " ".join(found[:3]) if found else "🎬"


async def _ai_tagline(title: str, year: str, genre: str, plot: str) -> Optional[str]:
    """One punchy AI-written hook line for the top of the movie card. Cheap + fast."""
    if not GROQ_API:
        return None
    prompt = (
        f"Movie: {title} ({year}), Genre: {genre}\n"
        f"Plot: {plot[:300]}\n\n"
        "Write ONE punchy, exciting hook line (max 14 words) that would make "
        "someone want to watch this. No quotes, no emoji, no title repetition. "
        "Just the line."
    )
    try:
        result = await ai_ask(prompt, max_tokens=40)
        if result:
            line = result.strip().strip('"').strip("'")
            if 5 < len(line) < 140:
                return line
    except Exception as e:
        print(f"⚠️ AI tagline failed: {e}")
    return None


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
                r = await asyncio.to_thread(
                    requests.get,
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
    _def_vals    = list(DEFAULT_SERVERS.values())
    search_urls  = [build_search_url(servers.get(f"s{i}", _def_vals[i-1])["url"], title) for i in range(1, 7)]
    names        = [servers.get(f"s{i}", _def_vals[i-1])["name"] for i in range(1, 7)]
    urls         = search_urls
    trailer      = f"https://www.youtube.com/results?search_query={quote(title + ' trailer')}"
    subs_url     = f"https://subscene.com/subtitles/searchbytitle?query={search_query}"

    try:
        uid = str(update.effective_user.id)
    except Exception:
        uid = "0"

    log_search(title, uid)
    if is_search: add_search_points(uid)

    genre_icons = _genre_emoji_row(genre)
    tagline     = await _ai_tagline(title, year, genre, plot)
    tagline_line = f"✨ _{tagline}_\n\n" if tagline else ""

    # Telegram photo captions hard-cap at 1024 chars. The box header + AI
    # tagline add extra length on top of the original fields, so trim the
    # most variable field (plot) first, then hard-cap the full caption as
    # a final safety net so reply_photo never gets rejected for length.
    plot_display = plot if len(plot) <= 280 else plot[:277].rsplit(" ", 1)[0] + "..."

    caption = (
        f"╔═══════════════════╗\n"
        f"   {genre_icons}  *{title.upper()}*  `{year}`\n"
        f"╚═══════════════════╝\n"
        f"{tagline_line}"
        f"{star_bar}\n"
        f"⭐ *IMDb:* `{rating}/10`   🍅 *RT:* `{rt_score}`\n"
        f"👥 *Community:* {comm_rat}\n"
        f"🗳 *Votes:* `{votes}`   🔞 *Rated:* `{rated}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎭 *Genre:*    `{genre}`\n"
        f"⏱ *Runtime:* `{runtime}`\n"
        f"🌍 *Lang:*     `{language}`\n"
        f"🎥 *Director:* `{director}`\n"
        f"👥 *Cast:*     `{actors}`\n"
        f"💰 *Box Office:* `{boxoff}`\n"
        f"🏆 *Awards:* `{awards}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📖 *Story:*\n_{plot_display}_\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ 6 Servers  •  🦁 Brave = No Ads"
    )
    if len(caption) > 1024:
        caption = caption[:1021] + "..."

    msg_obj = reply_to if reply_to else update.message

    temp_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 Direct Video ⚡", callback_data="gv_pending")],
        [InlineKeyboardButton("🎬 Trailer",   url=trailer),
         InlineKeyboardButton("📝 Subtitles", url=subs_url)],
        [InlineKeyboardButton("❤️ Watchlist", callback_data=f"wl_save|{title.replace('|','').replace('\\','')[:40]}|{year}|{rating}"),
         InlineKeyboardButton("🔔 Alert",     callback_data=f"alert_add|{title}|{year}")],
        [InlineKeyboardButton(f"⬇️ {names[0]}", url=urls[0])],
        [InlineKeyboardButton("🌐 All 6 Servers",   callback_data="s_tmp"),
         InlineKeyboardButton("🎯 Similar",          callback_data="sim_tmp")],
        [InlineKeyboardButton("🤖 AI Review",        callback_data="rev_tmp"),
         InlineKeyboardButton("💡 Fun Facts",        callback_data="fun_tmp")],
        [InlineKeyboardButton("⭐ Rate Movie",       callback_data="rate_tmp"),
         InlineKeyboardButton("🎥 Director Top 5",  callback_data=f"dir_{quote(director, safe='')}")],
        [InlineKeyboardButton("📝 Full Review",      callback_data="frev_tmp"),
         InlineKeyboardButton("🎭 Mood Match",       callback_data="mood_match_tmp")],
        [InlineKeyboardButton("🌟 Cast Analysis",    callback_data="cast_tmp"),
         InlineKeyboardButton("❓ Trivia Quiz",      callback_data="trivia_tmp")],
        [InlineKeyboardButton("🔥 Full AI Package",  callback_data="pkg_tmp")],
    ])

    if poster:
        try:
            sent = await msg_obj.reply_photo(
                photo=poster, caption=caption,
                parse_mode="Markdown", reply_markup=temp_keyboard)
        except Exception:
            sent = await msg_obj.reply_text(
                f"⚠️ _Poster load nahi hua_\n\n{caption}",
                parse_mode="Markdown", reply_markup=temp_keyboard)
    else:
        sent = await msg_obj.reply_text(
            caption, parse_mode="Markdown", reply_markup=temp_keyboard)

    msg_id = str(sent.message_id)
    context.user_data[msg_id] = {
        "servers": urls, "names": names, "trailer": trailer,
        "title": title, "year": year, "rating": rating,
        "director": director, "actors": actors, "plot": plot,
        "imdb_id": imdb_id, "genre": genre, "awards": awards,
    }

    async def _bg_resolve_links():
        try:
            direct = await resolve_server_urls(search_urls, title)
            if msg_id in context.user_data:
                context.user_data[msg_id]["servers"] = direct
        except Exception as e:
            print(f"⚠️ [BG] Direct link resolve error: {e}")
    asyncio.create_task(_bg_resolve_links())

    real_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 Direct Video ⚡", callback_data=f"gv_{msg_id}")],
        [InlineKeyboardButton("🎬 Trailer",   url=trailer),
         InlineKeyboardButton("📝 Subtitles", url=subs_url)],
        [InlineKeyboardButton("❤️ Watchlist", callback_data=f"wl_save|{title.replace('|','').replace('\\','')[:40]}|{year}|{rating}"),
         InlineKeyboardButton("🔔 Alert",     callback_data=f"alert_add|{title}|{year}")],
        [InlineKeyboardButton(f"⬇️ {names[0]}", url=urls[0])],
        [InlineKeyboardButton("🌐 All 6 Servers",   callback_data=f"srv_{msg_id}"),
         InlineKeyboardButton("🎯 Similar",          callback_data=f"sim_{msg_id}")],
        [InlineKeyboardButton("🤖 AI Review",        callback_data=f"rev_{imdb_id}"),
         InlineKeyboardButton("💡 Fun Facts",        callback_data=f"fun_{imdb_id}")],
        [InlineKeyboardButton("⭐ Rate Movie",       callback_data=f"rate_{msg_id}"),
         InlineKeyboardButton("🎥 Director Top 5",  callback_data=f"dir_{quote(director, safe='')}")],
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
#   FULL AI ANALYSIS CALLBACKS
# ═══════════════════════════════════════════════════════════════════
async def fullreview_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer("📝 Writing full review...")
    msg_id = query.data.split("_", 1)[1]
    md     = context.user_data.get(msg_id)
    if not md:
        await query.message.reply_text("⚠️ Session expired. Movie dobara search karo.")
        return
    loader = await query.message.reply_text("📝 Full review likh raha hai...\n" + progress_bar(0, 4), parse_mode="Markdown")
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
            parse_mode="Markdown")
    else:
        await query.message.reply_text("❌ AI review nahi likh paya. GROQ_API check karo.", parse_mode="Markdown")

async def moodmatch_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer("🎭 Mood match kar raha hai...")
    msg_id = query.data.split("_", 2)[2]
    md     = context.user_data.get(msg_id)
    if not md:
        await query.message.reply_text("⚠️ Session expired. Movie dobara search karo.")
        return
    loader = await query.message.reply_text("🎭 Mood analyze ho raha hai...\n" + progress_bar(0, 4), parse_mode="Markdown")
    await animate_generic(loader, FRAMES["moodmatch"])
    result = await ai_mood_match(md["title"], md.get("genre", "N/A"), md["plot"])
    try: await loader.delete()
    except: pass
    if result:
        await query.message.reply_text(
            f"╔══════════════════════════╗\n║  🎭  *MOOD MATCH*  ║\n╚══════════════════════════╝\n\n"
            f"🎬 *{md['title']}* ({md['year']})\n━━━━━━━━━━━━━━━━━━\n\n"
            f"{result}\n\n_Powered by Groq AI (Llama 3.3)_ 🤖",
            parse_mode="Markdown")
    else:
        await query.message.reply_text("❌ Mood match nahi hua.", parse_mode="Markdown")

async def castanalysis_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer("🌟 Cast analyze ho raha hai...")
    msg_id = query.data.split("_", 1)[1]
    md     = context.user_data.get(msg_id)
    if not md:
        await query.message.reply_text("⚠️ Session expired. Movie dobara search karo.")
        return
    loader = await query.message.reply_text("🌟 Cast analysis chal raha hai...\n" + progress_bar(0, 3), parse_mode="Markdown")
    await animate_generic(loader, FRAMES["castanalysis"])
    result = await ai_cast_analysis(md["title"], md["actors"], md["director"])
    try: await loader.delete()
    except: pass
    if result:
        await query.message.reply_text(
            f"╔══════════════════════════╗\n║  🌟  *CAST ANALYSIS*  ║\n╚══════════════════════════╝\n\n"
            f"🎬 *{md['title']}* ({md['year']})\n━━━━━━━━━━━━━━━━━━\n\n"
            f"{result}\n\n_Powered by Groq AI (Llama 3.3)_ 🤖",
            parse_mode="Markdown")
    else:
        await query.message.reply_text("❌ Cast analysis nahi hua.", parse_mode="Markdown")

async def trivia_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer("❓ Trivia question bana raha hai...")
    msg_id = query.data.split("_", 1)[1]
    md     = context.user_data.get(msg_id)
    if not md:
        await query.message.reply_text("⚠️ Session expired. Movie dobara search karo.")
        return
    loader = await query.message.reply_text("❓ Trivia bana raha hai...\n" + progress_bar(0, 3), parse_mode="Markdown")
    await animate_generic(loader, FRAMES["trivia"])
    result = await ai_trivia_quiz_movie(md["title"], md["year"], md["director"], md["actors"])
    try: await loader.delete()
    except: pass
    if result:
        await query.message.reply_text(
            f"╔══════════════════════════╗\n║  ❓  *MOVIE TRIVIA*  ║\n╚══════════════════════════╝\n\n"
            f"🎬 *{md['title']}* ({md['year']})\n━━━━━━━━━━━━━━━━━━\n\n"
            f"{result}\n\n_Powered by Groq AI (Llama 3.3)_ 🤖",
            parse_mode="Markdown")
    else:
        await query.message.reply_text("❌ Trivia nahi bana.", parse_mode="Markdown")

async def fullpackage_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer("🔥 Full package prepare ho raha hai...")
    msg_id = query.data.split("_", 1)[1]
    md     = context.user_data.get(msg_id)
    if not md:
        await query.message.reply_text("⚠️ Session expired. Movie dobara search karo.")
        return
    loader = await query.message.reply_text("🔥 Full AI Package loading...\n" + progress_bar(0, 5), parse_mode="Markdown")
    await animate_generic(loader, FRAMES["fullpackage"])
    try: await loader.delete()
    except: pass
    t  = md["title"];  y  = md["year"]
    g  = md.get("genre","N/A"); p  = md["plot"]
    r  = md["rating"]; d  = md["director"]
    a  = md["actors"]; aw = md.get("awards","N/A")
    sections = [
        ("📝 FULL REVIEW",    ai_full_review(t, y, g, p, r, d, a, aw)),
        ("🎯 SIMILAR MOVIES", ai_similar_deep(t, y, g)),
        ("🎭 MOOD MATCH",     ai_mood_match(t, g, p)),
        ("🌟 CAST ANALYSIS",  ai_cast_analysis(t, a, d)),
        ("❓ TRIVIA QUIZ",    ai_trivia_quiz_movie(t, y, d, a)),
    ]
    results = await asyncio.gather(*[coro for _, coro in sections], return_exceptions=True)
    full_text = (
        f"╔══════════════════════════╗\n║  🔥  *FULL AI PACKAGE*  ║\n╚══════════════════════════╝\n\n"
        f"🎬 *{t}* ({y})\n━━━━━━━━━━━━━━━━━━\n"
    )
    for i, (label, _) in enumerate(sections):
        res = results[i]
        full_text += f"\n\n*━━ {label} ━━*\n"
        if isinstance(res, Exception) or not res:
            full_text += "_AI response nahi aaya._"
        else:
            full_text += res
        if len(full_text) > 3800:
            await query.message.reply_text(full_text, parse_mode="Markdown")
            full_text = f"🎬 *{t}* — continued...\n"
    full_text += "\n\n_Powered by Groq AI (Llama 3.3)_ 🤖"
    if full_text.strip():
        await query.message.reply_text(full_text, parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════════
#   NEW COMMANDS — /fullreview /moodmatch /castinfo /trivia
# ═══════════════════════════════════════════════════════════════════
async def fullreview_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = " ".join(context.args).strip() if context.args else ""
    if not title:
        await update.message.reply_text("❌ *Usage:* `/fullreview Movie Name`", parse_mode="Markdown")
        return
    if not GROQ_API:
        await update.message.reply_text("⚠️ GROQ_API set nahi hai!", parse_mode="Markdown")
        return
    loader = await update.message.reply_text("📝 Movie info fetch ho rahi hai...\n" + progress_bar(1, 4), parse_mode="Markdown")
    data = await asyncio.to_thread(get_omdb, title)
    if not data or data.get("Response") == "False":
        await loader.edit_text(f"❌ *'{title}'* nahi mili!", parse_mode="Markdown")
        return
    await animate_generic(loader, FRAMES["fullreview"])
    result = await ai_full_review(
        data.get("Title","N/A"), data.get("Year","N/A"), data.get("Genre","N/A"),
        data.get("Plot","N/A"), data.get("imdbRating","N/A"),
        data.get("Director","N/A"), data.get("Actors","N/A"), data.get("Awards","N/A")
    )
    try: await loader.delete()
    except: pass
    if result:
        await update.message.reply_text(
            f"╔══════════════════════════╗\n║  📝  *FULL AI REVIEW*  ║\n╚══════════════════════════╝\n\n"
            f"🎬 *{data['Title']}* ({data['Year']})\n━━━━━━━━━━━━━━━━━━\n\n"
            f"{result}\n\n_Powered by Groq AI_ 🤖", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Review nahi likh paya.", parse_mode="Markdown")

async def moodmatch_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = " ".join(context.args).strip() if context.args else ""
    if not title:
        await update.message.reply_text("❌ *Usage:* `/moodmatch Movie Name`", parse_mode="Markdown")
        return
    if not GROQ_API:
        await update.message.reply_text("⚠️ GROQ_API set nahi hai!", parse_mode="Markdown")
        return
    loader = await update.message.reply_text("🎭 Mood analyze ho raha hai...\n" + progress_bar(1, 4), parse_mode="Markdown")
    data = await asyncio.to_thread(get_omdb, title)
    if not data or data.get("Response") == "False":
        await loader.edit_text(f"❌ *'{title}'* nahi mili!", parse_mode="Markdown")
        return
    await animate_generic(loader, FRAMES["moodmatch"])
    result = await ai_mood_match(data.get("Title","N/A"), data.get("Genre","N/A"), data.get("Plot","N/A"))
    try: await loader.delete()
    except: pass
    if result:
        await update.message.reply_text(
            f"╔══════════════════════╗\n║  🎭  *MOOD MATCH*  ║\n╚══════════════════════╝\n\n"
            f"🎬 *{data['Title']}* ({data['Year']})\n━━━━━━━━━━━━━━━━━━\n\n"
            f"{result}\n\n_Powered by Groq AI_ 🤖", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Mood match nahi hua.", parse_mode="Markdown")

async def castinfo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = " ".join(context.args).strip() if context.args else ""
    if not title:
        await update.message.reply_text("❌ *Usage:* `/castinfo Movie Name`", parse_mode="Markdown")
        return
    if not GROQ_API:
        await update.message.reply_text("⚠️ GROQ_API set nahi hai!", parse_mode="Markdown")
        return
    loader = await update.message.reply_text("🌟 Cast analyze ho raha hai...\n" + progress_bar(1, 3), parse_mode="Markdown")
    data = await asyncio.to_thread(get_omdb, title)
    if not data or data.get("Response") == "False":
        await loader.edit_text(f"❌ *'{title}'* nahi mili!", parse_mode="Markdown")
        return
    await animate_generic(loader, FRAMES["castanalysis"])
    result = await ai_cast_analysis(data.get("Title","N/A"), data.get("Actors","N/A"), data.get("Director","N/A"))
    try: await loader.delete()
    except: pass
    if result:
        await update.message.reply_text(
            f"╔══════════════════════════╗\n║  🌟  *CAST ANALYSIS*  ║\n╚══════════════════════════╝\n\n"
            f"🎬 *{data['Title']}* ({data['Year']})\n━━━━━━━━━━━━━━━━━━\n\n"
            f"{result}\n\n_Powered by Groq AI_ 🤖", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Cast info nahi aaya.", parse_mode="Markdown")

async def trivia_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = " ".join(context.args).strip() if context.args else ""
    if not title:
        await update.message.reply_text("❌ *Usage:* `/trivia Movie Name`", parse_mode="Markdown")
        return
    if not GROQ_API:
        await update.message.reply_text("⚠️ GROQ_API set nahi hai!", parse_mode="Markdown")
        return
    loader = await update.message.reply_text("❓ Trivia bana raha hai...\n" + progress_bar(1, 3), parse_mode="Markdown")
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
            f"{result}\n\n_Powered by Groq AI_ 🤖", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Trivia nahi bana.", parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════════
#   🔧 DOMAIN HEALER V6 — AI-POWERED SERVER LINK FINDER
#   Har server periodically check hota hai (live/down).
#   Down milne par: AI suggestion + Web search dono se candidate
#   domains nikalte hain, phir HAR candidate ko actually HTTP request
#   karke verify karte hain (real load test, sirf suggestion nahi).
#   v6: winning candidate ab ek FINAL independent AI double-check se
#   guzarta hai (real page content padh ke) — ye ek extra confidence
#   layer hai jo look-alike/spam domains ko admin tak pahunchne se
#   pehle hi filter kar deta hai.
#   Sabse best-scoring verified candidate admin ko approval ke liye
#   bheja jaata hai. Approve hote hi live servers.json update hota hai.
# ═══════════════════════════════════════════════════════════════════

# Safe fallbacks for globals this class depends on, in case this file
# is merged with a main file that already defines them (that definition
# will simply take precedence at import time / or these no-ops apply).
try:
    SRV_UP_CODES
except NameError:
    SRV_UP_CODES = {200, 201, 202, 301, 302, 303, 307, 308}

try:
    _BS4_AVAILABLE
except NameError:
    try:
        from bs4 import BeautifulSoup as _HealerBS4Probe  # noqa: F401
        _BS4_AVAILABLE = True
    except Exception:
        _BS4_AVAILABLE = False

try:
    _get_srv_headers
except NameError:
    def _get_srv_headers():
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

HEALER_DB_FILE = "healer_v6.db"
_healer_db_lock = threading.Lock()

# Module-level healer instance, set by post_init() once the bot starts.
try:
    _healer
except NameError:
    _healer = None


def _healer_init_db():
    with _healer_db_lock:
        con = sqlite3.connect(HEALER_DB_FILE)
        con.executescript("""
            CREATE TABLE IF NOT EXISTS heal_log (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                server_key    TEXT,
                server_name   TEXT,
                old_url       TEXT,
                new_url       TEXT,
                source        TEXT,
                confidence    REAL,
                status        TEXT,
                created_at    REAL
            );
            CREATE TABLE IF NOT EXISTS pending_heals (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                server_key    TEXT UNIQUE,
                server_name   TEXT,
                old_url       TEXT,
                candidate_url TEXT,
                source        TEXT,
                confidence    REAL,
                created_at    REAL
            );
        """)
        con.commit()
        con.close()

_healer_init_db()


def _healer_db_execute(query: str, params: tuple = ()):
    with _healer_db_lock:
        con = sqlite3.connect(HEALER_DB_FILE)
        try:
            con.execute(query, params)
            con.commit()
        finally:
            con.close()


def _healer_db_fetch(query: str, params: tuple = ()) -> list:
    with _healer_db_lock:
        con = sqlite3.connect(HEALER_DB_FILE)
        try:
            cur = con.execute(query, params)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
        finally:
            con.close()


class HealerV4:
    """
    Advanced domain healer.

    Public surface kept identical to what the rest of the bot expects
    (`HealerV4(bot=..., groq_sdk_client=..., admin_id=...)`,
    `.register_handlers(application)`, `.db.get_heal_log(limit=...)`)
    so it drops in without touching call sites elsewhere in the file.
    """

    def __init__(self, bot, groq_sdk_client=None, admin_id: int = 0,
                 check_interval_hours: float = 3.0):
        self.bot             = bot
        self.groq_sdk_client = groq_sdk_client
        self.admin_id        = admin_id
        self.check_interval  = check_interval_hours * 3600
        self.db              = self._DBFacade()
        self._running         = False

    # ── thin facade so existing call sites (`_healer.db.get_heal_log(...)`) work ──
    class _DBFacade:
        def get_heal_log(self, limit: int = 10) -> list:
            return _healer_db_fetch(
                "SELECT * FROM heal_log ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )

    # ── Register admin approve/reject buttons ──
    def register_handlers(self, application):
        application.add_handler(
            CallbackQueryHandler(self._approve_cb, pattern="^heal_approve_")
        )
        application.add_handler(
            CallbackQueryHandler(self._reject_cb, pattern="^heal_reject_")
        )

    # ── Background loop: checks all servers every `check_interval` ──
    async def run_forever(self):
        if self._running:
            return
        self._running = True
        while True:
            try:
                await self.check_all_servers()
            except Exception as e:
                print(f"⚠️ [Healer] check_all_servers error: {e}")
            await asyncio.sleep(self.check_interval)

    # ── Check every configured server, heal the ones that are down ──
    async def check_all_servers(self):
        servers = load_servers()
        for key, info in servers.items():
            url  = info.get("url", "")
            name = info.get("name", key)
            if not url:
                continue
            alive = await self._is_alive(url)
            if not alive:
                print(f"⚠️ [Healer] {name} ({url}) looks DOWN — starting heal")
                await self.heal_server(key, name, url)

    # ── Liveness check: real HTTP GET, not just a HEAD guess ──
    async def _is_alive(self, url: str, timeout_sec: int = 10) -> bool:
        try:
            timeout = aiohttp.ClientTimeout(sock_connect=6, sock_read=timeout_sec, total=timeout_sec + 4)
            async with aiohttp.ClientSession(timeout=timeout) as sess:
                async with sess.get(url, headers=_get_srv_headers(), allow_redirects=True, ssl=False) as resp:
                    if resp.status not in SRV_UP_CODES:
                        return False
                    # A domain-parked / "for sale" page often still returns 200 —
                    # sniff a bit of body text to rule those out.
                    body = (await resp.text(errors="ignore"))[:4000].lower()
                    parked_markers = [
                        "domain is for sale", "buy this domain", "domain parking",
                        "this domain may be for sale", "godaddy.com/domainsearch",
                    ]
                    if any(m in body for m in parked_markers):
                        return False
                    return True
        except Exception:
            return False

    # ── Full heal pipeline for one server ──
    async def heal_server(self, key: str, name: str, old_url: str):
        base_domain = urlparse(old_url).netloc

        # 1) Gather candidates from two independent sources
        ai_candidates     = await self._find_via_ai(name, base_domain)
        search_candidates = await self._find_via_search(name, base_domain)
        all_candidates     = list(dict.fromkeys(ai_candidates + search_candidates))  # dedupe, keep order

        if not all_candidates:
            print(f"❌ [Healer] No candidates found for {name}")
            self._log(key, name, old_url, None, "none", 0.0, "no_candidates")
            return

        # 2) Verify every candidate with a real request + score them
        scored = []
        for cand in all_candidates:
            score, source_tag, page_snippet = await self._verify_candidate(
                cand, name, ai_candidates, search_candidates
            )
            if score > 0:
                scored.append((cand, score, source_tag, page_snippet))

        if not scored:
            print(f"❌ [Healer] No candidate for {name} passed verification")
            self._log(key, name, old_url, None, "none", 0.0, "verification_failed")
            return

        # 3) Pick the best-scoring verified candidate
        scored.sort(key=lambda x: x[1], reverse=True)
        best_url, best_score, best_source, best_snippet = scored[0]

        # 4) Final independent AI double-check pass — reads the actual page
        #    content and gives one more confidence signal before this ever
        #    reaches the admin, catching cases where the heuristic score
        #    was fooled by a look-alike or unrelated site.
        ai_confidence = await self._ai_double_check(name, old_url, best_url, best_snippet)
        # Blend: heuristic score (0-100) stays dominant, AI opinion adjusts it
        final_score = min(100.0, (best_score * 0.7) + (ai_confidence * 100 * 0.3))

        if ai_confidence < 0.25:
            # AI is fairly confident this is NOT the right site — don't waste
            # the admin's time, log it and stop instead of forwarding a bad match.
            print(f"❌ [Healer] AI double-check rejected {best_url} for {name} (conf {ai_confidence:.2f})")
            self._log(key, name, old_url, best_url, best_source, final_score, "ai_rejected")
            return

        # 5) Send to admin for approval before going live
        await self._request_approval(key, name, old_url, best_url, best_source, final_score)


    # ── Source A: Groq AI suggestion ──
    async def _find_via_ai(self, name: str, base_domain: str) -> list:
        if not GROQ_API:
            return []
        prompt = (
            f"The website '{name}' (previously at domain '{base_domain}') "
            f"appears to be down or has changed its domain. "
            f"This is a movie-download search-engine style site. "
            f"List up to 3 likely CURRENT working domain names for this exact "
            f"site (same site, possibly a new TLD or subdomain change). "
            f"Return ONLY a comma-separated list of full https:// URLs, nothing else."
        )
        try:
            result = await ai_ask(prompt, max_tokens=150)
            if not result:
                return []
            urls = re.findall(r'https?://[^\s,"\']+', result)
            return urls[:3]
        except Exception as e:
            print(f"⚠️ [Healer] AI candidate search failed: {e}")
            return []

    # ── Source B: Web search (DuckDuckGo HTML — no API key needed) ──
    async def _find_via_search(self, name: str, base_domain: str) -> list:
        query = quote(f"{name} official site")
        search_url = f"https://duckduckgo.com/html/?q={query}"
        try:
            timeout = aiohttp.ClientTimeout(total=12)
            async with aiohttp.ClientSession(timeout=timeout) as sess:
                async with sess.get(search_url, headers=_get_srv_headers(), ssl=False) as resp:
                    if resp.status != 200:
                        return []
                    html = await resp.text(errors="ignore")
            if not _BS4_AVAILABLE:
                # Fallback: crude regex extraction if bs4 isn't available
                raw_links = re.findall(r'href="(https?://[^"]+)"', html)
            else:
                soup = BeautifulSoup(html, "html.parser")
                raw_links = [a.get("href", "") for a in soup.select("a.result__a")]
                if not raw_links:
                    raw_links = [a.get("href", "") for a in soup.select("a[href^='http']")]

            candidates = []
            skip_domains = {"duckduckgo.com", "google.com", "bing.com", "facebook.com", "twitter.com", "youtube.com"}
            for link in raw_links[:15]:
                netloc = urlparse(link).netloc.lower()
                if not netloc or any(s in netloc for s in skip_domains):
                    continue
                candidates.append(link)
                if len(candidates) >= 3:
                    break
            return candidates
        except Exception as e:
            print(f"⚠️ [Healer] Web search failed: {e}")
            return []

    # ── Verify one candidate: real request + name-relevance scoring ──
    async def _verify_candidate(self, url: str, expected_name: str,
                                 ai_list: list, search_list: list) -> tuple:
        alive = await self._is_alive(url, timeout_sec=8)
        if not alive:
            return 0.0, "dead", ""

        score = 40.0  # base score for being alive at all
        page_snippet = ""

        # Bonus: domain name resembles the expected site name
        netloc = urlparse(url).netloc.lower()
        name_tokens = [t for t in re.findall(r'[a-z0-9]+', expected_name.lower()) if len(t) > 2]
        if name_tokens and any(t in netloc for t in name_tokens):
            score += 30.0

        # Bonus: cross-source agreement (both AI and search suggested the same domain)
        in_ai     = any(urlparse(c).netloc.lower() == netloc for c in ai_list)
        in_search = any(urlparse(c).netloc.lower() == netloc for c in search_list)
        source_tag = "ai+search" if (in_ai and in_search) else ("ai" if in_ai else "search")
        if in_ai and in_search:
            score += 25.0

        # Bonus: homepage actually contains a search box (typical of these sites)
        try:
            timeout = aiohttp.ClientTimeout(total=8)
            async with aiohttp.ClientSession(timeout=timeout) as sess:
                async with sess.get(url, headers=_get_srv_headers(), ssl=False) as resp:
                    body = (await resp.text(errors="ignore"))[:6000]
                    page_snippet = body[:1500]  # kept for the AI double-check pass later
                    body_lower = body.lower()
                    if "<form" in body_lower and ("search" in body_lower or "?s=" in body_lower):
                        score += 5.0
        except Exception:
            pass

        return min(score, 100.0), source_tag, page_snippet

    # ── Final AI double-check pass on the winning candidate before it ever
    #    reaches the admin. Reads the actual fetched page text and asks the
    #    model whether this really looks like the same site — an extra,
    #    independent confidence signal beyond the scoring heuristics above. ──
    async def _ai_double_check(self, expected_name: str, old_url: str,
                                candidate_url: str, page_snippet: str) -> float:
        if not GROQ_API or not page_snippet.strip():
            return 0.5  # neutral — no signal either way
        prompt = (
            f"A movie-download site called '{expected_name}' (old domain: {old_url}) "
            f"went down. We found a possible replacement at: {candidate_url}\n\n"
            f"Here is a snippet of that page's actual HTML/text:\n"
            f"'''{page_snippet[:1200]}'''\n\n"
            "Based on this snippet, does this genuinely look like the same "
            "movie-download site (same branding, same type of content, same "
            "kind of layout) rather than an unrelated site or a parked/spam "
            "page? Respond with ONLY a number 0.0-1.0 for your confidence, "
            "nothing else."
        )
        try:
            result = await ai_ask(prompt, max_tokens=10)
            if result:
                match = re.search(r'(0?\.\d+|1\.0|0|1)', result.strip())
                if match:
                    return max(0.0, min(1.0, float(match.group(1))))
        except Exception as e:
            print(f"⚠️ [Healer] AI double-check failed: {e}")
        return 0.5

    # ── Send an approval request to the admin ──
    async def _request_approval(self, key, name, old_url, new_url, source, score):
        _healer_db_execute(
            """INSERT INTO pending_heals
               (server_key, server_name, old_url, candidate_url, source, confidence, created_at)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(server_key) DO UPDATE SET
                 candidate_url=excluded.candidate_url,
                 source=excluded.source,
                 confidence=excluded.confidence,
                 created_at=excluded.created_at""",
            (key, name, old_url, new_url, source, score, time.time()),
        )

        if not self.admin_id or not self.bot:
            return

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Approve", callback_data=f"heal_approve_{key}"),
             InlineKeyboardButton("❌ Reject",  callback_data=f"heal_reject_{key}")],
        ])
        try:
            await self.bot.send_message(
                chat_id=self.admin_id,
                text=(
                    f"🔧 *Domain Healer — {name} down*\n\n"
                    f"🔴 Old: `{old_url}`\n"
                    f"🟢 New candidate: `{new_url}`\n"
                    f"📡 Source: `{source}`\n"
                    f"🎯 Confidence: `{score:.0f}%`\n\n"
                    f"_Approve karo taaki live update ho._"
                ),
                parse_mode="Markdown",
                reply_markup=kb,
            )
        except Exception as e:
            print(f"⚠️ [Healer] Could not notify admin: {e}")

    # ── Admin tapped Approve ──
    async def _approve_cb(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not is_admin(query.from_user.id):
            await query.answer("🚫 Admin only.", show_alert=True)
            return
        key = query.data.replace("heal_approve_", "")
        rows = _healer_db_fetch("SELECT * FROM pending_heals WHERE server_key=?", (key,))
        if not rows:
            await query.answer("⚠️ Ye request expire ho gayi.", show_alert=True)
            return
        row = rows[0]

        servers = load_servers()
        if key in servers:
            servers[key]["url"] = row["candidate_url"]
            save_json("servers", servers)

        self._log(key, row["server_name"], row["old_url"], row["candidate_url"],
                   row["source"], row["confidence"], "approved")
        _healer_db_execute("DELETE FROM pending_heals WHERE server_key=?", (key,))

        await query.answer("✅ Applied!")
        try:
            await query.message.edit_text(
                f"✅ *Healed!*\n\n{row['server_name']} → `{row['candidate_url']}`",
                parse_mode="Markdown",
            )
        except Exception:
            pass

    # ── Admin tapped Reject ──
    async def _reject_cb(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not is_admin(query.from_user.id):
            await query.answer("🚫 Admin only.", show_alert=True)
            return
        key = query.data.replace("heal_reject_", "")
        rows = _healer_db_fetch("SELECT * FROM pending_heals WHERE server_key=?", (key,))
        if rows:
            row = rows[0]
            self._log(key, row["server_name"], row["old_url"], row["candidate_url"],
                       row["source"], row["confidence"], "rejected")
        _healer_db_execute("DELETE FROM pending_heals WHERE server_key=?", (key,))
        await query.answer("❌ Rejected.")
        try:
            await query.message.edit_text("❌ *Rejected.* Server manually check karo.", parse_mode="Markdown")
        except Exception:
            pass

    # ── Write a row to the permanent heal_log ──
    def _log(self, key, name, old_url, new_url, source, confidence, status):
        _healer_db_execute(
            """INSERT INTO heal_log
               (server_key, server_name, old_url, new_url, source, confidence, status, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (key, name, old_url, new_url, source, confidence, status, time.time()),
        )


# ── Background task wrapper: starts the healer's periodic loop ──
async def auto_server_checker(bot, admin_id):
    """Kept as a standalone task for compatibility with existing post_init call.
    The actual periodic logic now lives in HealerV4.run_forever(); this just
    drives it using whichever _healer instance post_init() created."""
    while True:
        try:
            if _healer is not None:
                await _healer.check_all_servers()
        except Exception as e:
            print(f"⚠️ [auto_server_checker] {e}")
        await asyncio.sleep(getattr(_healer, "check_interval", 3 * 3600) if _healer else 3 * 3600)


# ── /healerlog command: show recent heal history to admins ──
async def healerlog_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 Admin only command.")
        return
    if not _healer:
        await update.message.reply_text("⚠️ Healer not initialized.", parse_mode="Markdown")
        return
    log = _healer.db.get_heal_log(limit=10)
    if not log:
        await update.message.reply_text("📋 *Healer History*\n\n_Abhi tak koi heal nahi hua._", parse_mode="Markdown")
        return
    lines = ["📋 *HEALER v6 HISTORY* (last 10)\n━━━━━━━━━━━━━━━━━━"]
    for row in log:
        ts = datetime.fromtimestamp(row["created_at"]).strftime("%d %b, %H:%M") if row.get("created_at") else "?"
        status_icon = {"approved": "✅", "rejected": "❌", "no_candidates": "⚠️", "verification_failed": "⚠️", "ai_rejected": "🤖❌"}.get(row["status"], "❔")
        lines.append(
            f"\n{status_icon} *{row['server_name']}* _{ts}_\n"
            f"   `{row.get('old_url','?')}` → `{row.get('new_url') or '—'}`\n"
            f"   Source: `{row.get('source','?')}` | Confidence: `{row.get('confidence',0):.0f}%`"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── Shared: build the server-status text + refresh/stats keyboard ──
async def _build_server_status_view():
    if not _healer:
        return "⚠️ Healer not initialized.", None
    servers = load_servers()
    lines = ["📡 *SERVER STATUS*\n━━━━━━━━━━━━━━━━━━"]
    for key, info in servers.items():
        url = info.get("url", "")
        name = info.get("name", key)
        if not url:
            lines.append(f"⚠️ *{name}* — no URL configured")
            continue
        alive = await _healer._is_alive(url)
        icon = "✅" if alive else "❌"
        lines.append(f"{icon} *{name}* — `{url}`")
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 Refresh", callback_data="srvchk_refresh"),
            InlineKeyboardButton("📊 Stats", callback_data="srvchk_stats"),
        ]
    ])
    return "\n".join(lines), keyboard


# ── Admin panel button: "📡 Server Status" ──
async def server_status_admin_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🌐 Checking servers...")
    if not is_admin(update.effective_user.id):
        await query.message.reply_text("🚫 Admin only command.")
        return
    text, keyboard = await _build_server_status_view()
    await query.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)


# ── Refresh button on the server status view ──
async def srvchk_refresh_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🔄 Refreshing...")
    if not is_admin(update.effective_user.id):
        await query.message.reply_text("🚫 Admin only command.")
        return
    text, keyboard = await _build_server_status_view()
    try:
        await query.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    except Exception:
        await query.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)


# ── Stats button on the server status view ──
async def srvchk_stats_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("📊 Loading stats...")
    if not is_admin(update.effective_user.id):
        await query.message.reply_text("🚫 Admin only command.")
        return
    if not _healer:
        await query.message.reply_text("⚠️ Healer not initialized.", parse_mode="Markdown")
        return
    servers = load_servers()
    up = down = 0
    for key, info in servers.items():
        url = info.get("url", "")
        if not url:
            continue
        alive = await _healer._is_alive(url)
        if alive:
            up += 1
        else:
            down += 1
    total = up + down
    await query.message.reply_text(
        f"📊 *SERVER STATS*\n━━━━━━━━━━━━━━━━━━\n"
        f"✅ Up: `{up}`\n❌ Down: `{down}`\n📦 Total: `{total}`",
        parse_mode="Markdown",
    )


# ── /checkservers command: manually trigger a live check of all servers ──
async def checkservers_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 Admin only command.")
        return
    if not _healer:
        await update.message.reply_text("⚠️ Healer not initialized.", parse_mode="Markdown")
        return
    msg = await update.message.reply_text("🌐 Checking all servers, please wait...")
    servers = load_servers()
    lines = ["🌐 *SERVER STATUS*\n━━━━━━━━━━━━━━━━━━"]
    for key, info in servers.items():
        url = info.get("url", "")
        name = info.get("name", key)
        if not url:
            lines.append(f"⚠️ *{name}* — no URL configured")
            continue
        alive = await _healer._is_alive(url)
        icon = "✅" if alive else "❌"
        lines.append(f"{icon} *{name}* — `{url}`")
    try:
        await msg.edit_text("\n".join(lines), parse_mode="Markdown")
    except Exception:
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── /serverstats command: quick summary counts of up/down servers ──
async def serverstats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 Admin only command.")
        return
    if not _healer:
        await update.message.reply_text("⚠️ Healer not initialized.", parse_mode="Markdown")
        return
    servers = load_servers()
    up = down = 0
    for key, info in servers.items():
        url = info.get("url", "")
        if not url:
            continue
        alive = await _healer._is_alive(url)
        if alive:
            up += 1
        else:
            down += 1
    total = up + down
    await update.message.reply_text(
        f"📊 *SERVER STATS*\n━━━━━━━━━━━━━━━━━━\n"
        f"✅ Up: `{up}`\n❌ Down: `{down}`\n📦 Total: `{total}`",
        parse_mode="Markdown",
    )


# ═══════════════════════════════════════════════════════════════════
#   📦 GROUP FILE INDEX SYSTEM
#   Bot jis bhi group/channel ka admin hai, wahan uploaded
#   movies auto-index hoti hain SQLite mein.
#   User search kare → index check → mila toh direct forward
#                                  → nahi mila toh 6 servers
# ═══════════════════════════════════════════════════════════════════

# Env: GROUP_IDS = "-100123456,-100789012"  (comma separated)
_RAW_GROUP_IDS = os.getenv("GROUP_IDS", "")
WATCHED_GROUP_IDS: List[int] = []
for _gid in _RAW_GROUP_IDS.split(","):
    _gid = _gid.strip()
    if _gid:
        try:
            WATCHED_GROUP_IDS.append(int(_gid))
        except ValueError:
            pass

GRP_INDEX_DB = "group_index.db"
_grp_db_lock = threading.Lock()

# In-memory store: pending group-search results waiting on user confirmation
# key = user_id (int) -> {"results": [...], "search_name": str, "raw_name": str}
grp_pending_confirm: dict = {}
# key = user_id (int) -> True  → bot waiting for user to type "name year" after "Wrong"
grp_awaiting_retry: dict = {}


# ── DB init ──
def _grp_init_db():
    with _grp_db_lock:
        con = sqlite3.connect(GRP_INDEX_DB)
        con.executescript("""
            CREATE TABLE IF NOT EXISTS group_files (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id        INTEGER NOT NULL,
                message_id     INTEGER NOT NULL,
                file_id        TEXT,
                file_name      TEXT,
                clean_title    TEXT,
                quality        TEXT,
                language       TEXT,
                year           TEXT,
                size_mb        REAL,
                file_type      TEXT,
                content_type   TEXT,
                ai_confidence  REAL,
                indexed_at     REAL,
                UNIQUE(chat_id, message_id)
            );
            CREATE INDEX IF NOT EXISTS idx_gf_title ON group_files(clean_title);
            CREATE INDEX IF NOT EXISTS idx_gf_chat  ON group_files(chat_id);
        """)
        # Migration: add newer columns if upgrading from an older DB
        try:
            cols = [row[1] for row in con.execute("PRAGMA table_info(group_files)").fetchall()]
            for col_name, col_type in [
                ("file_type", "TEXT"), ("content_type", "TEXT"), ("ai_confidence", "REAL"),
            ]:
                if col_name not in cols:
                    con.execute(f"ALTER TABLE group_files ADD COLUMN {col_name} {col_type}")
        except Exception as e:
            print(f"⚠️ group_files migration check failed: {e}")
        con.commit()
        con.close()

_grp_init_db()


# ── Caption parser ──
# Input:  "Operation.Safed.Sagar.The.Highest.Air.Force.Mission.S01E04.1080p.NF.WEB-DL.Hindi.DDP5.1.H.265.mkv"
# Output: clean_title="Operation Safed Sagar The Highest Air Force Mission",
#         quality="1080p", language="Hindi", year="", season_ep="S01E04"

_RE_QUALITY  = re.compile(r'\b(4K|2160p|1080p|720p|480p|360p|HDRip|BluRay|WEB-?DL|WEBRip|DVDRip|HDTV)\b', re.I)
_RE_LANG     = re.compile(r'\b(Hindi|English|Tamil|Telugu|Malayalam|Kannada|Punjabi|Bengali|Dual|Multi)\b', re.I)
_RE_YEAR     = re.compile(r'\b(19|20)\d{2}\b')
_RE_SE       = re.compile(r'\bS\d{1,2}E\d{1,2}\b', re.I)
_RE_JUNK     = re.compile(
    r'\b(NF|AMZN|DSNP|HMAX|HDTV|WEB|DL|DDP\d*\.?\d*|AAC\d*\.?\d*|'
    r'H\.?26[45]|x26[45]|HEVC|AVC|10bit|HDR|SDR|DD\+?5?\.?1?|'
    r'BluRay|BRRip|BDRip|CAMRip|mkv|mp4|avi|mov|ts|srt|idx|sub)\b', re.I
)

def _parse_caption(caption: str) -> dict:
    """Parse dotted filename caption into structured fields."""
    # Replace dots/underscores with spaces
    text = re.sub(r'[._]', ' ', caption)
    # Remove extension
    text = re.sub(r'\.(mkv|mp4|avi|mov|ts)$', '', text, flags=re.I)

    quality   = (_RE_QUALITY.search(text) or type('', (), {'group': lambda s, n=0: ''})()).group(0).upper() or "N/A"
    language  = (_RE_LANG.search(text)    or type('', (), {'group': lambda s, n=0: ''})()).group(0).title() or "N/A"
    year      = (_RE_YEAR.search(text)    or type('', (), {'group': lambda s, n=0: ''})()).group(0) or ""
    season_ep = (_RE_SE.search(text)      or type('', (), {'group': lambda s, n=0: ''})()).group(0).upper() or ""

    # Remove all junk tokens to get clean title
    clean = _RE_QUALITY.sub('', text)
    clean = _RE_LANG.sub('', clean)
    clean = _RE_YEAR.sub('', clean)
    clean = _RE_SE.sub('', clean)
    clean = _RE_JUNK.sub('', clean)
    # Remove @channel mentions
    clean = re.sub(r'@\w+', '', clean)
    # Collapse spaces
    clean = re.sub(r'\s+', ' ', clean).strip()

    return {
        "clean_title": clean,
        "quality":     quality,
        "language":    language,
        "year":        year,
        "season_ep":   season_ep,
    }


# ── AI title cleaner (extra cleanup for messy captions) ──
async def _ai_extract_title_info(raw_caption: str, regex_parsed: dict) -> dict:
    """
    AI-smart structured extraction from a raw upload caption/filename.
    Returns a dict with clean_title, year, content_type, confidence — falling
    back gracefully to the regex-parsed values when AI is unavailable or
    returns something unusable.
    """
    fallback = {
        "clean_title":  regex_parsed.get("clean_title", ""),
        "year":         regex_parsed.get("year", ""),
        "content_type": "series" if regex_parsed.get("season_ep") else "movie",
        "confidence":   0.4,  # regex-only baseline
    }
    if not GROQ_API or not raw_caption.strip():
        return fallback

    prompt = (
        "You are cleaning a messy filename from a movie/TV file-sharing group.\n"
        f"Raw text: '{raw_caption[:200]}'\n\n"
        "Extract structured info. Respond with ONLY a JSON object, no markdown, "
        "no explanation, in exactly this shape:\n"
        '{"title": "<clean movie or show name>", "year": "<4-digit year or empty>", '
        '"type": "movie" or "series", "confidence": <0.0-1.0 number for how sure you are>}\n\n'
        "Rules: strip resolution, codec, language, release-group tags, and site "
        "watermarks. Fix obvious spelling mistakes in the title. If it has an "
        "S01E01-style tag, type is 'series'. If you cannot confidently tell what "
        "the title is, set confidence below 0.4."
    )
    try:
        result = await ai_ask(prompt, max_tokens=120)
        if not result:
            return fallback
        # Be tolerant of stray markdown fences the model might add
        cleaned_json = re.sub(r'^```(?:json)?|```$', '', result.strip(), flags=re.MULTILINE).strip()
        data = json.loads(cleaned_json)

        title = str(data.get("title", "")).strip().strip('"').strip("'")
        year  = str(data.get("year", "")).strip()
        ctype = data.get("type", "movie")
        conf  = float(data.get("confidence", 0.5))

        if not (1 <= len(title) <= 100):
            return fallback
        if year and not re.fullmatch(r'(19|20)\d{2}', year):
            year = regex_parsed.get("year", "")
        if ctype not in ("movie", "series"):
            ctype = "series" if regex_parsed.get("season_ep") else "movie"
        conf = max(0.0, min(1.0, conf))

        return {"clean_title": title, "year": year, "content_type": ctype, "confidence": conf}
    except Exception as e:
        print(f"⚠️ AI title extraction failed, using regex fallback: {e}")
        return fallback


async def _ai_clean_title(raw_title: str) -> str:
    """Legacy simple wrapper — kept for any external callers expecting a plain string."""
    if not GROQ_API or not raw_title.strip():
        return raw_title
    result = await ai_ask(
        f"Extract only the movie or TV show name from this text: '{raw_title}'\n"
        "Remove any extra words like resolution, codec, language, streaming service.\n"
        "Return ONLY the clean title, nothing else. Max 60 chars.",
        max_tokens=60,
    )
    if result:
        cleaned = result.strip().strip('"').strip("'")
        if 2 < len(cleaned) < 80:
            return cleaned
    return raw_title


# ── Index a single message ──
async def grp_index_message(message) -> bool:
    """
    Index a video/document message from a group.
    Returns True if indexed successfully.
    """
    # Only index video/document with caption
    file_obj  = message.video or message.document
    if not file_obj:
        return False

    caption = message.caption or ""
    if not caption.strip():
        # Try file name from document
        caption = getattr(file_obj, "file_name", "") or ""
    if not caption.strip():
        return False

    parsed    = _parse_caption(caption)
    raw_title = parsed["clean_title"]

    # AI structured extraction (title + year + type + confidence, cross-checked vs regex)
    ai_info     = await _ai_extract_title_info(caption, parsed)
    clean_title = (ai_info["clean_title"] or raw_title).lower().strip()
    final_year  = ai_info["year"] or parsed["year"]
    content_type = ai_info["content_type"]
    confidence   = ai_info["confidence"]

    if not clean_title or len(clean_title) < 2:
        return False

    size_mb   = round(getattr(file_obj, "file_size", 0) / (1024 * 1024), 1) if getattr(file_obj, "file_size", 0) else 0.0
    file_type = "video" if message.video else "document"

    try:
        await asyncio.to_thread(
            _db_grp_execute,
            """INSERT OR IGNORE INTO group_files
               (chat_id, message_id, file_id, file_name, clean_title,
                quality, language, year, size_mb, file_type,
                content_type, ai_confidence, indexed_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                message.chat.id,
                message.message_id,
                file_obj.file_id,
                caption[:200],
                clean_title,
                parsed["quality"],
                parsed["language"],
                final_year,
                size_mb,
                file_type,
                content_type,
                confidence,
                time.time(),
            )
        )
        print(f"✅ Indexed: '{clean_title}' ({content_type}, AI conf {confidence:.0%}) from chat {message.chat.id} msg {message.message_id}")
        return True
    except Exception as e:
        print(f"⚠️ grp_index_message error: {e}")
        return False


def _db_grp_execute(query: str, params: tuple = ()):
    with _grp_db_lock:
        con = sqlite3.connect(GRP_INDEX_DB)
        try:
            con.execute(query, params)
            con.commit()
        finally:
            con.close()

def _db_grp_fetch(query: str, params: tuple = ()) -> list:
    with _grp_db_lock:
        con = sqlite3.connect(GRP_INDEX_DB)
        try:
            cur = con.execute(query, params)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
        finally:
            con.close()


# ── Fuzzy title search ──
def _grp_title_similarity(a: str, b: str) -> float:
    """Simple word-overlap similarity score 0.0-1.0"""
    a_words = set(re.findall(r'\w+', a.lower()))
    b_words = set(re.findall(r'\w+', b.lower()))
    if not a_words or not b_words:
        return 0.0
    common = a_words & b_words
    # Ignore very short/common words
    stop   = {"the","a","an","of","in","on","at","to","and","or","is","it","wa","ho"}
    common -= stop
    if not common:
        return 0.0
    return len(common) / max(len(a_words), len(b_words))


async def _ai_semantic_rerank(query: str, candidates: List[dict], top_n: int = 8) -> dict:
    """
    When word-overlap scoring leaves close/ambiguous candidates (e.g. 'Don' vs
    'Don 2' vs 'Don 3'), ask the AI to pick which indexed titles genuinely
    match what the user meant. Returns {clean_title: confidence 0.0-1.0}.
    Cheap to skip: only called when the caller judges the top results ambiguous.
    """
    if not GROQ_API or not candidates:
        return {}
    # Unique candidate titles only, capped, to keep the prompt small
    titles = list(dict.fromkeys(c["clean_title"] for c in candidates))[:top_n]
    if not titles:
        return {}
    numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles))
    prompt = (
        f"A user searched for the movie/show: '{query}'\n\n"
        f"Here are indexed titles that partially matched by keyword overlap:\n{numbered}\n\n"
        "For EACH numbered title, decide how likely it is the SAME movie/show "
        "the user meant (not a sequel, not a different film with similar words). "
        "Respond with ONLY a JSON object mapping the number (as a string) to a "
        'confidence 0.0-1.0, e.g. {"1": 0.95, "2": 0.1, "3": 0.6}. No explanation.'
    )
    try:
        result = await ai_ask(prompt, max_tokens=150)
        if not result:
            return {}
        cleaned_json = re.sub(r'^```(?:json)?|```$', '', result.strip(), flags=re.MULTILINE).strip()
        raw_scores = json.loads(cleaned_json)
        out = {}
        for idx_str, conf in raw_scores.items():
            try:
                idx = int(idx_str) - 1
                if 0 <= idx < len(titles):
                    out[titles[idx]] = max(0.0, min(1.0, float(conf)))
            except (ValueError, TypeError):
                continue
        return out
    except Exception as e:
        print(f"⚠️ AI semantic rerank failed, keeping word-overlap scores: {e}")
        return {}


async def grp_search(raw_query: str, limit: int = 5) -> List[dict]:
    """
    Search group index for a movie title.
    1. AI spelling fix
    2. SQLite LIKE search
    3. Fuzzy word-overlap scoring
    4. AI semantic re-rank (only when results are ambiguous — e.g. several
       close scores that could be different movies with overlapping words)
    Returns top matches sorted by score.
    """
    # AI fix spelling
    fixed = await ai_fix_movie_name(raw_query)
    query_clean = fixed.lower().strip()

    # Also try original
    queries = list({query_clean, raw_query.lower().strip()})

    all_rows: List[dict] = []
    for q in queries:
        # LIKE search on each word
        words = [w for w in re.findall(r'\w+', q) if len(w) > 2]
        if not words:
            continue
        # Match rows containing ANY of the main words
        placeholders = " OR ".join(["clean_title LIKE ?"] * len(words))
        params       = tuple(f"%{w}%" for w in words)
        rows = await asyncio.to_thread(
            _db_grp_fetch,
            f"SELECT * FROM group_files WHERE {placeholders} LIMIT 50",
            params,
        )
        all_rows.extend(rows)

    if not all_rows:
        return []

    # Deduplicate by (chat_id, message_id)
    seen   = set()
    unique = []
    for r in all_rows:
        key = (r["chat_id"], r["message_id"])
        if key not in seen:
            seen.add(key)
            unique.append(r)

    # Score by fuzzy similarity
    scored = []
    for r in unique:
        score = _grp_title_similarity(query_clean, r["clean_title"])
        if score > 0.25:  # threshold
            r["_score"] = score
            scored.append(r)

    scored.sort(key=lambda x: x["_score"], reverse=True)

    # Ambiguity check: multiple DISTINCT titles bunched close in score →
    # word-overlap alone can't tell "Don" from "Don 2". Let AI break the tie.
    distinct_titles = {r["clean_title"] for r in scored[:8]}
    if len(distinct_titles) > 1 and scored and (scored[0]["_score"] - scored[min(len(scored)-1, 4)]["_score"]) < 0.35:
        ai_conf = await _ai_semantic_rerank(query_clean, scored[:8])
        if ai_conf:
            for r in scored:
                if r["clean_title"] in ai_conf:
                    # Blend: AI opinion carries more weight than raw overlap once it exists
                    r["_score"] = (0.3 * r["_score"]) + (0.7 * ai_conf[r["clean_title"]])
            scored.sort(key=lambda x: x["_score"], reverse=True)
            # Drop anything AI is confident is a mismatch
            scored = [r for r in scored if r["_score"] > 0.2]

    return scored[:limit]


# ── Build Telegram direct link ──
def _grp_direct_link(chat_id: int, message_id: int) -> str:
    """
    Public channel: t.me/username/msgid
    Private group:  t.me/c/CHATID/msgid  (remove -100 prefix)
    """
    chat_str = str(chat_id)
    if chat_str.startswith("-100"):
        numeric = chat_str[4:]  # remove -100
        return f"https://t.me/c/{numeric}/{message_id}"
    else:
        # public — we don't have username easily, use c/ format
        return f"https://t.me/c/{abs(chat_id)}/{message_id}"


# ── Group message handler (auto-index incoming files) ──
async def grp_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles new video/document in watched groups → auto index."""
    msg = update.effective_message
    if not msg:
        return
    chat_id = msg.chat.id
    if WATCHED_GROUP_IDS and chat_id not in WATCHED_GROUP_IDS:
        return
    if not (msg.video or msg.document):
        return
    await grp_index_message(msg)


# ── /index_channel command — bulk index existing messages ──
async def index_channel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /index_channel <chat_id> [limit]
    Admin command: bulk index existing messages from a group/channel.
    Default limit: 200 messages.
    """
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("🔒 Admin only.", parse_mode="Markdown")
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ *Usage:* `/index_channel CHAT_ID [limit]`\n\n"
            "Example: `/index_channel -1001234567890 500`\n\n"
            "Chat ID `GROUP_IDS` env var mein bhi add karo.",
            parse_mode="Markdown"
        )
        return

    try:
        target_chat = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid chat ID. Numbers mein dena.", parse_mode="Markdown")
        return

    limit = 200
    if len(args) >= 2:
        try:
            limit = min(int(args[1]), 2000)
        except ValueError:
            pass

    status_msg = await update.message.reply_text(
        f"📦 *Indexing chat* `{target_chat}`\n"
        f"Limit: `{limit}` messages\n\n"
        f"_Yeh kuch minutes le sakta hai..._",
        parse_mode="Markdown"
    )

    indexed  = 0
    skipped  = 0
    errors   = 0
    msg_id   = 1
    batch    = 0

    # Telegram mein direct history fetch nahi hota via Bot API
    # Workaround: forward messages from channel to bot's own chat (if public)
    # Better approach: use getUpdates history or forwardFrom
    # We use copyMessage approach — try message IDs sequentially
    # Get latest message_id first
    try:
        chat_info = await context.bot.get_chat(target_chat)
    except Exception as e:
        await status_msg.edit_text(f"❌ Chat access error: `{e}`\n\nBot ko group ka admin banao.", parse_mode="Markdown")
        return

    # Try to get recent messages via forwardMessage trick
    # We'll use a smarter approach: ask user to forward messages OR
    # use channel's linked group if available

    # Actually best approach for channels: iterate message IDs
    # We'll try IDs from high to low (guess latest ~10000)
    # For groups: same approach

    await status_msg.edit_text(
        f"📦 *Indexing* `{target_chat}`\n"
        f"_Message IDs scan kar raha hoon..._\n"
        f"⏳ Progress: `0/{limit}`",
        parse_mode="Markdown"
    )

    # Get a rough idea of latest msg_id by trying high numbers
    latest_id = 1
    for probe in [9999, 4999, 1999, 999, 499, 199, 99]:
        try:
            fwd = await context.bot.forward_message(
                chat_id=update.effective_chat.id,
                from_chat_id=target_chat,
                message_id=probe,
                disable_notification=True,
            )
            latest_id = max(latest_id, probe)
            try: await fwd.delete()
            except: pass
            break
        except Exception:
            pass

    # Scan from latest downward
    scanned  = 0
    check_id = latest_id
    while scanned < limit and check_id > 0:
        try:
            fwd = await context.bot.forward_message(
                chat_id=update.effective_chat.id,
                from_chat_id=target_chat,
                message_id=check_id,
                disable_notification=True,
            )
            # Check if it's a video/document
            if fwd.video or fwd.document:
                # Reconstruct a fake message-like object for grp_index_message
                caption = fwd.caption or ""
                if not caption and fwd.document:
                    caption = getattr(fwd.document, "file_name", "") or ""

                if caption.strip():
                    parsed    = _parse_caption(caption)
                    raw_title = parsed["clean_title"]

                    # Same AI-smart structured extraction used for live uploads,
                    # so bulk-backfilled old files get identical treatment.
                    ai_info      = await _ai_extract_title_info(caption, parsed)
                    clean_title  = (ai_info["clean_title"] or raw_title).lower().strip()
                    final_year   = ai_info["year"] or parsed["year"]
                    content_type = ai_info["content_type"]
                    confidence   = ai_info["confidence"]

                    if clean_title and len(clean_title) > 2:
                        file_obj  = fwd.video or fwd.document
                        file_type = "video" if fwd.video else "document"
                        size_mb   = round(
                            getattr(file_obj, "file_size", 0) / (1024 * 1024), 1
                        ) if getattr(file_obj, "file_size", 0) else 0.0

                        try:
                            await asyncio.to_thread(
                                _db_grp_execute,
                                """INSERT OR IGNORE INTO group_files
                                   (chat_id, message_id, file_id, file_name, clean_title,
                                    quality, language, year, size_mb, file_type,
                                    content_type, ai_confidence, indexed_at)
                                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                (
                                    target_chat,
                                    check_id,
                                    file_obj.file_id,
                                    caption[:200],
                                    clean_title,
                                    parsed["quality"],
                                    parsed["language"],
                                    final_year,
                                    size_mb,
                                    file_type,
                                    content_type,
                                    confidence,
                                    time.time(),
                                )
                            )
                            indexed += 1
                        except Exception:
                            skipped += 1
                    else:
                        skipped += 1
                else:
                    skipped += 1
            try: await fwd.delete()
            except: pass

        except Exception as e:
            err_str = str(e).lower()
            if "message to forward not found" in err_str or "invalid" in err_str:
                pass  # message doesn't exist at this ID
            else:
                errors += 1
                if errors > 20:
                    break

        check_id -= 1
        scanned  += 1
        batch    += 1

        if batch >= 50:
            batch = 0
            try:
                await status_msg.edit_text(
                    f"📦 *Indexing* `{target_chat}`\n"
                    f"⏳ Progress: `{scanned}/{limit}`\n"
                    f"✅ Indexed: `{indexed}` | ⏩ Skipped: `{skipped}`",
                    parse_mode="Markdown"
                )
            except: pass
            await asyncio.sleep(0.5)

    await status_msg.edit_text(
        f"✅ *Index Complete!*\n\n"
        f"📦 Chat: `{target_chat}`\n"
        f"✅ Indexed: `{indexed}` files\n"
        f"⏩ Skipped: `{skipped}`\n"
        f"❌ Errors: `{errors}`\n\n"
        f"_Ab users movie search karenge toh direct link milega!_",
        parse_mode="Markdown"
    )


# ── /grpstats — index stats ──
async def grpstats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("🔒 Admin only.")
        return
    rows = await asyncio.to_thread(
        _db_grp_fetch,
        "SELECT chat_id, COUNT(*) as cnt, MAX(indexed_at) as last FROM group_files GROUP BY chat_id",
        ()
    )
    if not rows:
        await update.message.reply_text(
            "📊 *Group Index Stats*\n\nAbhi koi files indexed nahi.\n\n"
            "👉 `/index_channel CHAT_ID` chalaao.",
            parse_mode="Markdown"
        )
        return
    total = sum(r["cnt"] for r in rows)
    text  = f"📊 *GROUP INDEX STATS*\n\n🗂 Total Files: `{total}`\n━━━━━━━━━━━━━━━━━━\n\n"
    for r in rows:
        last_ts = datetime.fromtimestamp(r["last"], tz=IST).strftime("%d %b, %I:%M %p") if r["last"] else "N/A"
        text += f"💬 Chat `{r['chat_id']}`\n   Files: `{r['cnt']}` | Last: _{last_ts}_\n\n"
    text += f"_Watched Groups: {WATCHED_GROUP_IDS or 'All (GROUP_IDS not set)'}_"
    await update.message.reply_text(text, parse_mode="Markdown")


# ── /clrindex — clear index ──
async def clrindex_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("🔒 Admin only.")
        return
    args = context.args
    if args:
        try:
            chat_id = int(args[0])
            await asyncio.to_thread(
                _db_grp_execute,
                "DELETE FROM group_files WHERE chat_id=?",
                (chat_id,)
            )
            await update.message.reply_text(f"🗑 Chat `{chat_id}` ka index clear ho gaya.", parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}", parse_mode="Markdown")
    else:
        await asyncio.to_thread(_db_grp_execute, "DELETE FROM group_files", ())
        await update.message.reply_text("🗑 *Poora group index clear ho gaya!*", parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════════
#       MOVIE SEARCH (OMDB)
# ═══════════════════════════════════════════════════════════════════
def _grp_file_caption(r: dict) -> str:
    quality  = r.get("quality",  "N/A")
    language = r.get("language", "N/A")
    year     = r.get("year",     "")
    size_mb  = r.get("size_mb",  0.0)
    size_str = f"{size_mb:.0f} MB" if size_mb else "N/A"
    return (
        f"🎬 *{r['clean_title'].title()}*"
        + (f" `({year})`" if year else "") + "\n"
        f"📺 `{quality}` | 🌐 `{language}` | 💾 `{size_str}`"
    )


async def _grp_send_one_file(context, chat_id, r: dict) -> bool:
    """Send a single indexed file (video or document) to chat_id. Returns True on success."""
    file_id = r.get("file_id", "")
    if not file_id:
        return False
    caption = _grp_file_caption(r)
    try:
        if r.get("file_type") == "video":
            await context.bot.send_video(
                chat_id=chat_id, video=file_id, caption=caption, parse_mode="Markdown",
            )
        else:
            await context.bot.send_document(
                chat_id=chat_id, document=file_id, caption=caption, parse_mode="Markdown",
            )
        return True
    except Exception as e:
        print(f"⚠️ Send file_id failed: {e}")
        try:
            await context.bot.send_document(
                chat_id=chat_id, document=file_id, caption=caption, parse_mode="Markdown",
            )
            return True
        except Exception:
            return False


async def _grp_send_all_files(update_or_query_message, context, chat_id, grp_results, user_id, search_name):
    """Send ALL matching files from group index, then a summary + web-server fallback button."""
    sent_count = 0
    fail_count = 0
    for r in grp_results:
        ok = await _grp_send_one_file(context, chat_id, r)
        if ok:
            sent_count += 1
            await asyncio.sleep(0.3)  # flood control
        else:
            fail_count += 1

    kb = [[InlineKeyboardButton("🌐 6 Web Servers", callback_data=f"grp_fallback_{search_name[:30]}")]]
    await update_or_query_message.reply_text(
        f"✅ *Done!*\n\n"
        f"📤 Sent: `{sent_count}` files\n"
        + (f"❌ Failed: `{fail_count}`\n" if fail_count else "")
        + f"\n_Web servers bhi chahiye?_ 👇",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb),
    )

    log_search(search_name, str(user_id))
    add_search_points(user_id)


async def _grp_offer_confirmation(context, chat_id, grp_results, raw_name, search_name, user_id):
    """Send 2-3 sample files from group index + Sahi/Wrong confirm buttons."""
    title_display = grp_results[0]["clean_title"].title()
    score_pct     = int(grp_results[0]["_score"] * 100)

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"⚡ *Group mein mila!*\n\n"
            f"🎬 *{title_display}*\n"
            f"🎯 Match: `{score_pct}%`\n"
            f"📦 Total files: `{len(grp_results)}`\n\n"
            f"_Pehle {min(3, len(grp_results))} sample bhej raha hoon, check karo 👇_"
        ),
        parse_mode="Markdown",
    )

    sample = grp_results[:3]
    for r in sample:
        await _grp_send_one_file(context, chat_id, r)
        await asyncio.sleep(0.3)

    # Store pending results for this user so callbacks can retrieve them
    grp_pending_confirm[user_id] = {
        "results": grp_results,
        "search_name": search_name,
        "raw_name": raw_name,
    }

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Sahi Movie",  callback_data="grp_confirm_yes"),
         InlineKeyboardButton("❌ Wrong Movie", callback_data="grp_confirm_no")],
    ])
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "🎯 *Ye sahi movie hai?*\n\n"
            "✅ Sahi → Sab quality/language files bhej dunga\n"
            "❌ Wrong → Naya naam + year batao"
        ),
        parse_mode="Markdown",
        reply_markup=kb,
    )


async def _run_omdb_fallback(update, context, loader, raw_name, search_name, user_id):
    """OMDB + web-server search (used when group index has no match)."""
    try:
        await loader.edit_text(
            "🌐 Web search chal raha hai...\n" + progress_bar(3, 6),
            parse_mode="Markdown"
        )
    except: pass

    data = await asyncio.to_thread(get_omdb, search_name)
    if not data or data.get("Response") == "False":
        data = await asyncio.to_thread(get_omdb, raw_name)

    if not data or data.get("Response") == "False":
        results = await asyncio.to_thread(get_omdb_search, search_name)
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
                    f"🔍 *'{raw_name}'* ke liye kaunsi movie chahiye?\n\nChoose karo 👇",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return

    if not data or data.get("Response") == "False":
        try:
            await loader.edit_text(
                f"❌ *'{raw_name}'* nahi mili\n\n"
                f"💡 *Try karo:*\n• /plotsearch\n• /suggest\n• /mood\n• /random",
                parse_mode="Markdown"
            )
        except: pass
        return

    try: await loader.delete()
    except: pass
    await _send_movie_card(update, context, data, is_search=True)


async def _run_full_search(update, context, raw_name: str):
    """Search pipeline: poster/info card only. Group video fetch happens on 'Direct Video' button tap."""
    user = update.effective_user
    loader = await update.message.reply_text(
        "🔍 Searching...\n" + progress_bar(0, 6), parse_mode="Markdown"
    )
    await animate_search(loader)

    # ── STEP 1: AI spelling fix ──
    fixed_name  = await ai_fix_movie_name(raw_name)
    search_name = fixed_name if fixed_name.lower() != raw_name.lower() else raw_name

    # ── STEP 2: Show poster/info card ──
    poster_data = await asyncio.to_thread(get_omdb, search_name)
    if not poster_data or poster_data.get("Response") == "False":
        poster_data = await asyncio.to_thread(get_omdb, raw_name)

    if poster_data and poster_data.get("Response") == "True":
        try: await loader.delete()
        except: pass
        await _send_movie_card(update, context, poster_data, is_search=True)
        return

    # ── STEP 3: OMDB has nothing → try group index directly, else full fallback ──
    grp_results = await grp_search(search_name, limit=20)
    if grp_results:
        try: await loader.delete()
        except: pass
        await _grp_offer_confirmation(context, update.effective_chat.id, grp_results, raw_name, search_name, user.id)
        return

    await _run_omdb_fallback(update, context, loader, raw_name, search_name, user.id)


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

    # If user was asked to retype "name year" after clicking Wrong, handle that here
    if grp_awaiting_retry.get(user.id):
        grp_awaiting_retry.pop(user.id, None)
        grp_pending_confirm.pop(user.id, None)
        await _run_full_search(update, context, raw_name)
        return

    await _run_full_search(update, context, raw_name)


# ── Callback: user confirms group sample is the correct movie ──
async def grp_confirm_yes_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    pending = grp_pending_confirm.pop(user_id, None)
    if not pending:
        await query.answer("⚠️ Session expired, dubara search karo.", show_alert=True)
        return
    await query.answer("📤 Sab files bhej raha hoon...")
    try:
        await query.message.edit_reply_markup(reply_markup=None)
    except: pass
    await _grp_send_all_files(
        query.message, context, query.message.chat.id,
        pending["results"], user_id, pending["search_name"],
    )


# ── Callback: user says sample was the wrong movie ──
async def grp_confirm_no_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    grp_pending_confirm.pop(user_id, None)
    grp_awaiting_retry[user_id] = True
    await query.answer()
    try:
        await query.message.edit_reply_markup(reply_markup=None)
    except: pass
    await query.message.reply_text(
        "❌ *Theek hai!*\n\n✏️ Sahi movie ka *naam aur year* bhejo\n"
        "_Example: Pathaan 2023_",
        parse_mode="Markdown",
    )


# ── Callback: user tapped "🎬 Direct Video ⚡" on the poster card ──
async def grp_direct_video_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    msg_id = query.data.replace("gv_", "")
    stored = context.user_data.get(msg_id) if msg_id != "pending" else None

    if not stored or not stored.get("title"):
        await query.message.reply_text(
            "⚠️ Session expired. Movie naam dubara bhejo.",
            parse_mode="Markdown",
        )
        return

    title = stored["title"]
    year  = stored.get("year", "")
    search_name = f"{title} {year}".strip()

    chat_id = query.message.chat.id
    loader  = await context.bot.send_message(
        chat_id=chat_id,
        text="⏳ *Finding...*\n" + progress_bar(0, 6),
        parse_mode="Markdown",
    )
    await animate_search(loader)

    grp_results = await grp_search(title, limit=20)
    try: await loader.delete()
    except: pass

    if grp_results:
        await _grp_offer_confirmation(context, chat_id, grp_results, search_name, title, user_id)
    else:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🌐 6 Web Servers", callback_data=f"grp_fallback_{title[:30]}")],
        ])
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"❌ *'{title}'* group mein nahi mili.\n\n_Web servers try karo 👇_",
            parse_mode="Markdown",
            reply_markup=kb,
        )


# ── Callback: user ne "6 Web Servers" choose kiya when group had result ──
async def grp_fallback_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🌐 Web servers load ho rahe hain...")
    raw_name = query.data.replace("grp_fallback_", "")
    loader   = await query.message.reply_text(
        "🌐 Web servers dhundh raha hoon...\n" + progress_bar(2, 6),
        parse_mode="Markdown"
    )
    data = await asyncio.to_thread(get_omdb, raw_name)
    if not data or data.get("Response") == "False":
        data = await asyncio.to_thread(get_omdb_search, raw_name)
        if data and isinstance(data, list) and data:
            data = await asyncio.to_thread(get_omdb, data[0].get("imdbID",""), True)
    try: await loader.delete()
    except: pass
    if data and isinstance(data, dict) and data.get("Response") == "True":
        await _send_movie_card(update, context, data, reply_to=query.message, is_search=False)
    else:
        await query.message.reply_text(
            f"❌ *'{raw_name}'* OMDB pe nahi mila.\n\n_Naam aur clearly likhke try karo._",
            parse_mode="Markdown"
        )

async def movieinfo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_maintenance() and not is_admin(update.effective_user.id):
        await update.message.reply_text("🚧 Maintenance mode.")
        return
    if not TMDB_API:
        await update.message.reply_text("⚠️ *TMDB_API not set!*", parse_mode="Markdown")
        return
    title = " ".join(context.args).strip() if context.args else ""
    if not title:
        await update.message.reply_text("❌ *Usage:* `/movieinfo Movie Name`", parse_mode="Markdown")
        return
    await send_movie_card(update, context, title)

async def pick_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    await query.answer("🎬 Loading...")
    imdb_id = query.data.replace("pick_", "")
    loader  = await query.message.reply_text("🎬 Loading...\n" + progress_bar(2, 6), parse_mode="Markdown")
    await animate_search(loader)
    data = await asyncio.to_thread(get_omdb, imdb_id, True)
    try: await loader.delete()
    except: pass
    if data and data.get("Response") == "True":
        await _send_movie_card(update, context, data, reply_to=query.message, is_search=True)
    else:
        await query.message.reply_text("❌ Load nahi hua. Try again.", parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════════
#   AI REVIEW / FUN FACTS / RATE / SIMILAR / SERVERS / BACK CALLBACKS
# ═══════════════════════════════════════════════════════════════════
async def review_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🤖 Writing review...")
    imdb_id    = query.data.split("_", 1)[1]
    movie_data = await asyncio.to_thread(get_omdb, imdb_id, True)
    if not movie_data or movie_data.get("Response") == "False":
        await query.message.reply_text("❌ Movie details fetch nahi ho payi!")
        return
    loader = await query.message.reply_text("🤖 Writing AI Review...\n" + progress_bar(0, 4), parse_mode="Markdown")
    await animate_generic(loader, FRAMES["review"])
    review = await ai_movie_review(
        movie_data.get("Title","N/A"), movie_data.get("Year","N/A"),
        movie_data.get("Plot","N/A"), movie_data.get("imdbRating","N/A")
    )
    try: await loader.delete()
    except: pass
    if review:
        await query.message.reply_text(
            f"╔══════════════════════╗\n║  🤖  *AI REVIEW* ║\n╚══════════════════════╝\n\n"
            f"🎬 *{movie_data['Title']}* ({movie_data['Year']})\n━━━━━━━━━━━━━━━━━━\n\n"
            f"{review}\n\n_Powered by Groq AI (Llama 3.3)_ 🤖",
            parse_mode="Markdown")
    else:
        await query.message.reply_text("❌ Groq API ne response nahi diya.", parse_mode="Markdown")

async def funfact_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("💡 Finding fun facts...")
    try: imdb_id = query.data.split("_", 1)[1]
    except IndexError:
        await query.message.reply_text("⚠️ Error.")
        return
    movie_data = await asyncio.to_thread(get_omdb, imdb_id, True)
    if not movie_data or movie_data.get("Response") == "False":
        await query.message.reply_text("❌ Movie details fetch nahi ho payi!")
        return
    loader = await query.message.reply_text("💡 Finding Fun Facts...\n" + progress_bar(0, 3), parse_mode="Markdown")
    await animate_generic(loader, FRAMES["ai"])
    facts = await ai_fun_facts(
        movie_data.get("Title","N/A"), movie_data.get("Year","N/A"),
        movie_data.get("Director","N/A"), movie_data.get("Actors","N/A")
    )
    try: await loader.delete()
    except: pass
    if facts:
        await query.message.reply_text(
            f"╔══════════════════════╗\n║  💡  *FUN FACTS* ║\n╚══════════════════════╝\n\n"
            f"🎬 *{movie_data.get('Title')}* ({movie_data.get('Year')})\n━━━━━━━━━━━━━━━━━━\n\n"
            f"{facts}\n\n_Powered by Groq AI (Llama 3.3)_ 🤖",
            parse_mode="Markdown")
    else:
        await query.message.reply_text("❌ Groq API ne response nahi diya.", parse_mode="Markdown")

async def rate_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query      = update.callback_query
    await query.answer()
    msg_id     = query.data.split("_", 1)[1]
    movie_data = context.user_data.get(msg_id)
    if not movie_data:
        await query.message.reply_text("⚠️ Session expired.", parse_mode="Markdown")
        return
    title    = movie_data["title"]
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
        await query.message.edit_text("⚠️ Session expired.", parse_mode="Markdown")
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

async def similar_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query      = update.callback_query
    await query.answer("🎯 Finding similar...")
    msg_id     = query.data.split("_", 1)[1]
    movie_data = context.user_data.get(msg_id)
    if not movie_data:
        await query.message.reply_text("⚠️ Session expired.")
        return
    loader = await query.message.reply_text("🎯 Loading...\n" + progress_bar(0, 3), parse_mode="Markdown")
    await animate_generic(loader, FRAMES["similar"])
    title   = movie_data["title"]
    similar = get_tmdb_similar(title)
    try: await loader.delete()
    except: pass
    if similar:
        text = f"🎯 *Similar to {title}:*\n━━━━━━━━━━━━━━━━━━\n\n"
        medals = ["🥇","🥈","🥉","🏅","🎖","🌟"]
        for i, (t, r) in enumerate(similar):
            text += f"{medals[i]} *{t}* ⭐`{r}`\n"
        text += "\n_Type naam to search_ 🔎"
    elif GROQ_API:
        result = await ai_similar_deep(title, movie_data.get("year",""), movie_data.get("genre",""))
        text = f"🤖 *AI Similar to {title}:*\n━━━━━━━━━━━━━━━━━━\n\n{result or 'Not found'}"
    else:
        text = "_TMDB/Groq API add karo for similar movies_"
    await query.message.reply_text(text, parse_mode="Markdown")

async def servers_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query      = update.callback_query
    await query.answer("🌐 Loading servers...")
    msg_id     = query.data.split("_", 1)[1]
    movie_data = context.user_data.get(msg_id)
    if not movie_data:
        await query.message.reply_text("⚠️ Session expired.")
        return
    loader = await query.message.reply_text("🌐 Loading servers...\n" + progress_bar(0, 4), parse_mode="Markdown")
    await animate_generic(loader, FRAMES["server"])
    try: await loader.delete()
    except: pass
    urls  = movie_data["servers"]
    names = movie_data["names"]
    title = movie_data["title"]
    medals   = ["🥇","🥈","🥉","🏅","🎖","🌟"]
    keyboard = [[InlineKeyboardButton(f"{medals[i]} {names[i]}", url=urls[i])] for i in range(6)]
    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data=f"bk_{msg_id}")])
    sent = await query.message.reply_text(
        f"🌐 *6 DOWNLOAD SERVERS*\n\n🎬 *{title}*\n━━━━━━━━━━━━━━━━━━\n"
        "Pick any server 👇\n\n🦁 *Brave Browser = No Ads!*\n⏱ _Deletes in 1 min_",
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
    loader = await query.message.reply_text("🔄 Loading...\n" + progress_bar(0, 3), parse_mode="Markdown")
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
             InlineKeyboardButton("❤️ Watchlist", callback_data=f"wl_save|{str(movie_data['title']).replace('|','')[:40]}|{movie_data['year']}|{movie_data['rating']}")],
            [InlineKeyboardButton(f"⬇️ {names[0]}", url=urls[0])],
            [InlineKeyboardButton("🌐 All 6 Servers", callback_data=f"srv_{msg_id}"),
             InlineKeyboardButton("🎯 Similar",       callback_data=f"sim_{msg_id}")]
        ])
    )

async def director_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query    = update.callback_query
    await query.answer("🎥 Loading director films...")
    from urllib.parse import unquote
    director = unquote(query.data.replace("dir_", ""))
    loader = await query.message.reply_text("🎥 Loading...\n" + progress_bar(0, 3), parse_mode="Markdown")
    await animate_generic(loader, FRAMES["similar"])
    movies = get_director_movies(director)
    try: await loader.delete()
    except: pass
    if movies:
        text = f"🎥 *Top 5 by {director}:*\n━━━━━━━━━━━━━━━━━━\n\n"
        medals = ["🥇","🥈","🥉","🏅","🎖"]
        for i, (t, r) in enumerate(movies):
            text += f"{medals[i]} *{t}* — ⭐`{r}`\n"
        text += "\n_Type naam to search_ 🔎"
    else:
        text = f"🎥 *{director}* ki movies:\n\nTMDB API add karo for results."
    await query.message.reply_text(text, parse_mode="Markdown")



# ═══════════════════════════════════════════════════════════════════
#   MOOD / COMPARE / SUGGEST / PLOTSEARCH
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
        "🎭 *MOOD PICKER*\n\n📝 *Apna mood batao:*\n\n"
        "• Sad hoon\n• Bored hoon comedy chahiye\n"
        "• Family ke saath dekhni\n• Late night thriller\n\n/cancel to exit",
        parse_mode="Markdown"
    )
    return W_MOOD

async def mood_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mood   = update.message.text.strip()
    loader = await update.message.reply_text("🎭 Mood samajh raha hun...\n" + progress_bar(0, 4), parse_mode="Markdown")
    await animate_generic(loader, FRAMES["mood"])
    result = await ai_mood_recommend(mood)
    try: await loader.delete()
    except: pass
    if result:
        await update.message.reply_text(
            f"🎭 *MOOD PICKS FOR YOU*\n\n*Tumhara mood:* _{mood}_\n━━━━━━━━━━━━━━━━━━\n\n"
            f"{result}\n\n_Type naam to search_ 🔎",
            parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ *Kuch nahi mila.*\n\n_GROQ_API add karo._", parse_mode="Markdown")
    return ConversationHandler.END

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
        "⚖️ *COMPARE MOVIES*\n\n📝 *Pehli movie ka naam bhejo:*\n\n/cancel",
        parse_mode="Markdown"
    )
    return W_COMPARE_1

async def compare_recv1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["compare_m1"] = update.message.text.strip()
    await update.message.reply_text(
        f"✅ *Movie 1:* _{context.user_data['compare_m1']}_\n\n📝 *Ab doosri movie:*\n\n/cancel",
        parse_mode="Markdown"
    )
    return W_COMPARE_2

async def compare_recv2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m1 = context.user_data.get("compare_m1", "")
    m2 = update.message.text.strip()
    loader = await update.message.reply_text("⚖️ Comparing...\n" + progress_bar(0, 4), parse_mode="Markdown")
    await animate_generic(loader, FRAMES["compare"])
    result = await ai_compare_movies(m1, m2)
    try: await loader.delete()
    except: pass
    if result:
        await update.message.reply_text(
            f"⚖️ *MOVIE COMPARISON*\n\n🎬 *{m1}*  vs  🎬 *{m2}*\n━━━━━━━━━━━━━━━━━━\n\n"
            f"{result}\n\n_Powered by Groq AI (Llama 3.3)_ 🤖",
            parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Comparison nahi hua.", parse_mode="Markdown")
    return ConversationHandler.END

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
        "🤖 *AI SUGGEST*\n\n📝 *Batao kya chahiye:*\n\n"
        "• Mujhe action movie chahiye\n• RRR jaisi movie\n• Best 2023 thriller\n\n/cancel to exit",
        parse_mode="Markdown"
    )
    return W_AI_QUERY

async def suggest_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.message.text.strip()
    loader = await update.message.reply_text("🤖 Thinking...\n" + progress_bar(0, 4), parse_mode="Markdown")
    await animate_generic(loader, FRAMES["ai"])
    result = await ai_recommend(query)
    try: await loader.delete()
    except: pass
    if result:
        await update.message.reply_text(
            f"🤖 *AI PICKS FOR YOU*\n\n{result}\n\n━━━━━━━━━━━━━━━━━━\n_Movie naam type karo to search_ 🔎",
            parse_mode="Markdown")
    else:
        await update.message.reply_text(
            "🥇 RRR (2022)\n🥈 KGF 2 (2022)\n🥉 Pushpa (2021)\n\n_GROQ_API add karo better results ke liye!_ 🤖",
            parse_mode="Markdown")
    return ConversationHandler.END

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
        "🔍 *PLOT SEARCH*\n\n📝 *Movie ka scene/plot describe karo:*\n\n"
        "• Train crash wali movie\n• Ladka matrix world mein jaata\n"
        "• Two brothers fight for gold\n\n/cancel to exit",
        parse_mode="Markdown"
    )
    return W_PLOT_SEARCH

async def plotsearch_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    desc   = update.message.text.strip()
    loader = await update.message.reply_text("🔍 Searching...\n" + progress_bar(0, 4), parse_mode="Markdown")
    await animate_generic(loader, FRAMES["ai"])
    result = await ai_plot_search(desc)
    try: await loader.delete()
    except: pass
    if result:
        await update.message.reply_text(
            f"🔍 *PLOT MATCH RESULTS*\n\n{result}\n\n━━━━━━━━━━━━━━━━━━\n_Movie naam type karo to search_ 🔎",
            parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ *Match nahi mila.*\n\n_GROQ_API add karo._", parse_mode="Markdown")
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════════════
#   LANGUAGE FILTER
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
#   TRENDING / RANDOM / DAILY
# ═══════════════════════════════════════════════════════════════════
async def trending_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_maintenance() and not is_admin(update.effective_user.id):
        await update.message.reply_text("🚧 Maintenance.")
        return
    loader = await update.message.reply_text("🔥 Loading trending...\n" + progress_bar(1, 3), parse_mode="Markdown")
    await asyncio.sleep(0.8)
    tmdb_t = get_tmdb_trending()
    bot_t  = get_trending(5)
    try: await loader.delete()
    except: pass
    text = "🔥 *TRENDING NOW*\n\n"
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
    loader = await update.message.reply_text("🎲 Picking random...\n" + progress_bar(3, 6), parse_mode="Markdown")
    await asyncio.sleep(1.2)
    seen = context.user_data.get("random_seen", [])
    pool = [m for m in RANDOM_POOL if m not in seen]
    if not pool:
        seen = []; pool = RANDOM_POOL.copy(); context.user_data["random_seen"] = []
    pick = random.choice(pool)
    seen.append(pick)
    context.user_data["random_seen"] = seen
    data = await asyncio.to_thread(get_omdb, pick)
    try: await loader.delete()
    except: pass
    if data and data.get("Response") == "True":
        remaining = len(RANDOM_POOL) - len(seen)
        await update.message.reply_text(f"🎲 *Random Pick* | _{remaining} more unseen_", parse_mode="Markdown")
        await _send_movie_card(update, context, data)
    else:
        await update.message.reply_text(f"🎲 *Random Pick:* _{pick}_\n\nType to search! 🔎", parse_mode="Markdown")

DAILY_MOVIES = [
    "Inception","The Dark Knight","Interstellar","RRR","KGF",
    "Bahubali 2","3 Idiots","Dangal","Andhadhun","Tumbbad",
    "Dune","Oppenheimer","Pathaan","Animal","Jawan",
]

async def daily_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_maintenance() and not is_admin(update.effective_user.id):
        await update.message.reply_text("🚧 Maintenance.")
        return
    today = str(today_ist())
    daily = load_json("daily")
    loader = await update.message.reply_text("🎬 Loading daily pick...\n" + progress_bar(0, 3), parse_mode="Markdown")
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
#   WATCHLIST / ALERTS / MYSTATS / REFER / LEADERBOARD / HISTORY
# ═══════════════════════════════════════════════════════════════════
async def watchlist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = str(update.effective_user.id)
    data = load_json("watchlist")
    wl   = data.get(uid, [])
    if not wl:
        await update.message.reply_text(
            "❤️ *WATCHLIST*\n\n📭 *Empty Watchlist!*\n\n_Movie search karo aur ❤️ tap karo_",
            parse_mode="Markdown")
        return
    text = f"❤️ *WATCHLIST*\n\n📋 *{len(wl)} Movies Saved:*\n━━━━━━━━━━━━━━━━━━\n\n"
    for i, m in enumerate(wl, 1):
        text += f"`{i}.` 🎬 *{m['title']}* `({m['year']})` ⭐`{m['rating']}`\n"
    text += "\n_Search karo movie naam type karke_ 🔎"
    await update.message.reply_text(
        text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🗑 Clear All", callback_data="wl_clear")]]))

async def wl_save_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try: parts = query.data.split("|"); title, year, rating = parts[1], parts[2], parts[3]
    except IndexError:
        await query.answer("⚠️ Error saving.", show_alert=True)
        return
    uid  = str(query.from_user.id)
    data = load_json("watchlist")
    if uid not in data: data[uid] = []
    if any(m["title"] == title for m in data[uid]):
        await query.answer("⚠️ Already in Watchlist!", show_alert=True)
        return
    data[uid].append({"title": title, "year": year, "rating": rating, "saved": now_ist().strftime("%d %b %Y")})
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

async def alerts_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid   = str(update.effective_user.id)
    data  = load_json("alerts")
    my_al = data.get(uid, [])
    text     = "🔔 *MY ALERTS*\n\n"
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
    await update.message.reply_text(text, parse_mode="Markdown",
                                    reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None)

async def alert_add_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try: parts = query.data.split("|"); title, year = parts[1], parts[2]
    except IndexError:
        await query.answer("⚠️ Error.", show_alert=True)
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
        f"📊 *MY STATS*\n\n👤 *{update.effective_user.full_name}*\n\n"
        f"🏆 Badge: {badge}\n⭐ Points: `{pts}`\n🔎 Searches: `{srch}`\n"
        f"❤️ Watchlist: `{len(wl)}`\n📜 History: `{hist}` movies\n👥 Refers: `{refs}`\n\n"
        f"📈 *Next:* {next_badge}\n\n_Search=+10 • Refer=+50 • Rate=+5_ 🎯",
        parse_mode="Markdown")

async def refer_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user     = update.effective_user
    uid      = str(user.id)
    users    = load_json("users")
    refs     = users.get(uid, {}).get("refs",   0)
    pts      = users.get(uid, {}).get("points", 0)
    bot_info = await context.bot.get_me()
    link     = f"https://t.me/{bot_info.username}?start={user.id}"
    await update.message.reply_text(
        f"👥 *REFER & EARN*\n\n🔗 *Your Link:*\n`{link}`\n\n"
        f"👥 Referred: `{refs}` users\n⭐ Points: `{pts}`\n\n"
        f"💰 Har refer = +50 points 🎁\n_Share karo aur points kamao!_ 🚀",
        parse_mode="Markdown")

async def leaderboard_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = load_json("users")
    sorted_users = sorted(users.values(), key=lambda x: x.get("points", 0), reverse=True)[:10]
    medals = ["🥇","🥈","🥉","🏅","🎖","⭐","🌟","💫","✨","🎬"]
    text = "🏆 *LEADERBOARD*\n\n*Top 10 CineBot Users:*\n━━━━━━━━━━━━━━━━━━\n\n"
    for i, u in enumerate(sorted_users):
        badge = get_badge(u.get("points", 0))
        raw_name = u.get("name", "Unknown")[:15]
        name = re.sub(r'([*_`\[\]()])', r'\\\1', raw_name)
        pts  = u.get("points", 0)
        text += f"{medals[i]} *{name}* — `{pts}` pts {badge}\n"
    text += "\n_Search=+10 | Refer=+50 | Rate=+5_ 🎯"
    await update.message.reply_text(text, parse_mode="Markdown")

async def history_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid     = str(update.effective_user.id)
    history = load_json("history")
    my_hist = history.get(uid, [])
    if not my_hist:
        await update.message.reply_text(
            "📜 *HISTORY*\n\n📭 *Koi history nahi!*\n\n_Movies search karo_ 🔎",
            parse_mode="Markdown")
        return
    text = f"📜 *MY HISTORY*\n\n*Last {len(my_hist)} Searches:*\n━━━━━━━━━━━━━━━━━━\n\n"
    for i, h in enumerate(my_hist, 1):
        text += f"`{i}.` 🎬 *{h['movie']}* — `{h['time']}`\n"
    text += "\n_Type naam to search again_ 🔎"
    await update.message.reply_text(text, parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════════
#   QUIZ
# ═══════════════════════════════════════════════════════════════════
QUIZ_QUESTIONS = [
    {"q": "🎬 'Inception' ka director kaun hai?",
     "opts": ["Christopher Nolan","Steven Spielberg","James Cameron","Ridley Scott"], "ans": 0},
    {"q": "🎬 'RRR' movie kab release hui?",
     "opts": ["2021","2022","2023","2020"], "ans": 1},
    {"q": "🎬 'Bahubali' ka villain kaun hai?",
     "opts": ["Bhallaladeva","Kattappa","Bijjaladeva","Inkoshi"], "ans": 0},
    {"q": "🎬 '3 Idiots' mein Rancho ka asli naam kya hai?",
     "opts": ["Farhan","Raju","Phunsukh Wangdu","Virus"], "ans": 2},
    {"q": "🎬 'KGF Chapter 2' mein villain kaun hai?",
     "opts": ["Rocky","Adheera","Garuda","Andrews"], "ans": 1},
    {"q": "🎬 'Dangal' kis par based hai?",
     "opts": ["Saina Nehwal","Mahavir Singh Phogat","MS Dhoni","Milkha Singh"], "ans": 1},
    {"q": "🎬 'Pushpa' main character ka naam kya hai?",
     "opts": ["Pushpa Raj","Pushpa Kumar","Pushpa Vikram","Pushpa Singh"], "ans": 0},
    {"q": "🎬 'Tumbbad' konse genre ki movie hai?",
     "opts": ["Action","Comedy","Horror/Fantasy","Romance"], "ans": 2},
    {"q": "🎬 'Andhadhun' mein main actor kaun hai?",
     "opts": ["Ayushmann Khurrana","Rajkummar Rao","Vicky Kaushal","Irrfan Khan"], "ans": 0},
    {"q": "🎬 'Pathaan' mein SRK ka character naam kya hai?",
     "opts": ["Tiger","Pathaan","Kabir","Arjun"], "ans": 1},
]

async def quiz_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_maintenance() and not is_admin(update.effective_user.id):
        await update.message.reply_text("🚧 Maintenance.")
        return
    loader = await update.message.reply_text("🎯 Loading quiz...\n" + progress_bar(0, 3), parse_mode="Markdown")
    await animate_generic(loader, FRAMES["quiz"])
    try: await loader.delete()
    except: pass
    asked = context.user_data.get("quiz_asked", [])
    remaining = [i for i in range(len(QUIZ_QUESTIONS)) if i not in asked]
    if not remaining:
        asked = []; remaining = list(range(len(QUIZ_QUESTIONS)))
    idx = random.choice(remaining)
    asked.append(idx)
    context.user_data["quiz_asked"] = asked
    q = QUIZ_QUESTIONS[idx]
    context.user_data["quiz_ans"]  = q["ans"]
    context.user_data["quiz_q"]    = q["q"]
    context.user_data["quiz_opts"] = q["opts"]
    keyboard = [
        [InlineKeyboardButton(f"{['A','B','C','D'][i]}. {opt}", callback_data=f"quiz_ans_{i}")]
        for i, opt in enumerate(q["opts"])
    ]
    await update.message.reply_text(
        f"🎮 *MOVIE QUIZ*\n\n{q['q']}\n\n_Sahi jawab = +20 points_ ⭐\n\nChoose your answer 👇",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard))

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
            parse_mode="Markdown")
    else:
        stored_opts  = context.user_data.get("quiz_opts", [])
        correct_text = stored_opts[correct] if stored_opts and 0 <= correct < len(stored_opts) else "N/A"
        await query.message.edit_text(
            f"❌ *GALAT JAWAB!*\n\n✅ Sahi: *{correct_text}*\n\n_/quiz — Try again_ 🎯",
            parse_mode="Markdown")



# ═══════════════════════════════════════════════════════════════════
#   UPCOMING MOVIES SYSTEM
# ═══════════════════════════════════════════════════════════════════
def _upcom_init_db():
    db_path = os.environ.get("DB_PATH", "movies.db")
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS upcom_reminders (
            user_id  INTEGER,
            movie_id INTEGER,
            title    TEXT,
            release  TEXT,
            PRIMARY KEY (user_id, movie_id)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS upcom_mylist (
            user_id    INTEGER,
            movie_id   INTEGER,
            title      TEXT,
            release    TEXT,
            genres     TEXT,
            poster     TEXT,
            rating     REAL,
            added_at   TEXT,
            PRIMARY KEY (user_id, movie_id)
        )
    """)
    con.commit()
    con.close()

_upcom_init_db()
_DB_PATH = os.environ.get("DB_PATH", "movies.db")

def _db_fetch(query: str, params: tuple = (), db: str = None) -> list:
    con = sqlite3.connect(db or _DB_PATH)
    try: rows = con.execute(query, params).fetchall()
    finally: con.close()
    return rows

def _db_execute(query: str, params: tuple = (), db: str = None) -> int:
    con = sqlite3.connect(db or _DB_PATH)
    try:
        cur = con.execute(query, params)
        con.commit()
        return cur.rowcount
    finally: con.close()

UPCOM_GENRE_MAP = {
    28:"Action",12:"Adventure",16:"Animation",35:"Comedy",
    80:"Crime",99:"Documentary",18:"Drama",10751:"Family",
    14:"Fantasy",36:"History",27:"Horror",10402:"Music",
    9648:"Mystery",10749:"Romance",878:"Sci-Fi",10770:"TV Movie",
    53:"Thriller",10752:"War",37:"Western",
}
UPCOM_NAME_TO_ID = {v.lower(): k for k, v in UPCOM_GENRE_MAP.items()}

def _upcom_genre_names(ids: list) -> str:
    return " · ".join(UPCOM_GENRE_MAP.get(i, "?") for i in ids[:3]) or "N/A"

UPCOM_PAGE_SIZE      = 5
UPCOM_POSTER_BASE    = "https://image.tmdb.org/t/p/w500"
UPCOM_DEFAULT_POSTER = "https://placehold.co/500x750?text=No+Poster"
upcom_sessions: dict = {}
UPCOM_SESSION_MAX_AGE = 3600

def _upcom_clean_sessions():
    now_ts = time.time()
    old = [k for k, v in upcom_sessions.items()
           if now_ts - v.get("_ts", now_ts) > UPCOM_SESSION_MAX_AGE]
    for k in old:
        upcom_sessions.pop(k, None)

def _upcom_parse_args(raw: str):
    parts = raw.strip().split()
    if len(parts) < 2:
        raise ValueError("Month aur Year dono zaroori hain")
    m_raw = parts[0]
    try: month = int(m_raw)
    except ValueError:
        try: month = list(calendar.month_name).index(m_raw.capitalize())
        except ValueError:
            try: month = list(calendar.month_abbr).index(m_raw.capitalize())
            except ValueError: raise ValueError(f"Month pehchana nahi gaya: *{m_raw}*")
    if not 1 <= month <= 12:
        raise ValueError("Month 1-12 ke beech hona chahiye")
    try: year = int(parts[1])
    except ValueError: raise ValueError(f"Invalid year: *{parts[1]}*")
    if not 2000 <= year <= 2100:
        raise ValueError("Year 2000-2100 ke beech hona chahiye")
    genre_id = None
    if len(parts) >= 3:
        g_name   = parts[2].lower()
        genre_id = UPCOM_NAME_TO_ID.get(g_name)
        if genre_id is None:
            available = ", ".join(sorted(UPCOM_NAME_TO_ID.keys()))
            raise ValueError(f"Genre *{parts[2]}* nahi pehchana\nAvailable:\n{available}")
    return month, year, genre_id

def _upcom_get_movies(month: int, year: int, genre_id: int = None) -> list:
    if not TMDB_API: return []
    last_day   = calendar.monthrange(year, month)[1]
    all_movies = []
    for page in range(1, 6):
        params = {
            "api_key": TMDB_API,
            "primary_release_date.gte": f"{year}-{month:02d}-01",
            "primary_release_date.lte": f"{year}-{month:02d}-{last_day}",
            "sort_by": "popularity.desc",
            "language": "en-US",
            "include_adult": False,
            "page": page,
        }
        if genre_id: params["with_genres"] = genre_id
        try:
            res = requests.get("https://api.themoviedb.org/3/discover/movie", params=params, timeout=10)
            res.raise_for_status()
            data        = res.json()
            results     = data.get("results", [])
            total_pages = data.get("total_pages", 1)
        except Exception as e:
            print(f"[UPCOM TMDB] {e}")
            break
        for m in results:
            pp = m.get("poster_path")
            all_movies.append({
                "id": m.get("id"), "title": m.get("title","Unknown"),
                "release": m.get("release_date","N/A"), "overview": m.get("overview",""),
                "rating": m.get("vote_average",0.0), "votes": m.get("vote_count",0),
                "genres": _upcom_genre_names(m.get("genre_ids",[])),
                "poster": f"{UPCOM_POSTER_BASE}{pp}" if pp else UPCOM_DEFAULT_POSTER,
            })
        if page >= total_pages: break
    return all_movies

def _upcom_get_trailer(movie_id: int):
    if not TMDB_API: return None
    try:
        res  = requests.get(f"https://api.themoviedb.org/3/movie/{movie_id}/videos",
                            params={"api_key": TMDB_API}, timeout=10)
        vids = res.json().get("results", [])
        for v in vids:
            if v.get("type") == "Trailer" and v.get("site") == "YouTube" and v.get("official"):
                return f"https://youtu.be/{v['key']}"
        for v in vids:
            if v.get("type") == "Trailer" and v.get("site") == "YouTube":
                return f"https://youtu.be/{v['key']}"
    except Exception: pass
    return None

def _upcom_search_by_name(query: str) -> list:
    if not TMDB_API: return []
    try:
        res = requests.get(
            "https://api.themoviedb.org/3/search/movie",
            params={"api_key": TMDB_API, "query": query, "language": "en-US",
                    "include_adult": False, "page": 1},
            timeout=10,
        )
        res.raise_for_status()
        results = res.json().get("results", [])
    except Exception as e:
        print(f"[UPCOM SEARCH] {e}")
        return []
    movies = []
    for m in results[:10]:
        pp = m.get("poster_path")
        movies.append({
            "id": m.get("id"), "title": m.get("title","Unknown"),
            "release": m.get("release_date","N/A"), "overview": m.get("overview",""),
            "rating": m.get("vote_average",0.0), "votes": m.get("vote_count",0),
            "genres": _upcom_genre_names(m.get("genre_ids",[])),
            "poster": f"{UPCOM_POSTER_BASE}{pp}" if pp else UPCOM_DEFAULT_POSTER,
        })
    return movies

def _upcom_nav_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    s           = upcom_sessions[chat_id]
    page        = s["page"]
    total       = len(s["movies"])
    total_pages = (total + UPCOM_PAGE_SIZE - 1) // UPCOM_PAGE_SIZE
    btns = []
    if page > 0:
        btns.append(InlineKeyboardButton("◀️ Prev", callback_data="upcom_prev"))
    btns.append(InlineKeyboardButton(f"{page+1} / {total_pages}", callback_data="upcom_noop"))
    if (page + 1) * UPCOM_PAGE_SIZE < total:
        btns.append(InlineKeyboardButton("Next ▶️", callback_data="upcom_next"))
    return InlineKeyboardMarkup([btns])

async def _upcom_send_card(chat_id: int, m: dict, context):
    trailer = await asyncio.to_thread(_upcom_get_trailer, m["id"])
    stars   = "⭐" * max(1, round(m["rating"] / 2))
    caption = (
        f"🎬 *{m['title']}*\n"
        f"📅 {m['release']}  |  🎭 {m['genres']}\n"
        f"{stars} {m['rating']:.1f}/10  ({m['votes']:,} votes)\n"
        f"📖 _{m['overview'][:200]}{'...' if len(m['overview']) > 200 else ''}_"
    )
    row1 = []
    if trailer:
        row1.append(InlineKeyboardButton("🎥 Trailer", url=trailer))
    row1.append(InlineKeyboardButton("🤖 AI Review", callback_data=f"upcom_ai_{m['id']}"))
    keyboard = InlineKeyboardMarkup([
        row1,
        [InlineKeyboardButton("❤️ Watchlist", callback_data=f"wl_save|{m['title'].replace('|','')[:40]}|{m['release'][:4]}|{m['rating']:.1f}"),
         InlineKeyboardButton("🔔 Remind Me", callback_data=f"upcom_rm_{m['id']}_{m['release']}")],
        [InlineKeyboardButton("📌 Add to My Upcoming", callback_data=f"upcom_add_{m['id']}")],
    ])
    try:
        await context.bot.send_photo(chat_id, photo=m["poster"],
                                     caption=caption, parse_mode="Markdown",
                                     reply_markup=keyboard)
    except Exception:
        await context.bot.send_message(chat_id, text=caption,
                                       parse_mode="Markdown", reply_markup=keyboard)

async def upcoming_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_maintenance() and not is_admin(update.effective_user.id):
        await update.message.reply_text("🚧 Maintenance mode.")
        return
    raw_args = " ".join(context.args).strip() if context.args else ""

    if not raw_args:
        loader = await update.message.reply_text("📅 Loading upcoming...\n" + progress_bar(1, 3), parse_mode="Markdown")
        await asyncio.sleep(0.8)
        movies = get_tmdb_upcoming()
        try: await loader.delete()
        except: pass
        if movies:
            text = "📅 *UPCOMING MOVIES*\n\n"
            for item in movies:
                if len(item) == 3: title, release, days = item
                else: title, days = item[0], item[1]; release = "TBA"
                bar = "🟩" * min(10, max(1, 10 - days // 10)) + "⬜" * max(0, 10 - min(10, max(1, 10 - days // 10)))
                countdown = "🔴 *TODAY!*" if days == 0 else (f"🟡 `{days}` days" if days <= 7 else f"🟢 `{days}` days")
                text += f"🎬 *{title}*\n📅 `{release}`  ⏳ {countdown}\n{bar}\n\n"
            text += (
                "_Type naam to search_ 🔎\n\n💡 *Tips:*\n"
                "`/upcoming 6 2026` — month browse\n"
                "`/upcoming June 2026 action` — genre filter\n"
                "`/upcoming Spider-Man` — movie naam se search\n"
                "`/upcoming mylist` — meri upcoming list 📌"
            )
        else:
            text = "📅 *UPCOMING MOVIES*\n\n⚠️ *TMDB API needed!*\n\n_Set TMDB_API env var_"
        await update.message.reply_text(text, parse_mode="Markdown")
        return

    if raw_args.lower() == "mylist":
        user_id = update.effective_user.id
        rows    = await asyncio.to_thread(
            _db_fetch,
            "SELECT movie_id, title, release, genres, rating, added_at "
            "FROM upcom_mylist WHERE user_id=? ORDER BY release ASC",
            (user_id,)
        )
        if not rows:
            await update.message.reply_text(
                "📌 *MY UPCOMING*\n\n📭 *Abhi koi movie nahi hai!*\n\n"
                "Movie search karo aur 📌 *Add to My Upcoming* dabao.\n\n"
                "_Example: `/upcoming Avengers`_",
                parse_mode="Markdown")
            return
        text  = "📌 *MY UPCOMING*\n\n"
        for movie_id, title, release, genres, rating, added_at in rows:
            try:
                rel_date  = datetime.strptime(release, "%Y-%m-%d").date()
                days_left = (rel_date - today_ist()).days
                if days_left < 0:      countdown = "✅ Released"
                elif days_left == 0:   countdown = "🔴 *TODAY!*"
                elif days_left <= 7:   countdown = f"🟡 {days_left} days left"
                else:                  countdown = f"🟢 {days_left} days left"
            except Exception:
                countdown = f"📅 {release}"
            stars = "⭐" * max(1, round((rating or 0) / 2))
            text += (
                f"🎬 *{title}*\n📅 {release}  |  {countdown}\n"
                f"{stars} {rating:.1f}  |  🎭 {genres or 'N/A'}\n"
                f"🗑 `/upcom_remove {movie_id}`\n\n"
            )
        text += f"_Total: {len(rows)} movies_"
        await update.message.reply_text(text, parse_mode="Markdown")
        return

    try:
        month, year, genre_id = _upcom_parse_args(raw_args)
        is_name_search = False
    except ValueError:
        is_name_search = True

    if is_name_search:
        parts     = raw_args.strip().rsplit(" ", 1)
        year_hint = None
        search_q  = raw_args
        if len(parts) == 2 and parts[1].isdigit() and 1900 <= int(parts[1]) <= 2100:
            year_hint = int(parts[1])
            search_q  = parts[0].strip()
        loading = await update.message.reply_text(f"🔍 *\"{raw_args}\"* search kar raha hoon…", parse_mode="Markdown")
        movies  = await asyncio.to_thread(_upcom_search_by_name, search_q)
        if year_hint and movies:
            filtered = [m for m in movies if str(year_hint) in m.get("release","")]
            if filtered: movies = filtered
        try: await loading.delete()
        except: pass
        if not movies:
            await update.message.reply_text(f"😕 *\"{raw_args}\"* — koi movie nahi mili.", parse_mode="Markdown")
            return
        _upcom_clean_sessions()
        chat_id = update.effective_chat.id
        upcom_sessions[chat_id] = {"movies": movies, "page": 0, "month": 0, "year": 0,
                                   "search": raw_args, "_ts": time.time()}
        year_tag = f" ({year_hint})" if year_hint else ""
        await update.message.reply_text(
            f"🔍 *\"{search_q}{year_tag}\"* — {len(movies)} results\n\n"
            f"_📌 Add to My Upcoming  |  ❤️ Watchlist  |  🔔 Remind_",
            parse_mode="Markdown")
        for m in movies[:UPCOM_PAGE_SIZE]:
            await _upcom_send_card(chat_id, m, context)
        if len(movies) > UPCOM_PAGE_SIZE:
            await context.bot.send_message(chat_id, "👇 Navigate karo:",
                                           reply_markup=_upcom_nav_keyboard(chat_id),
                                           parse_mode="Markdown")
        return

    month_name  = calendar.month_name[month]
    genre_label = ""
    if genre_id:
        gname       = next((k for k, v in UPCOM_NAME_TO_ID.items() if v == genre_id), "")
        genre_label = f" · {gname.title()}"
    loading = await update.message.reply_text(f"🔍 Searching *{month_name} {year}{genre_label}*…", parse_mode="Markdown")
    movies  = await asyncio.to_thread(_upcom_get_movies, month, year, genre_id)
    try: await loading.delete()
    except: pass
    if not movies:
        await update.message.reply_text(
            f"😕 *{month_name} {year}{genre_label}* mein koi movie nahi mili.", parse_mode="Markdown")
        return
    chat_id = update.effective_chat.id
    _upcom_clean_sessions()
    upcom_sessions[chat_id] = {"movies": movies, "page": 0, "month": month,
                               "year": year, "_ts": time.time()}
    total_pages = (len(movies) + UPCOM_PAGE_SIZE - 1) // UPCOM_PAGE_SIZE
    await update.message.reply_text(
        f"🎬 *{month_name} {year}{genre_label}*\n"
        f"📊 {len(movies)} movies  |  📄 Page 1/{total_pages}\n\n"
        f"_📌 Add to My Upcoming  |  ❤️ Watchlist  |  🔔 Remind Me_",
        parse_mode="Markdown")
    for m in movies[:UPCOM_PAGE_SIZE]:
        await _upcom_send_card(chat_id, m, context)
    await context.bot.send_message(chat_id, "👇 Navigate karo:",
                                   reply_markup=_upcom_nav_keyboard(chat_id),
                                   parse_mode="Markdown")

async def upcom_paginate_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    chat_id = query.message.chat.id
    if chat_id not in upcom_sessions:
        await query.answer("⚠️ Session expired. /upcoming dobara chalao.")
        return
    s = upcom_sessions[chat_id]
    if query.data == "upcom_prev":
        s["page"] = max(0, s["page"] - 1)
    elif query.data == "upcom_next":
        s["page"] = min((len(s["movies"]) - 1) // UPCOM_PAGE_SIZE, s["page"] + 1)
    else:
        await query.answer()
        return
    page        = s["page"]
    total_pages = (len(s["movies"]) + UPCOM_PAGE_SIZE - 1) // UPCOM_PAGE_SIZE
    chunk       = s["movies"][page * UPCOM_PAGE_SIZE: (page + 1) * UPCOM_PAGE_SIZE]
    await query.answer(f"📄 Page {page + 1}")
    month_label = calendar.month_name[s["month"]] if s.get("month") else s.get("search","")
    await context.bot.send_message(
        chat_id, f"📄 *Page {page+1}/{total_pages}* — {month_label} {s.get('year','')}",
        parse_mode="Markdown")
    for m in chunk:
        await _upcom_send_card(chat_id, m, context)
    await context.bot.send_message(chat_id, "👇 Navigate karo:",
                                   reply_markup=_upcom_nav_keyboard(chat_id),
                                   parse_mode="Markdown")

async def upcom_ai_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("⏳ AI Review generate ho raha hai…")
    try:
        movie_id = int(query.data.split("_")[2])
        res  = await asyncio.to_thread(
            lambda: requests.get(f"https://api.themoviedb.org/3/movie/{movie_id}",
                                 params={"api_key": TMDB_API}, timeout=10))
        data  = res.json()
        title = data.get("title","Unknown")
        overview = data.get("overview","")
        rating   = data.get("vote_average",0.0)
    except Exception as e:
        await query.message.reply_text(f"❌ Error: {e}")
        return
    if not GROQ_API:
        await query.message.reply_text("⚠️ GROQ_API set nahi hai!", parse_mode="Markdown")
        return
    loader = await query.message.reply_text("🤖 AI Review likh raha hai...\n" + progress_bar(0, 4), parse_mode="Markdown")
    await animate_generic(loader, FRAMES["review"])
    review = await ai_movie_review(title, "", overview, str(round(rating, 1)))
    try: await loader.delete()
    except: pass
    if review:
        await query.message.reply_text(
            f"🤖 *AI REVIEW*\n\n🎬 *{title}*\n━━━━━━━━━━━━━━━━━━\n\n"
            f"{review}\n\n_Powered by Groq AI_ 🤖",
            parse_mode="Markdown")
    else:
        await query.message.reply_text("❌ AI Review nahi aaya.", parse_mode="Markdown")

async def upcom_remind_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    user_id = query.from_user.id
    try:
        parts    = query.data.split("_")
        movie_id = int(parts[2])
        release  = parts[3]
        res      = await asyncio.to_thread(
            lambda: requests.get(f"https://api.themoviedb.org/3/movie/{movie_id}",
                                 params={"api_key": TMDB_API}, timeout=8))
        title = res.json().get("title","Movie")
    except Exception:
        await query.answer("⚠️ Error. Try again.", show_alert=True)
        return
    try:
        rel_date = datetime.strptime(release, "%Y-%m-%d")
        if rel_date.date() <= today_ist():
            await query.answer("⚠️ Ye movie already release ho chuki hai!", show_alert=True)
            return
    except ValueError:
        await query.answer("⚠️ Release date unknown.", show_alert=True)
        return
    try:
        await asyncio.to_thread(_db_execute,
            "INSERT OR IGNORE INTO upcom_reminders VALUES (?,?,?,?)",
            (user_id, movie_id, title, release))
        await query.answer(f"🔔 Reminder set! Release: {release}", show_alert=True)
    except Exception as e:
        await query.answer("❌ DB error.", show_alert=True)
        print(e)

async def upcom_add_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    user_id = query.from_user.id
    await query.answer("Adding...")
    try: movie_id = int(query.data.split("_")[2])
    except (IndexError, ValueError):
        await query.answer("Invalid data.", show_alert=True)
        return
    try:
        res = await asyncio.to_thread(
            lambda: requests.get(f"https://api.themoviedb.org/3/movie/{movie_id}",
                                 params={"api_key": TMDB_API}, timeout=8))
        data    = res.json()
        title   = data.get("title","Unknown")
        release = data.get("release_date","N/A")
        rating  = data.get("vote_average",0.0)
        genres  = " - ".join(g["name"] for g in data.get("genres",[])[:3]) or "N/A"
        pp      = data.get("poster_path")
        poster  = f"{UPCOM_POSTER_BASE}{pp}" if pp else UPCOM_DEFAULT_POSTER
    except Exception as e:
        await query.answer(f"TMDB error: {e}", show_alert=True)
        return
    added_at = now_ist().strftime("%d %b %Y")
    try:
        exists = await asyncio.to_thread(_db_fetch,
            "SELECT 1 FROM upcom_mylist WHERE user_id=? AND movie_id=?",
            (user_id, movie_id))
        if exists:
            await query.answer("Already in your list!", show_alert=True)
            return
        await asyncio.to_thread(_db_execute,
            "INSERT INTO upcom_mylist (user_id,movie_id,title,release,genres,poster,rating,added_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (user_id, movie_id, title, release, genres, poster, rating, added_at))
        await query.answer(f"{title} added to My Upcoming!", show_alert=True)
    except Exception as e:
        await query.answer("DB error.", show_alert=True)
        print(f"[UPCOM ADD] {e}")

async def upcom_remove_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text(
            "Usage: `/upcom_remove <movie_id>`", parse_mode="Markdown")
        return
    try: movie_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid movie ID.", parse_mode="Markdown")
        return
    try:
        rows = await asyncio.to_thread(_db_fetch,
            "SELECT title FROM upcom_mylist WHERE user_id=? AND movie_id=?",
            (user_id, movie_id))
        if not rows:
            await update.message.reply_text("Ye movie aapki list mein nahi hai.", parse_mode="Markdown")
            return
        await asyncio.to_thread(_db_execute,
            "DELETE FROM upcom_mylist WHERE user_id=? AND movie_id=?",
            (user_id, movie_id))
        await update.message.reply_text(
            f"{rows[0][0]} hata diya My Upcoming se.", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text("Error removing movie.", parse_mode="Markdown")
        print(f"[UPCOM REMOVE] {e}")

async def upcom_check_reminders(context=None):
    today = now_ist().strftime("%Y-%m-%d")
    rows  = await asyncio.to_thread(_db_fetch,
        "SELECT user_id, movie_id, title FROM upcom_reminders WHERE release=?", (today,))
    for user_id, movie_id, title in rows:
        try:
            trailer = await asyncio.to_thread(_upcom_get_trailer, movie_id)
            kb_rows = []
            if trailer:
                kb_rows.append([InlineKeyboardButton("🎥 Trailer", url=trailer)])
            kb = InlineKeyboardMarkup(kb_rows) if kb_rows else None
            if context and context.bot:
                await context.bot.send_message(
                    user_id,
                    f"🎬🔔 *{title}* aaj release ho rahi hai!\nPopcorn ready karo! 🍿",
                    parse_mode="Markdown", reply_markup=kb)
        except Exception as e:
            print(f"[UPCOM REMINDER] user={user_id} → {e}")
    if rows:
        await asyncio.to_thread(_db_execute,
            "DELETE FROM upcom_reminders WHERE release=?", (today,))


# ═══════════════════════════════════════════════════════════════════
#   /clean
# ═══════════════════════════════════════════════════════════════════
async def clean_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_admin(user.id):
        await update.message.reply_text(
            "🧹 *ADMIN CLEAN*\n\n"
            "⚠️ Telegram only allows bots to delete their own messages.\n\n/admin",
            parse_mode="Markdown")
        return
    try:
        await update.message.delete()
        confirm = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="🧹 *Your message deleted!*\n\n_Deletes in 5 seconds._",
            parse_mode="Markdown")
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
            parse_mode="Markdown")
        return
    try: target_id = int(args[0])
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
            expiry = now_ist().timestamp() + (hours * 3600)
            admins[str(target_id)] = {"id": target_id, "type": "temporary", "hours": hours,
                                      "expiry": expiry, "added_by": user.id,
                                      "added_at": now_ist().strftime("%Y-%m-%d %H:%M")}
            save_json("admins", admins)
            expiry_str = datetime.fromtimestamp(expiry, tz=IST).strftime("%d %b %Y, %I:%M %p IST")
            await update.message.reply_text(
                f"✅ *Temporary Admin Added!*\n\n👤 `{target_id}`\n⏱ `{hours} ghante`\n📅 Expires: `{expiry_str}`",
                parse_mode="Markdown")
            try:
                await context.bot.send_message(chat_id=target_id,
                    text=f"🎉 Aapko *CineBot* ka *Temporary Admin* banaya gaya hai!\n\n"
                         f"⏱ Duration: `{hours} ghante`\n📅 Expires: `{expiry_str}`\n\n/admin",
                    parse_mode="Markdown")
            except Exception: pass
        except ValueError:
            await update.message.reply_text("❌ Ghante sirf numbers mein!", parse_mode="Markdown")
    else:
        admins[str(target_id)] = {"id": target_id, "type": "permanent",
                                  "added_by": user.id, "added_at": now_ist().strftime("%Y-%m-%d %H:%M")}
        save_json("admins", admins)
        await update.message.reply_text(f"✅ *Permanent Admin Added!*\n\n👤 `{target_id}`", parse_mode="Markdown")
        try:
            await context.bot.send_message(chat_id=target_id,
                text="🎉 Aapko *CineBot* ka *Permanent Admin* banaya gaya!\n\n/admin",
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
    try: target_id = str(int(args[0]))
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
    now    = now_ist().timestamp()
    if not admins:
        await update.message.reply_text(
            f"📋 *Admin List*\n\n_Koi extra admin nahi._\n\n👑 Owner: `{ADMIN_ID}`",
            parse_mode="Markdown")
        return
    lines = [f"👑 *ADMIN LIST*\n\n👑 *Owner:* `{ADMIN_ID}` _(permanent)_\n━━━━━━━━━━━━━━━━━━━━━"]
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
                exp_str   = datetime.fromtimestamp(expiry, tz=IST).strftime("%d %b, %I:%M %p IST")
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
        "👑 *ADD NEW ADMIN*\n\n`USER_ID` — Permanent\n`USER_ID GHANTE` — Temporary\n\n❌ /cancel",
        parse_mode="Markdown")
    asyncio.create_task(auto_delete(sent, 120))
    return W_ADDADMIN

async def adm_addadmin_recv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return ConversationHandler.END
    text  = update.message.text.strip()
    parts = text.split()
    try: target_id = int(parts[0])
    except ValueError:
        await update.message.reply_text("❌ User ID numbers mein likhein.\n/cancel", parse_mode="Markdown")
        return W_ADDADMIN
    if target_id == ADMIN_ID:
        await update.message.reply_text("⚠️ Owner ko admin banana zaroori nahi!", parse_mode="Markdown")
        return ConversationHandler.END
    admins = load_json("admins")
    loader = await update.message.reply_text("⚙️ Processing...\n" + progress_bar(1, 3), parse_mode="Markdown")
    if len(parts) >= 2:
        try:
            hours  = int(parts[1])
            expiry = now_ist().timestamp() + (hours * 3600)
            admins[str(target_id)] = {"id": target_id, "type": "temporary", "hours": hours,
                                      "expiry": expiry, "added_by": update.effective_user.id,
                                      "added_at": now_ist().strftime("%Y-%m-%d %H:%M")}
            save_json("admins", admins)
            expiry_str = datetime.fromtimestamp(expiry, tz=IST).strftime("%d %b %Y, %I:%M %p IST")
            try: await loader.delete()
            except: pass
            sent = await update.message.reply_text(
                f"✅ *Admin Added!*\n\n👤 `{target_id}`\n🔑 Temporary — {hours}h\n📅 Expires: `{expiry_str}`",
                parse_mode="Markdown")
            asyncio.create_task(auto_delete(sent, 60))
            try:
                await context.bot.send_message(chat_id=target_id,
                    text=f"🎉 Aapko *CineBot* ka *Temporary Admin* banaya gaya!\n\n"
                         f"⏱ Duration: `{hours}h`\n📅 Expires: `{expiry_str}`\n\n/admin",
                    parse_mode="Markdown")
            except Exception: pass
        except ValueError:
            try: await loader.delete()
            except: pass
            await update.message.reply_text("❌ Ghante galat hain!\n/cancel", parse_mode="Markdown")
            return W_ADDADMIN
    else:
        admins[str(target_id)] = {"id": target_id, "type": "permanent",
                                  "added_by": update.effective_user.id,
                                  "added_at": now_ist().strftime("%Y-%m-%d %H:%M")}
        save_json("admins", admins)
        try: await loader.delete()
        except: pass
        sent = await update.message.reply_text(
            f"✅ *Admin Added!*\n\n👤 `{target_id}`\n🔑 Permanent", parse_mode="Markdown")
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
    now    = now_ist().timestamp()
    if not admins:
        sent = await query.message.reply_text(
            f"👑 *ADMIN LIST*\n\n_Koi extra admin nahi._\n\n👑 Owner: `{ADMIN_ID}`",
            parse_mode="Markdown")
        asyncio.create_task(auto_delete(sent, 60))
        return
    lines        = [f"👑 *ADMIN LIST*\n\n👑 *Owner:* `{ADMIN_ID}`\n"]
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
                exp_str   = datetime.fromtimestamp(expiry, tz=IST).strftime("%d %b, %I:%M %p IST")
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
        reply_markup=InlineKeyboardMarkup(remove_btns) if remove_btns else None)
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
        await query.message.edit_text(f"✅ *Admin Removed!*\n\n👤 `{target_id}`", parse_mode="Markdown")
    else:
        await query.message.edit_text(f"⚠️ User `{target_id}` list mein nahi tha.", parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════════
#   ADMIN PANEL
# ═══════════════════════════════════════════════════════════════════
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 *Access Denied!*", parse_mode="Markdown")
        return
    loader = await update.message.reply_text("🔐 Authenticating...\n" + progress_bar(1, 4), parse_mode="Markdown")
    await asyncio.sleep(0.4)
    try: await loader.edit_text("🗄 Loading data...\n" + progress_bar(2, 4), parse_mode="Markdown")
    except: pass
    await asyncio.sleep(0.35)
    try: await loader.edit_text("📊 Building panel...\n" + progress_bar(3, 4), parse_mode="Markdown")
    except: pass
    await asyncio.sleep(0.35)
    try: await loader.edit_text("✅ Ready!\n" + progress_bar(4, 4), parse_mode="Markdown")
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
    healer_stat = "✅ v4 Active" if _healer else "⚠️ Not init"
    now      = now_ist().timestamp()
    active_admins = sum(
        1 for v in admins.values()
        if v.get("type") == "permanent" or
           (v.get("type") == "temporary" and now < v.get("expiry", 0))
    )
    text = (
        f"👑 *ADMIN PANEL v10.0*  🎬\n\n"
        f"━━━━━  📊 LIVE STATS  ━━━━━\n"
        f"👥 *Total Users:*    `{len(users)}`\n"
        f"🔎 *Total Searches:* `{searches}`\n"
        f"🚫 *Banned Users:*   `{len(banned)}`\n"
        f"⭐ *Rated Movies:*   `{len(ratings)}`\n"
        f"👑 *Active Admins:*  `{active_admins + 1}`\n"
        f"🚧 *Maintenance:*    {status}\n"
        f"🤖 *AI Engine:*      {ai_stat}\n"
        f"🔧 *Domain Healer:*  {healer_stat}\n\n"
        f"━━━━━  📡 SERVERS  ━━━━━\n"
    )
    for i in range(1, 7):
        text += f"  `{i}.` _{servers[f's{i}']['name']}_\n"

    mb = "🔴 Turn Maintenance OFF" if maint.get("active") else "🟢 Turn Maintenance ON"
    keyboard = [
        [InlineKeyboardButton("📡 Manage Servers",      callback_data="adm_servers")],
        [InlineKeyboardButton(mb,                        callback_data="adm_maint_toggle")],
        [InlineKeyboardButton("✏️ Maintenance Message", callback_data="adm_maint_msg")],
        [InlineKeyboardButton("📢 Broadcast",           callback_data="adm_broadcast")],
        [InlineKeyboardButton("🚫 Ban User",            callback_data="adm_ban"),
         InlineKeyboardButton("✅ Unban User",          callback_data="adm_unban")],
        [InlineKeyboardButton("📋 Activity Logs",       callback_data="adm_logs")],
        [InlineKeyboardButton("📊 Full Stats",          callback_data="adm_stats")],
        [InlineKeyboardButton("🔔 Send Alerts",         callback_data="adm_send_alerts")],
        [InlineKeyboardButton("📤 Export Users",        callback_data="adm_export")],
        [InlineKeyboardButton("👑 Add Admin",           callback_data="adm_addadmin"),
         InlineKeyboardButton("📋 Admin List",          callback_data="adm_listadmins")],
        [InlineKeyboardButton("📡 Server Status",       callback_data="adm_srv_status")],
        [InlineKeyboardButton("🔧 Healer Log",          callback_data="adm_healerlog")],
    ]
    sent = await update.message.reply_text(
        text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard))
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
        parse_mode="Markdown")
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
        parse_mode="Markdown")
    return W_NAME

async def adm_recv_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    global bot_servers
    name    = update.message.text.strip()
    url     = context.user_data["new_url"]
    sk      = context.user_data["editing_server"]
    loader  = await update.message.reply_text("💾 Saving...\n" + progress_bar(0, 3), parse_mode="Markdown")
    await animate_generic(loader, FRAMES["save"])
    servers = load_json("servers", {k: v.copy() for k, v in DEFAULT_SERVERS.items()})
    servers[sk]["url"]  = url
    servers[sk]["name"] = name
    save_json("servers", servers)
    bot_servers = servers
    try: await loader.delete()
    except: pass
    sent = await update.message.reply_text(
        f"✅ *Server {sk[1]} Updated!*\n\n🏷 `{name}`\n🔗 `{url}`", parse_mode="Markdown")
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
    loader = await query.message.reply_text(frames[0] + "\n" + progress_bar(0, len(frames)), parse_mode="Markdown")
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
                    parse_mode="Markdown")
                success += 1
            except: failed += 1
            await asyncio.sleep(0.05)
        sent = await query.message.reply_text(
            f"🚨 *Maintenance ON!*\n✅ `{success}` sent | ❌ `{failed}` failed", parse_mode="Markdown")
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
        parse_mode="Markdown")
    return W_MAINT_MSG

async def adm_recv_maint_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    maint = load_json("maintenance", {"active": False})
    maint["message"] = update.message.text.strip()
    save_json("maintenance", maint)
    loader = await update.message.reply_text("💾 Saving...\n" + progress_bar(0, 3), parse_mode="Markdown")
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
    await query.message.reply_text("📢 *Broadcast Message*\n\nSabhi users ko message:\n\n/cancel", parse_mode="Markdown")
    return W_BROADCAST

async def adm_do_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    msg     = update.message.text.strip()
    users   = load_json("users")
    success = failed = 0
    loader  = await update.message.reply_text("📢 Broadcasting...\n" + progress_bar(0, 3), parse_mode="Markdown")
    await animate_generic(loader, FRAMES["broadcast"])
    try: await loader.delete()
    except: pass
    for uid in list(users.keys()):
        if int(uid) == ADMIN_ID: continue
        try:
            await context.bot.send_message(
                chat_id=int(uid),
                text=f"📢 *CineBot Announcement*\n━━━━━━━━━━━━━━━━━━\n\n{msg}",
                parse_mode="Markdown")
            success += 1
        except: failed += 1
        await asyncio.sleep(0.05)
    sent = await update.message.reply_text(
        f"✅ *Broadcast Done!*\n✅ Sent: `{success}`\n❌ Failed: `{failed}`", parse_mode="Markdown")
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
    try: ban_id = int(update.message.text.strip())
    except Exception:
        await update.message.reply_text("❌ Invalid ID. Try again or /cancel")
        return W_BAN_USER
    banned = load_json("banned")
    banned[str(ban_id)] = now_ist().strftime("%Y-%m-%d %H:%M")
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
            parse_mode="Markdown")
    sent = await query.message.reply_text("✅ *Export sent to your DM!*", parse_mode="Markdown")
    asyncio.create_task(auto_delete(sent, 30))

async def adm_logs_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    logs  = load_json("logs")
    today = str(today_ist())
    t_logs = logs.get(today, [])
    text  = f"📋 *ACTIVITY LOGS*\n\n📊 Today: `{len(t_logs)}` searches\n━━━━━━━━━━━━━━━━━━\n\n"
    for entry in t_logs[-10:]:
        text += f"`{entry['time']}` — {entry['movie']} by `{entry['user']}`\n"
    if not t_logs: text += "_No activity today_"
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
    text  = f"📊 *FULL STATS*\n\n"
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
    await query.answer("🔔 Sending alerts...")
    if not is_admin(query.from_user.id): return
    alerts = load_json("alerts")
    if not alerts:
        sent = await query.message.reply_text(
            "📭 *Koi alerts saved nahi hain!*", parse_mode="Markdown")
        asyncio.create_task(auto_delete(sent, 30))
        return
    total_movies = sum(len(movies) for movies in alerts.values())
    total_users  = len(alerts)
    await query.message.reply_text(
        f"📢 *Sending alerts to {total_users} users ({total_movies} movie alerts)...*",
        parse_mode="Markdown")
    sent_c = failed = 0
    for uid, movies in alerts.items():
        if not movies: continue
        movie_list = "\n".join(f"  🎬 *{m['title']}* ({m.get('year','N/A')})" for m in movies)
        try:
            await context.bot.send_message(
                chat_id=int(uid),
                text=(f"🔔 *Movie Release Alert!*\n━━━━━━━━━━━━━━━━━━\n\n"
                      f"Tumhari watchlist ki movies available hain:\n\n{movie_list}\n\n"
                      f"━━━━━━━━━━━━━━━━━━\n_Bot pe naam type karke search karo!_ 🎬"),
                parse_mode="Markdown")
            sent_c += 1
        except: failed += 1
        await asyncio.sleep(0.05)
    save_json("alerts", {})
    result = await query.message.reply_text(
        f"✅ *Alerts Sent & Cleared!*\n\n✅ Sent: `{sent_c}`\n❌ Failed: `{failed}`\n"
        f"🎬 Total Movies: `{total_movies}`",
        parse_mode="Markdown")
    asyncio.create_task(auto_delete(result, 60))

async def sendalert_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("🔒 Sirf admins ke liye!", parse_mode="Markdown")
        return
    msg = " ".join(context.args).strip() if context.args else ""
    if not msg:
        await update.message.reply_text(
            "📢 *Usage:*\n`/sendalert Your message here`", parse_mode="Markdown")
        return
    users  = load_json("users")
    loader = await update.message.reply_text(f"📢 *Sending to {len(users)} users...*", parse_mode="Markdown")
    success = failed = 0
    for uid in list(users.keys()):
        if int(uid) == update.effective_user.id: continue
        try:
            await context.bot.send_message(
                chat_id=int(uid),
                text=(f"📢 *CineBot Alert!*\n━━━━━━━━━━━━━━━━━━\n\n{msg}\n\n"
                      f"━━━━━━━━━━━━━━━━━━\n_CineBot — Your Movie Assistant_ 🎬"),
                parse_mode="Markdown")
            success += 1
        except: failed += 1
        await asyncio.sleep(0.05)
    try: await loader.delete()
    except: pass
    result = await update.message.reply_text(
        f"✅ *Alert Sent!*\n\n✅ Success: `{success}`\n❌ Failed: `{failed}`", parse_mode="Markdown")
    asyncio.create_task(auto_delete(result, 60))

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
    ratings  = load_json("ratings")
    searches = sum(u.get("searches", 0) for u in users.values())
    status   = "🔴 ON" if maint.get("active") else "🟢 OFF"
    ai_stat  = "✅ Groq" if GROQ_API else "❌ No API"
    healer_stat = "✅ v4 Active" if _healer else "⚠️ Not init"
    mb = "🔴 Turn Maintenance OFF" if maint.get("active") else "🟢 Turn Maintenance ON"
    text = (
        f"👑 *ADMIN PANEL v10.0*  🎬\n\n"
        f"👥 Users: `{len(users)}`  🔎 Searches: `{searches}`\n"
        f"🚫 Banned: `{len(banned)}`  ⭐ Rated: `{len(ratings)}`\n"
        f"🚧 Maintenance: {status}  🤖 AI: {ai_stat}\n"
        f"🔧 Healer: {healer_stat}\n"
    )
    keyboard = [
        [InlineKeyboardButton("📡 Manage Servers",      callback_data="adm_servers")],
        [InlineKeyboardButton(mb,                        callback_data="adm_maint_toggle")],
        [InlineKeyboardButton("✏️ Maintenance Message", callback_data="adm_maint_msg")],
        [InlineKeyboardButton("📢 Broadcast",           callback_data="adm_broadcast")],
        [InlineKeyboardButton("🚫 Ban User",            callback_data="adm_ban"),
         InlineKeyboardButton("✅ Unban User",          callback_data="adm_unban")],
        [InlineKeyboardButton("📋 Activity Logs",       callback_data="adm_logs")],
        [InlineKeyboardButton("📊 Full Stats",          callback_data="adm_stats")],
        [InlineKeyboardButton("🔔 Send Alerts",         callback_data="adm_send_alerts")],
        [InlineKeyboardButton("📤 Export Users",        callback_data="adm_export")],
        [InlineKeyboardButton("👑 Add Admin",           callback_data="adm_addadmin"),
         InlineKeyboardButton("📋 Admin List",          callback_data="adm_listadmins")],
        [InlineKeyboardButton("📡 Server Status",       callback_data="adm_srv_status")],
        [InlineKeyboardButton("🔧 Healer Log",          callback_data="adm_healerlog")],
    ]
    sent = await query.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    asyncio.create_task(auto_delete(sent, 60))

async def adm_healerlog_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    if not _healer:
        await query.message.reply_text("⚠️ Healer not initialized.", parse_mode="Markdown")
        return
    log = _healer.db.get_heal_log(limit=10)
    if not log:
        await query.message.reply_text("📋 Koi heal history nahi. Sab servers stable hain! ✅")
        return
    lines = ["📋 *HEALER v4 HISTORY* (last 10)\n━━━━━━━━━━━━━━━━━━"]
    for e in log:
        old_d = urlparse(e["old_url"] or "").netloc or (e["old_url"] or "")[:30]
        new_d = urlparse(e["new_url"] or "").netloc or (e["new_url"] or "")[:30]
        ts    = datetime.fromtimestamp(e["created_at"], tz=IST).strftime("%d %b, %I:%M %p")
        lines.append(
            f"\n🔄 *{e['site_key']}* — `{e['status']}`\n"
            f"   ❌ `{old_d}`\n   ✅ `{new_d}`\n   ⏰ _{ts}_")
    lines.append("\n━━━━━━━━━━━━━━━━━━")
    sent = await query.message.reply_text("\n".join(lines), parse_mode="Markdown")
    asyncio.create_task(auto_delete(sent, 60))

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ *Cancelled.*", parse_mode="Markdown")
    return ConversationHandler.END

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ai_status = "✅ Groq AI Active" if GROQ_API else "⚠️ Set GROQ_API for AI features"
    healer_status = "✅ Domain Healer v4 Active" if _healer else "⚠️ Healer not initialized"
    await update.message.reply_text(
        f"ℹ️ *CINEBOT HELP*\n\n"
        f"🤖 *AI Status:* {ai_status}\n"
        f"🔧 *Healer:* {healer_status}\n\n"
        "🔎 *Movie Search:* Seedha naam type karo\n\n"
        "📋 *Commands:*\n"
        "🎬 /movieinfo    — TMDB rich movie info\n"
        "📝 /fullreview   — Detailed AI review\n"
        "🎭 /moodmatch    — Mood match analysis\n"
        "🌟 /castinfo     — Cast & director info\n"
        "❓ /trivia       — MCQ trivia question\n"
        "📡 /checkservers — Server health (Admin)\n"
        "📊 /serverstats  — Uptime stats (Admin)\n"
        "🔧 /healerlog    — Domain heal history (Admin)\n"
        "📦 /index_channel — Group ka index banao (Admin)\n"
        "📊 /grpstats     — Index stats (Admin)\n"
        "🗑 /clrindex     — Index clear karo (Admin)\n"
        "📢 /sendalert    — Alert all users (Admin)\n"
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
        "🎯 *Movie card pe buttons:*\n"
        "📝 Full Review • 🎭 Mood Match\n"
        "🌟 Cast Analysis • ❓ Trivia Quiz\n"
        "🔥 Full AI Package\n\n"
        "🦁 *Brave Browser = No Ads!*",
        parse_mode="Markdown")



# ═══════════════════════════════════════════════════════════════════
#   DAILY REMINDER LOOP
# ═══════════════════════════════════════════════════════════════════
async def _reminder_daily_loop(bot):
    while True:
        try:
            now      = now_ist()
            next_run = now.replace(hour=9, minute=0, second=0, microsecond=0)
            if now >= next_run:
                next_run = next_run + timedelta(days=1)
            wait_sec = (next_run - now).total_seconds()
            print(f"⏰ Next reminder check: {next_run.strftime('%d %b %Y, %I:%M %p IST')}")
            await asyncio.sleep(wait_sec)
            class FakeCtx:
                pass
            ctx = FakeCtx()
            ctx.bot = bot
            await upcom_check_reminders(ctx)
            print("✅ Reminder check done")
        except Exception as e:
            print(f"⚠️ Reminder loop error: {e}")
            await asyncio.sleep(3600)


# ═══════════════════════════════════════════════════════════════════
#   POST INIT — start healer + background tasks
# ═══════════════════════════════════════════════════════════════════
async def post_init(application):
    global _healer

    # Initialize Healer (class kept as HealerV4 for backward-compat with
    # this call site; internal logic is the v6 AI-verification engine)
    _healer = HealerV4(
        bot=application.bot,
        groq_sdk_client=_groq_sdk_client,
        admin_id=ADMIN_ID,
    )
    _healer.register_handlers(application)
    print("✅ Domain Healer v6 initialized")

    # Group Index info
    if WATCHED_GROUP_IDS:
        print(f"✅ Group Index watching: {WATCHED_GROUP_IDS}")
    else:
        print("⚠️  GROUP_IDS not set — watching ALL groups bot is member of")

    # Auto server checker (uses healer internally)
    asyncio.create_task(auto_server_checker(application.bot, ADMIN_ID))

    # Daily upcoming reminders
    asyncio.create_task(_reminder_daily_loop(application.bot))


# ═══════════════════════════════════════════════════════════════════
#   APPLICATION BUILD
# ═══════════════════════════════════════════════════════════════════
application = (
    ApplicationBuilder()
    .token(TOKEN)
    .connect_timeout(30)
    .read_timeout(30)
    .write_timeout(30)
    .pool_timeout(30)
    .get_updates_connect_timeout(30)
    .get_updates_read_timeout(30)
    .post_init(post_init)
    .build()
)

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

# ── Commands ──
application.add_handler(CommandHandler("start",        start))
application.add_handler(CommandHandler("help",         help_cmd))
application.add_handler(CommandHandler("trending",     trending_cmd))
application.add_handler(CommandHandler("random",       random_cmd))
application.add_handler(CommandHandler("daily",        daily_cmd))
application.add_handler(CommandHandler("upcoming",     upcoming_cmd))
application.add_handler(CommandHandler("upcom_remove", upcom_remove_cmd))
application.add_handler(CommandHandler("watchlist",    watchlist_cmd))
application.add_handler(CommandHandler("alerts",       alerts_cmd))
application.add_handler(CommandHandler("quiz",         quiz_cmd))
application.add_handler(CommandHandler("refer",        refer_cmd))
application.add_handler(CommandHandler("lang",         lang_cmd))
application.add_handler(CommandHandler("mystats",      mystats_cmd))
application.add_handler(CommandHandler("admin",        admin_panel))
application.add_handler(CommandHandler("clean",        clean_cmd))
application.add_handler(CommandHandler("leaderboard",  leaderboard_cmd))
application.add_handler(CommandHandler("history",      history_cmd))
application.add_handler(CommandHandler("movieinfo",    movieinfo_cmd))
application.add_handler(CommandHandler("addadmin",     addadmin_cmd))
application.add_handler(CommandHandler("removeadmin",  removeadmin_cmd))
application.add_handler(CommandHandler("admins",       listadmins_cmd))
application.add_handler(CommandHandler("fullreview",   fullreview_cmd))
application.add_handler(CommandHandler("moodmatch",    moodmatch_cmd))
application.add_handler(CommandHandler("castinfo",     castinfo_cmd))
application.add_handler(CommandHandler("trivia",       trivia_cmd))
application.add_handler(CommandHandler(["checkservers","checkserver"], checkservers_cmd))
application.add_handler(CommandHandler("serverstats",  serverstats_cmd))
application.add_handler(CommandHandler("sendalert",    sendalert_cmd))
application.add_handler(CommandHandler("healerlog",     healerlog_cmd))
application.add_handler(CommandHandler("index_channel", index_channel_cmd))
application.add_handler(CommandHandler("grpstats",      grpstats_cmd))
application.add_handler(CommandHandler("clrindex",      clrindex_cmd))

# ── Admin callbacks ──
application.add_handler(CallbackQueryHandler(adm_servers_cb,        pattern="^adm_servers$"))
application.add_handler(CallbackQueryHandler(adm_maint_toggle,      pattern="^adm_maint_toggle$"))
application.add_handler(CallbackQueryHandler(adm_reset,             pattern="^adm_reset$"))
application.add_handler(CallbackQueryHandler(adm_stats_cb,          pattern="^adm_stats$"))
application.add_handler(CallbackQueryHandler(adm_back,              pattern="^adm_back$"))
application.add_handler(CallbackQueryHandler(adm_logs_cb,           pattern="^adm_logs$"))
application.add_handler(CallbackQueryHandler(adm_send_alerts,       pattern="^adm_send_alerts$"))
application.add_handler(CallbackQueryHandler(adm_unban_prompt,      pattern="^adm_unban$"))
application.add_handler(CallbackQueryHandler(do_unban_cb,           pattern="^dounban_"))
application.add_handler(CallbackQueryHandler(adm_export_cb,         pattern="^adm_export$"))
application.add_handler(CallbackQueryHandler(adm_listadmins_cb,     pattern="^adm_listadmins$"))
application.add_handler(CallbackQueryHandler(adm_rmadmin_cb,        pattern="^adm_rmadmin_"))
application.add_handler(CallbackQueryHandler(adm_healerlog_cb,      pattern="^adm_healerlog$"))

# ── Server checker callbacks ──
application.add_handler(CallbackQueryHandler(srvchk_refresh_cb,      pattern="^srvchk_refresh$"))
application.add_handler(CallbackQueryHandler(srvchk_stats_cb,        pattern="^srvchk_stats$"))
application.add_handler(CallbackQueryHandler(server_status_admin_cb, pattern="^adm_srv_status$"))

# ── Healer v4 approval callbacks (registered via healer.register_handlers in post_init) ──

# ── Full AI analysis callbacks ──
application.add_handler(CallbackQueryHandler(fullreview_cb,   pattern="^frev_"))
application.add_handler(CallbackQueryHandler(moodmatch_cb,    pattern="^mood_match_"))
application.add_handler(CallbackQueryHandler(castanalysis_cb, pattern="^cast_"))
application.add_handler(CallbackQueryHandler(trivia_cb,       pattern="^trivia_"))
application.add_handler(CallbackQueryHandler(fullpackage_cb,  pattern="^pkg_"))

# ── Upcoming callbacks ──
application.add_handler(CallbackQueryHandler(upcom_paginate_cb, pattern="^upcom_(prev|next|noop)$"))
application.add_handler(CallbackQueryHandler(upcom_ai_cb,       pattern="^upcom_ai_"))
application.add_handler(CallbackQueryHandler(upcom_remind_cb,   pattern="^upcom_rm_"))
application.add_handler(CallbackQueryHandler(upcom_add_cb,      pattern="^upcom_add_"))

# ── User callbacks ──
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

# ── Group fallback callback ──
application.add_handler(CallbackQueryHandler(grp_fallback_cb, pattern="^grp_fallback_"))

# ── Group sample confirm/wrong callbacks ──
application.add_handler(CallbackQueryHandler(grp_confirm_yes_cb, pattern="^grp_confirm_yes$"))
application.add_handler(CallbackQueryHandler(grp_confirm_no_cb,  pattern="^grp_confirm_no$"))

# ── Direct Video button on poster card ──
application.add_handler(CallbackQueryHandler(grp_direct_video_cb, pattern="^gv_"))

# ── Group file auto-indexer (video/document in watched groups) ──
application.add_handler(MessageHandler(
    (filters.VIDEO | filters.Document.ALL) & filters.ChatType.GROUPS,
    grp_file_handler,
))

# ── Movie search (last — catch-all) ──
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, movie))

print("✅ CineBot v10 + Domain Healer v4 ULTRA — Ready!")
print(f"   Groq AI: {'✅' if GROQ_API else '❌'}")
print(f"   Groq SDK: {'✅' if _groq_sdk_client else '❌ (pip install groq)'}")
print(f"   TMDB: {'✅' if TMDB_API else '⚠️ optional'}")

application.run_polling(
    allowed_updates=["message", "callback_query", "inline_query"],
    drop_pending_updates=True,
)
