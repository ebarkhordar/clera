"""Daily digest: what the secretary did, summarized to the owner's control chat.

The digest is the trust mechanism of automatic mode — the owner sees every
decision (replied / escalated / stayed silent / drafted) once a day without
being interrupted per message. ``build_digest`` is pure and unit-tested;
``digest_loop`` is a lightweight scheduler (no extra dependency) that checks
every few minutes whether a connection is due today's digest.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime

from app.config import settings
from app.store import repo as store
from app.store.models import Activity

log = logging.getLogger(__name__)

_KIND_LABELS = [
    ("replied", "↩️ Replied"),
    ("drafted", "✉️ Drafted for approval"),
    ("escalated", "👋 Escalated to you"),
    ("silent", "🤫 Stayed silent"),
]
_MAX_LINES = 5  # per section; keep the digest one screen tall


def build_digest(activities: list[Activity], day_label: str) -> str | None:
    """Render the digest text, or None when there is nothing to report."""
    if not activities:
        return None

    lines = [f"📊 *Clera digest — {day_label}*"]
    total = len(activities)
    chats = len({a.chat_id for a in activities})
    lines.append(f"Handled {total} message{'s' if total != 1 else ''} across {chats} chat(s).\n")

    for kind, label in _KIND_LABELS:
        matching = [a for a in activities if a.kind == kind]
        if not matching:
            continue
        lines.append(f"{label} ({len(matching)}):")
        for a in matching[:_MAX_LINES]:
            lines.append(f"  • {a.snippet}")
        if len(matching) > _MAX_LINES:
            lines.append(f"  … and {len(matching) - _MAX_LINES} more")
        lines.append("")

    return "\n".join(lines).rstrip()


async def send_digest(bot, conn, *, since_ts: int | None = None) -> bool:
    """Build and send a digest for one connection. True if something was sent."""
    now = time.time()
    since = since_ts if since_ts is not None else int(now - 86400)
    activities = store.activities_since(conn.business_connection_id, since)
    day_label = datetime.fromtimestamp(now).strftime("%a %d %b")
    text = build_digest(activities, day_label)
    if text is None:
        return False
    control = settings.control_chat_id or conn.owner_user_id
    await bot.send_message(chat_id=control, text=text, parse_mode="Markdown")
    return True


async def digest_loop(bot) -> None:
    """Background task: send each connection its digest once a day at digest_hour."""
    if settings.digest_hour < 0:
        return
    while True:
        await asyncio.sleep(300)
        try:
            now = datetime.now()
            if now.hour < settings.digest_hour:
                continue
            today = now.strftime("%Y-%m-%d")
            for conn in store.list_connections():
                if store.get_digest_marker(conn.business_connection_id) == today:
                    continue
                sent = await send_digest(bot, conn)
                store.set_digest_marker(conn.business_connection_id, today)
                if sent:
                    log.info("Sent daily digest for %s", conn.business_connection_id)
        except Exception:
            log.exception("Digest loop iteration failed")
