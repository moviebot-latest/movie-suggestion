"""
CineBot v12 — entrypoint.

Runs in WEBHOOK mode (not polling) using PTB's built-in webhook server
(backed by `tornado`/`aiohttp` under the hood via `run_webhook`), bound
to Render's assigned $PORT. Render's HTTPS termination handles TLS, so
the app itself just needs to listen on plain HTTP internally.
"""
from __future__ import annotations

import logging

from config import PORT, WEBHOOK_PATH, WEBHOOK_URL, BOT_TOKEN
from app import build_application

log = logging.getLogger("cinebot.main")


def main():
    application = build_application()

    log.info("🚀 Starting CineBot in webhook mode")
    log.info("   Listening on 0.0.0.0:%s%s", PORT, WEBHOOK_PATH)
    log.info("   Public webhook URL: %s", WEBHOOK_URL)

    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=WEBHOOK_PATH,
        webhook_url=WEBHOOK_URL,
        secret_token=None,  # path already contains an unguessable secret segment
        allowed_updates=["message", "callback_query", "inline_query"],
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
