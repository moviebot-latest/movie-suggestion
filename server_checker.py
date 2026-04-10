# ╔══════════════════════════════════════════╗
# ║  server_checker.py — /checkservers       ║
# ║  Edit to change server health logic      ║
# ╚══════════════════════════════════════════╝
import asyncio, aiohttp, time, random, threading, json, os
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import now_ist, today_ist, GROQ_API, ADMIN_ID
from storage import load_servers, is_admin
from ai_engine import ai_ask

# ═══════════════════════════════════════════════════════════════════
SRV_CHECK_INTERVAL_HOURS  = 12
SRV_DOWN_INTERVAL_MIN     = 30
SRV_DEGRADED_INTERVAL_HRS = 2
SRV_RETRY_COUNT           = 3        # ✅ v6 FIX: 3 attempts (was 2)
SRV_RETRY_DELAY           = 3        # ✅ v6 FIX: 3s (was 4)
SRV_CONNECT_TIMEOUT       = 8        # ✅ v6 FIX: DNS+connect timeout alag
SRV_READ_TIMEOUT          = 12       # ✅ v6 FIX: read timeout alag
SRV_STATUS_FILE           = "server_status.json"
SRV_HISTORY_MAX           = 20
SRV_ALERT_COOLDOWN_HRS    = 3
SRV_DEGRADED_MS           = 3000
_srv_file_lock            = threading.Lock()
_srv_alerted_at           = {}

# ✅ v6 FIX: Accurate UP/DOWN — 200-4xx = server hai (UP), 5xx = server broken (DOWN)
# 403/429 = blocking us but server IS alive
# 500/502/503/504 = server broken/down
SRV_UP_CODES   = {200, 206, 301, 302, 303, 307, 308, 400, 401, 403, 404, 405, 429}
SRV_DOWN_CODES = {500, 502, 503, 504, 520, 521, 522, 523, 524}

# ✅ v6 FIX: DNS error patterns — Linux + Windows + macOS sab cover
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
        "Accept":                    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language":           "en-US,en;q=0.9",
        "Accept-Encoding":           "gzip, deflate",   # brotli nahi — aiohttp pe decompress fail hota hai
        "Connection":                "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest":            "document",
        "Sec-Fetch-Mode":            "navigate",
        "Sec-Fetch-Site":            "none",
        "Cache-Control":             "no-cache",
        "Pragma":                    "no-cache",
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

# ✅ v5: Speed + state rating
def _srv_speed_rating(ms: int, up: bool) -> str:
    if not up:         return "💀 DOWN"
    if ms <= 0:        return "❓ UNKNOWN"
    if ms < 700:       return "⚡ FAST"
    if ms < 1800:      return "✅ NORMAL"
    if ms < SRV_DEGRADED_MS: return "🐢 SLOW"
    return "🔴 DEGRADED"

def _srv_uptime_pct(history: list) -> str:
    if not history:    return "N/A"
    up_count = sum(1 for h in history if h.get("up"))
    pct = int((up_count / len(history)) * 100)
    emoji = "🟢" if pct >= 95 else ("🟡" if pct >= 75 else "🔴")
    return f"{emoji} {pct}%"

def _srv_consec_fails(history: list) -> int:
    count = 0
    for h in history:
        if not h.get("up"):
            count += 1
        else:
            break
    return count

def _srv_avg_ms(history: list) -> int:
    ms_list = [h.get("ms", 0) for h in history if h.get("up") and h.get("ms", 0) > 0]
    return int(sum(ms_list) / len(ms_list)) if ms_list else 0

# ✅ v5: P95 response time
def _srv_p95_ms(history: list) -> int:
    ms_list = sorted([h.get("ms", 0) for h in history if h.get("up") and h.get("ms", 0) > 0])
    if not ms_list:    return 0
    idx = max(0, int(len(ms_list) * 0.95) - 1)
    return ms_list[idx]

