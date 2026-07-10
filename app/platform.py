"""Platform runtime: the manager bot plus one secretary runner per managed bot.

Run with ``python -m app.platform``. This is the hosted-product entrypoint:

  * the *manager bot* (TELEGRAM_BOT_TOKEN) onboards clients — /start hands out
    a creation link, ``managed_bot`` updates provision their new bot;
  * every managed bot in the store gets its own polling Application running the
    normal secretary handlers, all in one process / event loop;
  * a bot provisioned while running starts serving immediately.

Polling keeps development serverless. The webhook gateway (one public endpoint,
``setWebhook`` per managed bot) replaces this loop for real deployments — see
docs/PLATFORM.md backlog item 4.

``python -m app.main`` remains the single-bot dev mode (your own BotFather
token acting as the secretary directly).
"""

from __future__ import annotations

import asyncio
import logging
import signal

from telegram import Update
from telegram.ext import Application, ApplicationBuilder, CommandHandler, TypeHandler

from app.config import settings
from app.handlers import managed
from app.main import ALLOWED_UPDATES as SECRETARY_UPDATES
from app.main import on_error, register_secretary_handlers
from app.store import repo as store
from app.store.models import ManagedBot

log = logging.getLogger("clera.platform")

MANAGER_UPDATES = ["message", "callback_query", "managed_bot"]


def build_manager_application(token: str) -> Application:
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", managed.cmd_start))
    app.add_handler(CommandHandler("help", managed.cmd_start))

    async def _raw(update: Update, context) -> None:
        if managed.extract_managed_bot_payload(update) is not None:
            await managed.on_managed_bot_update(update, context)

    app.add_handler(TypeHandler(Update, _raw))
    app.add_error_handler(on_error)
    return app


def build_secretary_application(token: str) -> Application:
    app = ApplicationBuilder().token(token).build()
    register_secretary_handlers(app)
    return app


async def _start(app: Application, allowed_updates: list[str]) -> None:
    await app.initialize()
    await app.start()
    await app.updater.start_polling(allowed_updates=allowed_updates)


async def _stop(app: Application) -> None:
    if app.updater and app.updater.running:
        await app.updater.stop()
    if app.running:
        await app.stop()
    await app.shutdown()


async def run() -> None:
    if not settings.telegram_bot_token:
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN is not set — it must be the manager bot's token "
            "(Bot Management Mode enabled in BotFather)."
        )

    fleet: dict[int, Application] = {}

    async def launch_secretary(bot: ManagedBot) -> None:
        if bot.bot_user_id in fleet:
            return
        app = build_secretary_application(bot.token)
        await _start(app, SECRETARY_UPDATES)
        fleet[bot.bot_user_id] = app
        log.info("Secretary runner started for @%s (%s)", bot.username, bot.bot_user_id)

    # Newly provisioned bots go live without a restart.
    managed.set_on_provisioned(launch_secretary)

    manager = build_manager_application(settings.telegram_bot_token)
    await _start(manager, MANAGER_UPDATES)
    log.info("Manager bot polling (updates: %s)", ", ".join(MANAGER_UPDATES))

    for bot in store.list_managed_bots():
        try:
            await launch_secretary(bot)
        except Exception:
            # One broken token (revoked bot, etc.) must not take the fleet down.
            log.exception("Could not start secretary for bot %s", bot.bot_user_id)

    log.info("Platform up: 1 manager + %d secretaries", len(fleet))

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)
    await stop_event.wait()

    log.info("Shutting down %d secretaries + manager…", len(fleet))
    for app in fleet.values():
        await _stop(app)
    await _stop(manager)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    asyncio.run(run())


if __name__ == "__main__":
    main()
