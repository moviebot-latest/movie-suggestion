# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                    🎬  CineBot v11 — SINGLE FILE                           ║
# ║                                                                              ║
# ║  ✅ Domain Healer v6  — Pattern Predictor + Multi-AI Consensus              ║
# ║  ✅ Lang v2           — Full admin/user language management                 ║
# ║  ✅ Server Health v7  — P95 + trend + proactive monitor                     ║
# ║  ✅ Full AI Analysis  — Review, Mood, Cast, Trivia, Package                 ║
# ║  ✅ Admin Panel v11   — Multi-admin, ban, broadcast, export                 ║
# ║                                                                              ║
# ║  APIs: BOT_TOKEN, OMDB_API, TMDB_API, GROQ_API, ADMIN_ID                  ║
# ╚══════════════════════════════════════════════════════════════════════════════╝


# ════════════════════════════════════════════════════════════════════
#  STANDARD IMPORTS
# ════════════════════════════════════════════════════════════════════
from __future__ import annotations

import asyncio
import calendar
import hashlib
import json
import logging
import os
import random
import re
import sqlite3
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta, timezone
from enum import IntEnum, auto
from typing import (
    Any, Callable, Deque, Dict, List, Optional,
    Set, Tuple
)
from urllib.parse import quote, urlparse

import aiohttp
import requests
from flask import Flask
from telegram import (
    Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
)
from telegram.ext import (
    Application, ApplicationBuilder, CallbackQueryHandler,
    CommandHandler, ContextTypes, ConversationHandler,
    MessageHandler, filters
)

try:
    from bs4 import BeautifulSoup
    _BS4_AVAILABLE = True
except ImportError:
    _BS4_AVAILABLE = False
    print("⚠️ beautifulsoup4 not installed — DDG fallback disabled.")

# ════════════════════════════════════════════════════════════════════
#  TIMEZONE — Indian Standard Time (UTC+5:30)
# ════════════════════════════════════════════════════════════════════
IST = timezone(timedelta(hours=5, minutes=30))

def now_ist() -> datetime:
    return datetime.now(IST)

def today_ist() -> date:
    return now_ist().date()

# ════════════════════════════════════════════════════════════════════
#  LOGGING
# ════════════════════════════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
log = logging.getLogger("cinebot_v11")

# ════════════════════════════════════════════════════════════════════
#  ENV VARIABLES
# ════════════════════════════════════════════════════════════════════
TOKEN        = os.getenv("BOT_TOKEN")
OMDB_API     = os.getenv("OMDB_API")
TMDB_API     = os.getenv("TMDB_API",   "")
GROQ_API     = os.getenv("GROQ_API",   "")
ADMIN_ID     = int(os.getenv("ADMIN_ID", "0"))
if ADMIN_ID == 0:
    log.warning("⚠️ ADMIN_ID not set — admin features disabled")

TMDB_API_KEY = TMDB_API
OMDB_API_KEY = OMDB_API

GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"
GEMINI_API    = os.getenv("GEMINI_API",    "")
TAVILY_API    = os.getenv("TAVILY_API",    "")
ANTHROPIC_API = os.getenv("ANTHROPIC_API","")

GEMINI_URL  = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
TAVILY_URL  = "https://api.tavily.com/search"
CLAUDE_URL  = "https://api.anthropic.com/v1/messages"

if GEMINI_API:
    log.info("✅ Gemini Flash 1.5 API loaded")
if TAVILY_API:
    log.info("✅ Tavily Search API loaded")
if ANTHROPIC_API:
    log.info("✅ Anthropic Claude Haiku API loaded")


if not TOKEN:
    raise ValueError("❌ BOT_TOKEN environment variable is not set!")
if not OMDB_API:
    raise ValueError("❌ OMDB_API environment variable is not set!")

if GROQ_API:
    log.info("✅ Groq API (llama-3.3-70b-versatile) loaded")
else:
    log.warning("⚠️ GROQ_API not set — AI features disabled")

