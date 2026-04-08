# ╔══════════════════════════════════════════════════════════════════════════╗
# ║      🎬  CineBot v10 — GROQ EDITION + FULL AI + SERVER CHECKER          ║
# ║                                                                          ║
# ║  ✅ V9.1 BASE (all features intact):                                    ║
# ║     • Groq AI (llama-3.3-70b-versatile)                                 ║
# ║     • Full AI Analysis (review, mood, cast, trivia, package)            ║
# ║     • Admin panel, watchlist, alerts, quiz, refer, leaderboard          ║
# ║                                                                          ║
# ║  ✅ NEW — SERVER HEALTH CHECKER (v3 ULTRA integrated):                  ║
# ║     • /checkservers — Parallel async check (10 sec, not 3 min)         ║
# ║     • /checkserver  — Same command (alias)                              ║
# ║     • ✅ Response time (ms) per server                                  ║
# ║     • ✅ Uptime history bar (last 5 checks)                             ║
# ║     • ✅ AI diagnosis for DOWN servers (Groq)                           ║
# ║     • ✅ Admin panel mein "📡 Server Status" button added               ║
# ║     • ✅ Auto 12hr background check with alert                          ║
# ║     • ✅ Non-admin = proper error (not silent)                          ║
# ║     • ✅ Thread-safe file writes                                         ║
# ║     • ✅ Smart alert — sirf DOWN pe, UP pe no spam                      ║
# ║                                                                          ║
# ║  APIs: BOT_TOKEN, OMDB_API, TMDB_API, GROQ_API, ADMIN_ID               ║
# ╚══════════════════════════════════════════════════════════════════════════╝

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes, ConversationHandler
)
import requests, threading, json, os, asyncio, random, re, time, logging
from datetime import datetime, date, timedelta
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
def home(): return "🎬 CineBot v10 Groq + Full Analysis + Server Checker Running"

@web_app.route("/health")
def health(): return {"status": "ok", "version": "10.0", "ai": "groq", "analysis": "full", "server_checker": "v3"}

def run_web():
    web_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

threading.Thread(target=run_web, daemon=True).start()


# ═══════════════════════════════════════════════════════════════════
#                      PERSISTENT STORAGE
# ═══════════════════════════════════════════════════════════════════
FILES = {
    "servers":       "servers.json",
    "maintenance":   "maintenance.json",
    "users":         "users.json",
    "watchlist":     "watchlist.json",
    "searches":      "searches.json",
    "banned":        "banned.json",
    "logs":          "logs.json",
    "daily":         "daily.json",
    "quiz":          "quiz.json",
    "alerts":        "alerts.json",
    "refers":        "refers.json",
    "ratings":       "ratings.json",
    "history":       "history.json",
    "votes":         "votes.json",
    "admins":        "admins.json",
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
    "server":       ["🌐 Connecting", "🌐 Loading", "⚡ Almost", "✅ Ready"],
    "back":         ["🔄 Returning", "🔄 Loading", "✅ Back"],
    "save":         ["💾 Saving", "💾 Writing", "✅ Saved"],
    "maint_on":     ["🔧 Activating", "🔧 Processing", "🚨 Maintenance ON"],
    "maint_off":    ["🟢 Restoring", "🟢 Processing", "✅ Bot LIVE"],
    "broadcast":    ["📢 Sending", "📢 Delivering", "✅ Done"],
    "ai":           ["🤖 Thinking", "🤖 Processing", "✨ Ready"],
    "similar":      ["🔍 Analyzing", "🔍 Matching", "🎬 Found"],
    "quiz":         ["🎯 Preparing", "🎯 Loading", "✅ Ready"],
    "daily":        ["🎬 Picking", "🎬 Loading", "✅ Today's Pick"],
    "review":       ["🤖 Reading", "🤖 Analyzing", "✍️ Writing", "✅ Done"],
    "compare":      ["🔍 Loading 1st", "🔍 Loading 2nd", "⚖️ Comparing", "✅ Ready"],
    "mood":         ["🎭 Reading mood", "🤖 Thinking", "🎬 Picking", "✅ Ready"],
    "fullreview":   ["📖 Reading plot", "🤖 Analyzing", "✍️ Writing review", "✅ Done"],
    "moodmatch":    ["🎭 Sensing mood", "🤖 Matching", "🍿 Perfect pick!", "✅ Ready"],
    "castanalysis": ["🎬 Loading cast", "🌟 Analyzing", "✅ Done"],
    "trivia":       ["🧠 Thinking", "❓ Creating question", "✅ Ready"],
    "fullpackage":  ["📖 Review", "🎯 Similar", "🎭 Mood", "🌟 Cast", "✅ All Done!"],
    # ✅ NEW — Server checker frames
    "srvcheck":     ["🌐 Connecting servers", "⚡ Parallel checking", "📊 Analyzing", "✅ Done"],
}


