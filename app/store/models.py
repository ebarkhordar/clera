"""Core data models for the MVP.

These are plain dataclasses backed by the in-memory store. When we move to a real
DB (Postgres/SQLite) these become the table schemas — kept intentionally small.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Settings:
    """Per-connection user-facing settings (the 5-field settings screen)."""

    tone: str = "friendly and concise"
    tier: str = "fast"  # "best" | "fast"
    # Automatic secretary is the product: replies go out without approval.
    # False = legacy review mode (every reply becomes a draft to approve).
    auto_send: bool = True
    active_hours: tuple[int, int] = (0, 24)  # inclusive start, exclusive end (local hour)
    # Empty = handle every contact. Non-empty = only handle these user ids;
    # everyone else is left for the owner to answer personally.
    allowlist: set[int] = field(default_factory=set)


@dataclass
class ManagedBot:
    """A per-client secretary bot we provision and operate.

    Created via the manager bot's creation link; owned by the client, operated
    by us with the token from ``getManagedBotToken``.
    """

    bot_user_id: int  # the new bot's Telegram user id
    owner_user_id: int  # the client who owns the bot
    token: str  # operating token from getManagedBotToken
    username: str | None = None
    status: str = "active"  # active | revoked
    created_at: int = 0  # unix seconds


@dataclass
class Connection:
    """A business connection: the platform operating a bot on behalf of one owner.

    Keyed by Telegram's ``business_connection_id``.
    """

    business_connection_id: str
    owner_user_id: int  # the account owner (who the bot replies AS)
    can_reply: bool = False
    is_enabled: bool = True
    settings: Settings = field(default_factory=Settings)
    spent_usd: float = 0.0  # cumulative metered estimate (informational, not a balance)


@dataclass
class Draft:
    """A proposed reply awaiting the owner's approval in the control chat."""

    draft_id: str
    business_connection_id: str
    target_chat_id: int  # the contact's chat the reply would be sent to
    incoming_text: str
    proposed_text: str
    cost_usd: float
    status: str = "pending"  # pending | sent | discarded


@dataclass
class Message:
    """One message in a contact thread, either direction.

    direction: "in" = from the contact, "out" = from the owner (typed or bot-sent).
    """

    business_connection_id: str
    chat_id: int  # the contact's chat — identifies the thread
    direction: str
    sender_id: int | None
    text: str
    ts: int  # unix seconds


@dataclass
class Contact:
    """Durable per-contact memory for one thread."""

    business_connection_id: str
    chat_id: int
    name: str | None = None
    profile: str = ""  # LLM-maintained summary: who they are, tone, key facts
    message_count: int = 0
    updated_at: int = 0
