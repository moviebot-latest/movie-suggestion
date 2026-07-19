"""
Repository layer — every DB query the bot needs, in one place.

Fixes vs old single-file bot:
  - No more load_json()/save_json() race conditions: every write here is
    a single atomic SQL statement (INSERT ... ON CONFLICT, UPDATE ...),
    safe under concurrent access without any manual locking.
  - is_admin() logic ported 1:1 from the old bot (that part was already
    correct) but now backed by Postgres instead of a JSON file.
"""
from __future__ import annotations

import time
from typing import Optional

from config import ADMIN_ID
from database import get_pool


# ── Users ────────────────────────────────────────────────────────
async def register_user(user_id: int, name: str, username: Optional[str], referred_by: Optional[int] = None) -> bool:
    """Returns True if this was a brand-new user."""
    pool = await get_pool()
    result = await pool.execute(
        """
        INSERT INTO users (user_id, name, username, referred_by)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (user_id) DO NOTHING
        """,
        user_id, name, username or "N/A", referred_by,
    )
    return result == "INSERT 0 1"


async def get_user(user_id: int):
    pool = await get_pool()
    return await pool.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)


async def increment_search_count(user_id: int, points: int = 1):
    pool = await get_pool()
    await pool.execute(
        "UPDATE users SET searches = searches + 1, points = points + $2 WHERE user_id = $1",
        user_id, points,
    )


async def add_points(user_id: int, points: int):
    pool = await get_pool()
    await pool.execute("UPDATE users SET points = points + $2 WHERE user_id = $1", user_id, points)


async def set_lang(user_id: int, lang: str):
    pool = await get_pool()
    await pool.execute("UPDATE users SET lang = $2 WHERE user_id = $1", user_id, lang)


async def all_user_ids() -> list[int]:
    pool = await get_pool()
    rows = await pool.fetch("SELECT user_id FROM users")
    return [r["user_id"] for r in rows]


async def user_count() -> int:
    pool = await get_pool()
    return await pool.fetchval("SELECT COUNT(*) FROM users")


async def leaderboard(limit: int = 10):
    pool = await get_pool()
    return await pool.fetch(
        "SELECT user_id, name, points FROM users ORDER BY points DESC LIMIT $1", limit
    )


# ── Ban management ──────────────────────────────────────────────
async def is_banned(user_id: int) -> bool:
    pool = await get_pool()
    row = await pool.fetchval("SELECT 1 FROM banned_users WHERE user_id = $1", user_id)
    return row is not None


async def ban_user(user_id: int, reason: str = ""):
    pool = await get_pool()
    await pool.execute(
        "INSERT INTO banned_users (user_id, reason) VALUES ($1, $2) "
        "ON CONFLICT (user_id) DO UPDATE SET reason = $2",
        user_id, reason,
    )


async def unban_user(user_id: int):
    pool = await get_pool()
    await pool.execute("DELETE FROM banned_users WHERE user_id = $1", user_id)


async def list_banned():
    pool = await get_pool()
    return await pool.fetch("SELECT * FROM banned_users ORDER BY banned_at DESC")


# ── Admins ───────────────────────────────────────────────────────
def is_owner(user_id: int) -> bool:
    return user_id == ADMIN_ID


async def is_admin(user_id: int) -> bool:
    if user_id == ADMIN_ID:
        return True
    pool = await get_pool()
    row = await pool.fetchrow("SELECT admin_type, expiry_ts FROM admins WHERE user_id = $1", user_id)
    if not row:
        return False
    if row["admin_type"] == "permanent":
        return True
    # temporary
    if row["expiry_ts"] and time.time() < row["expiry_ts"]:
        return True
    # expired — clean up
    await pool.execute("DELETE FROM admins WHERE user_id = $1", user_id)
    return False


async def add_admin(user_id: int, added_by: int, hours: Optional[int] = None):
    pool = await get_pool()
    admin_type = "temporary" if hours else "permanent"
    expiry = time.time() + hours * 3600 if hours else None
    await pool.execute(
        """
        INSERT INTO admins (user_id, admin_type, expiry_ts, added_by)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (user_id) DO UPDATE SET admin_type = $2, expiry_ts = $3, added_by = $4, added_at = now()
        """,
        user_id, admin_type, expiry, added_by,
    )


async def remove_admin(user_id: int) -> bool:
    pool = await get_pool()
    result = await pool.execute("DELETE FROM admins WHERE user_id = $1", user_id)
    return result != "DELETE 0"


async def list_admins():
    pool = await get_pool()
    return await pool.fetch("SELECT * FROM admins ORDER BY added_at DESC")


# ── Settings (maintenance mode, servers config, etc.) — replaces FILES dict ──
async def get_setting(key: str, default=None):
    pool = await get_pool()
    row = await pool.fetchval("SELECT value FROM settings WHERE key = $1", key)
    return row if row is not None else default


async def set_setting(key: str, value):
    pool = await get_pool()
    import json
    await pool.execute(
        """
        INSERT INTO settings (key, value) VALUES ($1, $2::jsonb)
        ON CONFLICT (key) DO UPDATE SET value = $2::jsonb
        """,
        key, json.dumps(value),
    )


# ── Watchlist ────────────────────────────────────────────────────
async def watchlist_add(user_id: int, imdb_id: str, title: str):
    pool = await get_pool()
    await pool.execute(
        "INSERT INTO watchlist (user_id, imdb_id, title) VALUES ($1, $2, $3) "
        "ON CONFLICT (user_id, imdb_id) DO NOTHING",
        user_id, imdb_id, title,
    )


