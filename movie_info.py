# ╔══════════════════════════════════════════╗
# ║  movie_info.py — TMDB + OMDB fetching    ║
# ║  Edit to change how movies are fetched   ║
# ╚══════════════════════════════════════════╝
import asyncio, aiohttp, requests, logging
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import TMDB_API, OMDB_API, now_ist

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


