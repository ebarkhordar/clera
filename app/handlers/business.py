"""Business-connection handlers — the secretary core.

Two update types drive everything:
  * business_connection   -> owner enabled/edited/disabled the bot in their chats
  * business_message      -> a contact messaged the owner; we draft a reply

Replies are sent with ``business_connection_id`` so they go out AS THE OWNER.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import tempfile
import time

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import ContextTypes

from app.agent.secretary import DraftResult, draft_reply, summarize_contact
from app.config import settings
from app.policy.policy import Decision, decide, is_stale
from app.store import repo as store
from app.store.models import Connection, Contact

log = logging.getLogger(__name__)


def _can_reply_of(bc: object) -> bool:
    """Read reply permission across Bot API versions.

    Newer Bot API nests it under ``rights`` (BusinessBotRights); older versions
    expose a plain ``can_reply`` boolean. Handle both without assuming either.
    """
    rights = getattr(bc, "rights", None)
    if rights is not None:
        return bool(getattr(rights, "can_reply", False))
    return bool(getattr(bc, "can_reply", False))


async def on_business_connection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner connected, edited, or removed the bot as their business chatbot."""
    bc = update.business_connection
    if bc is None:
        return

    if bc.is_enabled:
        conn = store.upsert_connection(
            business_connection_id=bc.id,
            owner_user_id=bc.user.id,
            can_reply=_can_reply_of(bc),
        )
        log.info(
            "Business connection enabled: %s (owner %s, can_reply=%s)",
            bc.id,
            bc.user.id,
            conn.can_reply,
        )
        await context.bot.send_message(
            chat_id=_control_chat(conn.owner_user_id),
            text=(
                "✅ Clera connected.\n"
                "I'll answer your chats automatically, in your voice. When a "
                "message needs *you* (money, commitments, things I don't know), "
                "I'll ping you here instead of replying."
            ),
            parse_mode="Markdown",
        )
    else:
        store.disable_connection(bc.id)
        log.info("Business connection disabled: %s", bc.id)