# ════════════════════════════════════════════════════════════════════
#  WEB SERVER (KEEP ALIVE)
# ════════════════════════════════════════════════════════════════════
web_app = Flask(__name__)

@web_app.route("/")
def home():
    return "🎬 CineBot v11 Running"

@web_app.route("/health")
def health():
    return {"status": "ok", "version": "11.0", "ai": "groq", "healer": "v4"}

def run_web():
    import logging as _log
    _log.getLogger("werkzeug").setLevel(_log.ERROR)
    web_app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
        use_reloader=False,
        threaded=True,
    )

threading.Thread(target=run_web, daemon=True).start()

# ════════════════════════════════════════════════════════════════════
#  KEEP ALIVE — Render free plan 502 fix
# ════════════════════════════════════════════════════════════════════
def keep_alive_ping():
    RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
    if not RENDER_URL:
        log.warning("⚠️ RENDER_EXTERNAL_URL not set — keep-alive disabled")
        return
    log.info("✅ Keep-alive started → %s/health (every 10 min)", RENDER_URL)
    while True:
        time.sleep(600)
        try:
            r = requests.get(f"{RENDER_URL}/health", timeout=10)
            log.debug("💓 Keep-alive ping → %s", r.status_code)
        except Exception as e:
            log.warning("⚠️ Keep-alive failed: %s", e)

threading.Thread(target=keep_alive_ping, daemon=True).start()


# ════════════════════════════════════════════════════════════════════
#  SERVER HEALTH CHECKER — v7 ULTRA REAL DATA
# ════════════════════════════════════════════════════════════════════
SRV_CHECK_INTERVAL_HOURS  = 12
SRV_DOWN_INTERVAL_MIN     = 30
SRV_DEGRADED_INTERVAL_HRS = 2
SRV_RETRY_COUNT           = 5
SRV_RETRY_DELAY           = 2
SRV_CONNECT_TIMEOUT       = 8
SRV_READ_TIMEOUT          = 12
SRV_STATUS_FILE           = "server_status.json"
SRV_HISTORY_MAX           = 50
SRV_ALERT_COOLDOWN_HRS    = 3
SRV_DEGRADED_MS           = 3000
SRV_RECOVERY_ALERT        = True
_srv_file_lock            = threading.Lock()
_srv_alerted_at: Dict[str, float] = {}

SRV_UP_CODES   = {200, 206, 301, 302, 303, 307, 308, 400, 401, 403, 404, 405, 429}
SRV_DOWN_CODES = {500, 502, 503, 504, 520, 521, 522, 523, 524}

_DNS_ERROR_PATTERNS = (
    "name or service not known",
    "nodename nor servname provided",
    "getaddrinfo failed",
    "temporary failure in name resolution",
    "name resolution failure",
    "no address associated",
    "non-recoverable failure in name res",
)

SRV_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile Safari/604.1",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

def _get_srv_headers() -> dict:
    return {
        "User-Agent":                random.choice(SRV_USER_AGENTS),
        "Accept":                    "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language":           "en-US,en;q=0.9",
        "Accept-Encoding":           "gzip, deflate",
        "Connection":                "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control":             "no-cache",
    }

def srv_load_status() -> dict:
    with _srv_file_lock:
        if os.path.exists(SRV_STATUS_FILE):
            try:
                with open(SRV_STATUS_FILE) as f:
                    return json.load(f)
            except Exception:
                pass
    return {}

def srv_save_status(data: dict):
    with _srv_file_lock:
        with open(SRV_STATUS_FILE, "w") as f:
            json.dump(data, f, indent=2)

def _srv_speed_rating(ms: int, up: bool) -> str:
    if not up:       return "💀 DOWN"
    if ms <= 0:      return "❓ UNKNOWN"
    if ms < 700:     return "⚡ FAST"
    if ms < 1800:    return "✅ NORMAL"
    if ms < SRV_DEGRADED_MS: return "🐢 SLOW"
    return "🔴 DEGRADED"

def _srv_uptime_pct(history: list) -> str:
    if not history: return "N/A"
    up_count = sum(1 for h in history if h.get("up"))
    pct = int((up_count / len(history)) * 100)
    emoji = "🟢" if pct >= 95 else ("🟡" if pct >= 75 else "🔴")
    return f"{emoji} {pct}%"

