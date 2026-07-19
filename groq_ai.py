"""
Groq AI wrapper.

Fixes vs old single-file bot:
  - Old `ai_ask()` on HTTP 429 did `await asyncio.sleep(5)` then returned
    None WITHOUT ever retrying the request — the sleep accomplished
    nothing but delay. This version actually retries (once) after backoff.

New:
  - The Groq API key is no longer frozen at deploy time from the
    GROQ_API env var. It's stored in Postgres (`settings` table) and can
    be viewed/changed live via /groqstatus and /setgroqkey — no redeploy
    needed when a key expires or gets rotated. The env var is only used
    as the initial seed value the first time the bot boots.
  - /groqstatus makes a tiny live test call to Groq and reports whether
    the current key is actually working (Groq doesn't expose an
    "expiry date" via API, so "active vs expired/invalid" is determined
    by literally trying a request and reading the response code).
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

import aiohttp

from config import GROQ_API_KEY as _ENV_SEED_KEY, GROQ_URL, GROQ_MODEL

log = logging.getLogger("cinebot.groq")

_TIMEOUT = aiohttp.ClientTimeout(total=20)
_STATUS_TIMEOUT = aiohttp.ClientTimeout(total=10)

_SETTING_KEY = "groq_api_key"
_STATUS_KEY = "groq_key_status"  # cached last-known status, so /groqstatus doesn't always need a fresh call

# Small in-process cache so we don't hit Postgres on every single AI call.
_cache_key: Optional[str] = None
_cache_loaded_at: float = 0.0
_CACHE_TTL = 30  # seconds — short enough that /setgroqkey takes effect almost immediately


async def _get_active_key() -> Optional[str]:
    global _cache_key, _cache_loaded_at
    now = time.monotonic()
    if _cache_key is not None and (now - _cache_loaded_at) < _CACHE_TTL:
        return _cache_key

    import repository as repo
    stored = await repo.get_setting(_SETTING_KEY, None)
    if stored:
        _cache_key = stored
    elif _ENV_SEED_KEY:
        # First boot: seed the DB from the env var so future changes go through /setgroqkey.
        await repo.set_setting(_SETTING_KEY, _ENV_SEED_KEY)
        _cache_key = _ENV_SEED_KEY
    else:
        _cache_key = None
    _cache_loaded_at = now
    return _cache_key


async def set_groq_key(new_key: str):
    """Called by /setgroqkey. Persists to DB and invalidates the in-memory cache immediately."""
    global _cache_key, _cache_loaded_at
    import repository as repo
    await repo.set_setting(_SETTING_KEY, new_key.strip())
    _cache_key = new_key.strip()
    _cache_loaded_at = time.monotonic()
    log.info("Groq API key updated via /setgroqkey")


async def check_groq_status() -> dict:
    """
    Makes one tiny live request to Groq to check if the current key works.
    Returns a dict: {"active": bool, "detail": str, "checked_at": float}
    Also persists this result so it can be shown without re-checking every time.
    """
    import repository as repo
    key = await _get_active_key()
    checked_at = time.time()

    if not key:
        result = {"active": False, "detail": "No Groq API key configured.", "checked_at": checked_at}
        await repo.set_setting(_STATUS_KEY, result)
        return result

    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 5,
    }
    try:
        async with aiohttp.ClientSession(timeout=_STATUS_TIMEOUT) as session:
            async with session.post(GROQ_URL, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    result = {"active": True, "detail": "Key is valid and working.", "checked_at": checked_at}
                elif resp.status == 401:
                    result = {"active": False, "detail": "401 Unauthorized — key is invalid, revoked, or expired.", "checked_at": checked_at}
                elif resp.status == 429:
                    result = {"active": True, "detail": "429 Rate limited right now, but the key itself is valid.", "checked_at": checked_at}
                else:
                    text = (await resp.text())[:150]
                    result = {"active": False, "detail": f"HTTP {resp.status}: {text}", "checked_at": checked_at}
    except asyncio.TimeoutError:
        result = {"active": False, "detail": "Timed out contacting Groq.", "checked_at": checked_at}
    except Exception as e:
        result = {"active": False, "detail": f"Error: {e}", "checked_at": checked_at}

    await repo.set_setting(_STATUS_KEY, result)
    return result


async def get_cached_groq_status() -> Optional[dict]:
    """Last-known status without making a new API call (fast, for display in /admin panel etc.)."""
    import repository as repo
    return await repo.get_setting(_STATUS_KEY, None)


async def ai_ask(prompt: str, max_tokens: int = 1000, _retry: bool = True) -> Optional[str]:
    key = await _get_active_key()
    if not key:
        return None
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.75,
    }
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.post(GROQ_URL, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"].strip()
                elif resp.status == 429 and _retry:
                    log.info("Groq 429 — backing off 5s and retrying once")
                    await asyncio.sleep(5)
                    return await ai_ask(prompt, max_tokens, _retry=False)  # FIX: actually retry
                elif resp.status == 401:
                    log.warning("Groq API key rejected (401) — key may be expired/revoked. Use /setgroqkey to update it.")
                    return None
                else:
                    text = await resp.text()
                    log.warning("Groq API error %d: %s", resp.status, text[:200])
                    return None
    except asyncio.TimeoutError:
        log.warning("Groq API timeout")
        return None
    except Exception as e:
        log.warning("Groq API exception: %s", e)
        return None


async def ai_fix_movie_name(raw_name: str) -> str:
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


async def ai_mood_match(mood: str) -> Optional[str]:
    return await ai_ask(
        f"User's current mood: '{mood}'\n"
        "Suggest exactly 5 movies that fit this mood.\n"
        "Format: 🎬 Title (Year) — One line reason\n"
        "Be concise. Reply in Hinglish."
    )


async def ai_cast_analysis(title: str, cast_names: str) -> Optional[str]:
    return await ai_ask(
        f"Movie: '{title}'\nMain cast: {cast_names}\n\n"
        "Give a brief 3-4 sentence analysis of the cast performances/chemistry. "
        "Reply in Hinglish."
    )


async def ai_trivia(title: str, year: str) -> Optional[str]:
    return await ai_ask(
        f"Give 3 interesting trivia facts about the movie '{title}' ({year}).\n"
        "Format each as a bullet point with an emoji. Be concise. Reply in Hinglish."
    )
