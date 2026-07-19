"""
Shared handler decorators.

Old bot repeated `if is_banned(...): ...` / `if is_maintenance(): ...`
by hand in nearly every handler — easy to forget in a new handler.
These decorators make that check automatic and impossible to skip.
"""
from __future__ import annotations

import functools
import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot.db import repository as repo

log = logging.getLogger("cinebot.decorators")


def guarded(require_admin: bool = False, require_owner: bool = False):
    """
    Wraps a handler with, in order:
      1. ban check
      2. maintenance-mode check (admins bypass)
      3. optional admin/owner requirement
    Also catches & logs any unhandled exception so one bad update can't
    crash the dispatcher loop or leave the user with no response.
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *a, **kw):
            user = update.effective_user
            if user is None:
                return
            try:
                if await repo.is_banned(user.id):
                    if update.effective_message:
                        await update.effective_message.reply_text("🚫 You are banned.")
                    return

                if require_owner and not repo.is_owner(user.id):
                    if update.effective_message:
                        await update.effective_message.reply_text("🚫 Sirf *Owner* ye command use kar sakta hai!", parse_mode="Markdown")
                    return

                if require_admin and not await repo.is_admin(user.id):
                    if update.effective_message:
                        await update.effective_message.reply_text("🚫 Admin-only command.")
                    return

                if not require_admin and not require_owner:
                    maint = await repo.get_setting("maintenance", {"active": False})
                    if maint.get("active") and not await repo.is_admin(user.id):
                        msg = maint.get("message", "🔧 Maintenance mode chal raha hai, thodi der baad try karo.")
                        if update.effective_message:
                            await update.effective_message.reply_text(f"🚧 *Maintenance*\n\n{msg}", parse_mode="Markdown")
                        return

                return await func(update, context, *a, **kw)
            except Exception:
                log.exception("Unhandled error in handler %s", func.__name__)
                try:
                    if update.effective_message:
                        await update.effective_message.reply_text(
                            "❌ Kuch galat ho gaya. Please try again — agar problem rahe to /help dekho."
                        )
                except Exception:
                    pass
        return wrapper
    return decorator