# ✅ v5: Trend detect — improving/degrading/stable
def _srv_trend(history: list) -> str:
    ms_list = [h.get("ms", 0) for h in history if h.get("up") and h.get("ms", 0) > 0]
    if len(ms_list) < 4:    return "📊 N/A"
    recent = sum(ms_list[:3]) / 3
    older  = sum(ms_list[-3:]) / 3
    if older == 0:          return "📊 N/A"
    diff   = ((recent - older) / older) * 100
    if diff < -15:          return "📈 Improving"
    if diff > 15:           return "📉 Degrading"
    return "➡️ Stable"

# ✅ v5: Is server degraded (UP but very slow)?
def _srv_is_degraded(r: dict) -> bool:
    return r.get("up", False) and r.get("avg_ms", 0) > SRV_DEGRADED_MS

async def _srv_check_once_v6(session: aiohttp.ClientSession, url: str) -> tuple:
    """
    v6 ULTIMATE FIX:
    ✅ Accurate UP/DOWN: 2xx/3xx/4xx = UP (server hai), 5xx = DOWN (server broken)
    ✅ Separate connect+read timeout (DNS hang fix)
    ✅ Domain hijack detect (redirect ne domain badla = DOWN)
    ✅ Content validation (200 but empty body = suspicious)
    ✅ All aiohttp exceptions caught properly
    Returns (is_up, code, ms, final_url, error_msg, extra_info)
    """
    import urllib.parse as _urlparse
    t0          = time.monotonic()
    orig_domain = _urlparse.urlparse(url).netloc.lower().lstrip("www.")
    timeout     = aiohttp.ClientTimeout(
        sock_connect=SRV_CONNECT_TIMEOUT,  # DNS + TCP handshake timeout
        sock_read=SRV_READ_TIMEOUT,        # actual data read timeout
        total=SRV_CONNECT_TIMEOUT + SRV_READ_TIMEOUT + 2,
    )
    try:
        async with session.get(
            url,
            headers=_get_srv_headers(),
            timeout=timeout,
            allow_redirects=True,
            max_redirects=8,
        ) as resp:
            ms        = int((time.monotonic() - t0) * 1000)
            code      = resp.status
            final_url = str(resp.url)

            # ✅ Read partial body — ensures connection is real, not just headers
            body = b""
            try:
                body = await resp.content.read(2048)
            except (aiohttp.ClientPayloadError, aiohttp.ServerDisconnectedError,
                    asyncio.TimeoutError, Exception):
                pass

            # ✅ Domain hijack check — redirect ne domain badal diya?
            final_domain = _urlparse.urlparse(final_url).netloc.lower().lstrip("www.")
            domain_hijacked = (
                final_domain and orig_domain and
                final_domain != orig_domain and
                not final_domain.endswith("." + orig_domain) and
                not orig_domain.endswith("." + final_domain)
            )
            if domain_hijacked:
                return False, code, ms, final_url, f"Domain changed→{final_domain[:30]}", ""

            # ✅ Accurate status logic
            if code in SRV_UP_CODES:
                # Extra check: 200 with completely empty body = suspicious
                extra = ""
                if code == 200 and len(body) < 50:
                    extra = "⚠️ Empty body"
                return True, code, ms, final_url, "", extra

            # 5xx and other bad codes = DOWN
            return False, code, ms, final_url, f"HTTP {code}", ""

    except asyncio.TimeoutError:
        ms = int((time.monotonic() - t0) * 1000)
        phase = "Connect timeout" if ms < SRV_CONNECT_TIMEOUT * 1000 + 500 else "Read timeout"
        return False, 0, ms, "", phase, ""

    except aiohttp.ClientConnectorDNSError as e:
        ms = int((time.monotonic() - t0) * 1000)
        return False, 0, ms, "", "DNS failed", ""

    except aiohttp.ClientConnectorError as e:
        ms  = int((time.monotonic() - t0) * 1000)
        msg = str(e).lower()
        if any(p in msg for p in _DNS_ERROR_PATTERNS):
            err = "DNS failed"
        elif "ssl" in msg or "certificate" in msg:
            err = "SSL error"
        elif "connection refused" in msg:
            err = "Connection refused"
        else:
            err = f"Connect error: {str(e)[:40]}"
        return False, 0, ms, "", err, ""

    except aiohttp.ServerDisconnectedError:
        ms = int((time.monotonic() - t0) * 1000)
        return False, 0, ms, "", "Server disconnected", ""

    except aiohttp.ClientOSError as e:
        ms = int((time.monotonic() - t0) * 1000)
        return False, 0, ms, "", f"OS error: {str(e)[:40]}", ""

    except aiohttp.ClientPayloadError as e:
        # ✅ Payload errors = server IS responding, just garbled content → treat as UP
        ms = int((time.monotonic() - t0) * 1000)
        return True, 200, ms, url, "", "⚠️ Payload error"

    except aiohttp.TooManyRedirects:
        ms = int((time.monotonic() - t0) * 1000)
        return False, 0, ms, "", "Redirect loop (8+)", ""

    except aiohttp.InvalidURL:
        ms = int((time.monotonic() - t0) * 1000)
        return False, 0, ms, "", "Invalid URL", ""

    except Exception as e:
        ms      = int((time.monotonic() - t0) * 1000)
        err_str = str(e).lower()
        # Brotli/decompression = server UP, encoding issue only
        if "brotli" in err_str or "decompress" in err_str or "zlib" in err_str:
            return True, 200, ms, url, "", "⚠️ Decompress warn"
        return False, 0, ms, "", str(e)[:50], ""

