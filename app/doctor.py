"""Pre-flight check before a live test.

Run: ``python -m app.doctor``

Verifies, without sending any message:
  * .env is loaded and the bot token is present
  * the token is valid (calls Telegram getMe)
  * whether an Anthropic key is set (real drafts) or not (placeholder mode)
  * reminds you of the manual Telegram-app steps the bot cannot do for you

Exits non-zero if the bot token is missing or invalid.
"""

from __future__ import annotations

import asyncio
import sys

from app.config import settings


def _line(ok: bool | None, msg: str) -> str:
    mark = {True: "✅", False: "❌", None: "ℹ️ "}[ok]
    return f"{mark} {msg}"


def _effective_backend() -> tuple[str, bool]:
    """Report which draft backend will actually be used, and if it's real."""
    from app.agent.providers.claude_cli_provider import ClaudeCLIProvider

    choice = settings.llm_provider
    if choice == "anthropic" or (choice == "auto" and settings.anthropic_api_key):
        if settings.anthropic_api_key:
            return f"Anthropic API ({settings.model_fast} / {settings.model_best})", True
        return "Anthropic API requested but no key — placeholder", False
    if choice in ("cli", "auto") and ClaudeCLIProvider().live:
        return "Claude CLI (uses your Claude Code auth)", True
    return "placeholder (no API key, no CLI)", False


async def _check_token() -> tuple[bool, str]:
    if not settings.telegram_bot_token:
        return False, "TELEGRAM_BOT_TOKEN is not set (copy .env.example → .env)"
    try:
        from telegram import Bot

        bot = Bot(settings.telegram_bot_token)
        async with bot:
            me = await bot.get_me()
        return True, f"Bot token valid — @{me.username} (id {me.id})"
    except Exception as exc:  # noqa: BLE001 - report any failure to the user
        return False, f"Bot token rejected by Telegram: {exc}"


async def main() -> int:
    print("── Clera pre-flight ──")

    token_ok, token_msg = await _check_token()
    print(_line(token_ok, token_msg))

    backend, real = _effective_backend()
    print(_line(real, f"Draft backend: {backend}"))

    if settings.control_chat_id:
        print(_line(True, f"Control chat id set — approvals go to {settings.control_chat_id}"))
    else:
        print(_line(None, "CONTROL_CHAT_ID unset — approvals fall back to the owner's own chat"))

    print("\nManual steps I cannot do for you (need your Premium account):")
    print("  1. Telegram → Settings → Business → Chatbots → select this bot")
    print("  2. Grant it reply permission and pick the chats it covers")
    print("  3. Start the bot: python -m app.main")
    print("  4. From another account, message a covered chat — a draft should")
    print("     appear in your control chat with ✅ Send / 🗑 Discard")

    return 0 if token_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
