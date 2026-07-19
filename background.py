"""
Background periodic tasks, run as native asyncio tasks inside the bot's
own event loop (NOT separate OS threads like the old bot used).

This avoids the concurrency hazards of the old design, where a
`threading.Thread` health-checker and the asyncio bot loop both touched
a shared sqlite3 connection with no lock.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from telegram.ext import Application

import repository as repo
from database import get_pool
from formatting import today_ist

log = logging.getLogger("cinebot.background")


async def reminder_sweep(app: Application):
    """Checks upcoming_reminders daily; notifies users on release day."""
    while True:
        try:
            pool = await get_pool()
            today_str = today_ist().strftime("%Y-%m-%d")
            rows = await pool.fetch(
                "SELECT user_id, title, movie_id FROM upcoming_reminders WHERE release_date = $1",
                today_str,
            )
            for r in rows:
                try:
                    await app.bot.send_message(
                        chat_id=r["user_id"],
                        text=f"🎉 *{r['title']}* releases TODAY! 🍿",
                        parse_mode="Markdown",
                    )
                except Exception as e:
                    log.debug("Reminder send failed for %s: %s", r["user_id"], e)
            if rows:
                await pool.execute("DELETE FROM upcoming_reminders WHERE release_date = $1", today_str)
        except Exception:
            log.exception("reminder_sweep iteration failed")

        await asyncio.sleep(3600)  # hourly check is enough for a daily-granularity reminder


async def start_background_tasks(app: Application):
    app.create_task(reminder_sweep(app))
    log.info("✅ Background tasks started")