def _srv_consec_fails(history: list) -> int:
    count = 0
    for h in history:
        if not h.get("up"): count += 1
        else: break
    return count

def _srv_avg_ms(history: list) -> int:
    ms_list = [h.get("ms", 0) for h in history if h.get("up") and h.get("ms", 0) > 0]
    return int(sum(ms_list) / len(ms_list)) if ms_list else 0

def _srv_p95_ms(history: list) -> int:
    ms_list = sorted([h.get("ms", 0) for h in history if h.get("up") and h.get("ms", 0) > 0])
    if not ms_list: return 0
    idx = max(0, int(len(ms_list) * 0.95) - 1)
    return ms_list[idx]

def _srv_min_ms(history: list) -> int:
    ms_list = [h.get("ms", 0) for h in history if h.get("up") and h.get("ms", 0) > 0]
    return min(ms_list) if ms_list else 0

def _srv_max_ms(history: list) -> int:
    ms_list = [h.get("ms", 0) for h in history if h.get("up") and h.get("ms", 0) > 0]
    return max(ms_list) if ms_list else 0

def _srv_last_down(history: list) -> str:
    for h in history:
        if not h.get("up"):
            return h.get("checked", "N/A")
    return "Never ✅"

def _srv_trend(history: list) -> str:
    ms_list = [h.get("ms", 0) for h in history if h.get("up") and h.get("ms", 0) > 0]
    if len(ms_list) < 4: return "📊 N/A"
    recent = sum(ms_list[:3]) / 3
    older  = sum(ms_list[-3:]) / 3
    if older == 0: return "📊 N/A"
    diff = ((recent - older) / older) * 100
    if diff < -15: return "📈 Improving"
    if diff > 15:  return "📉 Degrading"
    return "➡️ Stable"

def _srv_is_degraded(r: dict) -> bool:
    return r.get("up", False) and r.get("avg_ms", 0) > SRV_DEGRADED_MS

async def _srv_check_once_v6(session: aiohttp.ClientSession, url: str) -> tuple:
    import urllib.parse as _urlparse
    t0 = time.monotonic()
    orig_domain = _urlparse.urlparse(url).netloc.lower().lstrip("www.")
    timeout = aiohttp.ClientTimeout(
        sock_connect=SRV_CONNECT_TIMEOUT,
        sock_read=SRV_READ_TIMEOUT,
        total=SRV_CONNECT_TIMEOUT + SRV_READ_TIMEOUT + 2,
    )
    try:
        async with session.get(
            url, headers=_get_srv_headers(), timeout=timeout,
            allow_redirects=True, max_redirects=8,
        ) as resp:
            ms   = int((time.monotonic() - t0) * 1000)
            code = resp.status
            final_url = str(resp.url)
            body = b""
            try:
                body = await resp.content.read(2048)
            except Exception:
                pass
            final_domain = _urlparse.urlparse(final_url).netloc.lower().lstrip("www.")
            domain_hijacked = (
                final_domain and orig_domain and
                final_domain != orig_domain and
                not final_domain.endswith("." + orig_domain) and
                not orig_domain.endswith("." + final_domain)
            )
            if domain_hijacked:
                return False, code, ms, final_url, f"Domain changed→{final_domain[:30]}", ""
            if code in SRV_UP_CODES:
                extra = "⚠️ Empty body" if code == 200 and len(body) < 50 else ""
                return True, code, ms, final_url, "", extra
            return False, code, ms, final_url, f"HTTP {code}", ""

    except asyncio.TimeoutError:
        ms = int((time.monotonic() - t0) * 1000)
        phase = "Connect timeout" if ms < SRV_CONNECT_TIMEOUT * 1000 + 500 else "Read timeout"
        return False, 0, ms, "", phase, ""
    except aiohttp.ClientConnectorDNSError:
        ms = int((time.monotonic() - t0) * 1000)
        return False, 0, ms, "", "DNS failed", ""
    except aiohttp.ClientConnectorError as e:
        ms  = int((time.monotonic() - t0) * 1000)
        msg = str(e).lower()
        if any(p in msg for p in _DNS_ERROR_PATTERNS): err = "DNS failed"
        elif "ssl" in msg or "certificate" in msg:     err = "SSL error"
        elif "connection refused" in msg:              err = "Connection refused"
        else:                                          err = f"Connect error: {str(e)[:40]}"
        return False, 0, ms, "", err, ""
    except aiohttp.ServerDisconnectedError:
        ms = int((time.monotonic() - t0) * 1000)
        return False, 0, ms, "", "Server disconnected", ""
    except aiohttp.ClientOSError as e:
        ms = int((time.monotonic() - t0) * 1000)
        return False, 0, ms, "", f"OS error: {str(e)[:40]}", ""
    except aiohttp.ClientPayloadError:
        ms = int((time.monotonic() - t0) * 1000)
        return True, 200, ms, url, "", "⚠️ Payload error"
    except aiohttp.TooManyRedirects:
        ms = int((time.monotonic() - t0) * 1000)
        return False, 0, ms, "", "Redirect loop (8+)", ""
    except aiohttp.InvalidURL:
        ms = int((time.monotonic() - t0) * 1000)
        return False, 0, ms, "", "Invalid URL", ""
    except Exception as e:
        ms = int((time.monotonic() - t0) * 1000)
        err_str = str(e).lower()
        if "brotli" in err_str or "decompress" in err_str or "zlib" in err_str:
            return True, 200, ms, url, "", "⚠️ Decompress warn"
        return False, 0, ms, "", str(e)[:50], ""

