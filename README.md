# CineBot v12 — Deployment Guide

## ⚠️ Important: Render's free PostgreSQL is NOT suitable for this bot

Render's free PostgreSQL tier **deletes your database (and all its data) automatically 30 days after creation** — no grace period. That defeats the entire point of moving off local JSON files. Use **Neon.tech** instead for the database — it's free forever with no expiry, and works as a drop-in `DATABASE_URL`.

## Setup Steps (Render web service + Neon database)

1. **Database — Neon.tech (free, never expires):**
   - Sign up at neon.tech (no credit card needed), create a project.
   - Copy the connection string from the dashboard — looks like:
     `postgresql://user:password@ep-xxx.region.aws.neon.tech/dbname?sslmode=require`
   - This is your `DATABASE_URL`.
   - Note: Neon "scales to zero" after inactivity — the first query after idle time takes ~1-2s to wake up. The bot already retries on cold start (`bot/db/database.py`), so this is handled automatically.

2. **Cache — Render Key Value (free, 25MB):**
   - Create a Key Value instance on Render → copy its Internal URL → set as `REDIS_URL`.

3. **Web Service — Render (free):**
   - Connect this repo. Render auto-sets `RENDER_EXTERNAL_URL` and `PORT`.
   - Note: free web services sleep after 15 minutes of inactivity, with a 30-60s cold start on the next request. This means the bot may respond slowly (or Telegram may retry the webhook) after a quiet period — this is a Render free-tier limitation, not a bot bug. Render's paid Starter plan ($7/mo) keeps it always-on if that matters to you.

4. Set these environment variables in the Render dashboard:
   - `BOT_TOKEN` — from @BotFather
   - `OMDB_API` — your OMDB API key
   - `ADMIN_ID` — **your own numeric Telegram user ID** (get it from @userinfobot). Required — the bot won't start without it, instead of silently locking you out like the old version did.
   - `DATABASE_URL` — the Neon connection string from step 1
   - `REDIS_URL` — the Render Key Value URL from step 2
   - `TMDB_API` — optional, enables /upcoming, /castinfo, trailers
   - `GROQ_API` — optional, seeds the initial AI key (can be rotated later via `/setgroqkey`, no redeploy needed)
   - `WEBHOOK_SECRET_TOKEN` — optional, any random string
5. Deploy. On boot, the bot automatically creates all Postgres tables (`bot/db/database.py`'s `SCHEMA`) and registers its webhook with Telegram — no manual migration step needed.
6. Send `/start` to your bot on Telegram to confirm it's alive.

## New in this update

- **`/groqstatus`** — makes a live test call to Groq and tells you if the current AI key is active or expired/invalid (Groq's API doesn't expose an expiry date, so this checks by actually trying a request).
- **`/setgroqkey <new_key>`** — owner-only. Rotates the Groq API key immediately, stored in Postgres — **no redeploy needed**. The message containing the raw key is auto-deleted right after saving.
- **`/shutdown [reason]`** — admin-only. Instantly puts the bot into maintenance mode: all non-admin users get a maintenance message on every command; admins are unaffected.
- **`/recover`** — admin-only. Turns maintenance mode back off.
- Both `/shutdown`/`/recover` and Groq status/key are also available as buttons in `/admin`.

## What changed vs the old single-file bot

| Area | Old bot | This version |
|---|---|---|
| Storage | Local JSON files + SQLite on Render's ephemeral disk — **wiped every redeploy** | PostgreSQL (Neon, free forever) — persists across deploys/restarts |
| Caching | None — every search hit OMDB/TMDB live | Redis caching (24h for movie data, 30min for search lists) |
| Transport | Long-polling | Webhook (lower latency, lighter on Render's free tier) |
| Sharing | Bot chat only | + Inline mode (`@YourBot movie name` in any chat) |
| `ADMIN_ID` | Silently defaulted to `0` if unset → admin panel silently unusable | Required at startup; bot exits with a clear error if missing |
| Concurrency | `load_json()`/`save_json()` read-modify-write races; shared sqlite3 connection with no lock | Atomic SQL (`INSERT ... ON CONFLICT`) via asyncpg pool — safe under concurrent access |
| Error handling | 58 bare `except:` clauses swallowing all errors silently | Targeted exception handling + `@guarded()` decorator that logs and reports unhandled errors instead of crashing a handler silently |
| Groq 429 handling | Slept 5s then gave up without retrying | Actually retries once after backoff |
| `requirements.txt` | `python-telegram-bot` unpinned (risk of breaking upgrades) | All dependencies pinned to tested versions |
| Background jobs | `threading.Thread` health-checker running alongside the asyncio bot loop, sharing an unlocked DB connection | Native `asyncio` background task in the same event loop — no cross-thread DB access |
| Structure | One 6226-line `main.py` | Modular package (`bot/config`, `bot/db`, `bot/services`, `bot/handlers`, `bot/utils`) |

## Project layout

```
main.py                    entrypoint — builds the app, starts the webhook server
bot/
  config.py                 env var loading + validation
  db/
    database.py              asyncpg pool + schema migrations
    repository.py            every DB query, in one place
  services/
    cache.py                  Redis wrapper
    omdb.py, tmdb.py          external API clients (cached, async)
    groq_ai.py                AI features (review, suggest, mood, plot search)
    background.py             periodic reminder sweep
  handlers/                   one file per feature area (search, admin, upcoming, ...)
  utils/
    decorators.py              @guarded() — ban/maintenance/admin checks + error catching
    keyboards.py, formatting.py
```

## Local testing

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in real values
export $(cat .env | xargs)
python main.py
```

Note: webhook mode needs a publicly reachable HTTPS URL. For local testing without deploying,
you can temporarily use a tunnel tool (e.g. ngrok) and set `WEBHOOK_URL` to the tunnel's HTTPS URL.