# ═══════════════════════════════════════════════════════════════════
#   ✅ NEW — SERVER HEALTH CHECKER MODULE (v3 ULTRA)
#   Integrated from server_checker.py — NO circular imports
# ═══════════════════════════════════════════════════════════════════

# ── Config ──────────────────────────────────────────────────────────
SRV_CHECK_INTERVAL_HOURS = 12
SRV_RETRY_COUNT          = 3
SRV_RETRY_DELAY          = 3
SRV_REQUEST_TIMEOUT      = 10
SRV_STATUS_FILE          = "server_status.json"
SRV_HISTORY_MAX          = 5
_srv_file_lock           = threading.Lock()

SRV_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Connection":      "keep-alive",
}

logger = logging.getLogger(__name__)

# ── Status Persistence ───────────────────────────────────────────────
def srv_load_status() -> dict:
    with _srv_file_lock:
        if os.path.exists(SRV_STATUS_FILE):
            try:
                with open(SRV_STATUS_FILE) as f:
                    return json.load(f)
            except Exception:
                pass
    return {}

def srv_save_status(data: dict):
    with _srv_file_lock:
        with open(SRV_STATUS_FILE, "w") as f:
            json.dump(data, f, indent=2)

# ── Single Check (HEAD → GET fallback) ──────────────────────────────
async def _srv_check_once(session: aiohttp.ClientSession, url: str) -> tuple:
    for method in ("HEAD", "GET"):
        t0 = time.monotonic()
        try:
            fn = session.head if method == "HEAD" else session.get
            kw = dict(
                url=url,
                headers=SRV_HEADERS,
                timeout=aiohttp.ClientTimeout(total=SRV_REQUEST_TIMEOUT),
                allow_redirects=True,
            )
            async with fn(**kw) as resp:
                ms   = int((time.monotonic() - t0) * 1000)
                code = resp.status
                if code < 400:
                    return True, code, ms, method
                if method == "HEAD":
                    continue
                return False, code, ms, method
        except asyncio.TimeoutError:
            ms = int((time.monotonic() - t0) * 1000)
            if method == "GET":
                return False, 0, ms, "Timeout"
        except aiohttp.ClientConnectorError:
            ms = int((time.monotonic() - t0) * 1000)
            if method == "GET":
                return False, 0, ms, "Connection refused"
        except Exception as e:
            ms = int((time.monotonic() - t0) * 1000)
            if method == "GET":
                return False, 0, ms, str(e)[:50]
    return False, 0, 0, "Unknown"

# ── Single Server — with retries ────────────────────────────────────
async def srv_check_server(key: str, name: str, url: str) -> dict:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    if not url:
        return {
            "key": key, "name": name, "url": url,
            "up": False, "code": 0, "method": "N/A",
            "response_ms": 0, "attempts": 0,
            "error": "No URL configured", "checked": ts,
        }
    connector = aiohttp.TCPConnector(ssl=False, limit=1)
    async with aiohttp.ClientSession(connector=connector) as session:
        code, ms, method = 0, 0, "?"
        for attempt in range(1, SRV_RETRY_COUNT + 1):
            is_up, code, ms, method = await _srv_check_once(session, url)
            if is_up:
                return {
                    "key": key, "name": name, "url": url,
                    "up": True, "code": code, "method": method,
                    "response_ms": ms, "attempts": attempt, "checked": ts,
                }
            if attempt < SRV_RETRY_COUNT:
                await asyncio.sleep(SRV_RETRY_DELAY)
    return {
        "key": key, "name": name, "url": url,
        "up": False, "code": code, "method": method,
        "response_ms": ms, "attempts": SRV_RETRY_COUNT, "checked": ts,
    }

