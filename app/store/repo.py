"""Storage selector.

Call sites import this module (``from app.store import repo as store``) and get
the backend chosen by ``STORE_BACKEND`` — persistent SQLite by default, or the
in-memory store for tests/ephemeral runs. Both implement the same API.
"""

from __future__ import annotations

from app.config import settings

if settings.store_backend == "memory":
    from app.store import memory_store as _impl
else:
    from app.store import sqlite_store as _impl

upsert_connection = _impl.upsert_connection
disable_connection = _impl.disable_connection
get_connection = _impl.get_connection
create_draft = _impl.create_draft
get_draft = _impl.get_draft
set_draft_status = _impl.set_draft_status
record_spend = _impl.record_spend
record_message = _impl.record_message
recent_messages = _impl.recent_messages
bump_contact = _impl.bump_contact
get_contact = _impl.get_contact
update_contact_profile = _impl.update_contact_profile
