"""Tests for transcript/prompt construction (language- and label-agnostic)."""

from app.agent.prompts import (
    build_draft_system,
    format_exemplars,
    format_transcript,
    mine_exemplars,
)
from app.store.models import Message


def test_mine_exemplars_pairs_in_then_out():
    history = [
        Message("bc", 1, "in", 1, "سلام", 0),
        Message("bc", 1, "out", 2, "سلام عزیزم", 0),
        Message("bc", 1, "out", 2, "چطوری؟", 0),
        Message("bc", 1, "in", 1, "خوبم", 0),
    ]
    assert mine_exemplars(history) == [("سلام", "سلام عزیزم")]


def test_mine_exemplars_samples_across_long_history():
    history = []
    for i in range(40):
        history.append(Message("bc", 1, "in", 1, f"q{i}", 0))
        history.append(Message("bc", 1, "out", 2, f"a{i}", 0))
    pairs = mine_exemplars(history, max_pairs=6)
    assert len(pairs) == 6
    assert pairs[0] == ("q0", "a0")  # oldest voice represented
    assert int(pairs[-1][0][1:]) > 30  # ...and recent voice too


def test_exemplars_render_into_system_prompt():
    system = build_draft_system("friendly", "profile", [("hi", "hey!")])
    assert 'They said: "hi" → Owner replied: "hey!"' in system
    assert format_exemplars([]) == ""


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
