"""
OMDB API wrapper — cached, fully async (aiohttp instead of requests+to_thread).

Fixes vs old single-file bot:
  - Old code used sync `requests.get` wrapped in asyncio.to_thread — works,
    but ties up a thread-pool worker per call. Native aiohttp is lighter
    at scale.
  - Responses are cached in Redis so identical searches don't repeatedly
    hit OMDB's rate-limited free tier.
  - No bare `except:` — every failure path is logged with context.
"""
from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import quote

import aiohttp

from bot.config import OMDB_API_KEY, CACHE_TTL_OMDB, CACHE_TTL_SEARCH
from bot.services.cache import cache_get, cache_set

log = logging.getLogger("cinebot.omdb")

_BASE = "https://www.omdbapi.com/"
_TIMEOUT = aiohttp.ClientTimeout(total=8)


async def get_omdb(title: str, by_id: bool = False) -> Optional[dict]:
    """Fetch a single movie by title or IMDb ID, with Redis caching."""
    param = "i" if by_id else "t"
    cache_key = f"omdb:{param}:{title.lower()}"

    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    url = f"{_BASE}?{param}={quote(title)}&apikey={OMDB_API_KEY}&plot=full"
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.get(url) as resp:
                data = await resp.json()
    except Exception as e:
        log.warning("OMDB fetch failed for %r: %s", title, e)
        return None

    if data and data.get("Response") == "True":
        await cache_set(cache_key, data, CACHE_TTL_OMDB)
    return data


async def get_omdb_search(query: str) -> list:
    """Fuzzy title search returning up to 5 candidates, with Redis caching."""
    cache_key = f"omdb:search:{query.lower()}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    url = f"{_BASE}?s={quote(query)}&apikey={OMDB_API_KEY}"
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.get(url) as resp:
                data = await resp.json()
    except Exception as e:
        log.warning("OMDB search failed for %r: %s", query, e)
        return []

    results = data.get("Search", [])[:5]
    if results:
        await cache_set(cache_key, results, CACHE_TTL_SEARCH)
    return results
