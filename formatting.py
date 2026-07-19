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


def _stars(rating: str) -> str:
    """Convert a '0-10' IMDb rating into a quick 5-star visual."""
    try:
        val = float(rating)
    except (TypeError, ValueError):
        return ""
    filled = round(val / 2)
    return "⭐" * filled + "☆" * (5 - filled)


def movie_card_text(data: dict) -> str:
    title    = data.get("Title", "N/A")
    year     = data.get("Year", "N/A")
    rating   = data.get("imdbRating", "N/A")
    genre    = data.get("Genre", "N/A")
    plot     = data.get("Plot", "N/A")
    runtime  = data.get("Runtime", "N/A")
    director = data.get("Director", "N/A")
    actors   = data.get("Actors", "N/A")
    language = data.get("Language", "N/A")
    rated    = data.get("Rated", "N/A")
    awards   = data.get("Awards", "N/A")

    stars = _stars(rating)
    rating_line = f"⭐ *{rating}*/10" + (f"  {stars}" if stars else "")

    lines = [
        f"🎬 *{escape_md(title)}* `({year})`",
        "",
        f"{rating_line}   •   ⏱ {runtime}   •   🔞 {rated}",
        f"🎭 _{genre}_",
        "━━━━━━━━━━━━━━━━━━━━",
        f"📝 {plot}",
        "━━━━━━━━━━━━━━━━━━━━",
        f"🎥 *Director:* {director}",
        f"🌟 *Cast:* {actors}",
        f"🗣 *Language:* {language}",
    ]
    if awards and awards != "N/A":
        lines.append(f"🏆 *Awards:* {awards}")

    return "\n".join(lines)
