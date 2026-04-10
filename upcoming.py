# ╔══════════════════════════════════════════╗
# ║  upcoming.py — /upcoming command         ║
# ║  Edit to change upcoming movie features  ║
# ╚══════════════════════════════════════════╝
import asyncio, requests, sqlite3, re, calendar, time
from datetime import datetime
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import TMDB_API, now_ist, today_ist
from storage import _db_fetch, _db_execute, is_maintenance, is_admin
from ai_engine import ai_movie_review
from helpers import progress_bar, animate_generic, FRAMES

def _upcom_init_db():
    con = sqlite3.connect("movies.db")
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
    # ✅ NEW: Personal upcoming tracker — user apni movies add kar sakta hai
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


UPCOM_GENRE_MAP = {
    28:"Action", 12:"Adventure", 16:"Animation", 35:"Comedy",
    80:"Crime",  99:"Documentary", 18:"Drama",   10751:"Family",
    14:"Fantasy", 36:"History",   27:"Horror",   10402:"Music",
    9648:"Mystery", 10749:"Romance", 878:"Sci-Fi", 10770:"TV Movie",
    53:"Thriller", 10752:"War",    37:"Western",
}
UPCOM_NAME_TO_ID = {v.lower(): k for k, v in UPCOM_GENRE_MAP.items()}

def _upcom_genre_names(ids: list) -> str:
    return " · ".join(UPCOM_GENRE_MAP.get(i, "?") for i in ids[:3]) or "N/A"

UPCOM_PAGE_SIZE      = 5
UPCOM_POSTER_BASE    = "https://image.tmdb.org/t/p/w500"
UPCOM_DEFAULT_POSTER = "https://placehold.co/500x750?text=No+Poster"
upcom_sessions: dict = {}
UPCOM_SESSION_MAX_AGE = 3600   # 1 hour — purani sessions auto-clean

def _upcom_clean_sessions():
    """Memory leak fix — 1hr se purani sessions hata do."""
    import time as _time
    now_ts = _time.time()
    old    = [k for k, v in upcom_sessions.items()
              if now_ts - v.get("_ts", now_ts) > UPCOM_SESSION_MAX_AGE]
    for k in old:
        upcom_sessions.pop(k, None)

def _upcom_parse_args(raw: str):
    parts = raw.strip().split()
    if len(parts) < 2:
        raise ValueError("Month aur Year dono zaroori hain")
    m_raw = parts[0]
    try:
        month = int(m_raw)
    except ValueError:
        try:
            month = list(calendar.month_name).index(m_raw.capitalize())
        except ValueError:
            try:
                month = list(calendar.month_abbr).index(m_raw.capitalize())
            except ValueError:
                raise ValueError(f"Month pehchana nahi gaya: *{m_raw}*")
    if not 1 <= month <= 12:
        raise ValueError("Month 1-12 ke beech hona chahiye")
    try:
        year = int(parts[1])
    except ValueError:
        raise ValueError(f"Invalid year: *{parts[1]}*")
    if not 2000 <= year <= 2100:
        raise ValueError("Year 2000-2100 ke beech hona chahiye")
    genre_id = None
    if len(parts) >= 3:
        g_name = parts[2].lower()
        genre_id = UPCOM_NAME_TO_ID.get(g_name)
        if genre_id is None:
            available = ", ".join(sorted(UPCOM_NAME_TO_ID.keys()))
            raise ValueError(f"Genre *{parts[2]}* nahi pehchana\nAvailable:\n{available}")
    return month, year, genre_id

def _upcom_get_movies(month: int, year: int, genre_id: int = None) -> list:
    if not TMDB_API:
        return []
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
        if genre_id:
            params["with_genres"] = genre_id
        try:
            res = requests.get("https://api.themoviedb.org/3/discover/movie",
                               params=params, timeout=10)
            res.raise_for_status()
            data = res.json()
        except Exception as e:
            print(f"[UPCOM TMDB] {e}")
            break
        results     = data.get("results", [])
        total_pages = data.get("total_pages", 1)
        for m in results:
            pp = m.get("poster_path")
            all_movies.append({
                "id":      m.get("id"),
                "title":   m.get("title", "Unknown"),
                "release": m.get("release_date", "N/A"),
                "overview":m.get("overview", ""),
                "rating":  m.get("vote_average", 0.0),
                "votes":   m.get("vote_count", 0),
                "genres":  _upcom_genre_names(m.get("genre_ids", [])),
                "poster":  f"{UPCOM_POSTER_BASE}{pp}" if pp else UPCOM_DEFAULT_POSTER,
            })
        if page >= total_pages:
            break
    return all_movies

