from __future__ import annotations
from urllib.parse import quote_plus

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# Legal streaming platforms — button opens that platform's own search
# page with the movie title pre-filled. No scraping, no third-party
# "download server" links — just a shortcut into each platform's search.
_WATCH_PLATFORMS = [
    ("JioHotstar", "https://www.jiohotstar.com/search?q={q}"),
    ("Netflix", "https://www.netflix.com/search?q={q}"),
    ("Prime Video", "https://www.primevideo.com/search/ref=atv_nb_sr?phrase={q}"),
    ("Zee5", "https://www.zee5.com/search?q={q}"),
]


def watch_links_keyboard(title: str) -> list:
    """Returns rows of URL buttons (2 per row): YouTube trailer + legal streaming platforms."""
    q = quote_plus(title)
    yt_button = InlineKeyboardButton(
        "▶️ YouTube Trailer", url=f"https://www.youtube.com/results?search_query={quote_plus(title + ' official trailer')}"
    )
    platform_buttons = [InlineKeyboardButton(f"📺 {name}", url=url.format(q=q)) for name, url in _WATCH_PLATFORMS]
    buttons = [yt_button] + platform_buttons
    return [buttons[i:i + 2] for i in range(0, len(buttons), 2)]


def main_menu_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("🎬 AI Suggest", callback_data="cmd_suggest"),
         InlineKeyboardButton("🔍 Plot Search", callback_data="cmd_plotsearch")],
        [InlineKeyboardButton("😊 Mood Match", callback_data="cmd_mood"),
         InlineKeyboardButton("⚖️ Compare", callback_data="cmd_compare")],
        [InlineKeyboardButton("🔥 Trending", callback_data="cmd_trending"),
         InlineKeyboardButton("🎲 Random", callback_data="cmd_random")],
        [InlineKeyboardButton("📅 Upcoming", callback_data="cmd_upcoming"),
         InlineKeyboardButton("📋 Watchlist", callback_data="cmd_watchlist")],
        [InlineKeyboardButton("🧠 Quiz", callback_data="cmd_quiz"),
         InlineKeyboardButton("📊 My Stats", callback_data="cmd_mystats")],
    ]
    return InlineKeyboardMarkup(rows)


def movie_card_keyboard(imdb_id: str, title: str = "") -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("🤖 AI Review", callback_data=f"rev_{imdb_id}"),
         InlineKeyboardButton("🎭 Similar Movies", callback_data=f"sim_{imdb_id}")],
        [InlineKeyboardButton("⭐ Rate It", callback_data=f"rate_{imdb_id}"),
         InlineKeyboardButton("💾 Add to Watchlist", callback_data=f"wl_save|{imdb_id}")],
        [InlineKeyboardButton("📖 Full Review", callback_data=f"frev_{imdb_id}"),
         InlineKeyboardButton("🎉 Fun Fact", callback_data=f"fun_{imdb_id}")],
    ]
    if title:
        rows.extend(watch_links_keyboard(title))
    rows.append([InlineKeyboardButton("⬅️ Back to Menu", callback_data="bk_home")])
    return InlineKeyboardMarkup(rows)


def rating_keyboard(imdb_id: str) -> InlineKeyboardMarkup:
    row1 = [InlineKeyboardButton(str(i), callback_data=f"dorat_{imdb_id}_{i}") for i in range(1, 6)]
    row2 = [InlineKeyboardButton(str(i), callback_data=f"dorat_{imdb_id}_{i}") for i in range(6, 11)]
    return InlineKeyboardMarkup([row1, row2])


def back_keyboard(target: str = "bk_home") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data=target)]])