async def srv_check_single(key: str, name: str, url: str,
                           session: Optional[aiohttp.ClientSession] = None) -> dict:
    ts = now_ist().strftime("%Y-%m-%d %H:%M")
    if not url:
        return {"key": key, "name": name, "url": url, "up": False, "code": 0,
                "method": "GET", "response_ms": 0, "attempts": 0,
                "error": "No URL configured", "extra": "", "checked": ts}
    check_url = url.split("?")[0].rstrip("/")
    if not check_url.startswith("http"):
        check_url = "https://" + check_url

    async def _do_check(sess):
        code, ms, final_url, err, extra = 0, 0, "", "", ""
        for attempt in range(1, SRV_RETRY_COUNT + 1):
            is_up, code, ms, final_url, err, extra = await _srv_check_once_v6(sess, check_url)
            if is_up:
                return {"key": key, "name": name, "url": url, "up": True, "code": code,
                        "method": "GET", "response_ms": ms, "attempts": attempt,
                        "final_url": final_url, "error": "", "extra": extra, "checked": ts}
            if attempt < SRV_RETRY_COUNT:
                await asyncio.sleep(SRV_RETRY_DELAY)
        return {"key": key, "name": name, "url": url, "up": False, "code": code,
                "method": "GET", "response_ms": ms, "attempts": SRV_RETRY_COUNT,
                "error": err, "extra": extra, "final_url": final_url, "checked": ts}

    if session:
        return await _do_check(session)
    else:
        connector = aiohttp.TCPConnector(ssl=False, limit=1, enable_cleanup_closed=True)
        async with aiohttp.ClientSession(connector=connector) as own_sess:
            return await _do_check(own_sess)