async def watchlist_get(user_id: int):
    pool = await get_pool()
    return await pool.fetch("SELECT * FROM watchlist WHERE user_id = $1 ORDER BY added_at DESC", user_id)


async def watchlist_clear(user_id: int):
    pool = await get_pool()
    await pool.execute("DELETE FROM watchlist WHERE user_id = $1", user_id)


# ── Ratings ──────────────────────────────────────────────────────
async def rate_movie(user_id: int, imdb_id: str, title: str, rating: int):
    pool = await get_pool()
    await pool.execute(
        """
        INSERT INTO ratings (user_id, imdb_id, title, rating) VALUES ($1, $2, $3, $4)
        ON CONFLICT (user_id, imdb_id) DO UPDATE SET rating = $4, rated_at = now()
        """,
        user_id, imdb_id, title, rating,
    )


# ── Search history ───────────────────────────────────────────────
async def log_search(user_id: int, query: str):
    pool = await get_pool()
    await pool.execute("INSERT INTO search_history (user_id, query) VALUES ($1, $2)", user_id, query)


async def get_history(user_id: int, limit: int = 20):
    pool = await get_pool()
    return await pool.fetch(
        "SELECT query, searched_at FROM search_history WHERE user_id = $1 "
        "ORDER BY searched_at DESC LIMIT $2",
        user_id, limit,
    )


# ── Alerts ───────────────────────────────────────────────────────
async def alert_add(user_id: int, keyword: str):
    pool = await get_pool()
    await pool.execute(
        "INSERT INTO alerts (user_id, keyword) VALUES ($1, $2) ON CONFLICT DO NOTHING",
        user_id, keyword.lower(),
    )


async def alert_del(user_id: int, keyword: str):
    pool = await get_pool()
    await pool.execute("DELETE FROM alerts WHERE user_id = $1 AND keyword = $2", user_id, keyword.lower())


async def alert_clear(user_id: int):
    pool = await get_pool()
    await pool.execute("DELETE FROM alerts WHERE user_id = $1", user_id)


async def alert_list(user_id: int):
    pool = await get_pool()
    return await pool.fetch("SELECT keyword FROM alerts WHERE user_id = $1", user_id)


# ── Upcoming reminders / mylist ──────────────────────────────────
async def upcoming_reminder_add(user_id: int, movie_id: int, title: str, release_date: str):
    pool = await get_pool()
    await pool.execute(
        "INSERT INTO upcoming_reminders (user_id, movie_id, title, release_date) VALUES ($1,$2,$3,$4) "
        "ON CONFLICT DO NOTHING",
        user_id, movie_id, title, release_date,
    )


async def upcoming_mylist_add(user_id: int, movie_id: int, title: str):
    pool = await get_pool()
    await pool.execute(
        "INSERT INTO upcoming_mylist (user_id, movie_id, title) VALUES ($1,$2,$3) ON CONFLICT DO NOTHING",
        user_id, movie_id, title,
    )


async def upcoming_mylist_remove(user_id: int, movie_id: int) -> bool:
    pool = await get_pool()
    result = await pool.execute(
        "DELETE FROM upcoming_mylist WHERE user_id = $1 AND movie_id = $2", user_id, movie_id
    )
    return result != "DELETE 0"


async def upcoming_mylist_has(user_id: int, movie_id: int) -> bool:
    pool = await get_pool()
    row = await pool.fetchval(
        "SELECT 1 FROM upcoming_mylist WHERE user_id = $1 AND movie_id = $2", user_id, movie_id
    )
    return row is not None


# ── Quiz ─────────────────────────────────────────────────────────
async def quiz_record(user_id: int, correct: bool):
    pool = await get_pool()
    await pool.execute(
        """
        INSERT INTO quiz_scores (user_id, correct, total) VALUES ($1, $2, 1)
        ON CONFLICT (user_id) DO UPDATE SET
            correct = quiz_scores.correct + $2,
            total = quiz_scores.total + 1
        """,
        user_id, 1 if correct else 0,
    )


async def quiz_stats(user_id: int):
    pool = await get_pool()
    return await pool.fetchrow("SELECT correct, total FROM quiz_scores WHERE user_id = $1", user_id)


# ── Domain healer history ────────────────────────────────────────
async def domain_history_record(site_key: str, domain: str, is_up: bool):
    pool = await get_pool()
    now = time.time()
    up_inc = 1 if is_up else 0
    down_inc = 0 if is_up else 1
    await pool.execute(
        """
        INSERT INTO server_domain_history (site_key, domain, first_seen, last_seen, times_up, times_down)
        VALUES ($1, $2, $3, $3, $4, $5)
        ON CONFLICT (site_key, domain) DO UPDATE SET
            last_seen = $3,
            times_up = server_domain_history.times_up + $4,
            times_down = server_domain_history.times_down + $5
        """,
        site_key, domain, now, up_inc, down_inc,
    )


async def heal_log_add(site_key: str, old_url: str, new_url: str, status: str):
    pool = await get_pool()
    await pool.execute(
        "INSERT INTO heal_log (site_key, old_url, new_url, status, created_at) VALUES ($1,$2,$3,$4,$5)",
        site_key, old_url, new_url, status, time.time(),
    )


async def heal_log_recent(limit: int = 20):
    pool = await get_pool()
    return await pool.fetch("SELECT * FROM heal_log ORDER BY created_at DESC LIMIT $1", limit)
