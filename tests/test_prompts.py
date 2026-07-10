"""Tests for transcript/prompt construction (language- and label-agnostic)."""

from app.agent.prompts import build_draft_system, format_transcript
from app.store.models import Message


def _msg(direction: str, text: str) -> Message:
    return Message("bc1", 100, direction, 1, text, 0)


def test_transcript_labels_owner_and_contact():
    history = [_msg("in", "سلام"), _msg("out", "سلام عزیزم"), _msg("in", "خوبی؟")]
    t = format_transcript(history, "Amir")
    assert "Amir: سلام" in t
    assert "Me: سلام عزیزم" in t
    # order preserved, oldest first
    assert t.index("Amir: سلام") < t.index("Me: سلام عزیزم") < t.index("Amir: خوبی")


def test_transcript_falls_back_to_them_without_name():
    t = format_transcript([_msg("in", "hi")], None)
    assert t == "Them: hi"


def test_empty_transcript():
    assert format_transcript([], "Amir") == "(no earlier messages)"


def test_draft_system_includes_profile_and_tone():
    sys = build_draft_system(tone="warm and brief", profile="close friend; casual Persian")
    assert "close friend; casual Persian" in sys
    assert "warm and brief" in sys


def test_draft_system_handles_empty_profile():
    sys = build_draft_system(tone="warm", profile="")
    assert "Nothing yet" in sys
