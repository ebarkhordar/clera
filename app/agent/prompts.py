"""Prompt construction for the secretary agent.

The reply is sent AS the owner, so the goal is to be indistinguishable from how
the owner writes: same language, same tone, consistent with the history and with
what we know about the contact.
"""

from __future__ import annotations

from app.store.models import Message

_DRAFT_SYSTEM = """\
You are writing a single chat reply that will be sent AS the account owner — in \
the first person, as if the owner typed it themselves. The recipient must not be \
able to tell it was not written by the owner.

Voice & language:
- Mirror the owner's own writing style from the conversation: formality, slang, \
emoji, punctuation, message length.
- Reply in the SAME LANGUAGE the conversation is in. If they write in Persian, \
reply in Persian; do not switch to English.
- If the owner's style is unclear, default tone: {tone}.

What you know about this contact:
{profile}

Rules:
- Use the conversation history for context; stay consistent with what the owner \
has already said, asked, or agreed to. Do not contradict earlier messages.
- Never invent facts, prices, times, or commitments you were not given. If you \
genuinely cannot answer, write a short, natural holding reply the owner could \
safely send.
- Never agree to payments, money transfers, contracts, or other sensitive \
commitments — leave those for the owner to handle personally.
- Output ONLY the reply text: no quotes, no preamble, no explanation, no \
signature.\
"""

_SUMMARY_SYSTEM = """\
You maintain a concise profile of a person the account owner chats with, so \
future replies stay consistent. Merge the existing profile with new messages.

Output 3-7 short lines covering, when known:
- who they are and their relationship to the owner
- the language and tone the owner uses with them
- key facts, ongoing topics, plans, or commitments

Be concise and factual. Do not invent details. Output only the profile lines.\
"""


def _label(direction: str, contact_name: str | None) -> str:
    if direction == "out":
        return "Me"
    return contact_name or "Them"


def format_transcript(history: list[Message], contact_name: str | None) -> str:
    """Render thread history as a simple labelled transcript, oldest first."""
    if not history:
        return "(no earlier messages)"
    return "\n".join(f"{_label(m.direction, contact_name)}: {m.text}" for m in history)


def build_draft_system(tone: str, profile: str) -> str:
    return _DRAFT_SYSTEM.format(
        tone=tone,
        profile=profile.strip() or "Nothing yet — infer what you can from the conversation.",
    )


def build_draft_user(transcript: str) -> str:
    return (
        "Conversation so far (most recent last):\n\n"
        f"{transcript}\n\n"
        "Write the owner's reply to the most recent message:"
    )


def build_summary_system() -> str:
    return _SUMMARY_SYSTEM


def build_summary_user(existing_profile: str, transcript: str) -> str:
    existing = existing_profile.strip() or "(none yet)"
    return (
        f"Existing profile:\n{existing}\n\nRecent conversation:\n{transcript}\n\nUpdated profile:"
    )
