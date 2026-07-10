"""Policy engine: decide what to do with an incoming business message.

Safety-first defaults for v1: everything becomes a DRAFT for the owner to approve.
Auto-send is only ever considered when the owner explicitly enabled it AND the
contact is allowlisted AND we're inside active hours — but the MVP handler still
routes to draft, keeping a human in the loop. This module centralizes the rules
so tightening/loosening them is one place.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.store.models import Connection


class Decision(Enum):
    DRAFT = "draft"  # propose to owner, wait for approval
    AUTO_SEND = "auto_send"  # send without approval (opt-in, allowlisted)
    IGNORE = "ignore"  # do nothing (e.g. outside active hours, no reply rights)


@dataclass(frozen=True)
class PolicyOutcome:
    decision: Decision
    reason: str


def decide(conn: Connection, sender_user_id: int | None, local_hour: int) -> PolicyOutcome:
    if not conn.is_enabled:
        return PolicyOutcome(Decision.IGNORE, "connection disabled")
    if not conn.can_reply:
        return PolicyOutcome(Decision.IGNORE, "no reply permission on connection")

    start, end = conn.settings.active_hours
    if not (start <= local_hour < end):
        return PolicyOutcome(Decision.IGNORE, "outside active hours")

    allowlisted = sender_user_id is not None and sender_user_id in conn.settings.allowlist
    if conn.settings.auto_send and allowlisted:
        return PolicyOutcome(Decision.AUTO_SEND, "auto-send enabled + allowlisted")

    return PolicyOutcome(Decision.DRAFT, "default draft-first")
