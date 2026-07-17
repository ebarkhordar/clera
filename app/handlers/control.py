"""Control-chat handlers: the owner approving/discarding drafts, and /start /help.

The approval callback is what actually sends a reply AS THE OWNER, using the
stored ``business_connection_id``.
"""

from __future__ import annotations

import logging
import time

from telegram import Update
from telegram.ext import ContextTypes

from app.store import repo as store
from app.store.models import Connection

log = logging.getLogger(__name__)


def _conn_for(update: Update) -> Connection | None:
    """The command sender's business connection (owner-keyed)."""
    user = update.effective_user
    if user is None:
        return None
    return store.get_connection_by_owner(user.id)


async def _reply(update: Update, text: str) -> None:
    if update.effective_message is not None:
        await update.effective_message.reply_text(text, parse_mode="Markdown")


def _resolve_contact(conn: Connection, query: str):
    """Match a contact by chat id or (case-insensitive) name substring."""
    contacts = store.list_contacts(conn.business_connection_id)
    if query.lstrip("-").isdigit():
        wanted = int(query)
        return [c for c in contacts if c.chat_id == wanted]
    q = query.casefold()
    return [c for c in contacts if c.name and q in c.name.casefold()]


_COMMANDS_HELP = (
    "*Commands*\n"
    "/status — what I'm doing right now\n"
    "/auto — reply automatically (escalate what needs you)\n"
    "/review — every reply waits for your ✅\n"
    "/pause · /resume — stop/start acting (recording continues)\n"
    "/mute <name> · /unmute <name> — never act in one chat\n"
    "/digest — what I did in the last 24h\n"
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Onboarding checklist built from live state, not a static blurb."""
    if update.effective_message is None:
        return
    conn = _conn_for(update)

    if conn is None or not conn.is_enabled:
        await update.effective_message.reply_text(
            "👋 Welcome to Clera — your Telegram secretary.\n\n"
            "I answer your chats *automatically, in your voice*, and hand you "
            "the messages only you can answer (money, commitments, personal "
            "things).\n\n"
            "*Setup — 2 minutes:*\n"
            "1️⃣ Telegram → Settings → *Business* → *Chatbots* → pick me\n"
            "2️⃣ Give me *reply* permission and choose which chats I cover\n"
            "3️⃣ Come back here and send /status\n\n"
            "I start in review mode: every reply waits for your tap until you "
            "run /auto.",
            parse_mode="Markdown",
        )
        return

    mode = (
        "⏸ paused"
        if conn.settings.paused
        else ("🤖 automatic" if conn.settings.auto_send else "✅ review")
    )
    reply_ok = "✅" if conn.can_reply else "⚠️ missing — enable it in Business → Chatbots"
    contacts = store.list_contacts(conn.business_connection_id)
    await update.effective_message.reply_text(
        f"👋 Connected and running.\n\n"
        f"Mode: {mode}\n"
        f"Reply permission: {reply_ok}\n"
        f"Contacts learned: {len(contacts)}\n\n" + _COMMANDS_HELP,
        parse_mode="Markdown",
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Live overview: mode, activity today, spend, muted contacts."""
    conn = _conn_for(update)
    if conn is None:
        await _reply(update, "No business connection yet — see /start for setup steps.")
        return

    mode = (
        "⏸ paused"
        if conn.settings.paused
        else ("🤖 automatic" if conn.settings.auto_send else "✅ review (drafts need your tap)")
    )
    day_start = int(time.time()) - 86400
    acts = store.activities_since(conn.business_connection_id, day_start)
    counts = {
        k: sum(1 for a in acts if a.kind == k)
        for k in ("replied", "drafted", "escalated", "silent")
    }
    contacts = store.list_contacts(conn.business_connection_id)
    muted = [c.name or str(c.chat_id) for c in contacts if c.muted]
    total_msgs = sum(c.message_count for c in contacts)

    await _reply(
        update,
        f"*Clera status*\n"
        f"Mode: {mode}\n"
        f"Reply permission: {'yes' if conn.can_reply else 'NO — enable in Business settings'}\n"
        f"Contacts known: {len(contacts)} ({total_msgs} messages recorded)\n"
        f"Last 24h: {counts['replied']} replied · {counts['drafted']} drafted · "
        f"{counts['escalated']} escalated · {counts['silent']} silent\n"
        f"Muted: {', '.join(muted) if muted else 'nobody'}\n"
        f"Estimated spend to date: ${conn.spent_usd:.2f}",
    )


async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conn = _conn_for(update)
    if conn is None:
        return await _reply(update, "No connection yet — see /start.")
    store.update_connection_settings(conn.business_connection_id, paused=True)
    await _reply(
        update,
        "⏸ Paused. I'll keep recording but won't reply, draft, or ping you. /resume to continue.",
    )


async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conn = _conn_for(update)
    if conn is None:
        return await _reply(update, "No connection yet — see /start.")
    store.update_connection_settings(conn.business_connection_id, paused=False)
    mode = "automatic" if conn.settings.auto_send else "review"
    await _reply(update, f"▶️ Resumed in {mode} mode.")


async def auto_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conn = _conn_for(update)
    if conn is None:
        return await _reply(update, "No connection yet — see /start.")
    store.update_connection_settings(conn.business_connection_id, auto_send=True, paused=False)
    await _reply(
        update,
        "🤖 Automatic mode ON. I reply as you without approval; anything needing you "
        "personally gets escalated here instead. /review to go back to approvals.",
    )


async def review_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conn = _conn_for(update)
    if conn is None:
        return await _reply(update, "No connection yet — see /start.")
    store.update_connection_settings(conn.business_connection_id, auto_send=False, paused=False)
    await _reply(update, "✅ Review mode ON. Every reply waits for your tap here.")


async def _set_mute(update: Update, context: ContextTypes.DEFAULT_TYPE, muted: bool) -> None:
    conn = _conn_for(update)
    if conn is None:
        return await _reply(update, "No connection yet — see /start.")
    verb = "mute" if muted else "unmute"
    if not context.args:
        return await _reply(update, f"Usage: /{verb} <contact name or chat id>")
    query = " ".join(context.args)
    matches = _resolve_contact(conn, query)
    if not matches:
        return await _reply(update, f"No contact matching “{query}”. Try /status for the list.")
    if len(matches) > 1:
        names = ", ".join(f"{c.name or c.chat_id}" for c in matches[:5])
        return await _reply(update, f"“{query}” is ambiguous: {names}. Be more specific.")
    contact = matches[0]
    store.set_contact_muted(conn.business_connection_id, contact.chat_id, muted)
    label = contact.name or str(contact.chat_id)
    if muted:
        await _reply(
            update, f"🔇 Muted *{label}* — recording continues, but I'll never act in that chat."
        )
    else:
        await _reply(update, f"🔊 Unmuted *{label}*.")


async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _set_mute(update, context, muted=True)


async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _set_mute(update, context, muted=False)


async def digest_now(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the last-24h digest on demand."""
    from app.digest import send_digest

    conn = _conn_for(update)
    if conn is None:
        return await _reply(update, "No connection yet — see /start.")
    sent = await send_digest(context.bot, conn)
    if not sent:
        await _reply(update, "Nothing to report in the last 24h.")


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
