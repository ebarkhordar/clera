"""Tests for the agent's reply/silent/notify action protocol."""

from app.agent.secretary import parse_action


def test_plain_text_is_a_reply():
    assert parse_action("سلام! فردا می‌بینمت") == ("reply", "سلام! فردا می‌بینمت")


def test_silent_marker():
    assert parse_action("[SILENT]") == ("silent", "")
    assert parse_action("  [SILENT]  ") == ("silent", "")


def test_notify_marker_keeps_the_note_for_the_owner():
    action, note = parse_action("[NOTIFY] They're asking you to confirm the $500 payment.")
    assert action == "notify"
    assert note == "They're asking you to confirm the $500 payment."


def test_notify_marker_without_note():
    assert parse_action("[NOTIFY]") == ("notify", "")


def test_markers_only_count_at_the_start():
    action, text = parse_action("I'll send it. [SILENT] is what I'd say otherwise.")
    assert action == "reply"
    assert text.startswith("I'll send it.")
