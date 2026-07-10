"""Control-chat handlers: the owner approving/discarding drafts, and /start /help.

The approval callback is what actually sends a reply AS THE OWNER, using the
stored ``business_connection_id``.
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.store import repo as store

log = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message is None:
        return
    await update.effective_message.reply_text(
        "👋 This is your Clera control chat.\n\n"
        "I answer your chats *automatically*, in your voice, using our full "
        "conversation history with each contact. When a message needs you "
        "personally — money, commitments, things only you know — I don't "
        "reply; I ping you here instead.\n\n"
        "To go live, enable me as a chatbot in Telegram Settings → Business → "
        "Chatbots.",
        parse_mode="Markdown",
    )


async def on_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """A voice note sent/forwarded to the control chat → reply with its transcript.

    Recovery tool: lets the owner transcribe a contact's voice note the bot
    missed (or any audio) by forwarding it here.
    """
    msg = update.effective_message
    if msg is None or msg.voice is None:
        return
    from app.handlers.business import _voice_to_text

    await msg.reply_text("🎙 Transcribing…")
    transcript = await _voice_to_text(context, msg)
    if transcript is None:
        await msg.reply_text("⚠️ Could not transcribe that voice note.")
        return
    await msg.reply_text(f"🎙 Transcript:\n{transcript}")


async def on_decision(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the ✅ Send / 🗑 Discard inline buttons."""
    query = update.callback_query
    if query is None or not query.data:
        return
    await query.answer()

    action, _, draft_id = query.data.partition(":")
    draft = store.get_draft(draft_id)
    if draft is None or draft.status != "pending":
        await query.edit_message_text("⚠️ This draft is no longer available.")
        return

    if action == "discard":
        store.set_draft_status(draft_id, "discarded")
        log.info("Draft %s discarded by owner", draft_id)
        await query.edit_message_text("🗑 Draft discarded. Nothing was sent.")
        return

    if action == "send":
        try:
            sent = await context.bot.send_message(
                chat_id=draft.target_chat_id,
                text=draft.proposed_text,
                business_connection_id=draft.business_connection_id,
            )
        except Exception as exc:  # keep the owner informed on failure
            log.exception("Failed to send approved draft %s", draft_id)
            await query.edit_message_text(f"❌ Could not send: {exc}")
            return

        store.set_draft_status(draft_id, "sent")
        # Record what we sent so it becomes part of the thread history/voice.
        conn = store.get_connection(draft.business_connection_id)
        store.record_message(
            business_connection_id=draft.business_connection_id,
            chat_id=draft.target_chat_id,
            direction="out",
            sender_id=conn.owner_user_id if conn else None,
            text=draft.proposed_text,
            ts=int(sent.date.timestamp()) if sent.date else 0,
        )
        log.info("Sent approved draft %s to chat %s", draft_id, draft.target_chat_id)
        await query.edit_message_text(f"✅ Sent as you:\n{draft.proposed_text}")