async def srv_check_single(key: str, name: str, url: str,
                           session: Optional[aiohttp.ClientSession] = None) -> dict:
    """✅ v6: Accepts shared session OR creates its own (fallback)."""
    ts = now_ist().strftime("%Y-%m-%d %H:%M")
    if not url:
        return {
            "key": key, "name": name, "url": url,
            "up": False, "code": 0, "method": "GET",
            "response_ms": 0, "attempts": 0,
            "error": "No URL configured", "extra": "", "checked": ts,
        }
    check_url = url.split("?")[0].rstrip("/")
    if not check_url.startswith("http"):
        check_url = "https://" + check_url

    # ✅ v6: Use shared session if provided, else create own
    async def _do_check(sess):
        code, ms, final_url, err, extra = 0, 0, "", "", ""
        for attempt in range(1, SRV_RETRY_COUNT + 1):
            is_up, code, ms, final_url, err, extra = await _srv_check_once_v6(sess, check_url)
            if is_up:
                return {
                    "key": key, "name": name, "url": url,
                    "up": True, "code": code, "method": "GET",
                    "response_ms": ms, "attempts": attempt,
                    "final_url": final_url, "error": "", "extra": extra, "checked": ts,
                }
            if attempt < SRV_RETRY_COUNT:
                await asyncio.sleep(SRV_RETRY_DELAY)
        return {
            "key": key, "name": name, "url": url,
            "up": False, "code": code, "method": "GET",
            "response_ms": ms, "attempts": SRV_RETRY_COUNT,
            "error": err, "extra": extra, "final_url": final_url, "checked": ts,
        }

    if session:
        return await _do_check(session)
    else:
        # Fallback: own session (should not happen in normal flow)
        connector = aiohttp.TCPConnector(ssl=False, limit=1, enable_cleanup_closed=True)
        async with aiohttp.ClientSession(connector=connector) as own_sess:
            return await _do_check(own_sess)

