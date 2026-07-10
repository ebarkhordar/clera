"""Policy engine: decide what to do with an incoming business message.

The product is a fully automatic secretary, so the default decision is
AUTO_SEND. Policy only decides *whether the agent engages at all* (connection
enabled, reply rights, active hours, optional contact allowlist) and which mode
applies. Whether a given message is actually answered, left alone, or escalated
to the owner is the *agent's* decision (see ``app.agent.secretary``), made from
the conversation itself.

DRAFT survives as an opt-in review mode (``auto_send = False``) for owners who
want to approve everything; it is no longer the default. This module centralizes
the rules so tightening/loosening them is one place.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.store.models import Connection


class Decision(Enum):
    AUTO_SEND = "auto_send"  # default: the agent replies as the owner, no approval
    DRAFT = "draft"  # opt-in review mode: propose to owner, wait for approval
    IGNORE = "ignore"  # do nothing (disabled, no rights, outside hours, not allowlisted)


@dataclass(frozen=True)
class PolicyOutcome:
    decision: Decision
    reason: str


def is_stale(message_ts: int, now_ts: int, max_age_s: int) -> bool:
    """True when a message is too old to answer (e.g. from a queued backlog).

    Telegram re-delivers updates that arrived while the bot was offline. The
    owner has usually already handled those chats themselves, so replying late
    would talk over a conversation that moved on — record them for history, but
    never answer. A zero/unknown timestamp is treated as fresh.
    """
    if max_age_s <= 0 or message_ts <= 0:
        return False
    return now_ts - message_ts > max_age_s


def decide(conn: Connection, sender_user_id: int | None, local_hour: int) -> PolicyOutcome:
    if not conn.is_enabled:
        return PolicyOutcome(Decision.IGNORE, "connection disabled")
    if not conn.can_reply:
        return PolicyOutcome(Decision.IGNORE, "no reply permission on connection")

    start, end = conn.settings.active_hours
    if not (start <= local_hour < end):
        return PolicyOutcome(Decision.IGNORE, "outside active hours")

    # A non-empty allowlist restricts which contacts the secretary handles at
    # all; everyone else stays untouched for the owner to answer personally.
    if conn.settings.allowlist and sender_user_id not in conn.settings.allowlist:
        return PolicyOutcome(Decision.IGNORE, "contact not in allowlist")

    if conn.settings.auto_send:
        return PolicyOutcome(Decision.AUTO_SEND, "automatic secretary (default)")

    return PolicyOutcome(Decision.DRAFT, "review mode enabled by owner")
