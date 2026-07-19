"""
PostgreSQL connection pool + schema setup.

Fixes vs old single-file bot:
  - Data now survives redeploys (old bot stored everything in local
    JSON files / SQLite on Render's ephemeral filesystem — wiped on
    every restart).
  - asyncpg pool handles concurrency safely — no more read-modify-write
    races that the old load_json()/save_json() pattern had.

Works with Neon's free serverless Postgres:
  - Neon requires SSL (`sslmode=require` in the connection string) —
    asyncpg parses that from the DSN automatically, no extra code needed.
  - Neon "scales to zero" after inactivity: the very first query after
    a period of idleness can take ~1-2s while it wakes up. min_size=1
    (rather than a larger idle pool) avoids holding open connections
    that would otherwise keep the database artificially awake, and the
    retry-on-first-connect below absorbs that one-time wake-up delay
    instead of crashing startup.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import asyncpg

from bot.config import DATABASE_URL

log = logging.getLogger("cinebot.db")

_pool: Optional[asyncpg.Pool] = None


async def init_pool() -> asyncpg.Pool:
    global _pool
    if _pool is not None:
        return _pool

    last_error = None
    for attempt in range(1, 4):
        try:
            _pool = await asyncpg.create_pool(
                dsn=DATABASE_URL,
                min_size=1,
                max_size=10,
                command_timeout=30,
                # Neon's connection can take a moment to wake from scale-to-zero.
                timeout=15,
            )
            break
        except (asyncpg.exceptions.PostgresError, OSError, asyncio.TimeoutError) as e:
            last_error = e
            log.warning("DB pool connection attempt %d/3 failed (%s) — retrying in 3s (likely Neon cold start)", attempt, e)
            await asyncio.sleep(3)
    else:
        log.error("❌ Could not connect to database after 3 attempts: %s", last_error)
        raise last_error

    log.info("✅ PostgreSQL pool created")
    await _run_migrations(_pool)
    return _pool


async def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialized — call init_pool() first (post_init).")
    return _pool


async def close_pool():
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        log.info("PostgreSQL pool closed")


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id     BIGINT PRIMARY KEY,
    name        TEXT,
    username    TEXT,
    joined_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    searches    INTEGER NOT NULL DEFAULT 0,
    points      INTEGER NOT NULL DEFAULT 0,
    lang        TEXT NOT NULL DEFAULT 'Any',
    referred_by BIGINT
);

CREATE TABLE IF NOT EXISTS banned_users (
    user_id    BIGINT PRIMARY KEY,
    banned_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    reason     TEXT
);

CREATE TABLE IF NOT EXISTS admins (
    user_id    BIGINT PRIMARY KEY,
    admin_type TEXT NOT NULL CHECK (admin_type IN ('permanent', 'temporary')),
    expiry_ts  DOUBLE PRECISION,
    added_by   BIGINT,
    added_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS watchlist (
    user_id    BIGINT NOT NULL,
    imdb_id    TEXT NOT NULL,
    title      TEXT,
    added_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, imdb_id)
);

CREATE TABLE IF NOT EXISTS ratings (
    user_id    BIGINT NOT NULL,
    imdb_id    TEXT NOT NULL,
    title      TEXT,
    rating     SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 10),
    rated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, imdb_id)
);

CREATE TABLE IF NOT EXISTS search_history (
    id         BIGSERIAL PRIMARY KEY,
    user_id    BIGINT NOT NULL,
    query      TEXT NOT NULL,
    searched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS alerts (
    user_id    BIGINT NOT NULL,
    keyword    TEXT NOT NULL,
    added_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, keyword)
);

CREATE TABLE IF NOT EXISTS upcoming_reminders (
    user_id    BIGINT NOT NULL,
    movie_id   INTEGER NOT NULL,
    title      TEXT,
    release_date TEXT,
    PRIMARY KEY (user_id, movie_id)
);

CREATE TABLE IF NOT EXISTS upcoming_mylist (
    user_id    BIGINT NOT NULL,
    movie_id   INTEGER NOT NULL,
    title      TEXT,
    added_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, movie_id)
);

CREATE TABLE IF NOT EXISTS quiz_scores (
    user_id    BIGINT PRIMARY KEY,
    correct    INTEGER NOT NULL DEFAULT 0,
    total      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS server_domain_history (
    id         BIGSERIAL PRIMARY KEY,
    site_key   TEXT NOT NULL,
    domain     TEXT NOT NULL,
    first_seen DOUBLE PRECISION NOT NULL,
    last_seen  DOUBLE PRECISION NOT NULL,
    times_up   INTEGER NOT NULL DEFAULT 0,
    times_down INTEGER NOT NULL DEFAULT 0,
    UNIQUE (site_key, domain)
);

CREATE TABLE IF NOT EXISTS heal_log (
    id         BIGSERIAL PRIMARY KEY,
    site_key   TEXT NOT NULL,
    old_url    TEXT,
    new_url    TEXT,
    status     TEXT,
    created_at DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_search_history_user ON search_history(user_id);
CREATE INDEX IF NOT EXISTS idx_watchlist_user ON watchlist(user_id);
CREATE INDEX IF NOT EXISTS idx_ratings_user ON ratings(user_id);
"""


async def _run_migrations(pool: asyncpg.Pool):
    async with pool.acquire() as con:
        async with con.transaction():
            await con.execute(SCHEMA)
    log.info("✅ Schema migrations applied")
