"""Managed-bots provisioning — how a non-technical client gets their own bot.

Flow (see docs/PLATFORM.md):

  1. We run this *manager bot* with Bot Management Mode enabled in BotFather.
  2. The client taps a creation deep link:
        https://t.me/newbot/{manager_bot_username}/{new_username}?name={new_name}
     and confirms a pre-filled dialog. The new bot is OWNED BY THE CLIENT.
  3. We receive a ``managed_bot`` update (ManagedBotUpdated).
  4. We call ``getManagedBotToken`` for the operating token, persist it, and
     hand the bot to the platform runtime (see app/platform.py) which starts a
     secretary runner for it.

python-telegram-bot's typed support for these updates lags the Bot API, so the
payload is read defensively (typed attribute, else ``api_kwargs``) and the token
call goes through ``Bot.do_api_request``.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from urllib.parse import quote

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.store import repo as store
from app.store.models import ManagedBot

log = logging.getLogger(__name__)

# The platform runtime registers a callback here so a freshly provisioned bot
# starts serving immediately, without a restart.
_on_provisioned: Callable[[ManagedBot], Awaitable[None]] | None = None


def set_on_provisioned(callback: Callable[[ManagedBot], Awaitable[None]]) -> None:
    global _on_provisioned
    _on_provisioned = callback


def build_creation_link(manager_bot_username: str, new_username: str, new_name: str) -> str:
    """Deep link a client taps to create their own secretary bot (pre-filled, editable)."""
    return f"https://t.me/newbot/{manager_bot_username}/{new_username}?name={quote(new_name)}"


def suggest_username(first_name: str | None, user_id: int) -> str:
    """A valid, likely-free username suggestion; the client can edit it anyway.

    Must be 5-32 chars of [A-Za-z0-9_] and end in 'bot'.
    """
    base = re.sub(r"[^a-zA-Z0-9_]", "", (first_name or "my").lower()) or "my"
    return f"{base}_{user_id % 10000}_clera_bot"[:32]


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Manager-bot /start: greet the client and offer their own secretary bot."""
    msg = update.effective_message
    user = update.effective_user
    if msg is None or user is None or context.bot.username is None:
        return
    link = build_creation_link(
        context.bot.username,
        suggest_username(user.first_name, user.id),
        f"{user.first_name}'s secretary",
    )
    await msg.reply_text(
        "👋 Welcome to Clera.\n\n"
        "Tap the button to create *your own* secretary bot — you own it, we run "
        "it. Then connect it to your account in Telegram Settings → Business → "
        "Chatbots, and it will start answering your chats in your voice.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🤖 Create my secretary bot", url=link)]]
        ),
    )


def _field(payload: object, *names: str) -> object:
    """Read a field from a typed object or a raw dict, trying several names."""
    for name in names:
        if isinstance(payload, dict):
            if name in payload:
                return payload[name]
        else:
            value = getattr(payload, name, None)
            if value is not None:
                return value
    return None


def extract_managed_bot_payload(update: Update) -> object | None:
    """The ``managed_bot`` update, whether PTB parses it or leaves it raw."""
    payload = getattr(update, "managed_bot", None)
    if payload is None and update.api_kwargs:
        payload = update.api_kwargs.get("managed_bot")
    return payload


async def on_managed_bot_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """A client created (or updated) a bot through our manager bot."""
    payload = extract_managed_bot_payload(update)
    if payload is None:
        return

    bot_info = _field(payload, "bot", "bot_user")
    bot_user_id = _field(bot_info, "id", "user_id") if bot_info is not None else None
    if bot_user_id is None:
        bot_user_id = _field(payload, "bot_user_id", "bot_id")
    if bot_user_id is None:
        log.warning("managed_bot update without a bot id; payload=%r", payload)
        return
    bot_user_id = int(bot_user_id)  # raw payloads carry it as JSON number or string

    username = _field(bot_info, "username") if bot_info is not None else None
    owner = _field(payload, "owner", "user", "from_user", "from")
    owner_user_id = int(_field(owner, "id") or 0) if owner is not None else 0
    date = _field(payload, "date")
    created_at = int(date.timestamp()) if hasattr(date, "timestamp") else int(date or 0)

    try:
        result = await context.bot.do_api_request(
            "getManagedBotToken", api_kwargs={"bot_user_id": bot_user_id}
        )
    except Exception:
        log.exception("getManagedBotToken failed for bot %s", bot_user_id)
        return
    token = result.get("token") if isinstance(result, dict) else result
    if not isinstance(token, str) or not token:
        log.error("Unexpected getManagedBotToken result for bot %s: %r", bot_user_id, result)
        return

    bot = store.upsert_managed_bot(
        bot_user_id=bot_user_id,
        owner_user_id=owner_user_id,
        token=token,
        username=str(username) if username else None,
        created_at=created_at,
    )
    log.info("Provisioned managed bot %s (@%s) for owner %s", bot_user_id, username, owner_user_id)

    if _on_provisioned is not None:
        await _on_provisioned(bot)

    if owner_user_id:
        await context.bot.send_message(
            chat_id=owner_user_id,
            text=(
                f"🎉 Your secretary bot @{username or bot_user_id} is live!\n\n"
                "Last step: connect it to your account in Telegram Settings → "
                "Business → Chatbots. From then on it answers your chats "
                "automatically, in your voice."
            ),
        )
