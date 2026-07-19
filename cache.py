"""
Redis caching layer (Render Key Value instance via REDIS_URL).

Used to cache OMDB/TMDB API responses so repeat searches for the same
movie don't burn API quota or add latency. Falls back gracefully to
"no cache" (direct API call) if Redis is briefly unreachable — a cache
outage should never take the bot down.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

import redis.asyncio as redis

from config import REDIS_URL

log = logging.getLogger("cinebot.cache")

_client: Optional[redis.Redis] = None


async def init_cache() -> redis.Redis:
    global _client
    if _client is not None:
        return _client
    _client = redis.from_url(REDIS_URL, decode_responses=True, socket_timeout=5)
    try:
        await _client.ping()
        log.info("✅ Redis cache connected")
    except Exception as e:
        log.warning("⚠️ Redis ping failed at startup: %s (will retry lazily)", e)
    return _client


async def close_cache():
    global _client
    if _client is not None:
        await _client.close()
        _client = None


async def cache_get(key: str) -> Optional[Any]:
    if _client is None:
        return None
    try:
        raw = await _client.get(key)
        return json.loads(raw) if raw else None
    except Exception as e:
        log.debug("cache_get(%s) failed: %s", key, e)
        return None


async def cache_set(key: str, value: Any, ttl: int):
    if _client is None:
        return
    try:
        await _client.set(key, json.dumps(value), ex=ttl)
    except Exception as e:
        log.debug("cache_set(%s) failed: %s", key, e)


async def cache_delete(key: str):
    if _client is None:
        return
    try:
        await _client.delete(key)
    except Exception as e:
        log.debug("cache_delete(%s) failed: %s", key, e)
