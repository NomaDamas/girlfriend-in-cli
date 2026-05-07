"""Tests for user-message read receipts."""

from datetime import datetime, timezone
from pathlib import Path

from girlfriend_generator.engine import ConversationSession
from girlfriend_generator.models import ChatMessage
from girlfriend_generator.personas import load_persona
from girlfriend_generator.session_io import _parse_messages, _serialize_message


def _persona():
    return load_persona(Path("personas/dua-international.json"))


def test_new_user_message_starts_as_sent() -> None:
    session = ConversationSession(persona=_persona())
    session.add_user_message("hey")

    last = next(message for message in reversed(session.messages) if message.role == "user")

    assert last.read_state == "sent"
    assert last.seen_at is None


def test_mark_progresses_sent_to_delivered_to_seen() -> None:
    session = ConversationSession(persona=_persona())
    session.add_user_message("hi")

    session.mark_last_user_message("delivered")
    last = next(message for message in reversed(session.messages) if message.role == "user")
    assert last.read_state == "delivered"

    session.mark_last_user_message("seen")
    last = next(message for message in reversed(session.messages) if message.role == "user")
    assert last.read_state == "seen"
    assert last.seen_at is not None


def test_mark_does_not_regress() -> None:
    session = ConversationSession(persona=_persona())
    session.add_user_message("hi")

    session.mark_last_user_message("seen")
    session.mark_last_user_message("sent")

    last = next(message for message in reversed(session.messages) if message.role == "user")
    assert last.read_state == "seen"


def test_mark_only_touches_latest_user_message() -> None:
    session = ConversationSession(persona=_persona())
    session.add_user_message("first")
    session.add_assistant_message("hi", schedule_nudge=False)
    session.add_user_message("second")

    session.mark_last_user_message("seen")

    user_messages = [message for message in session.messages if message.role == "user"]
    assert user_messages[0].read_state == "sent"
    assert user_messages[1].read_state == "seen"


def test_seen_delay_is_persona_aware_and_within_bounds() -> None:
    session = ConversationSession(persona=_persona())

    samples = [session.seen_delay_seconds() for _ in range(20)]

    assert all(0.4 <= sample <= 6.0 for sample in samples)


def test_seen_delay_warm_persona_faster_than_cold() -> None:
    persona = _persona()
    persona.style_profile.warmth = 0.95
    persona.style_profile.directness = 0.9
    warm = ConversationSession(persona=persona)

    cold = ConversationSession(persona=_persona())
    cold.persona.style_profile.warmth = 0.05
    cold.persona.style_profile.directness = 0.1
    cold.mood.shift("sulky", intensity=0.9)

    warm_avg = sum(warm.seen_delay_seconds() for _ in range(40)) / 40
    cold_avg = sum(cold.seen_delay_seconds() for _ in range(40)) / 40

    assert warm_avg < cold_avg, (warm_avg, cold_avg)


def test_session_io_roundtrip_preserves_read_state() -> None:
    message = ChatMessage(
        role="user",
        text="hi",
        created_at=datetime(2026, 4, 30, 12, 0, tzinfo=timezone.utc),
        read_state="seen",
        seen_at=datetime(2026, 4, 30, 12, 0, 2, tzinfo=timezone.utc),
    )
    payload = {"messages": [_serialize_message(message)]}

    parsed = _parse_messages(payload)

    assert parsed[0].read_state == "seen"
    assert parsed[0].seen_at is not None
    assert parsed[0].seen_at.tzinfo is not None


def test_session_io_legacy_messages_default_to_sent() -> None:
    payload = {
        "messages": [
            {
                "role": "user",
                "text": "legacy",
                "created_at": datetime(2026, 4, 1, tzinfo=timezone.utc).isoformat(),
            }
        ]
    }

    parsed = _parse_messages(payload)

    assert parsed[0].read_state == "sent"
