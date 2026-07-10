"""In-memory store for the MVP skeleton.

Single source of truth for connections and drafts while we prove the flow. Swap
this module for a DB-backed repository later; the call sites only use the small
API below.
"""

from __future__ import annotations

import itertools
import threading

from app.config import settings
from app.store.models import Connection, Contact, Draft, Message, Settings

_draft_counter = itertools.count(1)
_lock = threading.Lock()

_connections: dict[str, Connection] = {}
_drafts: dict[str, Draft] = {}
_messages: list[Message] = []
_contacts: dict[tuple[str, int], Contact] = {}


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


def update_contact_profile(business_connection_id: str, chat_id: int, profile: str) -> None:
    with _lock:
        contact = _contacts.get((business_connection_id, chat_id))
        if contact:
            contact.profile = profile
