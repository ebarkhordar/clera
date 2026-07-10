"""Entrypoint: wire handlers and run the bot.

MVP runs in long-polling mode so you can develop without a public webhook URL.
We explicitly request the business_* update types (not delivered by default).
"""

from __future__ import annotations

import asyncio
import logging

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from app.config import settings
from app.handlers import business, control

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
# httpx logs the full request URL, which contains the bot token — quiet it so the
# token never lands in logs.
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("clera")

# Updates we need Telegram to deliver. business_* are opt-in.
ALLOWED_UPDATES = [
    "message",
    "callback_query",
    "business_connection",
    "business_message",
    "edited_business_message",
]


async def on_error(update: object, context) -> None:
    """Log any unhandled exception from a handler instead of dropping a raw trace."""
    log.error("Unhandled handler error", exc_info=context.error)


def build_application():
    if not settings.telegram_bot_token:
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN is not set. Copy .env.example to .env and add a "
            "bot token from @BotFather."
        )

    app = ApplicationBuilder().token(settings.telegram_bot_token).build()

    # Control chat: commands + draft approval buttons.
    app.add_handler(CommandHandler("start", control.start))
    app.add_handler(CommandHandler("help", control.start))
    app.add_handler(CallbackQueryHandler(control.on_decision, pattern=r"^(send|discard):"))

    # Clera core: business connection + incoming business messages.
    app.add_handler(
        MessageHandler(filters.UpdateType.BUSINESS_MESSAGE, business.on_business_message)
    )
    # business_connection updates aren't a MessageHandler; use the typed handler
    # if available, else fall back to a generic TypeHandler.
    try:
        from telegram.ext import BusinessConnectionHandler

        app.add_handler(BusinessConnectionHandler(business.on_business_connection))
    except ImportError:  # older PTB: catch it via a raw update TypeHandler
        from telegram.ext import TypeHandler

        async def _raw(update: Update, context) -> None:
            if update.business_connection is not None:
                await business.on_business_connection(update, context)

        app.add_handler(TypeHandler(Update, _raw))

    app.add_error_handler(on_error)
    return app


def main() -> None:
    # Python 3.12+ deprecated (and 3.14 removed) implicit event-loop creation in
    # the main thread; PTB's run_polling still calls asyncio.get_event_loop().
    # Ensure a loop exists so startup works across Python versions.
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    app = build_application()
    log.info("Clera starting (draft-first mode). Polling for updates…")
    app.run_polling(allowed_updates=ALLOWED_UPDATES)


if __name__ == "__main__":
    main()
