"""In-memory store for the MVP skeleton.

Single source of truth for connections and drafts while we prove the flow. Swap
this module for a DB-backed repository later; the call sites only use the small
API below.
"""

from __future__ import annotations

import itertools
import threading

from app.config import settings
from app.store.models import (
    Activity,
    Connection,
    Contact,
    Draft,
    ManagedBot,
    Message,
    Settings,
)

_draft_counter = itertools.count(1)
_lock = threading.Lock()

_connections: dict[str, Connection] = {}
_drafts: dict[str, Draft] = {}
_messages: list[Message] = []
_contacts: dict[tuple[str, int], Contact] = {}
_managed_bots: dict[int, ManagedBot] = {}
_activities: list[Activity] = []
_digest_markers: dict[str, str] = {}


# --- Connections -----------------------------------------------------------
def upsert_connection(
    business_connection_id: str, owner_user_id: int, can_reply: bool
) -> Connection:
    with _lock:
        conn = _connections.get(business_connection_id)
        if conn is None:
            conn = Connection(
                business_connection_id=business_connection_id,
                owner_user_id=owner_user_id,
                can_reply=can_reply,
                settings=Settings(tier=settings.default_tier),
            )
            _connections[business_connection_id] = conn
        else:
            conn.owner_user_id = owner_user_id
            conn.can_reply = can_reply
            conn.is_enabled = True
        return conn


def disable_connection(business_connection_id: str) -> None:
    with _lock:
        conn = _connections.get(business_connection_id)
        if conn:
            conn.is_enabled = False


def get_connection(business_connection_id: str) -> Connection | None:
    return _connections.get(business_connection_id)


def list_connections(enabled_only: bool = True) -> list[Connection]:
    conns = list(_connections.values())
    if enabled_only:
        conns = [c for c in conns if c.is_enabled]
    return conns


def get_connection_by_owner(owner_user_id: int) -> Connection | None:
    enabled = [c for c in _connections.values() if c.owner_user_id == owner_user_id]
    enabled.sort(key=lambda c: c.is_enabled, reverse=True)
    return enabled[0] if enabled else None


def update_connection_settings(
    business_connection_id: str,
    *,
    auto_send: bool | None = None,
    paused: bool | None = None,
    tone: str | None = None,
    tier: str | None = None,
) -> None:
    with _lock:
        conn = _connections.get(business_connection_id)
        if conn is None:
            return
        if auto_send is not None:
            conn.settings.auto_send = auto_send
        if paused is not None:
            conn.settings.paused = paused
        if tone is not None:
            conn.settings.tone = tone
        if tier is not None:
            conn.settings.tier = tier


def get_digest_marker(business_connection_id: str) -> str:
    return _digest_markers.get(business_connection_id, "")


def set_digest_marker(business_connection_id: str, day: str) -> None:
    _digest_markers[business_connection_id] = day


# --- Drafts ----------------------------------------------------------------
def create_draft(
    business_connection_id: str,
    target_chat_id: int,
    incoming_text: str,
    proposed_text: str,
    cost_usd: float,
) -> Draft:
    with _lock:
        draft_id = f"d{next(_draft_counter)}"
        draft = Draft(
            draft_id=draft_id,
            business_connection_id=business_connection_id,
            target_chat_id=target_chat_id,
            incoming_text=incoming_text,
            proposed_text=proposed_text,
            cost_usd=cost_usd,
        )
        _drafts[draft_id] = draft
        return draft


def get_draft(draft_id: str) -> Draft | None:
    return _drafts.get(draft_id)


def set_draft_status(draft_id: str, status: str) -> None:
    with _lock:
        draft = _drafts.get(draft_id)
        if draft:
            draft.status = status


# --- Metering (informational; no prepaid balance in the MVP) ---------------
def record_spend(business_connection_id: str, cost_usd: float) -> None:
    """Accumulate the metered cost estimate. Not a balance, not a gate."""
    with _lock:
        conn = _connections.get(business_connection_id)
        if conn:
            conn.spent_usd += cost_usd


