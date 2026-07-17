"""SQLite-backed store — persistent implementation of the store API.

Same function surface as ``memory_store`` so the two are interchangeable via
``app.store.repo``. Uses stdlib ``sqlite3`` (no extra dependency). A single
shared connection guarded by a lock is fine for the bot's workload; move to a
connection pool / Postgres when scaling out.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading

from app.config import settings
from app.store.models import Activity, Connection, Contact, Draft, ManagedBot, Message, Settings

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None

_SCHEMA = """
CREATE TABLE IF NOT EXISTS connections (
    business_connection_id TEXT PRIMARY KEY,
    owner_user_id          INTEGER NOT NULL,
    can_reply              INTEGER NOT NULL DEFAULT 0,
    is_enabled             INTEGER NOT NULL DEFAULT 1,
    spent_usd              REAL    NOT NULL DEFAULT 0,
    tone                   TEXT    NOT NULL,
    tier                   TEXT    NOT NULL,
    auto_send              INTEGER NOT NULL DEFAULT 1,
    active_start           INTEGER NOT NULL DEFAULT 0,
    active_end             INTEGER NOT NULL DEFAULT 24,
    allowlist              TEXT    NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS drafts (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    business_connection_id TEXT    NOT NULL,
    target_chat_id         INTEGER NOT NULL,
    incoming_text          TEXT    NOT NULL,
    proposed_text          TEXT    NOT NULL,
    cost_usd               REAL    NOT NULL,
    status                 TEXT    NOT NULL DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS messages (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    business_connection_id TEXT    NOT NULL,
    chat_id                INTEGER NOT NULL,
    direction              TEXT    NOT NULL,   -- 'in' | 'out'
    sender_id              INTEGER,
    text                   TEXT    NOT NULL,
    ts                     INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_thread
    ON messages (business_connection_id, chat_id, id);

-- Per-client secretary bots we operate (tokens from getManagedBotToken).
-- TODO before hosting real users: encrypt tokens at rest.
CREATE TABLE IF NOT EXISTS managed_bots (
    bot_user_id            INTEGER PRIMARY KEY,
    owner_user_id          INTEGER NOT NULL,
    token                  TEXT    NOT NULL,
    username               TEXT,
    status                 TEXT    NOT NULL DEFAULT 'active',
    created_at             INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS contacts (
    business_connection_id TEXT    NOT NULL,
    chat_id                INTEGER NOT NULL,
    name                   TEXT,
    profile                TEXT    NOT NULL DEFAULT '',
    message_count          INTEGER NOT NULL DEFAULT 0,
    updated_at             INTEGER NOT NULL DEFAULT 0,
    muted                  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (business_connection_id, chat_id)
);

-- Secretary decisions, for /status counts and the daily digest.
CREATE TABLE IF NOT EXISTS activity (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    business_connection_id TEXT    NOT NULL,
    chat_id                INTEGER NOT NULL,
    kind                   TEXT    NOT NULL,  -- replied | drafted | escalated | silent
    snippet                TEXT    NOT NULL,
    ts                     INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_activity_conn_ts
    ON activity (business_connection_id, ts);
"""

# Columns added after first release: applied to pre-existing databases on
# connect (CREATE IF NOT EXISTS never alters an existing table).
_MIGRATIONS = [
    ("connections", "paused", "INTEGER NOT NULL DEFAULT 0"),
    ("connections", "digest_last_day", "TEXT NOT NULL DEFAULT ''"),
    ("contacts", "muted", "INTEGER NOT NULL DEFAULT 0"),
]


def _connect(path: str) -> sqlite3.Connection:
    if path != ":memory:":
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    for table, column, decl in _MIGRATIONS:
        have = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if column not in have:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
    conn.commit()
    return conn


def _c() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = _connect(settings.sqlite_path)
    return _conn


def reset_for_tests(path: str = ":memory:") -> None:
    """Re-point the store at a fresh database (used by tests)."""
    global _conn
    _conn = _connect(path)


# --- Row mapping -----------------------------------------------------------
def _row_to_connection(row: sqlite3.Row) -> Connection:
    return Connection(
        business_connection_id=row["business_connection_id"],
        owner_user_id=row["owner_user_id"],
        can_reply=bool(row["can_reply"]),
        is_enabled=bool(row["is_enabled"]),
        spent_usd=row["spent_usd"],
        settings=Settings(
            tone=row["tone"],
            tier=row["tier"],
            auto_send=bool(row["auto_send"]),
            paused=bool(row["paused"]),
            active_hours=(row["active_start"], row["active_end"]),
            allowlist=set(json.loads(row["allowlist"])),
        ),
    )


def _row_to_draft(row: sqlite3.Row) -> Draft:
    return Draft(
        draft_id=f"d{row['id']}",
        business_connection_id=row["business_connection_id"],
        target_chat_id=row["target_chat_id"],
        incoming_text=row["incoming_text"],
        proposed_text=row["proposed_text"],
        cost_usd=row["cost_usd"],
        status=row["status"],
    )


def _draft_pk(draft_id: str) -> int | None:
    try:
        return int(draft_id.lstrip("d"))
    except ValueError:
        return None


# --- Connections -----------------------------------------------------------
def upsert_connection(
    business_connection_id: str, owner_user_id: int, can_reply: bool
) -> Connection:
    with _lock:
        conn = _c()
        exists = conn.execute(
            "SELECT 1 FROM connections WHERE business_connection_id = ?",
            (business_connection_id,),
        ).fetchone()
        if exists is None:
            defaults = Settings()
            conn.execute(
                "INSERT INTO connections "
                "(business_connection_id, owner_user_id, can_reply, is_enabled, tone, tier, "
                "auto_send) VALUES (?, ?, ?, 1, ?, ?, ?)",
                (
                    business_connection_id,
                    owner_user_id,
                    int(can_reply),
                    defaults.tone,
                    settings.default_tier,
                    int(defaults.auto_send),
                ),
            )
        else:
            conn.execute(
                "UPDATE connections SET owner_user_id = ?, can_reply = ?, is_enabled = 1 "
                "WHERE business_connection_id = ?",
                (owner_user_id, int(can_reply), business_connection_id),
            )
        conn.commit()
    got = get_connection(business_connection_id)
    assert got is not None  # just written
    return got


def disable_connection(business_connection_id: str) -> None:
    with _lock:
        conn = _c()
        conn.execute(
            "UPDATE connections SET is_enabled = 0 WHERE business_connection_id = ?",
            (business_connection_id,),
        )
        conn.commit()


def get_connection(business_connection_id: str) -> Connection | None:
    row = (
        _c()
        .execute(
            "SELECT * FROM connections WHERE business_connection_id = ?",
            (business_connection_id,),
        )
        .fetchone()
    )
    return _row_to_connection(row) if row else None


def list_connections(enabled_only: bool = True) -> list[Connection]:
    sql = "SELECT * FROM connections"
    if enabled_only:
        sql += " WHERE is_enabled = 1"
    return [_row_to_connection(r) for r in _c().execute(sql).fetchall()]


def get_connection_by_owner(owner_user_id: int) -> Connection | None:
    """The owner's active connection (for control-chat commands)."""
    row = (
        _c()
        .execute(
            "SELECT * FROM connections WHERE owner_user_id = ? ORDER BY is_enabled DESC LIMIT 1",
            (owner_user_id,),
        )
        .fetchone()
    )
    return _row_to_connection(row) if row else None


def update_connection_settings(
    business_connection_id: str,
    *,
    auto_send: bool | None = None,
    paused: bool | None = None,
    tone: str | None = None,
    tier: str | None = None,
) -> None:
    """Apply owner-command changes to a connection's settings."""
    sets, args = [], []
    for column, value in (
        ("auto_send", None if auto_send is None else int(auto_send)),
        ("paused", None if paused is None else int(paused)),
        ("tone", tone),
        ("tier", tier),
    ):
        if value is not None:
            sets.append(f"{column} = ?")
            args.append(value)
    if not sets:
        return
    with _lock:
        conn = _c()
        conn.execute(
            f"UPDATE connections SET {', '.join(sets)} WHERE business_connection_id = ?",
            (*args, business_connection_id),
        )
        conn.commit()


def get_digest_marker(business_connection_id: str) -> str:
    row = (
        _c()
        .execute(
            "SELECT digest_last_day FROM connections WHERE business_connection_id = ?",
            (business_connection_id,),
        )
        .fetchone()
    )
    return row["digest_last_day"] if row else ""


def set_digest_marker(business_connection_id: str, day: str) -> None:
    with _lock:
        conn = _c()
        conn.execute(
            "UPDATE connections SET digest_last_day = ? WHERE business_connection_id = ?",
            (day, business_connection_id),
        )
        conn.commit()


# --- Drafts ----------------------------------------------------------------
def create_draft(
    business_connection_id: str,
    target_chat_id: int,
    incoming_text: str,
    proposed_text: str,
    cost_usd: float,
) -> Draft:
    with _lock:
        conn = _c()
        cur = conn.execute(
            "INSERT INTO drafts "
            "(business_connection_id, target_chat_id, incoming_text, proposed_text, cost_usd) "
            "VALUES (?, ?, ?, ?, ?)",
            (business_connection_id, target_chat_id, incoming_text, proposed_text, cost_usd),
        )
        conn.commit()
        pk = cur.lastrowid
    row = _c().execute("SELECT * FROM drafts WHERE id = ?", (pk,)).fetchone()
    return _row_to_draft(row)


def get_draft(draft_id: str) -> Draft | None:
    pk = _draft_pk(draft_id)
    if pk is None:
        return None
    row = _c().execute("SELECT * FROM drafts WHERE id = ?", (pk,)).fetchone()
    return _row_to_draft(row) if row else None


def set_draft_status(draft_id: str, status: str) -> None:
    pk = _draft_pk(draft_id)
    if pk is None:
        return
    with _lock:
        conn = _c()
        conn.execute("UPDATE drafts SET status = ? WHERE id = ?", (status, pk))
        conn.commit()


# --- Metering (informational; no prepaid balance in the MVP) ---------------
def record_spend(business_connection_id: str, cost_usd: float) -> None:
    with _lock:
        conn = _c()
        conn.execute(
            "UPDATE connections SET spent_usd = spent_usd + ? WHERE business_connection_id = ?",
            (cost_usd, business_connection_id),
        )
        conn.commit()


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
        conn = _c()
        conn.execute(
            "INSERT INTO messages "
            "(business_connection_id, chat_id, direction, sender_id, text, ts) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (business_connection_id, chat_id, direction, sender_id, text, ts),
        )
        conn.commit()


def recent_messages(business_connection_id: str, chat_id: int, limit: int) -> list[Message]:
    """Return up to `limit` most recent messages for a thread, oldest first."""
    rows = (
        _c()
        .execute(
            "SELECT * FROM ("
            "  SELECT * FROM messages WHERE business_connection_id = ? AND chat_id = ? "
            "  ORDER BY id DESC LIMIT ?"
            ") ORDER BY id ASC",
            (business_connection_id, chat_id, limit),
        )
        .fetchall()
    )
    return [
        Message(
            business_connection_id=r["business_connection_id"],
            chat_id=r["chat_id"],
            direction=r["direction"],
            sender_id=r["sender_id"],
            text=r["text"],
            ts=r["ts"],
        )
        for r in rows
    ]


# --- Managed bots (per-client secretary bots we operate) -------------------
def _row_to_managed_bot(row: sqlite3.Row) -> ManagedBot:
    return ManagedBot(
        bot_user_id=row["bot_user_id"],
        owner_user_id=row["owner_user_id"],
        token=row["token"],
        username=row["username"],
        status=row["status"],
        created_at=row["created_at"],
    )


def upsert_managed_bot(
    bot_user_id: int,
    owner_user_id: int,
    token: str,
    username: str | None,
    created_at: int,
) -> ManagedBot:
    with _lock:
        conn = _c()
        conn.execute(
            "INSERT INTO managed_bots (bot_user_id, owner_user_id, token, username, "
            "status, created_at) VALUES (?, ?, ?, ?, 'active', ?) "
            "ON CONFLICT(bot_user_id) DO UPDATE SET owner_user_id = excluded.owner_user_id, "
            "token = excluded.token, username = COALESCE(excluded.username, username), "
            "status = 'active'",
            (bot_user_id, owner_user_id, token, username, created_at),
        )
        conn.commit()
    got = get_managed_bot(bot_user_id)
    assert got is not None
    return got


def get_managed_bot(bot_user_id: int) -> ManagedBot | None:
    row = (
        _c().execute("SELECT * FROM managed_bots WHERE bot_user_id = ?", (bot_user_id,)).fetchone()
    )
    return _row_to_managed_bot(row) if row else None


def list_managed_bots(active_only: bool = True) -> list[ManagedBot]:
    sql = "SELECT * FROM managed_bots"
    if active_only:
        sql += " WHERE status = 'active'"
    return [_row_to_managed_bot(r) for r in _c().execute(sql).fetchall()]


def set_managed_bot_status(bot_user_id: int, status: str) -> None:
    with _lock:
        conn = _c()
        conn.execute(
            "UPDATE managed_bots SET status = ? WHERE bot_user_id = ?", (status, bot_user_id)
        )
        conn.commit()


# --- Contacts (durable per-thread memory) ----------------------------------
def bump_contact(business_connection_id: str, chat_id: int, name: str | None, ts: int) -> Contact:
    """Increment the message count (and refresh name/ts) for a contact thread."""
    with _lock:
        conn = _c()
        row = conn.execute(
            "SELECT 1 FROM contacts WHERE business_connection_id = ? AND chat_id = ?",
            (business_connection_id, chat_id),
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO contacts "
                "(business_connection_id, chat_id, name, message_count, updated_at) "
                "VALUES (?, ?, ?, 1, ?)",
                (business_connection_id, chat_id, name, ts),
            )
        else:
            conn.execute(
                "UPDATE contacts SET message_count = message_count + 1, "
                "updated_at = ?, name = COALESCE(?, name) "
                "WHERE business_connection_id = ? AND chat_id = ?",
                (ts, name, business_connection_id, chat_id),
            )
        conn.commit()
    got = get_contact(business_connection_id, chat_id)
    assert got is not None
    return got


def list_contacts(business_connection_id: str) -> list[Contact]:
    rows = (
        _c()
        .execute(
            "SELECT * FROM contacts WHERE business_connection_id = ? ORDER BY message_count DESC",
            (business_connection_id,),
        )
        .fetchall()
    )
    return [_row_to_contact(r) for r in rows]


def set_contact_muted(business_connection_id: str, chat_id: int, muted: bool) -> None:
    with _lock:
        conn = _c()
        conn.execute(
            "UPDATE contacts SET muted = ? WHERE business_connection_id = ? AND chat_id = ?",
            (int(muted), business_connection_id, chat_id),
        )
        conn.commit()


# --- Activity (secretary decisions, for /status and the daily digest) -------
def record_activity(
    business_connection_id: str, chat_id: int, kind: str, snippet: str, ts: int
) -> None:
    with _lock:
        conn = _c()
        conn.execute(
            "INSERT INTO activity (business_connection_id, chat_id, kind, snippet, ts) "
            "VALUES (?, ?, ?, ?, ?)",
            (business_connection_id, chat_id, kind, snippet, ts),
        )
        conn.commit()


def activities_since(business_connection_id: str, since_ts: int) -> list[Activity]:
    rows = (
        _c()
        .execute(
            "SELECT * FROM activity WHERE business_connection_id = ? AND ts >= ? ORDER BY id",
            (business_connection_id, since_ts),
        )
        .fetchall()
    )
    return [
        Activity(
            business_connection_id=r["business_connection_id"],
            chat_id=r["chat_id"],
            kind=r["kind"],
            snippet=r["snippet"],
            ts=r["ts"],
        )
        for r in rows
    ]


def _row_to_contact(row: sqlite3.Row) -> Contact:
    return Contact(
        business_connection_id=row["business_connection_id"],
        chat_id=row["chat_id"],
        name=row["name"],
        profile=row["profile"],
        message_count=row["message_count"],
        updated_at=row["updated_at"],
        muted=bool(row["muted"]),
    )


def get_contact(business_connection_id: str, chat_id: int) -> Contact | None:
    row = (
        _c()
        .execute(
            "SELECT * FROM contacts WHERE business_connection_id = ? AND chat_id = ?",
            (business_connection_id, chat_id),
        )
        .fetchone()
    )
    return _row_to_contact(row) if row else None


def update_contact_profile(business_connection_id: str, chat_id: int, profile: str) -> None:
    with _lock:
        conn = _c()
        conn.execute(
            "UPDATE contacts SET profile = ? WHERE business_connection_id = ? AND chat_id = ?",
            (profile, business_connection_id, chat_id),
        )
        conn.commit()
