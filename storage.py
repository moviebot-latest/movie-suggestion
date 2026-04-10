# ╔══════════════════════════════════════════╗
# ║  storage.py — JSON & SQLite storage      ║
# ║  Edit to change how data is saved        ║
# ╚══════════════════════════════════════════╝
import json, os, sqlite3, threading, asyncio
from config import now_ist, today_ist, ADMIN_ID

# ── JSON file paths ──
FILES = {
    "users":       "data/users.json",
    "banned":      "data/banned.json",
    "admins":      "data/admins.json",
    "maintenance": "data/maintenance.json",
    "servers":     "data/servers.json",
    "searches":    "data/searches.json",
    "logs":        "data/logs.json",
    "history":     "data/history.json",
    "refers":      "data/refers.json",
    "ratings":     "data/ratings.json",
    "alerts":      "data/alerts.json",
    "watchlist":   "data/watchlist.json",
    "lang":        "data/lang.json",
    "dc":          "data/dc.json",
}

# Create data directory if not exists
os.makedirs("data", exist_ok=True)

# ── Default servers ──
DEFAULT_SERVERS = {
    "s1": {"name": "Server 1", "url": "https://vidsrc.to/embed/movie/"},
    "s2": {"name": "Server 2", "url": "https://vidsrc.me/embed/movie?tmdb="},
    "s3": {"name": "Server 3", "url": "https://embed.su/embed/movie/"},
    "s4": {"name": "Server 4", "url": "https://multiembed.mov/directstream.php?video_id="},
    "s5": {"name": "Server 5", "url": "https://www.2embed.cc/embed/"},
    "s6": {"name": "Server 6", "url": "https://player.videasy.net/movie/"},
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
            "joined":   now_ist().strftime("%Y-%m-%d %H:%M"),
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
        if now_ist().timestamp() < expiry:
            return True
        else:
            del admins[str(uid)]
            save_json("admins", admins)
            return False
    return False

def is_maintenance(): return load_json("maintenance", {"active": False}).get("active", False)

def _db_fetch(query: str, params: tuple = (), db: str = "movies.db") -> list:
    """Thread-safe sqlite3 fetch — use with asyncio.to_thread."""
    con = sqlite3.connect(db)
    try:
        rows = con.execute(query, params).fetchall()
    finally:
        con.close()
    return rows

def _db_execute(query: str, params: tuple = (), db: str = "movies.db") -> int:
    """Thread-safe sqlite3 write — use with asyncio.to_thread. Returns rowcount."""
    con = sqlite3.connect(db)
    try:
        cur = con.execute(query, params)
        con.commit()
        return cur.rowcount
    finally:
        con.close()

