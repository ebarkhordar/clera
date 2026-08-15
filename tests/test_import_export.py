"""Telegram Desktop export parsing (pure functions, no store)."""

from app.import_export import flatten_text, iter_personal_chats, message_row, sender_id_of

OWNER = 42


def msg(**kwargs):
    base = {"type": "message", "date_unixtime": "1700000000", "from_id": "user7", "text": "hi"}
    base.update(kwargs)
    return base


def test_flatten_plain_and_entity_text():
    assert flatten_text("سلام") == "سلام"
    assert (
        flatten_text(["see ", {"type": "link", "text": "https://x.y"}, " ok"])
        == "see https://x.y ok"
    )
    assert flatten_text(None) == ""


def test_sender_parsing():
    assert sender_id_of({"from_id": "user123"}) == 123
    assert sender_id_of({"from_id": "channel55"}) is None
    assert sender_id_of({}) is None


def test_message_row_direction_data():
    text, ts, sender = message_row(msg(from_id=f"user{OWNER}", text="من"), OWNER)
    assert (text, ts, sender) == ("من", 1700000000, OWNER)


def test_service_messages_and_empty_are_skipped():
    assert message_row(msg(type="service"), OWNER) is None
    assert message_row(msg(text=""), OWNER) is None
    assert message_row(msg(date_unixtime="0"), OWNER) is None


def test_media_become_stubs():
    text, _, _ = message_row(msg(text="", media_type="voice_message"), OWNER)
    assert text == "[voice] (from export, no transcript)"
    text, _, _ = message_row(msg(text="نگاه کن", photo="photos/x.jpg"), OWNER)
    assert text == "[photo] (caption: نگاه کن)"
    text, _, _ = message_row(msg(text="", media_type="sticker", sticker_emoji="😂"), OWNER)
    assert text == "[sticker 😂]"


def test_chat_iteration_both_shapes():
    single = {"type": "personal_chat", "id": 1, "messages": []}
    assert iter_personal_chats(single) == [single]

    full = {"chats": {"list": [single, {"type": "public_channel", "id": 2}]}}
    assert iter_personal_chats(full) == [single]
