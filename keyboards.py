from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


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


def movie_card_keyboard(imdb_id: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("🤖 AI Review", callback_data=f"rev_{imdb_id}"),
         InlineKeyboardButton("🎭 Similar", callback_data=f"sim_{imdb_id}")],
        [InlineKeyboardButton("⭐ Rate", callback_data=f"rate_{imdb_id}"),
         InlineKeyboardButton("💾 Watchlist", callback_data=f"wl_save|{imdb_id}")],
        [InlineKeyboardButton("📖 Full Review", callback_data=f"frev_{imdb_id}"),
         InlineKeyboardButton("🎉 Fun Fact", callback_data=f"fun_{imdb_id}")],
        [InlineKeyboardButton("⬅️ Back to Menu", callback_data="bk_home")],
    ]
    return InlineKeyboardMarkup(rows)


def rating_keyboard(imdb_id: str) -> InlineKeyboardMarkup:
    row1 = [InlineKeyboardButton(str(i), callback_data=f"dorat_{imdb_id}_{i}") for i in range(1, 6)]
    row2 = [InlineKeyboardButton(str(i), callback_data=f"dorat_{imdb_id}_{i}") for i in range(6, 11)]
    return InlineKeyboardMarkup([row1, row2])


def back_keyboard(target: str = "bk_home") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data=target)]])
