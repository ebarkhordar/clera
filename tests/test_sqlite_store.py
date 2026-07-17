"""Round-trip tests for the SQLite store against an in-memory database."""

import pytest
from app.store import sqlite_store as store


@pytest.fixture(autouse=True)
def fresh_db():
    store.reset_for_tests(":memory:")
    yield


def test_connection_upsert_and_fetch():
    conn = store.upsert_connection("bc1", owner_user_id=42, can_reply=True)
    assert conn.owner_user_id == 42
    assert conn.can_reply is True
    assert conn.is_enabled is True

    again = store.get_connection("bc1")
    assert again is not None
    assert again.settings.tone == "friendly and concise"
    assert again.settings.allowlist == set()


def test_upsert_updates_existing_not_duplicates():
    store.upsert_connection("bc1", owner_user_id=42, can_reply=False)
    updated = store.upsert_connection("bc1", owner_user_id=42, can_reply=True)
    assert updated.can_reply is True


def test_disable_connection():
    store.upsert_connection("bc1", owner_user_id=42, can_reply=True)
    store.disable_connection("bc1")
    conn = store.get_connection("bc1")
    assert conn is not None and conn.is_enabled is False


def test_draft_lifecycle():
    store.upsert_connection("bc1", owner_user_id=42, can_reply=True)
    draft = store.create_draft(
        business_connection_id="bc1",
        target_chat_id=999,
        incoming_text="hi",
        proposed_text="hello!",
        cost_usd=0.0012,
    )
    assert draft.draft_id.startswith("d")
    assert draft.status == "pending"

    fetched = store.get_draft(draft.draft_id)
    assert fetched is not None and fetched.proposed_text == "hello!"

    store.set_draft_status(draft.draft_id, "sent")
    assert store.get_draft(draft.draft_id).status == "sent"


def test_record_spend_accumulates():
    store.upsert_connection("bc1", owner_user_id=42, can_reply=True)
    store.record_spend("bc1", 0.01)
    store.record_spend("bc1", 0.02)
    conn = store.get_connection("bc1")
    assert conn is not None and round(conn.spent_usd, 4) == 0.03


def test_get_missing_returns_none():
    assert store.get_connection("nope") is None
    assert store.get_draft("d999") is None
    assert store.get_draft("garbage") is None


def test_message_history_roundtrip_and_thread_isolation():
    store.record_message("bc1", 100, "in", 5, "hi", 1)
    store.record_message("bc1", 100, "out", 42, "hello", 2)
    store.record_message("bc1", 200, "in", 9, "different thread", 3)

    msgs = store.recent_messages("bc1", 100, 10)
    assert [(m.direction, m.text) for m in msgs] == [("in", "hi"), ("out", "hello")]
    # other thread is isolated
    assert [m.text for m in store.recent_messages("bc1", 200, 10)] == ["different thread"]


def test_recent_messages_limit_keeps_latest_oldest_first():
    for i in range(5):
        store.record_message("bc1", 100, "in", 5, f"m{i}", i)
    msgs = store.recent_messages("bc1", 100, 3)
    assert [m.text for m in msgs] == ["m2", "m3", "m4"]


def test_contact_bump_preserves_name_and_counts():
    c = store.bump_contact("bc1", 100, name="Amir", ts=1)
    assert c.message_count == 1 and c.name == "Amir"
    c2 = store.bump_contact("bc1", 100, name=None, ts=2)
    assert c2.message_count == 2 and c2.name == "Amir"  # name not wiped by None


def test_contact_profile_update():
    store.bump_contact("bc1", 100, name="Amir", ts=1)
    store.update_contact_profile("bc1", 100, "friend; casual Persian; buying a phone")
    assert store.get_contact("bc1", 100).profile == "friend; casual Persian; buying a phone"


def test_connection_settings_updates_and_owner_lookup():
    store.upsert_connection("bc1", owner_user_id=42, can_reply=True)
    assert store.get_connection_by_owner(42).business_connection_id == "bc1"
    assert store.get_connection_by_owner(999) is None

    store.update_connection_settings("bc1", auto_send=False, paused=True, tier="best")
    conn = store.get_connection("bc1")
    assert conn.settings.auto_send is False
    assert conn.settings.paused is True
    assert conn.settings.tier == "best"

    assert [c.business_connection_id for c in store.list_connections()] == ["bc1"]
    store.disable_connection("bc1")
    assert store.list_connections() == []
    assert len(store.list_connections(enabled_only=False)) == 1


def test_contact_mute_roundtrip():
    store.bump_contact("bc1", 100, name="Amir", ts=1)
    store.set_contact_muted("bc1", 100, True)
    assert store.get_contact("bc1", 100).muted is True
    assert store.list_contacts("bc1")[0].muted is True
    store.set_contact_muted("bc1", 100, False)
    assert store.get_contact("bc1", 100).muted is False


def test_activity_log_and_digest_marker():
    store.upsert_connection("bc1", owner_user_id=42, can_reply=True)
    store.record_activity("bc1", 100, "replied", "Amir: hey", ts=50)
    store.record_activity("bc1", 100, "silent", "Amir: ok", ts=60)
    store.record_activity("bc2", 200, "replied", "other conn", ts=70)

    acts = store.activities_since("bc1", 55)
    assert [(a.kind, a.snippet) for a in acts] == [("silent", "Amir: ok")]
    assert len(store.activities_since("bc1", 0)) == 2

    assert store.get_digest_marker("bc1") == ""
    store.set_digest_marker("bc1", "2026-07-17")
    assert store.get_digest_marker("bc1") == "2026-07-17"