# ── Parallel Bulk Check ──────────────────────────────────────────────
async def srv_check_all_parallel(servers: dict) -> dict:
    """All servers PARALLEL — 3 min → ~10 sec."""
    tasks = [
        srv_check_server(k, v.get("name", k), v.get("url", ""))
        for k, v in servers.items()
    ]
    results_list = await asyncio.gather(*tasks, return_exceptions=True)
    saved        = srv_load_status()
    results      = {}

    for r in results_list:
        if isinstance(r, Exception):
            logger.error(f"Task exception: {r}")
            continue
        key          = r["key"]
        prev_history = saved.get(key, {}).get("history", [])
        new_entry    = {"up": r["up"], "checked": r["checked"], "ms": r.get("response_ms", 0)}
        r["history"] = ([new_entry] + prev_history)[:SRV_HISTORY_MAX]
        results[key] = r

        icon = "✅" if r["up"] else "❌"
        logger.info(f"{icon} {r['name']} | {r.get('response_ms')}ms | code={r.get('code')}")

    srv_save_status(results)
    return results

# ── AI Diagnosis for DOWN Servers ────────────────────────────────────
async def srv_ai_diagnose(results: dict) -> Optional[str]:
    """Groq AI — DOWN servers ka diagnosis (uses existing GROQ_API)."""
    if not GROQ_API:
        return None
    down  = [r for r in results.values() if not r.get("up")]
    up    = [r for r in results.values() if r.get("up")]
    up_ms = [r.get("response_ms", 0) for r in up if r.get("response_ms", 0) > 0]
    avg   = int(sum(up_ms) / len(up_ms)) if up_ms else 0

    if not down:
        return None

    down_info = "\n".join(
        f"- {r['name']} | URL: {r['url'][:55]} | Code: {r.get('code',0)} | Error: {r.get('method','?')}"
        for r in down
    )
    prompt = (
        f"You are a server reliability expert for a movie download bot.\n\n"
        f"DOWN SERVERS ({len(down)}):\n{down_info}\n\n"
        f"UP: {len(up)} servers fine. Avg response: {avg}ms\n\n"
        f"For each DOWN server give:\n"
        f"1. Likely reason (based on code/error)\n"
        f"2. Quick fix for admin\n\n"
        f"Format (Hinglish, short):\n"
        f"🔴 [Name]\n"
        f"   ⚠️ Reason: ...\n"
        f"   🔧 Fix: ...\n\n"
        f"End with one-line overall summary."
    )
    headers = {"Authorization": f"Bearer {GROQ_API}", "Content-Type": "application/json"}
    payload = {
        "model":       GROQ_MODEL,
        "messages":    [{"role": "user", "content": prompt}],
        "max_tokens":  500,
        "temperature": 0.4,
    }
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.post(GROQ_URL, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.warning(f"AI diagnosis error: {e}")
    return None

# ── Formatters ───────────────────────────────────────────────────────
def _srv_history_bar(history: list) -> str:
    icons = ["🟩" if h.get("up") else "🟥" for h in history[:5]]
    icons += ["⬜"] * (5 - len(icons))
    return "".join(icons)

def srv_format_status(results: dict, title: str = "🖥️ SERVER STATUS") -> str:
    now    = datetime.now().strftime("%d %b %Y, %H:%M")
    up_cnt = sum(1 for r in results.values() if r.get("up"))
    total  = len(results)

    if up_cnt == total:
        health = "🟢 ALL OK"
    elif up_cnt == 0:
        health = "🔴 ALL DOWN"
    else:
        health = f"🟡 {up_cnt}/{total} UP"

    lines = [
        f"*{title}*",
        f"📅 {now}  |  📊 {health}",
        "━━━━━━━━━━━━━━━━━━━━━━━",
    ]

    for key, r in sorted(results.items()):
        name = r.get("name", key)
        up   = r.get("up", False)
        code = r.get("code", 0)
        ms   = r.get("response_ms", 0)
        bar  = _srv_history_bar(r.get("history", []))

        if up:
            spd = "⚡" if ms < 800 else ("🟡" if ms < 2000 else "🐢")
            lines.append(f"\n✅ *{name}*  {spd} {ms}ms")
            lines.append(f"   Code `{code}` | History: {bar}")
        else:
            lines.append(f"\n❌ *{name}* — DOWN!")
            lines.append(f"   Code `{code}` | {r.get('attempts',0)}x failed | History: {bar}")

    lines.append("\n━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("🔄 Next auto-check: 12hrs mein")
    return "\n".join(lines)

def srv_format_alert(down_keys: list, results: dict) -> str:
    now   = datetime.now().strftime("%d %b %Y, %H:%M")
    count = len(down_keys)
    lines = [
        f"🚨 *{count} SERVER{'S' if count > 1 else ''} DOWN* 🚨",
        f"⏰ {now}\n",
    ]
    for key in down_keys:
        r = results.get(key, {})
        lines += [
            f"🔴 *{r.get('name', key)}*",
            f"   `{r.get('url','')[:55]}`",
            f"   Code `{r.get('code',0)}` | {r.get('attempts',0)}x failed",
            f"   History: {_srv_history_bar(r.get('history',[]))}",
            "",
        ]
    lines += [
        "━━━━━━━━━━━━━━━━━━",
        "👉 Fix: `/admin` → Servers → Edit",
        "👉 `/checkservers` se manual check karo",
    ]
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
#   ✅ NEW — /checkservers & /checkserver COMMAND
# ═══════════════════════════════════════════════════════════════════
async def checkservers_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin-only. Parallel server check + optional AI diagnosis."""
    uid = update.effective_user.id

    if not is_admin(uid):
        await update.message.reply_text(
            "🔒 *Access Denied!*\n\n"
            "Yeh command sirf admins ke liye hai.\n"
            "Apne admin se request karo ya `/admin` check karo.",
            parse_mode="Markdown",
        )
        return

    loading = await update.message.reply_text(
        "🔍 *Checking all servers in parallel...*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "⚡ Simultaneous checks running\n"
        "🤖 AI diagnosis on standby\n\n"
        "_10-15 seconds mein complete hoga..._",
        parse_mode="Markdown",
    )

    servers = load_servers()
    if not servers:
        await loading.edit_text("❌ Koi server configured nahi. `/admin` → Servers.")
        return

    results   = await srv_check_all_parallel(servers)
    down_keys = [k for k, v in results.items() if not v.get("up")]

    # AI diagnosis if servers down
    ai_text = None
    if down_keys and GROQ_API:
        await loading.edit_text("🤖 *AI analyzing DOWN servers...*", parse_mode="Markdown")
        ai_text = await srv_ai_diagnose(results)

    text = srv_format_status(results, "🖥️ SERVER CHECK")
    if ai_text:
        text += f"\n\n🤖 *AI DIAGNOSIS:*\n{ai_text}"

    kb = [
        [InlineKeyboardButton("🔄 Refresh",       callback_data="srvchk_refresh"),
         InlineKeyboardButton("⚙️ Edit Servers",  callback_data="adm_servers")],
        [InlineKeyboardButton("📊 Admin Panel",   callback_data="open_admin")],
    ]
    await loading.edit_text(text, parse_mode="Markdown",
                            reply_markup=InlineKeyboardMarkup(kb))


# ═══════════════════════════════════════════════════════════════════
#   ✅ NEW — Refresh Callback
# ═══════════════════════════════════════════════════════════════════
async def srvchk_refresh_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid   = query.from_user.id

    if not is_admin(uid):
        await query.answer("🔒 Sirf admins refresh kar sakte hain!", show_alert=True)
        return

    await query.answer("🔍 Re-checking...")
    await query.edit_message_text("🔄 *Refreshing...*", parse_mode="Markdown")

    servers   = load_servers()
    results   = await srv_check_all_parallel(servers)
    down_keys = [k for k, v in results.items() if not v.get("up")]

    ai_text = None
    if down_keys and GROQ_API:
        ai_text = await srv_ai_diagnose(results)

    text = srv_format_status(results, "🔄 SERVER REFRESH")
    if ai_text:
        text += f"\n\n🤖 *AI DIAGNOSIS:*\n{ai_text}"

    kb = [
        [InlineKeyboardButton("🔄 Refresh Again", callback_data="srvchk_refresh"),
         InlineKeyboardButton("⚙️ Edit Servers",  callback_data="adm_servers")],
        [InlineKeyboardButton("📊 Admin Panel",   callback_data="open_admin")],
    ]
    await query.edit_message_text(text, parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(kb))


# ═══════════════════════════════════════════════════════════════════
#   ✅ NEW — Admin Panel "Server Status" widget
# ═══════════════════════════════════════════════════════════════════
async def server_status_admin_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin panel 'Server Status' button."""
    query = update.callback_query
    await query.answer()

    saved = srv_load_status()
    if not saved:
        text = (
            "📡 *Server Status*\n\n"
            "_Abhi tak koi check nahi hua._\n\n"
            "👉 `/checkservers` run karo\n"
            "👉 Ya 12 ghante mein auto-check hoga."
        )
    else:
        text = srv_format_status(saved, "📡 LAST CHECK RESULTS")

    kb = [
        [InlineKeyboardButton("🔄 Check Now", callback_data="srvchk_refresh")],
        [InlineKeyboardButton("🔙 Back",      callback_data="adm_back")],
    ]
    await query.edit_message_text(text, parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(kb))


# ═══════════════════════════════════════════════════════════════════
#   ✅ NEW — Auto 12hr Background Server Checker
# ═══════════════════════════════════════════════════════════════════
async def auto_server_checker(bot, admin_id: int):
    """
    Har 12 ghante auto check.
    DOWN = admin Telegram alert (with AI diagnosis).
    All UP = silent (no spam).
    """
    logger.info("🕐 Auto server checker started (12hr interval)")
    await asyncio.sleep(300)   # 5 min warmup

    while True:
        try:
            logger.info(f"🔍 Auto-check @ {datetime.now().strftime('%H:%M')}")
            servers   = load_servers()
            results   = await srv_check_all_parallel(servers)
            down_keys = [k for k, v in results.items() if not v.get("up")]

            if down_keys:
                ai_text = await srv_ai_diagnose(results) if GROQ_API else None

                alert = srv_format_alert(down_keys, results)
                if ai_text:
                    alert += f"\n\n🤖 *AI DIAGNOSIS:*\n{ai_text}"

                kb = [[
                    InlineKeyboardButton("🔄 Check Again", callback_data="srvchk_refresh"),
                    InlineKeyboardButton("⚙️ Edit",        callback_data="adm_servers"),
                ]]
                await bot.send_message(
                    chat_id=admin_id, text=alert,
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(kb),
                )
                logger.warning(f"🚨 Alert sent: {len(down_keys)} DOWN")
            else:
                logger.info("✅ All UP — no alert")

        except Exception as e:
            logger.error(f"Auto checker error: {e}")

        nxt = datetime.now() + timedelta(hours=SRV_CHECK_INTERVAL_HOURS)
        logger.info(f"⏰ Next check: {nxt.strftime('%Y-%m-%d %H:%M')}")
        await asyncio.sleep(SRV_CHECK_INTERVAL_HOURS * 3600)


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


# ═══════════════════════════════════════════════════════════════════
#                    GROQ AI FUNCTIONS
# ═══════════════════════════════════════════════════════════════════
async def ai_ask(prompt: str, max_tokens: int = 400, temperature: float = 0.7) -> Optional[str]:
    if not GROQ_API:
        return None
    headers = {"Authorization": f"Bearer {GROQ_API}", "Content-Type": "application/json"}
    payload = {
        "model":       GROQ_MODEL,
        "messages":    [{"role": "user", "content": prompt}],
        "max_tokens":  max_tokens,
        "temperature": temperature,
    }
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
            async with s.post(GROQ_URL, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.warning(f"ai_ask error: {e}")
    return None

async def ai_movie_review(title, year, plot, rating):
    return await ai_ask(
        f"Movie '{title}' ({year}) ka ek punchy 3-sentence review likho.\n"
        f"IMDB: {rating}/10\nPlot: {plot}\n\n"
        f"1. Hook — core premise.\n2. Kya exciting ya unique hai.\n"
        f"3. Kaun dekhe + Hype score/10 🔥\nCasual, fun, emoji-friendly. No spoilers.",
        max_tokens=200, temperature=0.85
    )

async def ai_fun_facts(title, year, director, actors):
    return await ai_ask(
        f"Movie '{title}' ({year}) ke baare mein 5 interesting behind-the-scenes facts do.\n"
        f"Director: {director}, Cast: {actors}\n\n"
        f"Format:\n💡 *Fact 1:* ...\n💡 *Fact 2:* ...\n\nHinglish. Lesser-known facts prefer karo.",
        max_tokens=400
    )

async def ai_similar_movies(title, year, genre):
    return await ai_ask(
        f"Movie '{title}' ({year}, {genre}) se similar 5 movies suggest karo.\n\n"
        f"Format:\n🎬 *[Title]* ([Year]) — [1 line reason why similar]\n\n"
        f"Hinglish. Variety rakhna — same director, theme, vibe sab mix karo.",
        max_tokens=400
    )

async def ai_mood_recommend(mood: str):
    return await ai_ask(
        f"User ka mood: '{mood}'\n\n"
        f"Is mood ke liye 5 perfect movies suggest karo.\n"
        f"Format:\n🎬 *[Title]* — [1 line kyun perfect hai]\n\n"
        f"Hinglish. Mix Hindi + English movies.",
        max_tokens=400
    )

async def ai_compare_movies(t1, y1, r1, p1, t2, y2, r2, p2):
    return await ai_ask(
        f"Do movies compare karo:\n\n"
        f"Movie 1: {t1} ({y1}) — IMDB {r1}/10\nPlot: {p1}\n\n"
        f"Movie 2: {t2} ({y2}) — IMDB {r2}/10\nPlot: {p2}\n\n"
        f"3 categories mein compare karo: Story, Acting, Entertainment.\n"
        f"End mein winner declare karo with reason.\nHinglish, fun tone.",
        max_tokens=500
    )

async def ai_plot_search(description: str):
    return await ai_ask(
        f"User ne ek movie describe ki: '{description}'\n\n"
        f"Is description se match karne wali 3-5 movies suggest karo.\n"
        f"Format:\n🎬 *[Title]* ([Year]) — [kyun match karta hai]\n\nHinglish.",
        max_tokens=400
    )

# ── Full Analysis AI Functions (v10 NEW) ────────────────────────────
async def ai_full_review(title, year, genre, plot, rating, director, actors, awards):
    return await ai_ask(
        f"""Movie '{title}' ({year}) ka detailed review likho.
Genre: {genre} | Rating: {rating}/10 | Director: {director}
Cast: {actors} | Awards: {awards}
Plot: {plot}

Format:
📝 *Synopsis:* [2-3 lines plot summary, no spoilers]

✅ *Positives:*
• [point 1]
• [point 2]
• [point 3]

❌ *Negatives:*
• [point 1]
• [point 2]

🏆 *Verdict:* [2 lines final verdict]
⭐ *Rating:* [X/10] 🔥 [tagline]

Hinglish mein. Honest aur specific raho.""",
        max_tokens=600
    )

async def ai_similar_deep(title, year, genre):
    return await ai_ask(
        f"""Movie '{title}' ({year}, {genre}) se similar 5 movies suggest karo.

Har ek ke liye:
🎬 *[Title]* ([Year])
   🎭 Genre: [genre]
   🔗 Similarity: [2 lines — kyun similar hai, theme/vibe/director]
   ⭐ Must watch if: [1 line]

Hinglish. Variety rakhna.""",
        max_tokens=600
    )

async def ai_mood_match(title, genre, plot):
    return await ai_ask(
        f"""Movie '{title}' (Genre: {genre}) ke liye mood match analysis karo.
Plot summary: {plot}

Format:
🎭 *Best Mood to Watch:* [specific mood — e.g., "Adventurous, curious"]
⏰ *Best Time:* [e.g., "Late night solo viewing"]
👥 *Best With:* [e.g., "Friends who love sci-fi"]
🍿 *Snack Pairing:* [fun snack suggestion]
💯 *Vibe Score:* [X/10] for [specific audience]

2-3 lines overall recommendation.
Hinglish mein. Fun aur specific raho.""",
        max_tokens=400
    )

async def ai_cast_analysis(title, actors, director):
    return await ai_ask(
        f"""Movie '{title}' ke cast aur director ka analysis karo.
Director: {director}
Main Cast: {actors}

Format:
🎬 *Director — {director}:*
[2 lines — unki direction style aur is movie mein kya khas kiya]

🎭 *Cast Performance:*
Har ek ke liye:
🎬 [Naam] — [1-2 line performance analysis ya career highlight]

End mein:
🏆 *Standout Performance:* [sabse acha kaun tha aur kyun — 2 lines]

Hinglish mein. Honest aur specific raho.""",
        max_tokens=600
    )

async def ai_trivia_quiz_movie(title, year, director, actors):
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
#   MOVIE CARD (OMDB) — with Full Analysis buttons
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

    star_bar = build_star_bar(rating)

    # Community rating
    ratings_data = load_json("ratings")
    comm_rat = "N/A"
    if title in ratings_data and ratings_data[title]:
        avg = sum(ratings_data[title].values()) / len(ratings_data[title])
        comm_rat = f"⭐ {avg:.1f}/5 ({len(ratings_data[title])} votes)"

    servers = load_servers()
    names   = [servers[f"s{i}"]["name"] for i in range(1, 7)]
    urls    = [servers[f"s{i}"]["url"] + quote(title) for i in range(1, 7)]

    trailer  = f"https://www.youtube.com/results?search_query={quote(title+' '+year+' trailer')}"
    subs_url = f"https://www.opensubtitles.org/en/search/sublanguageid-all/moviename-{quote(title)}"

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
#   NEW CALLBACKS — Full Analysis
# ═══════════════════════════════════════════════════════════════════
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
        await query.message.reply_text("❌ AI review nahi likh paya.\n_GROQ_API check karo._", parse_mode="Markdown")

async def moodmatch_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer("🎭 Mood match kar raha hai...")
    msg_id = query.data.split("_", 2)[2]
    md     = context.user_data.get(msg_id)
    if not md:
        await query.message.reply_text("⚠️ Session expired. Movie dobara search karo.")
        return
    loader = await query.message.reply_text("🎭 Mood analyze ho raha hai...\n" + progress_bar(0, 4))
    await animate_generic(loader, FRAMES["moodmatch"])
    result = await ai_mood_match(md["title"], md.get("genre", "N/A"), md["plot"])
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
    result = await ai_trivia_quiz_movie(md["title"], md["year"], md["director"], md["actors"])
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
        await update.message.reply_text("❌ *Usage:* `/fullreview Movie Name`\nExample: `/fullreview Inception`", parse_mode="Markdown")
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
    title = " ".join(context.args).strip() if context.args else ""
    if not title:
        await update.message.reply_text("❌ *Usage:* `/moodmatch Movie Name`\nExample: `/moodmatch Inception`", parse_mode="Markdown")
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
    result = await ai_mood_match(data.get("Title","N/A"), data.get("Genre","N/A"), data.get("Plot","N/A"))
    try: await loader.delete()
    except: pass
    if result:
        await update.message.reply_text(
            f"╔══════════════════╗\n║  🎭  *MOOD MATCH*  ║\n╚══════════════════╝\n\n"
            f"🎬 *{data['Title']}* ({data['Year']})\n━━━━━━━━━━━━━━━━━━\n\n"
            f"{result}\n\n_Powered by Groq AI_ 🤖",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("❌ Mood match nahi hua. Try again.", parse_mode="Markdown")

async def castinfo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = " ".join(context.args).strip() if context.args else ""
    if not title:
        await update.message.reply_text("❌ *Usage:* `/castinfo Movie Name`\nExample: `/castinfo Inception`", parse_mode="Markdown")
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
    result = await ai_cast_analysis(data.get("Title","N/A"), data.get("Actors","N/A"), data.get("Director","N/A"))
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
        await update.message.reply_text("❌ Cast analysis nahi hua. Try again.", parse_mode="Markdown")

async def trivia_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = " ".join(context.args).strip() if context.args else ""
    if not title:
        await update.message.reply_text("❌ *Usage:* `/trivia Movie Name`\nExample: `/trivia Inception`", parse_mode="Markdown")
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
#   [All remaining handlers from v9.1 — unchanged below]
#   trending_cmd, random_cmd, daily_cmd, upcoming_cmd,
#   watchlist handlers, alert handlers, similar_cb,
#   review_cb, funfact_cb, rate_cb, dorat_cb,
#   servers_cb, back_cb, director_cb,
#   mood_cmd, compare_cmd (and their receive handlers),
#   suggest_cmd, plotsearch_cmd,
#   quiz_cmd, quiz_answer_cb,
#   mystats_cmd, refer_cmd,
#   leaderboard_cmd, history_cmd, lang_cmd, clean_cmd,
#   movieinfo_cmd, pick_cb,
#   admin functions (admin_panel, adm_servers_cb, etc.)
#   — PASTE THEM HERE from your v9.1 file unchanged —
# ═══════════════════════════════════════════════════════════════════

# [YOUR EXISTING V9.1 HANDLERS GO HERE — copy/paste from line ~1400 onward of v9.1]


# ═══════════════════════════════════════════════════════════════════
#   ✅ UPDATED ADMIN PANEL — "📡 Server Status" button added
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

    # Server checker — last check info
    srv_saved = srv_load_status()
    if srv_saved:
        up_count = sum(1 for r in srv_saved.values() if r.get("up"))
        srv_stat = f"🟢 {up_count}/{len(srv_saved)} UP"
    else:
        srv_stat = "⬜ Not checked yet"

    text = (
        f"╔════════════════════════════╗\n"
        f"║  👑  *ADMIN PANEL v10*  🎬  ║\n"
        f"╚════════════════════════════╝\n\n"
        f"━━━━━  📊 LIVE STATS  ━━━━━\n"
        f"👥 *Total Users:*    `{len(users)}`\n"
        f"🔎 *Total Searches:* `{searches}`\n"
        f"🚫 *Banned Users:*   `{len(banned)}`\n"
        f"⭐ *Rated Movies:*   `{len(ratings)}`\n"
        f"👑 *Active Admins:*  `{active_admins + 1}` (incl. owner)\n"
        f"🚧 *Maintenance:*    {status}\n"
        f"🤖 *AI Engine:*      {ai_stat}\n"
        f"📡 *Server Health:*  {srv_stat}\n\n"  # ✅ NEW
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
        # ✅ NEW — Server Status button
        [InlineKeyboardButton("📡 Server Status",        callback_data="adm_srv_status")],
    ]
    sent = await update.message.reply_text(
        text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    asyncio.create_task(auto_delete(sent, 60))


# ═══════════════════════════════════════════════════════════════════
#                        HELP COMMAND
# ═══════════════════════════════════════════════════════════════════
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ai_status = "✅ Groq AI Active" if GROQ_API else "⚠️ Set GROQ_API for AI features"
    await update.message.reply_text(
        "╔═══════════════════╗\n║  ℹ️  *CINEBOT HELP*  ║\n╚═══════════════════╝\n\n"
        f"🤖 *AI Status:* {ai_status}\n\n"
        "🔎 *Movie Search:* Seedha naam type karo\n\n"
        "📋 *Commands:*\n"
        "🎬 /movieinfo    — TMDB rich movie info\n"
        "📝 /fullreview   — Detailed AI review\n"
        "🎭 /moodmatch    — Mood match analysis\n"
        "🌟 /castinfo     — Cast & director info\n"
        "❓ /trivia       — MCQ trivia question\n"
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
        "📊 /mystats      — Points & badge\n"
        "📡 /checkservers — Server health ✅NEW (Admin)\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🎯 *Movie card pe buttons:*\n"
        "📝 Full Review • 🎭 Mood Match\n"
        "🌟 Cast Analysis • ❓ Trivia Quiz\n"
        "🔥 Full AI Package (sab ek saath)\n\n"
        "🦁 *Brave Browser = No Ads!*",
        parse_mode="Markdown"
    )


# ═══════════════════════════════════════════════════════════════════
#   ✅ post_init — Auto server checker start karta hai
# ═══════════════════════════════════════════════════════════════════
async def post_init(application):
    """Called after bot starts — launches background server checker."""
    asyncio.create_task(
        auto_server_checker(application.bot, ADMIN_ID)
    )
    print("🕐 Auto server checker background task started!")


# ═══════════════════════════════════════════════════════════════════
#                        BOT START
# ═══════════════════════════════════════════════════════════════════
application = ApplicationBuilder().token(TOKEN).post_init(post_init).build()

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
application.add_handler(CommandHandler("fullreview",  fullreview_cmd))
application.add_handler(CommandHandler("moodmatch",   moodmatch_cmd))
application.add_handler(CommandHandler("castinfo",    castinfo_cmd))
application.add_handler(CommandHandler("trivia",      trivia_cmd))
# ✅ NEW — Server checker (both aliases work)
application.add_handler(CommandHandler(["checkservers", "checkserver"], checkservers_cmd))

# Admin callbacks
application.add_handler(CallbackQueryHandler(adm_servers_cb,      pattern="^adm_servers$"))
application.add_handler(CallbackQueryHandler(adm_maint_toggle,    pattern="^adm_maint_toggle$"))
application.add_handler(CallbackQueryHandler(adm_reset,           pattern="^adm_reset$"))
application.add_handler(CallbackQueryHandler(adm_stats_cb,        pattern="^adm_stats$"))
application.add_handler(CallbackQueryHandler(adm_back,            pattern="^adm_back$"))
application.add_handler(CallbackQueryHandler(adm_logs_cb,         pattern="^adm_logs$"))
application.add_handler(CallbackQueryHandler(adm_send_alerts,     pattern="^adm_send_alerts$"))
application.add_handler(CallbackQueryHandler(adm_unban_prompt,    pattern="^adm_unban$"))
application.add_handler(CallbackQueryHandler(do_unban_cb,         pattern="^dounban_"))
application.add_handler(CallbackQueryHandler(adm_export_cb,       pattern="^adm_export$"))
application.add_handler(CallbackQueryHandler(adm_listadmins_cb,   pattern="^adm_listadmins$"))
application.add_handler(CallbackQueryHandler(adm_rmadmin_cb,      pattern="^adm_rmadmin_"))
# ✅ NEW — Server status in admin panel
application.add_handler(CallbackQueryHandler(server_status_admin_cb, pattern="^adm_srv_status$"))
application.add_handler(CallbackQueryHandler(srvchk_refresh_cb,      pattern="^srvchk_refresh$"))

# Full analysis callbacks
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

# Movie search (last — catch-all)
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, movie))

print("✅ CineBot v10 — Groq AI + Full Analysis + Server Checker integrated!")
application.run_polling()
