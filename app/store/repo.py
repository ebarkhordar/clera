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
get_connection_by_owner = _impl.get_connection_by_owner
list_connections = _impl.list_connections
update_connection_settings = _impl.update_connection_settings
get_digest_marker = _impl.get_digest_marker
set_digest_marker = _impl.set_digest_marker
list_contacts = _impl.list_contacts
set_contact_muted = _impl.set_contact_muted
record_activity = _impl.record_activity
activities_since = _impl.activities_since
create_draft = _impl.create_draft
get_draft = _impl.get_draft
set_draft_status = _impl.set_draft_status
record_spend = _impl.record_spend
record_message = _impl.record_message
upsert_managed_bot = _impl.upsert_managed_bot
get_managed_bot = _impl.get_managed_bot
list_managed_bots = _impl.list_managed_bots
set_managed_bot_status = _impl.set_managed_bot_status
recent_messages = _impl.recent_messages
bump_contact = _impl.bump_contact
get_contact = _impl.get_contact
update_contact_profile = _impl.update_contact_profile
