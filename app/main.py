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
    """Log any unhandled exception from a handler instead of dropping a raw trace.

    Transient network drops (poll timeouts, mid-read disconnects) are routine on
    a long-running poller and self-heal via PTB's retry — warn without the
    traceback so real failures stand out in the log.
    """
    from telegram.error import NetworkError, TimedOut

    err = context.error
    if isinstance(err, (NetworkError, TimedOut)):
        log.warning("Transient network error (auto-retrying): %s", err)
        return
    log.error("Unhandled handler error", exc_info=err)


def register_secretary_handlers(app) -> None:
    """Wire the secretary handlers onto an Application (any bot token).

    Used both by single-bot dev mode (this module) and by the platform runtime
    (app/platform.py), which runs one such Application per managed bot.
    """
    # Control chat: commands + draft approval buttons (review mode).
    app.add_handler(CommandHandler("start", control.start))
    app.add_handler(CommandHandler("help", control.start))
    app.add_handler(CommandHandler("status", control.status))
    app.add_handler(CommandHandler("pause", control.pause))
    app.add_handler(CommandHandler("resume", control.resume))
    app.add_handler(CommandHandler("auto", control.auto_mode))
    app.add_handler(CommandHandler("review", control.review_mode))
    app.add_handler(CommandHandler("mute", control.mute))
    app.add_handler(CommandHandler("unmute", control.unmute))
    app.add_handler(CommandHandler("digest", control.digest_now))
    app.add_handler(CallbackQueryHandler(control.on_decision, pattern=r"^(send|discard):"))
    # Voice notes sent/forwarded to the control chat → transcript (recovery tool).
    app.add_handler(
        MessageHandler(filters.VOICE & ~filters.UpdateType.BUSINESS_MESSAGES, control.on_voice)
    )

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


async def _post_init(app) -> None:
    """Start background jobs once the event loop is running."""
    if not settings.collect_only:
        from app.digest import digest_loop

        app.create_task(digest_loop(app.bot))


def build_application():
    if not settings.telegram_bot_token:
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN is not set. Copy .env.example to .env and add a "
            "bot token from @BotFather."
        )

    app = ApplicationBuilder().token(settings.telegram_bot_token).post_init(_post_init).build()
    register_secretary_handlers(app)
    return app


def acquire_single_instance_lock():
    """Refuse to start when another Clera instance is already polling.

    Two pollers on one token fight over getUpdates (Telegram 409 Conflict) and
    silently split the update stream. The lock file lives next to the database
    and is released by the OS on any kind of process death.
    """
    import fcntl
    import os

    lock_path = os.path.join(os.path.dirname(settings.sqlite_path) or ".", "clera.lock")
    os.makedirs(os.path.dirname(lock_path) or ".", exist_ok=True)
    handle = open(lock_path, "w")  # noqa: SIM115 — held for process lifetime
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        raise SystemExit(
            "Another Clera instance is already running (data/clera.lock is held). "
            "Stop it first — two pollers on one bot token conflict."
        ) from None
    handle.write(str(os.getpid()))
    handle.flush()
    return handle


def main() -> None:
    # Python 3.12+ deprecated (and 3.14 removed) implicit event-loop creation in
    # the main thread; PTB's run_polling still calls asyncio.get_event_loop().
    # Ensure a loop exists so startup works across Python versions.
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    lock = acquire_single_instance_lock()  # held until exit
    app = build_application()
    mode = "collect-only" if settings.collect_only else "secretary"
    log.info("Clera starting (%s mode). Polling for updates…", mode)
    try:
        app.run_polling(allowed_updates=ALLOWED_UPDATES)
    finally:
        lock.close()


if __name__ == "__main__":
    main()