async def srv_check_all_parallel(servers: dict) -> dict:
    """
    ✅ v6: One shared aiohttp session for ALL checks (faster, no connection pool waste).
    ✅ All exceptions caught — empty results pe graceful fallback.
    ✅ ssl=False + dns_cache=True for reliable checks.
    """
    saved   = srv_load_status()
    results = {}

    # ✅ v6: One connector + session shared across all parallel checks
    connector = aiohttp.TCPConnector(
        ssl=False,
        limit=30,                    # up to 30 concurrent connections
        limit_per_host=3,            # max 3 per host (retry friendly)
        enable_cleanup_closed=True,
        ttl_dns_cache=300,           # DNS cache 5 min — avoids repeat lookups
        use_dns_cache=True,
    )
    try:
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = [
                srv_check_single(k, v.get("name", k), v.get("url", ""), session)
                for k, v in servers.items()
            ]
            results_list = await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as e:
        print(f"⚠️ srv_check_all_parallel session error: {e}")
        results_list = []
    finally:
        if not connector.closed:
            await connector.close()

    # ✅ v6: Process results + handle exceptions gracefully
    all_failed = True
    for r in results_list:
        if isinstance(r, Exception):
            print(f"⚠️ Server check exception: {r}")
            continue
        all_failed = False
        key          = r["key"]
        prev_history = saved.get(key, {}).get("history", [])
        new_entry    = {"up": r["up"], "checked": r["checked"], "ms": r.get("response_ms", 0)}
        r["history"] = ([new_entry] + prev_history)[:SRV_HISTORY_MAX]
        r["uptime_pct"]   = _srv_uptime_pct(r["history"])
        r["consec_fails"] = _srv_consec_fails(r["history"])
        r["avg_ms"]       = _srv_avg_ms(r["history"])
        r["p95_ms"]       = _srv_p95_ms(r["history"])
        r["trend"]        = _srv_trend(r["history"])
        r["speed_rating"] = _srv_speed_rating(r.get("response_ms", 0), r["up"])
        r["degraded"]     = _srv_is_degraded(r)
        results[key] = r
        icon  = "✅" if r["up"] else "❌"
        deg   = " ⚠️DEGRADED" if r["degraded"] else ""
        extra = f" [{r.get('extra','')}]" if r.get("extra") else ""
        print(f"{icon} {r['name']} | {r.get('response_ms')}ms | {r['speed_rating']}{deg}{extra} | uptime={r['uptime_pct']}")

    # ✅ v6: If ALL tasks failed (network issue at host level), return saved data with warning
    if all_failed and saved:
        print("⚠️ All checks failed — returning cached data")
        return {k: {**v, "_cached": True} for k, v in saved.items()}

    if results:
        srv_save_status(results)
    return results

async def srv_ai_diagnose(results: dict) -> Optional[str]:
    """v5: Deep AI analysis — DOWN + DEGRADED + trend + suggestions."""
    if not GROQ_API:
        return None

    down     = [r for r in results.values() if not r.get("up")]
    degraded = [r for r in results.values() if r.get("degraded")]
    up_ok    = [r for r in results.values() if r.get("up") and not r.get("degraded")]
    up_ms    = [r.get("response_ms", 0) for r in up_ok if r.get("response_ms", 0) > 0]
    avg_all  = int(sum(up_ms) / len(up_ms)) if up_ms else 0

    # All UP aur no degraded — brief health summary
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

    # Build detailed problem info
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
        sections.append(f"⚠️ DEGRADED SERVERS (slow but up) ({len(degraded)}):\n{deg_info}")

    if up_ok:
        best = min(up_ok, key=lambda x: x.get("avg_ms", 9999))
        sections.append(f"✅ BEST WORKING: {best['name']} | Avg: {best.get('avg_ms')}ms")

    full_info = "\n\n".join(sections)

    prompt = (
        f"You are an expert server analyst for a movie download Telegram bot.\n\n"
        f"{full_info}\n\n"
        f"Overall avg response (working servers): {avg_all}ms\n\n"
        f"Provide analysis in Hinglish (mix Hindi+English) with:\n\n"
        f"For each DOWN server:\n"
        f"🔴 [Name] — Severity: X/10\n"
        f"   ⚠️ Reason: (specific reason based on error code/DNS/timeout)\n"
        f"   🔧 Fix: (concrete action admin le sakta hai)\n"
        f"   🔄 Alternative: (suggest karo kon sa working server use kare)\n\n"
        f"For each DEGRADED server:\n"
        f"🟡 [Name]\n"
        f"   ⚠️ Issue: (slow kyun ho sakta hai)\n"
        f"   💡 Action: (kya karna chahiye)\n\n"
        f"End with:\n"
        f"📊 OVERALL: one line summary with urgency level (LOW/MEDIUM/HIGH/CRITICAL)"
    )
    return await ai_ask(prompt, max_tokens=800)