async def srv_check_all_parallel(servers: dict) -> dict:
    saved   = srv_load_status()
    results = {}
    connector = aiohttp.TCPConnector(
        ssl=False, limit=30, limit_per_host=3,
        enable_cleanup_closed=True, ttl_dns_cache=300, use_dns_cache=True,
    )
    try:
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = [
                srv_check_single(k, v.get("name", k), v.get("url", ""), session)
                for k, v in servers.items()
            ]
            results_list = await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as e:
        log.error("srv_check_all_parallel error: %s", e)
        results_list = []
    finally:
        if not connector.closed:
            await connector.close()

    all_failed = True
    for r in results_list:
        if isinstance(r, Exception):
            log.warning("Server check exception: %s", r)
            continue
        all_failed = False
        key = r["key"]
        prev_history = saved.get(key, {}).get("history", [])
        new_entry = {"up": r["up"], "checked": r["checked"], "ms": r.get("response_ms", 0)}
        r["history"]      = ([new_entry] + prev_history)[:SRV_HISTORY_MAX]
        r["uptime_pct"]   = _srv_uptime_pct(r["history"])
        r["consec_fails"] = _srv_consec_fails(r["history"])
        r["avg_ms"]       = _srv_avg_ms(r["history"])
        r["p95_ms"]       = _srv_p95_ms(r["history"])
        r["min_ms"]       = _srv_min_ms(r["history"])
        r["max_ms"]       = _srv_max_ms(r["history"])
        r["last_down"]    = _srv_last_down(r["history"])
        r["trend"]        = _srv_trend(r["history"])
        r["speed_rating"] = _srv_speed_rating(r.get("response_ms", 0), r["up"])
        r["degraded"]     = _srv_is_degraded(r)
        results[key] = r
        icon  = "✅" if r["up"] else "❌"
        deg   = " ⚠️DEGRADED" if r["degraded"] else ""
        extra = f" [{r.get('extra','')}]" if r.get("extra") else ""
        log.info("%s %s | %dms | %s%s%s | uptime=%s",
                 icon, r["name"], r.get("response_ms",0), r["speed_rating"], deg, extra, r["uptime_pct"])

    if all_failed and saved:
        log.warning("All checks failed — returning cached data")
        return {k: {**v, "_cached": True} for k, v in saved.items()}
    if results:
        srv_save_status(results)
    return results

async def srv_ai_diagnose(results: dict) -> Optional[str]:
    if not GROQ_API:
        return None
    down     = [r for r in results.values() if not r.get("up")]
    degraded = [r for r in results.values() if r.get("degraded")]
    up_ok    = [r for r in results.values() if r.get("up") and not r.get("degraded")]
    up_ms    = [r.get("response_ms", 0) for r in up_ok if r.get("response_ms", 0) > 0]
    avg_all  = int(sum(up_ms) / len(up_ms)) if up_ms else 0

    if not down and not degraded:
        up_info = "\n".join(
            f"- {r['name']} | {r.get('response_ms')}ms | Uptime: {r.get('uptime_pct')} | Trend: {r.get('trend')}"
            for r in up_ok
        )
        prompt = (
            f"You are a server health expert for a movie download bot.\n\n"
            f"ALL SERVERS UP ✅\n{up_info}\n\n"
            f"Give a 2-line health summary in Hinglish. "
            f"Mention which server is fastest and if any trend is concerning. "
            f"Be brief and positive but honest."
        )
        return await ai_ask(prompt, max_tokens=200)

    sections = []
    if down:
        down_info = "\n".join(
            f"- {r['name']} | Code: {r.get('code',0)} | Error: {r.get('error','?')} | "
            f"Consec fails: {r.get('consec_fails',0)} | Uptime: {r.get('uptime_pct')} | "
            f"Trend: {r.get('trend')} | URL: {r['url'][:50]}"
            for r in down
        )
        sections.append(f"❌ DOWN SERVERS ({len(down)}):\n{down_info}")
    if degraded:
        deg_info = "\n".join(
            f"- {r['name']} | Avg: {r.get('avg_ms')}ms | P95: {r.get('p95_ms')}ms | "
            f"Trend: {r.get('trend')} | Uptime: {r.get('uptime_pct')}"
            for r in degraded
        )
        sections.append(f"⚠️ DEGRADED SERVERS ({len(degraded)}):\n{deg_info}")
    if up_ok:
        best = min(up_ok, key=lambda x: x.get("avg_ms", 9999))
        sections.append(f"✅ BEST WORKING: {best['name']} | Avg: {best.get('avg_ms')}ms")

    full_info = "\n\n".join(sections)
    prompt = (
        f"You are an expert server analyst for a movie download Telegram bot.\n\n"
        f"{full_info}\n\n
