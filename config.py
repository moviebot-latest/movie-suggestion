# ╔══════════════════════════════════════════╗
# ║  config.py — ENV vars & constants        ║
# ║  Edit this to change API keys/settings   ║
# ╚══════════════════════════════════════════╝
import os
from datetime import datetime, date, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
def now_ist() -> datetime: return datetime.now(IST)
def today_ist() -> date:   return now_ist().date()

TOKEN      = os.getenv("BOT_TOKEN")
OMDB_API   = os.getenv("OMDB_API")
TMDB_API   = os.getenv("TMDB_API",   "")
GROQ_API   = os.getenv("GROQ_API",   "")
ADMIN_ID   = int(os.getenv("ADMIN_ID", "0"))

TMDB_API_KEY = TMDB_API
OMDB_API_KEY = OMDB_API

GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"

if not TOKEN:
    raise ValueError("❌ BOT_TOKEN environment variable is not set!")
if not OMDB_API:
    raise ValueError("❌ OMDB_API environment variable is not set!")

if GROQ_API:
    print("✅ Groq API (llama-3.3-70b-versatile) loaded")
else:
    print("⚠️ GROQ_API not set — AI features disabled")


