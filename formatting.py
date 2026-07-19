from __future__ import annotations

from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


def now_ist() -> datetime:
    return datetime.now(IST)


def today_ist():
    return now_ist().date()


def progress_bar(step: int, total: int, width: int = 10) -> str:
    filled = int(width * step / total) if total else 0
    return "▰" * filled + "▱" * (width - filled)


def escape_md(text: str) -> str:
    """Escape Telegram legacy-Markdown special characters."""
    if not text:
        return ""
    for ch in ["_", "*", "`", "["]:
        text = text.replace(ch, f"\\{ch}")
    return text


def movie_card_text(data: dict) -> str:
    title  = data.get("Title", "N/A")
    year   = data.get("Year", "N/A")
    rating = data.get("imdbRating", "N/A")
    genre  = data.get("Genre", "N/A")
    plot   = data.get("Plot", "N/A")
    runtime = data.get("Runtime", "N/A")
    return (
        f"🎬 *{escape_md(title)}* ({year})\n"
        f"⭐ IMDb: `{rating}/10`  |  ⏱ {runtime}\n"
        f"🎭 {genre}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{plot}"
    )