# --- Message history -------------------------------------------------------
def record_message(
    business_connection_id: str,
    chat_id: int,
    direction: str,
    sender_id: int | None,
    text: str,
    ts: int,
) -> None:
    with _lock:
        _messages.append(
            Message(
                business_connection_id=business_connection_id,
                chat_id=chat_id,
                direction=direction,
                sender_id=sender_id,
                text=text,
                ts=ts,
            )
        )


def recent_messages(business_connection_id: str, chat_id: int, limit: int) -> list[Message]:
    thread = [
        m
        for m in _messages
        if m.business_connection_id == business_connection_id and m.chat_id == chat_id
    ]
    return thread[-limit:]


# --- Managed bots (per-client secretary bots we operate) -------------------
def upsert_managed_bot(
    bot_user_id: int,
    owner_user_id: int,
    token: str,
    username: str | None,
    created_at: int,
) -> ManagedBot:
    with _lock:
        existing = _managed_bots.get(bot_user_id)
        bot = ManagedBot(
            bot_user_id=bot_user_id,
            owner_user_id=owner_user_id,
            token=token,
            username=username or (existing.username if existing else None),
            status="active",
            created_at=existing.created_at if existing else created_at,
        )
        _managed_bots[bot_user_id] = bot
        return bot


def get_managed_bot(bot_user_id: int) -> ManagedBot | None:
    return _managed_bots.get(bot_user_id)


def list_managed_bots(active_only: bool = True) -> list[ManagedBot]:
    bots = list(_managed_bots.values())
    if active_only:
        bots = [b for b in bots if b.status == "active"]
    return bots


def set_managed_bot_status(bot_user_id: int, status: str) -> None:
    with _lock:
        bot = _managed_bots.get(bot_user_id)
        if bot:
            bot.status = status


# --- Contacts (durable per-thread memory) ----------------------------------
def bump_contact(business_connection_id: str, chat_id: int, name: str | None, ts: int) -> Contact:
    key = (business_connection_id, chat_id)
    with _lock:
        contact = _contacts.get(key)
        if contact is None:
            contact = Contact(
                business_connection_id=business_connection_id,
                chat_id=chat_id,
                name=name,
                message_count=1,
                updated_at=ts,
            )
            _contacts[key] = contact
        else:
            contact.message_count += 1
            contact.updated_at = ts
            if name:
                contact.name = name
        return contact


def get_contact(business_connection_id: str, chat_id: int) -> Contact | None:
    return _contacts.get((business_connection_id, chat_id))


def list_contacts(business_connection_id: str) -> list[Contact]:
    found = [c for (bc, _), c in _contacts.items() if bc == business_connection_id]
    return sorted(found, key=lambda c: c.message_count, reverse=True)


def set_contact_muted(business_connection_id: str, chat_id: int, muted: bool) -> None:
    with _lock:
        contact = _contacts.get((business_connection_id, chat_id))
        if contact:
            contact.muted = muted


# --- Activity (secretary decisions, for /status and the daily digest) -------
def record_activity(
    business_connection_id: str, chat_id: int, kind: str, snippet: str, ts: int
) -> None:
    with _lock:
        _activities.append(
            Activity(
                business_connection_id=business_connection_id,
                chat_id=chat_id,
                kind=kind,
                snippet=snippet,
                ts=ts,
            )
        )


def activities_since(business_connection_id: str, since_ts: int) -> list[Activity]:
    return [
        a
        for a in _activities
        if a.business_connection_id == business_connection_id and a.ts >= since_ts
    ]


def update_contact_profile(business_connection_id: str, chat_id: int, profile: str) -> None:
    with _lock:
        contact = _contacts.get((business_connection_id, chat_id))
        if contact:
            contact.profile = profile