def _upcom_get_trailer(movie_id: int):
    if not TMDB_API:
        return None
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
    except Exception:
        pass
    return None

def _upcom_search_by_name(query: str, year: int = None) -> list:
    """
    Movie naam se TMDB search karo.
    Optional year — agar diya to sirf us saal ki movies.
    Returns list of movie dicts (same format as _upcom_get_movies).
    """
    if not TMDB_API:
        return []
    params = {
        "api_key":       TMDB_API,
        "query":         query,
        "language":      "en-US",
        "include_adult": False,
        "page":          1,
    }
    if year:
        params["year"] = year          # TMDB exact year filter
    try:
        res = requests.get(
            "https://api.themoviedb.org/3/search/movie",
            params=params,
            timeout=10,
        )
        res.raise_for_status()
        results = res.json().get("results", [])
    except Exception as e:
        print(f"[UPCOM SEARCH] {e}")
        return []

    # ── Year se filter: agar TMDB ne mixed results diye to locally bhi filter ──
    if year:
        results = [
            m for m in results
            if str(m.get("release_date", ""))[:4] == str(year)
        ]

    movies = []
    for m in results[:10]:
        pp = m.get("poster_path")
        movies.append({
            "id":       m.get("id"),
            "title":    m.get("title", "Unknown"),
            "release":  m.get("release_date", "N/A"),
            "overview": m.get("overview", ""),
            "rating":   m.get("vote_average", 0.0),
            "votes":    m.get("vote_count", 0),
            "genres":   _upcom_genre_names(m.get("genre_ids", [])),
            "poster":   f"{UPCOM_POSTER_BASE}{pp}" if pp else UPCOM_DEFAULT_POSTER,
        })
    return movies
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

    # ✅ NEW: Add to My Upcoming button — compact data in callback
    safe_title   = re.sub(r'[^a-zA-Z0-9 ]', '', m['title'])[:20].strip()
    safe_genres  = re.sub(r'[^a-zA-Z0-9 ·]', '', m.get('genres',''))[:20].strip()
    # callback format: upcom_add_MOVIEID (full data fetched from TMDB in callback)
    keyboard = InlineKeyboardMarkup([
        row1,
        [InlineKeyboardButton("❤️ Watchlist",       callback_data=f"wl_save|{m['title'].replace('|','')[:40]}|{m['release'][:4]}|{m['rating']:.1f}"),
         InlineKeyboardButton("🔔 Remind Me",        callback_data=f"upcom_rm_{m['id']}_{m['release']}")],
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
    """
    /upcoming              → Simple TMDB upcoming list
    /upcoming 6 2026       → June 2026 browse with cards
    /upcoming June 2026 action → Genre filter
    /upcoming <movie name> → Search movie by name ✅ NEW
    /upcoming mylist       → My personal upcoming tracker ✅ NEW
    """
    if is_maintenance() and not is_admin(update.effective_user.id):
        await update.message.reply_text("🚧 Maintenance mode.")
        return

    raw_args = " ".join(context.args).strip() if context.args else ""

    # ── No args: simple list ──
    if not raw_args:
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
            text += (
                "_Type naam to search_ 🔎\n\n"
                "💡 *Tips:*\n"
                "`/upcoming 6 2026` — month browse\n"
                "`/upcoming June 2026 action` — genre filter\n"
                "`/upcoming Spider-Man` — movie naam se search 🔍\n"
                "`/upcoming Spider-Man 2025` — naam + year exact search 🎯\n"
                "`/upcoming mylist` — meri upcoming list 📌"
            )
        else:
            text = (
                "╔═══════════════════════╗\n║  📅  *UPCOMING MOVIES*  ║\n╚═══════════════════════╝\n\n"
                "⚠️ *TMDB API needed!*\n\n_Set TMDB_API env var_\n\n🆓 Free: themoviedb.org"
            )
        await update.message.reply_text(text, parse_mode="Markdown")
        return

    # ── ✅ NEW: mylist — personal upcoming tracker ──
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
                "╔══════════════════════╗\n║  📌  *MY UPCOMING*  ║\n╚══════════════════════╝\n\n"
                "📭 *Abhi koi movie nahi hai!*\n\n"
                "Movie search karo aur 📌 *Add to My Upcoming* dabao.\n\n"
                "_Example: `/upcoming Avengers`_",
                parse_mode="Markdown"
            )
            return
        text  = "╔══════════════════════╗\n║  📌  *MY UPCOMING*  ║\n╚══════════════════════╝\n\n"
        today = str(today_ist())
        for movie_id, title, release, genres, rating, added_at in rows:
            try:
                rel_date = datetime.strptime(release, "%Y-%m-%d").date()
                days_left = (rel_date - today_ist()).days
                if days_left < 0:
                    countdown = "✅ Released"
                elif days_left == 0:
                    countdown = "🔴 *TODAY!*"
                elif days_left <= 7:
                    countdown = f"🟡 {days_left} days left"
                else:
                    countdown = f"🟢 {days_left} days left"
            except Exception:
                countdown = f"📅 {release}"
            stars = "⭐" * max(1, round((rating or 0) / 2))
            text += (
                f"🎬 *{title}*\n"
                f"📅 {release}  |  {countdown}\n"
                f"{stars} {rating:.1f}  |  🎭 {genres or 'N/A'}\n"
                f"🗑 `/upcom_remove {movie_id}`\n\n"
            )
        text += f"_Total: {len(rows)} movies  |  `/upcoming mylist` refresh_"
        await update.message.reply_text(text, parse_mode="Markdown")
        return

    # ── With args: try month/year parse first, else treat as movie name search ──
    try:
        month, year, genre_id = _upcom_parse_args(raw_args)
        is_name_search = False
    except ValueError:
        # Not a month/year — treat as movie name search
        is_name_search = True

    # ── Movie name search (naam + optional year) ──
    if is_name_search:
        # Last token 4-digit year hai? e.g. "Spider-Man 2025"
        parts       = raw_args.split()
        search_year = None
        search_name = raw_args
        if len(parts) >= 2:
            last = parts[-1]
            if last.isdigit() and 2000 <= int(last) <= 2100:
                search_year = int(last)
                search_name = " ".join(parts[:-1])

        year_label = f" ({search_year})" if search_year else ""
        loading = await update.message.reply_text(
            f"🔍 *\"{search_name}{year_label}\"* search kar raha hoon…",
            parse_mode="Markdown"
        )
        movies = await asyncio.to_thread(_upcom_search_by_name, search_name, search_year)
        try: await loading.delete()
        except: pass
        if not movies:
            tip = (
                f"\n\n💡 Bina year ke try karo:\n`/upcoming {search_name}`"
                if search_year else ""
            )
            await update.message.reply_text(
                f"😕 *\"{search_name}{year_label}\"* — koi movie nahi mili.{tip}\n\n"
                f"Spelling check karo ya alag naam try karo.",
                parse_mode="Markdown"
            )
            return
        _upcom_clean_sessions()
        chat_id = update.effective_chat.id
        upcom_sessions[chat_id] = {
            "movies": movies, "page": 0, "month": 0,
            "year": search_year or 0, "search": search_name,
            "_ts": __import__("time").time()
        }
        await update.message.reply_text(
            f"🔍 *\"{search_name}{year_label}\"* — {len(movies)} results\n\n"
            f"_📌 Add to My Upcoming  |  ❤️ Watchlist  |  🔔 Remind_",
            parse_mode="Markdown"
        )
        for m in movies[:UPCOM_PAGE_SIZE]:
            await _upcom_send_card(chat_id, m, context)
        if len(movies) > UPCOM_PAGE_SIZE:
            await context.bot.send_message(chat_id, "👇 Navigate karo:",
                                           reply_markup=_upcom_nav_keyboard(chat_id))
        return

    # ── Month/year browse (existing) ──
    month_name  = calendar.month_name[month]
    genre_label = ""
    if genre_id:
        gname = next((k for k, v in UPCOM_NAME_TO_ID.items() if v == genre_id), "")
        genre_label = f" · {gname.title()}"

    loading = await update.message.reply_text(
        f"🔍 Searching *{month_name} {year}{genre_label}*…", parse_mode="Markdown"
    )
    movies = await asyncio.to_thread(_upcom_get_movies, month, year, genre_id)
    try: await loading.delete()
    except: pass

    if not movies:
        await update.message.reply_text(
            f"😕 *{month_name} {year}{genre_label}* mein koi movie nahi mili.\nAlag month/genre try karo.",
            parse_mode="Markdown"
        )
        return

    chat_id = update.effective_chat.id
    _upcom_clean_sessions()   # memory leak fix
    upcom_sessions[chat_id] = {"movies": movies, "page": 0, "month": month, "year": year, "_ts": __import__("time").time()}
    total_pages = (len(movies) + UPCOM_PAGE_SIZE - 1) // UPCOM_PAGE_SIZE

    await update.message.reply_text(
        f"🎬 *{month_name} {year}{genre_label}*\n"
        f"📊 {len(movies)} movies  |  📄 Page 1/{total_pages}\n\n"
        f"_📌 Add to My Upcoming  |  ❤️ Watchlist  |  🔔 Remind Me  |  🤖 AI Review_",
        parse_mode="Markdown"
    )
    for m in movies[:UPCOM_PAGE_SIZE]:
        await _upcom_send_card(chat_id, m, context)
    await context.bot.send_message(chat_id, "👇 Navigate karo:",
                                   reply_markup=_upcom_nav_keyboard(chat_id))


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
    await context.bot.send_message(
        chat_id,
        f"📄 *Page {page+1}/{total_pages}* — {calendar.month_name[s['month']]} {s['year']}",
        parse_mode="Markdown"
    )
    for m in chunk:
        await _upcom_send_card(chat_id, m, context)
    await context.bot.send_message(chat_id, "👇 Navigate karo:",
                                   reply_markup=_upcom_nav_keyboard(chat_id))


async def upcom_ai_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("⏳ AI Review generate ho raha hai…")
    try:
        movie_id = int(query.data.split("_")[2])
        res  = await asyncio.to_thread(
            lambda: requests.get(f"https://api.themoviedb.org/3/movie/{movie_id}",
                                 params={"api_key": TMDB_API}, timeout=10)
        )
        data = res.json()
        title    = data.get("title", "Unknown")
        overview = data.get("overview", "")
        rating   = data.get("vote_average", 0.0)
    except Exception as e:
        await query.message.reply_text(f"❌ Error: {e}")
        return
    if not GROQ_API:
        await query.message.reply_text("⚠️ GROQ_API set nahi hai!")
        return
    loader = await query.message.reply_text("🤖 AI Review likh raha hai...\n" + progress_bar(0, 4))
    await animate_generic(loader, FRAMES["review"])
    review = await ai_movie_review(title, "", overview, str(round(rating, 1)))
    try: await loader.delete()
    except: pass
    if review:
        await query.message.reply_text(
            f"╔══════════════════════╗\n║  🤖  *AI REVIEW*  ║\n╚══════════════════════╝\n\n"
            f"🎬 *{title}*\n━━━━━━━━━━━━━━━━━━\n\n{review}\n\n_Powered by Groq AI_ 🤖",
            parse_mode="Markdown"
        )
    else:
        await query.message.reply_text("❌ AI Review nahi aaya. Try again.")


async def upcom_remind_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    user_id = query.from_user.id
    try:
        # format: upcom_rm_MOVIEID_YYYY-MM-DD
        parts    = query.data.split("_")
        movie_id = int(parts[2])
        release  = parts[3]
        # fetch title from TMDB — non-blocking
        res   = await asyncio.to_thread(
            lambda: requests.get(f"https://api.themoviedb.org/3/movie/{movie_id}",
                                 params={"api_key": TMDB_API}, timeout=8)
        )
        title = res.json().get("title", "Movie")
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
        await asyncio.to_thread(
            _db_execute,
            "INSERT OR IGNORE INTO upcom_reminders VALUES (?,?,?,?)",
            (user_id, movie_id, title, release)
        )
        await query.answer(f"🔔 Reminder set! Release: {release}", show_alert=True)
    except Exception as e:
        await query.answer("❌ DB error.", show_alert=True)
        print(e)




async def upcom_add_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """NEW: Add to My Upcoming."""
    query   = update.callback_query
    user_id = query.from_user.id
    await query.answer("Adding...")

    try:
        movie_id = int(query.data.split("_")[2])
    except (IndexError, ValueError):
        await query.answer("Invalid data.", show_alert=True)
        return

    try:
        res = await asyncio.to_thread(
            lambda: requests.get(
                f"https://api.themoviedb.org/3/movie/{movie_id}",
                params={"api_key": TMDB_API},
                timeout=8,
            )
        )
        data    = res.json()
        title   = data.get("title", "Unknown")
        release = data.get("release_date", "N/A")
        rating  = data.get("vote_average", 0.0)
        genres  = " - ".join(g["name"] for g in data.get("genres", [])[:3]) or "N/A"
        pp      = data.get("poster_path")
        poster  = f"{UPCOM_POSTER_BASE}{pp}" if pp else UPCOM_DEFAULT_POSTER
    except Exception as e:
        await query.answer(f"TMDB error: {e}", show_alert=True)
        return

    added_at = now_ist().strftime("%d %b %Y")
    try:
        # Check duplicate
        exists = await asyncio.to_thread(
            _db_fetch,
            "SELECT 1 FROM upcom_mylist WHERE user_id=? AND movie_id=?",
            (user_id, movie_id)
        )
        if exists:
            await query.answer("Already in your list!", show_alert=True)
            return
        await asyncio.to_thread(
            _db_execute,
            "INSERT INTO upcom_mylist (user_id, movie_id, title, release, genres, poster, rating, added_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (user_id, movie_id, title, release, genres, poster, rating, added_at)
        )
        await query.answer(
            f"{title} added to My Upcoming! Check: /upcoming mylist",
            show_alert=True
        )
    except Exception as e:
        await query.answer("DB error.", show_alert=True)
        print(f"[UPCOM ADD] {e}")


async def upcom_remove_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """NEW: /upcom_remove <movie_id>"""
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text(
            "Usage: `/upcom_remove <movie_id>`\n\nMovie ID `/upcoming mylist` mein dikha raha hai.",
            parse_mode="Markdown"
        )
        return
    try:
        movie_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid movie ID.")
        return
    try:
        rows = await asyncio.to_thread(
            _db_fetch,
            "SELECT title FROM upcom_mylist WHERE user_id=? AND movie_id=?",
            (user_id, movie_id)
        )
        if not rows:
            await update.message.reply_text("Ye movie aapki list mein nahi hai.")
            return
        await asyncio.to_thread(
            _db_execute,
            "DELETE FROM upcom_mylist WHERE user_id=? AND movie_id=?",
            (user_id, movie_id)
        )
        await update.message.reply_text(
            f"{rows[0][0]} hata diya My Upcoming se.\n/upcoming mylist se check karo.",
        )
    except Exception as e:
        await update.message.reply_text("Error removing movie.")
        print(f"[UPCOM REMOVE] {e}")


async def upcom_check_reminders(context=None):
    """Daily 9 AM — notify users about releasing movies."""
    today = now_ist().strftime("%Y-%m-%d")
    rows  = await asyncio.to_thread(
        _db_fetch,
        "SELECT user_id, movie_id, title FROM upcom_reminders WHERE release=?",
        (today,)
    )
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
                    parse_mode="Markdown", reply_markup=kb
                )
        except Exception as e:
            print(f"[UPCOM REMINDER] user={user_id} → {e}")
    if rows:
        await asyncio.to_thread(
            _db_execute,
            "DELETE FROM upcom_reminders WHERE release=?",
            (today,)
        )


# ═══════════════════════════════════════════════════════════════════
#           AI SUGGEST
# ═══════════════════════════════════════════════════════════════════
