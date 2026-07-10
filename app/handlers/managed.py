"""Managed-bots provisioning — STUB for the MVP.

In production this is how a non-technical user gets a bot without touching
BotFather:

  1. Platform runs a *manager bot* with Bot Management Mode enabled in BotFather.
  2. User taps a deep link:
        https://t.me/newbot/{manager_bot_username}/{new_username}?name={new_name}
  3. User confirms -> the new bot is created, OWNED BY THE USER.
  4. Manager bot receives a ``managed_bot`` update (ManagedBotUpdated).
  5. Platform calls ``getManagedBotToken`` to fetch the token and starts
     operating that bot (webhook, agent loop, sending).

python-telegram-bot's typed support for these updates is still catching up to
the Bot API, so this file documents the flow and provides the seam. Wire it to a
real manager-bot deployment when we leave single-bot demo mode.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def build_creation_link(manager_bot_username: str, new_username: str, new_name: str) -> str:
    """Deep link a user taps to create their own managed secretary bot."""
    from urllib.parse import quote

    return f"https://t.me/newbot/{manager_bot_username}/{new_username}?name={quote(new_name)}"


async def on_managed_bot_update(payload: dict) -> None:
    """Placeholder for the ``managed_bot`` update handler.

    Real implementation:
      * read the new bot id + creator from the ManagedBotUpdated payload
      * call getManagedBotToken to obtain the operating token
      * register a new bot runner / webhook for that token
    """
    log.info("managed_bot update received (stub): %s", payload)