async def on_business_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle a message in a connected chat.

    Messages the owner types themselves are recorded (as voice/context) but never
    replied to. Only messages *from the contact* produce a draft.
    """
    msg = update.business_message
    if msg is None:
        return
    text = msg.text
    if not text and msg.voice is not None:
        transcript = await _voice_to_text(context, msg)
        if transcript is None:
            log.warning("Voice message in chat %s could not be transcribed", msg.chat.id)
            return
        text = f"[voice] {transcript}"
    if not text:
        return

    bc_id = msg.business_connection_id
    conn = store.get_connection(bc_id)
    if conn is None:
        # We may have missed (or failed to process) the business_connection
        # update. Recover by fetching the connection details on demand.
        try:
            bc = await context.bot.get_business_connection(bc_id)
            conn = store.upsert_connection(
                business_connection_id=bc.id,
                owner_user_id=bc.user.id,
                can_reply=_can_reply_of(bc),
            )
            log.info("Recovered business connection %s on demand", bc_id)
        except Exception:
            log.exception("Could not resolve business connection %s", bc_id)
            return

    sender_id = msg.from_user.id if msg.from_user else None
    chat_id = msg.chat.id
    ts = int(msg.date.timestamp()) if msg.date else 0
    from_owner = sender_id is not None and sender_id == conn.owner_user_id

    # Record every message in the thread for history + contact memory.
    store.record_message(
        business_connection_id=bc_id,
        chat_id=chat_id,
        direction="out" if from_owner else "in",
        sender_id=sender_id,
        text=text,
        ts=ts,
    )
    contact_name = None if from_owner else (msg.from_user.first_name if msg.from_user else None)
    contact = store.bump_contact(bc_id, chat_id, name=contact_name, ts=ts)

    if from_owner:
        # The owner typed this themselves — learn from it, never reply to it.
        log.info("Recorded owner message on %s chat %s (not drafting)", bc_id, chat_id)
        await _maybe_refresh_profile(conn, chat_id, contact)
        return

    # From the contact → consider drafting a reply.
    # Backlog catch-up guard: updates queued while the bot was offline arrive
    # late; the owner has usually handled those already. History only, no reply.
    if is_stale(ts, int(time.time()), settings.stale_after_seconds):
        log.info("Message on %s chat %s is stale (backlog); recorded, not replying", bc_id, chat_id)
        return

    local_hour = msg.date.hour if msg.date else 12
    outcome = decide(conn, sender_id, local_hour)
    if outcome.decision is Decision.IGNORE:
        log.info("Ignoring message on %s: %s", bc_id, outcome.reason)
        return

    history = store.recent_messages(bc_id, chat_id, settings.history_limit)
    result = await asyncio.to_thread(
        draft_reply,
        history=history,
        contact_name=contact.name,
        profile=contact.profile,
        tone=conn.settings.tone,
        tier=conn.settings.tier,
    )
    store.record_spend(bc_id, result.cost_usd)

    if outcome.decision is Decision.AUTO_SEND:
        await _handle_auto(context, conn, chat_id, msg, text, result, ts)
        await _maybe_refresh_profile(conn, chat_id, contact)
        return

    # DRAFT (opt-in review mode): post to the owner's control chat for approval.
    # Silent/notify decisions apply here too — there is nothing to approve.
    if result.action == "silent":
        log.info("Agent stayed silent on %s chat %s (review mode)", bc_id, chat_id)
        return
    if result.action == "notify":
        await context.bot.send_message(
            chat_id=_control_chat(conn.owner_user_id),
            text=f"👋 *A contact needs you:*\n{text}\n\n_{result.text}_",
            parse_mode="Markdown",
        )
        return

    draft = store.create_draft(
        business_connection_id=bc_id,
        target_chat_id=chat_id,
        incoming_text=text,
        proposed_text=result.text,
        cost_usd=result.cost_usd,
    )
    demo = " _(placeholder — set ANTHROPIC_API_KEY for real drafts)_" if result.placeholder else ""
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Send", callback_data=f"send:{draft.draft_id}"),
                InlineKeyboardButton("🗑 Discard", callback_data=f"discard:{draft.draft_id}"),
            ]
        ]
    )
    await context.bot.send_message(
        chat_id=_control_chat(conn.owner_user_id),
        text=(
            f"✉️ *New message from a contact:*\n{text}\n\n"
            f"🤖 *Proposed reply* (~${result.cost_usd:.4f}, {result.model}){demo}:\n"
            f"{result.text}"
        ),
        parse_mode="Markdown",
        reply_markup=keyboard,
    )
    log.info(
        "Drafted reply on %s (draft %s, ~$%.4f, awaiting approval)",
        bc_id,
        draft.draft_id,
        result.cost_usd,
    )
    await _maybe_refresh_profile(conn, chat_id, contact)


async def _voice_to_text(context, msg) -> str | None:
    """Download a Telegram voice note and transcribe it locally. None on failure."""
    from app.agent import transcribe

    if not transcribe.available():
        return None
    tg_file = await context.bot.get_file(msg.voice.file_id)
    fd, path = tempfile.mkstemp(suffix=".oga")
    os.close(fd)
    try:
        await tg_file.download_to_drive(custom_path=path)
        return await asyncio.to_thread(transcribe.transcribe, path)
    finally:
        with contextlib.suppress(OSError):
            os.unlink(path)


async def _handle_auto(
    context, conn: Connection, chat_id: int, msg, incoming_text: str, result: DraftResult, ts: int
) -> None:
    """Fully automatic mode: act on the agent's reply/silent/notify decision."""
    bc_id = conn.business_connection_id
    contact_label = (msg.from_user.first_name if msg.from_user else None) or "a contact"
    control = _control_chat(conn.owner_user_id)

    if result.action == "silent":
        log.info("Agent stayed silent on %s chat %s", bc_id, chat_id)
        return

    # A placeholder completion (no LLM configured) must never be sent as the
    # owner — surface it to them instead.
    if result.action == "notify" or result.placeholder:
        note = (
            result.text
            if result.action == "notify"
            else "no LLM is configured (set ANTHROPIC_API_KEY), so I can't reply for you."
        )
        await context.bot.send_message(
            chat_id=control,
            text=f"👋 *{contact_label} needs you:*\n{incoming_text}\n\n_{note}_",
            parse_mode="Markdown",
        )
        log.info("Escalated message on %s chat %s to owner", bc_id, chat_id)
        return

    # The owner may have answered while we were generating — never talk over them.
    latest = store.recent_messages(bc_id, chat_id, 1)
    if latest and latest[-1].direction == "out":
        log.info("Owner replied on %s chat %s while drafting; staying silent", bc_id, chat_id)
        return

    sent = await context.bot.send_message(
        chat_id=chat_id,
        text=result.text,
        business_connection_id=bc_id,
    )
    store.record_message(
        business_connection_id=bc_id,
        chat_id=chat_id,
        direction="out",
        sender_id=conn.owner_user_id,
        text=result.text,
        ts=int(sent.date.timestamp()) if sent.date else ts,
    )
    log.info("Auto-replied on %s chat %s (cost $%.4f)", bc_id, chat_id, result.cost_usd)

    if settings.notify_auto_replies:
        await context.bot.send_message(
            chat_id=control,
            text=f"↩️ *{contact_label}:* {incoming_text}\n*Me:* {result.text}",
            parse_mode="Markdown",
        )


def _control_chat(owner_user_id: int) -> int:
    """Where escalations and activity notes go: configured chat, else the owner's own."""
    return settings.control_chat_id or owner_user_id


async def _maybe_refresh_profile(conn: Connection, chat_id: int, contact: Contact) -> None:
    """Rebuild the contact's durable profile every N messages.

    Runs the summarizer off the event loop so it never blocks message handling.
    """
    every = settings.profile_refresh_every
    if every <= 0 or contact.message_count % every != 0:
        return

    bc_id = conn.business_connection_id
    history = store.recent_messages(bc_id, chat_id, settings.history_limit)

    def _work() -> str | None:
        return summarize_contact(
            history=history,
            contact_name=contact.name,
            existing_profile=contact.profile,
            tier=conn.settings.tier,
        )

    profile = await asyncio.to_thread(_work)
    if profile:
        store.update_contact_profile(bc_id, chat_id, profile)
        log.info(
            "Refreshed profile for %s chat %s (%d msgs)", bc_id, chat_id, contact.message_count
        )