def _srv_history_bar(history: list) -> str:
    icons = ["🟩" if h.get("up") else "🟥" for h in history[:10]]
    icons += ["⬜"] * (10 - len(icons))
    return "".join(icons)

def srv_format_status(results: dict, title: str = "🖥️ SERVER STATUS") -> str:
    now      = now_ist().strftime("%d %b %Y, %I:%M %p IST")
    up_cnt   = sum(1 for r in results.values() if r.get("up"))
    deg_cnt  = sum(1 for r in results.values() if r.get("degraded"))
    total    = len(results)
    cached   = any(r.get("_cached") for r in results.values())

    if up_cnt == total and deg_cnt == 0:
        health = "🟢 ALL OK"
    elif up_cnt == 0:
        health = "🔴 ALL DOWN"
    elif deg_cnt > 0:
        health = f"🟡 {up_cnt}/{total} UP  ⚠️{deg_cnt} DEGRADED"
    else:
        health = f"🟡 {up_cnt}/{total} UP"

    lines = [
        f"*{title}*",
        f"📅 {now}  |  📊 {health}",
    ]
    if cached:
        lines.append("⚠️ _Cached data — live check failed (network issue)_")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━")

    for key, r in sorted(results.items()):
        name   = r.get("name", key)
        up     = r.get("up", False)
        code   = r.get("code", 0)
        ms     = r.get("response_ms", 0)
        bar    = _srv_history_bar(r.get("history", []))
        uptime = r.get("uptime_pct", "N/A")
        speed  = r.get("speed_rating", "")
        avg_ms = r.get("avg_ms", 0)
        p95    = r.get("p95_ms", 0)
        trend  = r.get("trend", "")
        deg    = r.get("degraded", False)
        extra  = r.get("extra", "")
        extra_str = f"  `{extra}`" if extra else ""

        if up and not deg:
            lines.append(f"\n✅ *{name}*  {speed} `{ms}ms`{extra_str}")
            lines.append(f"   Code `{code}` | Avg `{avg_ms}ms` | P95 `{p95}ms`")
            lines.append(f"   Uptime: {uptime} | {trend}")
            lines.append(f"   History: {bar}")
        elif up and deg:
            lines.append(f"\n⚠️ *{name}* — DEGRADED (very slow){extra_str}")
            lines.append(f"   `{ms}ms` now | Avg `{avg_ms}ms` | P95 `{p95}ms`")
            lines.append(f"   Uptime: {uptime} | {trend}")
            lines.append(f"   History: {bar}")
        else:
            fails = r.get("consec_fails", 0)
            err   = r.get("error", "")
            lines.append(f"\n❌ *{name}* — DOWN!")
            lines.append(f"   Code `{code}` | `{err}` | {fails} consec ❌")
            lines.append(f"   Uptime: {uptime} | History: {bar}")
    lines.append("\n━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"🔄 Auto-recheck: ALL OK=12hr | SLOW=2hr | DOWN=30min")
    return "\n".join(lines)

def srv_format_stats(results: dict) -> str:
    now   = now_ist().strftime("%d %b %Y, %I:%M %p IST")
    lines = [
        "📊 *SERVER DEEP STATS — v6*",
        f"📅 {now} | Last {SRV_HISTORY_MAX} checks",
        "━━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]
    for key, r in sorted(results.items()):
        name   = r.get("name", key)
        uptime = r.get("uptime_pct", "N/A")
        avg_ms = r.get("avg_ms", 0)
        p95    = r.get("p95_ms", 0)
        trend  = r.get("trend", "N/A")
        fails  = r.get("consec_fails", 0)
        speed  = r.get("speed_rating", "—")
        up     = r.get("up", False)
        deg    = r.get("degraded", False)
        if up and not deg:
            status = "✅ UP"
        elif deg:
            status = "⚠️ DEGRADED"
        else:
            status = f"❌ DOWN ({fails} consec)"
        lines.append(f"*{name}*")
        lines.append(f"   {status}  |  Uptime: {uptime}")
        lines.append(f"   Avg: `{avg_ms}ms` | P95: `{p95}ms` | {speed}")
        lines.append(f"   Trend: {trend}")
        lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("_P95 = 95% requests is speed se fast the_")
    return "\n".join(lines)

def srv_format_alert(down_keys: list, results: dict, degraded_keys: list = None) -> str:
    now   = now_ist().strftime("%d %b %Y, %I:%M %p IST")
    count = len(down_keys)
    lines = [
        f"🚨 *SERVER ALERT* 🚨",
        f"⏰ {now}\n",
    ]
    for key in down_keys:
        r      = results.get(key, {})
        fails  = r.get("consec_fails", 0)
        uptime = r.get("uptime_pct", "N/A")
        err    = r.get("error", "")
        lines += [
            f"❌ *{r.get('name', key)}* — DOWN",
            f"   Error: `{err}` | Code `{r.get('code',0)}`",
            f"   {fails} consec fails | Uptime: {uptime}",
            f"   History: {_srv_history_bar(r.get('history',[]))}",
            "",
        ]
    if degraded_keys:
        for key in degraded_keys:
            r = results.get(key, {})
            lines += [
                f"⚠️ *{r.get('name', key)}* — DEGRADED",
                f"   Avg: `{r.get('avg_ms')}ms` | P95: `{r.get('p95_ms')}ms`",
                f"   Trend: {r.get('trend')}",
                "",
            ]
    lines += [
        "━━━━━━━━━━━━━━━━━━",
        "👉 `/admin` → Servers → Edit se fix karo",
        "👉 `/checkservers` — manual recheck",
        "📊 `/serverstats` — full deep stats",
    ]
    return "\n".join(lines)

# ── /checkservers & /checkserver command ──
async def checkservers_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text(
            "🔒 *Access Denied!*\n\nYeh command sirf admins ke liye hai.",
            parse_mode="Markdown",
        )
        return

    loading = await update.message.reply_text(
        "🔍 *Server Health Check v6 ULTIMATE*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "⚡ Parallel GET checks (1 shared session)\n"
        "🔄 Browser headers rotating\n"
        "🛡️ Separate connect+read timeout\n"
        "📊 P95 + trend + domain hijack detect\n"
        "🤖 Deep AI diagnosis ready\n\n"
        "_15-20 seconds mein complete..._",
        parse_mode="Markdown",
    )

    servers = load_servers()
    if not servers:
        await loading.edit_text("❌ Koi server configured nahi. `/admin` → Servers.")
        return

    results      = await srv_check_all_parallel(servers)
    down_keys    = [k for k, v in results.items() if not v.get("up")]
    degraded_keys = [k for k, v in results.items() if v.get("degraded")]

    if down_keys or degraded_keys:
        await loading.edit_text("🤖 *AI deep analysis kar raha hai...*", parse_mode="Markdown")

    ai_text = await srv_ai_diagnose(results)
    text    = srv_format_status(results, "🖥️ SERVER CHECK v6 ULTIMATE")
    if ai_text:
        text += f"\n\n🤖 *AI ANALYSIS:*\n{ai_text}"

    kb = [
        [InlineKeyboardButton("🔄 Refresh",      callback_data="srvchk_refresh"),
         InlineKeyboardButton("📊 Deep Stats",    callback_data="srvchk_stats")],
        [InlineKeyboardButton("⚙️ Edit Servers",  callback_data="adm_servers"),
         InlineKeyboardButton("🏠 Admin Panel",   callback_data="open_admin")],
    ]
    await loading.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

# ── Refresh button callback ──
async def srvchk_refresh_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("🔒 Sirf admins!", show_alert=True)
        return
    await query.answer("🔍 Re-checking...")
    await query.edit_message_text("🔄 *Refreshing...*", parse_mode="Markdown")
    servers      = load_servers()
    results      = await srv_check_all_parallel(servers)
    ai_text      = await srv_ai_diagnose(results)
    text         = srv_format_status(results, "🔄 SERVER REFRESH v6")
    if ai_text:
        text += f"\n\n🤖 *AI ANALYSIS:*\n{ai_text}"
    kb = [
        [InlineKeyboardButton("🔄 Refresh Again", callback_data="srvchk_refresh"),
         InlineKeyboardButton("📊 Deep Stats",    callback_data="srvchk_stats")],
        [InlineKeyboardButton("⚙️ Edit Servers",  callback_data="adm_servers"),
         InlineKeyboardButton("🏠 Admin Panel",   callback_data="open_admin")],
    ]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

# ── Stats button callback ──
async def srvchk_stats_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("🔒 Sirf admins!", show_alert=True)
        return
    await query.answer("📊 Loading deep stats...")
    saved = srv_load_status()
    text  = srv_format_stats(saved) if saved else "📊 *No stats yet.*\n\nPehle `/checkservers` run karo."
    kb = [
        [InlineKeyboardButton("🔄 Check Now", callback_data="srvchk_refresh")],
        [InlineKeyboardButton("🔙 Back",      callback_data="adm_back")],
    ]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

# ── /serverstats command ──
async def serverstats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("🔒 Sirf admins ke liye!", parse_mode="Markdown")
        return
    saved = srv_load_status()
    if not saved:
        await update.message.reply_text(
            "📊 *Koi stats nahi abhi.*\n\nPehle `/checkservers` run karo.",
            parse_mode="Markdown"
        )
        return
    text = srv_format_stats(saved)
    kb   = [[InlineKeyboardButton("🔄 Check Now", callback_data="srvchk_refresh")]]
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

# ── Admin panel server status callback ──
async def server_status_admin_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.answer("🔒 Sirf admins!", show_alert=True)
        return
    saved = srv_load_status()
    if not saved:
        text = (
            "📡 *Server Status*\n\n"
            "_Abhi tak koi check nahi hua._\n\n"
            "👉 `/checkservers` run karo\n"
            "👉 Auto-check har 12hr mein hoga."
        )
    else:
        text = srv_format_status(saved, "📡 LAST CHECK RESULTS")
    kb = [
        [InlineKeyboardButton("🔄 Check Now",  callback_data="srvchk_refresh"),
         InlineKeyboardButton("📊 Stats",       callback_data="srvchk_stats")],
        [InlineKeyboardButton("🔙 Back",        callback_data="adm_back")],
    ]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

# ── Auto background checker — v5: smart 3-speed interval ──
async def auto_server_checker(bot, admin_id: int):
    """
    v5: 3-speed smart interval
    - ALL OK     → 12hr
    - DEGRADED   → 2hr
    - ANY DOWN   → 30min fast recheck
    + Alert throttle per server
    """
    print("🕐 Auto server checker v6 ULTIMATE started")
    await asyncio.sleep(300)

    while True:
        try:
            print(f"🔍 Auto check @ {now_ist().strftime('%I:%M %p')} IST")
            servers      = load_servers()
            results      = await srv_check_all_parallel(servers)
            down_keys    = [k for k, v in results.items() if not v.get("up")]
            degraded_keys = [k for k, v in results.items() if v.get("degraded")]

            if down_keys:
                now_ts   = time.time()
                to_alert = [k for k in down_keys
                            if now_ts - _srv_alerted_at.get(k, 0) > SRV_ALERT_COOLDOWN_HRS * 3600]
                for k in to_alert:
                    _srv_alerted_at[k] = now_ts

                if to_alert:
                    ai_text = await srv_ai_diagnose(results)
                    alert   = srv_format_alert(to_alert, results, degraded_keys)
                    if ai_text:
                        alert += f"\n\n🤖 *AI ANALYSIS:*\n{ai_text}"
                    kb = [[
                        InlineKeyboardButton("🔄 Recheck", callback_data="srvchk_refresh"),
                        InlineKeyboardButton("⚙️ Edit",    callback_data="adm_servers"),
                    ]]
                    await bot.send_message(chat_id=admin_id, text=alert,
                                           parse_mode="Markdown",
                                           reply_markup=InlineKeyboardMarkup(kb))
                    print(f"🚨 Alert: {len(to_alert)} DOWN (throttled {len(down_keys)-len(to_alert)})")

                sleep_sec = SRV_DOWN_INTERVAL_MIN * 60
                print(f"⚡ Fast mode: recheck in {SRV_DOWN_INTERVAL_MIN}min")

            elif degraded_keys:
                print(f"⚠️ {len(degraded_keys)} degraded — recheck in {SRV_DEGRADED_INTERVAL_HRS}hr")
                sleep_sec = SRV_DEGRADED_INTERVAL_HRS * 3600
            else:
                # Reset cooldown for recovered servers
                for k in list(_srv_alerted_at.keys()):
                    if results.get(k, {}).get("up"):
                        _srv_alerted_at.pop(k, None)
                print("✅ All servers healthy")
                sleep_sec = SRV_CHECK_INTERVAL_HOURS * 3600

        except Exception as e:
            print(f"Auto checker error: {e}")
            sleep_sec = SRV_CHECK_INTERVAL_HOURS * 3600

        nxt = now_ist() + timedelta(seconds=sleep_sec)
        print(f"⏰ Next check: {nxt.strftime('%d %b %Y, %I:%M %p')} IST")
        await asyncio.sleep(sleep_sec)
# ═══════════════════════════════════════════════════════════════════


# ── Download Servers (servers_cb) ──
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import now_ist
from storage import load_servers, is_maintenance

async def servers_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query      = update.callback_query
    await query.answer("🌐 Loading servers...")
    msg_id     = query.data.split("_", 1)[1]
    movie_data = context.user_data.get(msg_id)
    if not movie_data:
        await query.message.reply_text("⚠️ Session expired. Search again.")
        return
    loader = await query.message.reply_text("🌐 Loading servers...\n" + progress_bar(0, 4))
    await animate_generic(loader, FRAMES["server"])
    try: await loader.delete()
    except: pass
    urls   = movie_data["servers"]
    names  = movie_data["names"]
    title  = movie_data["title"]
    medals = ["🥇","🥈","🥉","🏅","🎖","🌟"]
    keyboard = [[InlineKeyboardButton(f"{medals[i]} {names[i]}", url=urls[i])] for i in range(6)]
    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data=f"bk_{msg_id}")])
    sent = await query.message.reply_text(
        f"╔═══════════════════════╗\n║  🌐  *6 DOWNLOAD SERVERS*  ║\n╚═══════════════════════╝\n\n"
        f"🎬 *{title}*\n━━━━━━━━━━━━━━━━━━\nPick any server 👇\n\n🦁 *Brave Browser = No Ads!*\n⏱ _Deletes in 1 min_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    asyncio.create_task(auto_delete(sent, 60))

async def back_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query      = update.callback_query
    await query.answer()
    msg_id     = query.data.split("_", 1)[1]
    movie_data = context.user_data.get(msg_id)
    if not movie_data:
        await query.message.reply_text("⚠️ Expired. Search again.")
        return
    loader = await query.message.reply_text("🔄 Loading...\n" + progress_bar(0, 3))
    await animate_generic(loader, FRAMES["back"])
    try: await loader.delete()
    except: pass
    urls  = movie_data["servers"]
    names = movie_data["names"]
    await query.message.reply_text(
        f"🎬 *Back to:* _{movie_data['title']}_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎬 Trailer", url=movie_data["trailer"]),
             InlineKeyboardButton("❤️ Watchlist", callback_data=f"wl_save|{str(movie_data['title']).replace('|','')[:40]}|{movie_data['year']}|{movie_data['rating']}")],
            [InlineKeyboardButton(f"⬇️ {names[0]}", url=urls[0])],
            [InlineKeyboardButton("🌐 All 6 Servers", callback_data=f"srv_{msg_id}"),
             InlineKeyboardButton("🎯 Similar", callback_data=f"sim_{msg_id}")]
        ])
    )


# ═══════════════════════════════════════════════════════════════════
#   /clean
