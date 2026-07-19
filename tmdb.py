"""
TMDB API wrapper — cached, fully async. Powers /upcoming, /castinfo,
trailers, and similar-movie suggestions.
"""
from __future__ import annotations

import calendar
import logging
from typing import Optional

import aiohttp

from bot.config import TMDB_API_KEY, CACHE_TTL_TMDB

log = logging.getLogger("cinebot.tmdb")

_BASE = "https://api.themoviedb.org/3"
_TIMEOUT = aiohttp.ClientTimeout(total=10)
POSTER_BASE = "https://image.tmdb.org/t/p/w500"
DEFAULT_POSTER = "https://via.placeholder.com/500x750?text=No+Poster"

GENRE_MAP = {
    28: "Action", 12: "Adventure", 16: "Animation", 35: "Comedy",
    80: "Crime", 99: "Documentary", 18: "Drama", 10751: "Family",
    14: "Fantasy", 36: "History", 27: "Horror", 10402: "Music",
    9648: "Mystery", 10749: "Romance", 878: "Sci-Fi", 10770: "TV Movie",
    53: "Thriller", 10752: "War", 37: "Western",
}
NAME_TO_ID = {v.lower(): k for k, v in GENRE_MAP.items()}


def _genre_names(ids: list) -> str:
    names = [GENRE_MAP.get(i) for i in ids if GENRE_MAP.get(i)]
    return ", ".join(names[:3]) if names else "N/A"


from bot.services.cache import cache_get, cache_set


async def _get(path: str, params: dict) -> Optional[dict]:
    if not TMDB_API_KEY:
        return None
    params = {**params, "api_key": TMDB_API_KEY}
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.get(f"{_BASE}{path}", params=params) as resp:
                resp.raise_for_status()
                return await resp.json()
    except Exception as e:
        log.warning("TMDB %s failed: %s", path, e)
        return None


async def get_movies_for_month(month: int, year: int, genre_id: Optional[int] = None) -> list:
    cache_key = f"tmdb:month:{year}-{month:02d}:{genre_id or 'all'}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    last_day = calendar.monthrange(year, month)[1]
    all_movies = []
    for page in range(1, 6):
        params = {
            "primary_release_date.gte": f"{year}-{month:02d}-01",
            "primary_release_date.lte": f"{year}-{month:02d}-{last_day}",
            "sort_by": "popularity.desc",
            "language": "en-US",
            "include_adult": "false",
            "page": page,
        }
        if genre_id:
            params["with_genres"] = genre_id
        data = await _get("/discover/movie", params)
        if not data:
            break
        results = data.get("results", [])
        total_pages = data.get("total_pages", 1)
        for m in results:
            pp = m.get("poster_path")
            all_movies.append({
                "id": m.get("id"),
                "title": m.get("title", "Unknown"),
                "release": m.get("release_date", "N/A"),
                "overview": m.get("overview", ""),
                "rating": m.get("vote_average", 0.0),
                "votes": m.get("vote_count", 0),
                "genres": _genre_names(m.get("genre_ids", [])),
                "poster": f"{POSTER_BASE}{pp}" if pp else DEFAULT_POSTER,
            })
        if page >= total_pages:
            break

    if all_movies:
        await cache_set(cache_key, all_movies, CACHE_TTL_TMDB)
    return all_movies


async def search_by_name(query: str, year: Optional[int] = None) -> list:
    cache_key = f"tmdb:search:{query.lower()}:{year or 'any'}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    params = {"query": query, "language": "en-US", "include_adult": "false", "page": 1}
    if year:
        params["primary_release_year"] = year

    data = await _get("/search/movie", params)
    if not data:
        return []
    movies = []
    for m in data.get("results", [])[:10]:
        pp = m.get("poster_path")
        movies.append({
            "id": m.get("id"), "title": m.get("title", "Unknown"),
            "release": m.get("release_date", "N/A"), "overview": m.get("overview", ""),
            "rating": m.get("vote_average", 0.0), "votes": m.get("vote_count", 0),
            "genres": _genre_names(m.get("genre_ids", [])),
            "poster": f"{POSTER_BASE}{pp}" if pp else DEFAULT_POSTER,
        })
    if movies:
        await cache_set(cache_key, movies, CACHE_TTL_TMDB)
    return movies


async def get_trailer(movie_id: int) -> Optional[str]:
    cache_key = f"tmdb:trailer:{movie_id}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached or None

    data = await _get(f"/movie/{movie_id}/videos", {})
    if not data:
        return None
    vids = data.get("results", [])
    url = None
    for v in vids:
        if v.get("type") == "Trailer" and v.get("site") == "YouTube" and v.get("official"):
            url = f"https://youtu.be/{v['key']}"
            break
    if not url:
        for v in vids:
            if v.get("type") == "Trailer" and v.get("site") == "YouTube":
                url = f"https://youtu.be/{v['key']}"
                break
    await cache_set(cache_key, url or "", CACHE_TTL_TMDB)
    return url


async def get_movie_details(movie_id: int) -> Optional[dict]:
    cache_key = f"tmdb:movie:{movie_id}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached
    data = await _get(f"/movie/{movie_id}", {})
    if data:
        await cache_set(cache_key, data, CACHE_TTL_TMDB)
    return data


async def get_credits(movie_id: int) -> Optional[dict]:
    cache_key = f"tmdb:credits:{movie_id}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached
    data = await _get(f"/movie/{movie_id}/credits", {})
    if data:
        await cache_set(cache_key, data, CACHE_TTL_TMDB)
    return data


async def get_similar(movie_id: int) -> list:
    data = await _get(f"/movie/{movie_id}/similar", {"language": "en-US", "page": 1})
    if not data:
        return []
    return data.get("results", [])[:5]
