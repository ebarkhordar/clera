"""Policy tests: automatic secretary is the default; policy only gates engagement."""

from app.policy.policy import Decision, decide
from app.store.models import Connection, Settings


def conn(**settings_kwargs) -> Connection:
    return Connection(
        business_connection_id="bc1",
        owner_user_id=42,
        can_reply=True,
        settings=Settings(**settings_kwargs),
    )


def test_default_is_auto_send():
    outcome = decide(conn(), sender_user_id=7, local_hour=12)
    assert outcome.decision is Decision.AUTO_SEND


def test_disabled_connection_is_ignored():
    c = conn()
    c.is_enabled = False
    assert decide(c, 7, 12).decision is Decision.IGNORE


def test_no_reply_rights_is_ignored():
    c = conn()
    c.can_reply = False
    assert decide(c, 7, 12).decision is Decision.IGNORE


def test_outside_active_hours_is_ignored():
    c = conn(active_hours=(9, 18))
    assert decide(c, 7, local_hour=3).decision is Decision.IGNORE
    assert decide(c, 7, local_hour=9).decision is Decision.AUTO_SEND


def test_allowlist_restricts_who_is_handled():
    c = conn(allowlist={7})
    assert decide(c, 7, 12).decision is Decision.AUTO_SEND
    assert decide(c, 8, 12).decision is Decision.IGNORE
    assert decide(c, None, 12).decision is Decision.IGNORE


def test_empty_allowlist_handles_everyone():
    assert decide(conn(), 999, 12).decision is Decision.AUTO_SEND


def test_review_mode_routes_to_draft():
    c = conn(auto_send=False)
    assert decide(c, 7, 12).decision is Decision.DRAFT
