from pathlib import Path

import pytest

from girlfriend_generator.photo import (
    PhotoState,
    _slugify,
    render_photo_message,
)


def test_photo_state_disabled_by_default() -> None:
    state = PhotoState()
    assert state.enabled is False
    assert state.can_send() is False
    assert state.remaining() == 5


def test_photo_state_caps_per_session() -> None:
    state = PhotoState(enabled=True)
    assert state.can_send() is True
    state.sent_count = 5
    assert state.can_send() is False
    assert state.remaining() == 0


def test_photo_state_remaining_clamps_negative() -> None:
    state = PhotoState(enabled=True, max_per_session=3)
    state.sent_count = 100
    assert state.remaining() == 0


def test_slugify_handles_korean_and_strips_punctuation() -> None:
    out = _slugify("창문 밖 풍경 — !!!")
    assert "창문" in out
    assert "!" not in out
    assert "—" not in out


def test_slugify_falls_back_when_empty() -> None:
    assert _slugify("###@@@") == "photo"


def test_slugify_truncates() -> None:
    long = "ab" * 50
    assert len(_slugify(long)) <= 40


def test_render_photo_message_includes_clickable_path(tmp_path: Path) -> None:
    photo = tmp_path / "shot.png"
    photo.write_bytes(b"\x89PNG")
    rendered = render_photo_message(photo, "selfie at the desk", remaining=4)
    assert "selfie at the desk" in rendered
    assert f"file://{photo.resolve()}" in rendered
    assert "4장 남음" in rendered


def test_provider_reply_includes_photo_prompt_field() -> None:
    from girlfriend_generator.models import ProviderReply
    reply = ProviderReply(text="hi", typing_seconds=1.0, trace_note="test")
    assert hasattr(reply, "photo_prompt")
    assert reply.photo_prompt == ""


def test_pending_delivery_carries_photo_prompt() -> None:
    from girlfriend_generator.app import PendingDelivery
    delivery = PendingDelivery(
        kind="reply",
        text="hi",
        due_at=0.0,
        trace_note="t",
        photo_prompt="selfie at desk",
    )
    assert delivery.photo_prompt == "selfie at desk"


def test_cli_photos_flag_defaults_off() -> None:
    from girlfriend_generator.cli import build_parser
    args = build_parser().parse_args([])
    assert args.photos is False
    assert args.photos_no_open is False


def test_cli_photos_flag_can_be_enabled() -> None:
    from girlfriend_generator.cli import build_parser
    args = build_parser().parse_args(["--photos", "--photos-no-open"])
    assert args.photos is True
    assert args.photos_no_open is True
