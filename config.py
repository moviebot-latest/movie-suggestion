"""
Central configuration & environment validation.

Fixes vs old single-file bot:
  - ADMIN_ID is now REQUIRED (old code silently defaulted to 0, which
    silently locked everyone out of admin features with no warning).
  - All required env vars are validated at import time with clear errors.
  - DATABASE_URL / REDIS_URL are required now that storage moved off
    the local (ephemeral) filesystem.
"""
from __future__ import annotations

import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
log = logging.getLogger("cinebot")


def _require(name: str) -> str:
    val = os.getenv(name)
    if not val:
        log.error("❌ Missing required environment variable: %s", name)
        sys.exit(1)
    return val


def _require_int(name: str) -> int:
    raw = _require(name)
    try:
        return int(raw)
    except ValueError:
        log.error("❌ Environment variable %s must be an integer, got: %r", name, raw)
        sys.exit(1)


# ── Required ────────────────────────────────────────────────────────
BOT_TOKEN    = _require("BOT_TOKEN")
OMDB_API_KEY = _require("OMDB_API")
ADMIN_ID     = _require_int("ADMIN_ID")          # FIX: was silently defaulting to 0
DATABASE_URL = _require("DATABASE_URL")           # PostgreSQL (postgres://... or postgresql://...)
REDIS_URL    = _require("REDIS_URL")              # Render Key Value instance

# ── Webhook (required now that we're not polling) ───────────────────
# Render sets RENDER_EXTERNAL_URL automatically for web services.
WEBHOOK_BASE_URL = os.getenv("RENDER_EXTERNAL_URL") or os.getenv("WEBHOOK_URL", "")
if not WEBHOOK_BASE_URL:
    log.error("❌ No webhook base URL found (RENDER_EXTERNAL_URL / WEBHOOK_URL).")
    sys.exit(1)
WEBHOOK_BASE_URL = WEBHOOK_BASE_URL.rstrip("/")

# Secret path segment so random people can't POST fake updates to your webhook.
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET_TOKEN") or BOT_TOKEN.split(":")[-1]
WEBHOOK_PATH   = f"/webhook/{WEBHOOK_SECRET}"
WEBHOOK_URL    = f"{WEBHOOK_BASE_URL}{WEBHOOK_PATH}"

PORT = int(os.getenv("PORT", "10000"))

# ── Optional ──────────────────────────────────────────────────────
TMDB_API_KEY = os.getenv("TMDB_API", "")
GROQ_API_KEY = os.getenv("GROQ_API", "")

GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"

if not TMDB_API_KEY:
    log.warning("⚠️ TMDB_API not set — upcoming movies / cast / trailer features disabled.")
if not GROQ_API_KEY:
    log.warning("⚠️ GROQ_API not set — AI features (review, mood, plot search) disabled.")

# ── Cache TTLs (seconds) ─────────────────────────────────────────
CACHE_TTL_OMDB   = 60 * 60 * 24   # 24h — movie metadata rarely changes
CACHE_TTL_TMDB   = 60 * 60 * 12   # 12h
CACHE_TTL_SEARCH = 60 * 30        # 30 min — search result lists

log.info("✅ Config loaded. Admin owner ID: %s | Webhook: %s", ADMIN_ID, WEBHOOK_URL)
