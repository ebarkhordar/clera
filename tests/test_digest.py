"""Digest rendering tests (pure function)."""

from app.digest import build_digest
from app.store.models import Activity


def act(kind: str, snippet: str, chat_id: int = 1) -> Activity:
    return Activity(
        business_connection_id="bc1", chat_id=chat_id, kind=kind, snippet=snippet, ts=100
    )


def test_empty_day_renders_nothing():
    assert build_digest([], "Mon 1 Jan") is None


def test_counts_and_sections():
    text = build_digest(
        [
            act("replied", "Amir: launch date?"),
            act("replied", "Narges: vpn help", chat_id=2),
            act("escalated", "Zeynab: money for the backpack", chat_id=3),
            act("silent", "Amir: ok"),
        ],
        "Mon 1 Jan",
    )
    assert text is not None
    assert "Handled 4 messages across 3 chat(s)" in text
    assert "↩️ Replied (2):" in text
    assert "👋 Escalated to you (1):" in text
    assert "🤫 Stayed silent (1):" in text
    assert "Zeynab: money for the backpack" in text


def test_long_sections_truncate():
    many = [act("replied", f"contact {i}: msg", chat_id=i) for i in range(9)]
    text = build_digest(many, "Mon 1 Jan")
    assert "… and 4 more" in text


def test_absent_kinds_are_omitted():
    text = build_digest([act("replied", "Amir: hey")], "Mon 1 Jan")
    assert "Drafted" not in text and "Escalated" not in text and "silent" not in text
