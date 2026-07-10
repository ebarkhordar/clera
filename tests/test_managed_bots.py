"""Managed-bot registry (sqlite store) and provisioning helpers."""

import pytest
from app.handlers.managed import build_creation_link, suggest_username
from app.store import sqlite_store as store


@pytest.fixture(autouse=True)
def fresh_db():
    store.reset_for_tests(":memory:")
    yield


def test_managed_bot_roundtrip():
    bot = store.upsert_managed_bot(
        bot_user_id=111, owner_user_id=42, token="111:AAA", username="amir_clera_bot", created_at=5
    )
    assert bot.status == "active"

    got = store.get_managed_bot(111)
    assert got is not None and got.token == "111:AAA" and got.owner_user_id == 42


def test_upsert_refreshes_token_and_keeps_username():
    store.upsert_managed_bot(111, 42, "111:AAA", "amir_clera_bot", created_at=5)
    updated = store.upsert_managed_bot(111, 42, "111:BBB", None, created_at=9)
    assert updated.token == "111:BBB"
    assert updated.username == "amir_clera_bot"  # not wiped by None


def test_list_filters_revoked_by_default():
    store.upsert_managed_bot(111, 42, "111:AAA", "a_bot", created_at=1)
    store.upsert_managed_bot(222, 43, "222:AAA", "b_bot", created_at=2)
    store.set_managed_bot_status(222, "revoked")

    assert [b.bot_user_id for b in store.list_managed_bots()] == [111]
    assert len(store.list_managed_bots(active_only=False)) == 2


def test_creation_link_format():
    link = build_creation_link("CleraManagerBot", "amir_clera_bot", "Amir's secretary")
    assert link == "https://t.me/newbot/CleraManagerBot/amir_clera_bot?name=Amir%27s%20secretary"


def test_suggested_username_is_valid():
    name = suggest_username("Éhsan!", 987654)
    assert name.endswith("bot")
    assert 5 <= len(name) <= 32
    assert all(c.isalnum() or c == "_" for c in name)


def test_suggested_username_handles_empty_name():
    assert suggest_username(None, 1).endswith("bot")
