"""Import a Telegram Desktop chat export into Clera's memory.

The Bot API cannot read chat history, so live collection starts from zero.
Telegram Desktop can export *years* of it: Settings → Advanced → Export
Telegram data (JSON). Feeding that export in gives every contact a deep
history and voice profile in one shot:

    python -m app.import_export path/to/result.json
    python -m app.import_export result.json --owner-id 123456789   # no connection yet

Handles both shapes of export: a single chat (one object with "messages")
and a full export ({"chats": {"list": [...]}}). Only personal chats are
imported. Re-running is safe — already-recorded messages are skipped, so an
export can overlap with live-collected history.

Media messages are recorded as stubs ("[voice] …", "[photo] …") so threads
keep their shape; transcripts for exported voice files can be added later.
"""

from __future__ import annotations

import argparse
import json

from app.store import repo as store


def flatten_text(text: object) -> str:
    """Export 'text' is a string, or a list of strings and entity dicts."""
    if isinstance(text, str):
        return text
    if isinstance(text, list):
        parts = []
        for part in text:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                parts.append(str(part.get("text", "")))
        return "".join(parts)
    return ""


def sender_id_of(message: dict) -> int | None:
    """'from_id' looks like 'user123456789' (channels use other prefixes)."""
    raw = str(message.get("from_id", ""))
    if raw.startswith("user"):
        suffix = raw.removeprefix("user")
        if suffix.isdigit():
            return int(suffix)
    return None


def message_row(message: dict, owner_id: int) -> tuple[str, int, int] | None:
    """Map one export message to (text, ts, sender_id-ish direction data).

    Returns (text, ts, sender_id) or None when the message carries nothing
    worth recording. Media become stubs so the thread keeps its rhythm.
    """
    if message.get("type") != "message":
        return None
    ts = int(message.get("date_unixtime") or 0)
    if ts <= 0:
        return None
    sender = sender_id_of(message)
    if sender is None:
        return None

    text = flatten_text(message.get("text"))
    media = message.get("media_type", "")
    if message.get("photo"):
        text = f"[photo] (caption: {text})" if text else "[photo]"
    elif media == "voice_message":
        text = f"[voice] {text}".strip() if text else "[voice] (from export, no transcript)"
    elif media == "video_message":
        text = "[video message]"
    elif media == "sticker":
        text = f"[sticker {message.get('sticker_emoji', '')}]".strip()
    if not text:
        return None
    return text, ts, sender


def iter_personal_chats(data: dict) -> list[dict]:
    # Full-account exports nest chats under "chats.list"; a single-chat export
    # is itself the chat object.
    chats = data.get("chats", {}).get("list", []) if "chats" in data else [data]
    return [c for c in chats if c.get("type") in ("personal_chat", "private")]


def run(path: str, connection_id: str | None, owner_id: int | None) -> None:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)

    conns = store.list_connections(enabled_only=False)
    if connection_id is None:
        if not conns:
            raise SystemExit(
                "No business connection in the database yet — pass --connection "
                "and --owner-id explicitly."
            )
        connection_id = conns[0].business_connection_id
    if owner_id is None:
        conn = store.get_connection(connection_id)
        if conn is None:
            raise SystemExit(f"Unknown connection {connection_id}; pass --owner-id too.")
        owner_id = conn.owner_user_id

    chats = iter_personal_chats(data)
    if not chats:
        raise SystemExit("No personal chats found in this export.")

    grand_new = grand_skipped = 0
    for chat in chats:
        chat_id = int(chat.get("id", 0))
        name = chat.get("name") or None
        if chat_id <= 0:
            continue
        new = skipped = 0
        for message in chat.get("messages", []):
            row = message_row(message, owner_id)
            if row is None:
                continue
            text, ts, sender = row
            if store.has_message(connection_id, chat_id, ts, text):
                skipped += 1
                continue
            store.record_message(
                business_connection_id=connection_id,
                chat_id=chat_id,
                direction="out" if sender == owner_id else "in",
                sender_id=sender,
                text=text,
                ts=ts,
            )
            store.bump_contact(connection_id, chat_id, name=name, ts=ts)
            new += 1
        grand_new += new
        grand_skipped += skipped
        print(f"✓ {name or chat_id}: {new} imported, {skipped} already known")

    print(f"\nImport complete: {grand_new} new messages, {grand_skipped} duplicates skipped.")
    if grand_new:
        print("Next: python -m app.backfill --force   (rebuild profiles from the fuller history)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="result.json from Telegram Desktop export")
    parser.add_argument("--connection", help="business_connection_id (default: first known)")
    parser.add_argument("--owner-id", type=int, help="your numeric Telegram id")
    args = parser.parse_args()
    run(args.path, args.connection, args.owner_id)


if __name__ == "__main__":
    main()
