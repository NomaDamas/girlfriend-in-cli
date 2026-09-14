"""Tests for YouTube persona source normalization."""

import pytest

from girlfriend_generator.youtube_ingest import (
    YouTubeIngestInput,
    build_youtube_persona_context,
    is_youtube_url,
    parse_youtube_url,
)


def test_parse_watch_url_extracts_video_id() -> None:
    source = parse_youtube_url("https://www.youtube.com/watch?v=abc123XYZ_9")
    assert source.video_id == "abc123XYZ_9"


def test_parse_short_url_extracts_video_id() -> None:
    source = parse_youtube_url("https://youtu.be/abc123XYZ_9")
    assert source.video_id == "abc123XYZ_9"


def test_parse_shorts_url_extracts_video_id() -> None:
    source = parse_youtube_url("https://www.youtube.com/shorts/short123")
    assert source.video_id == "short123"


def test_parse_rejects_non_youtube_url() -> None:
    with pytest.raises(ValueError):
        parse_youtube_url("https://example.com/watch?v=abc")


def test_is_youtube_url_handles_invalid_values() -> None:
    assert is_youtube_url("https://www.youtube.com/watch?v=abc") is True
    assert is_youtube_url("not a url") is False


def test_build_context_includes_captions_stt_and_research_notes() -> None:
    context = build_youtube_persona_context(
        YouTubeIngestInput(
            url="https://www.youtube.com/watch?v=abc123",
            title="Interview with Mina",
            channel="Mina Channel",
            description="A long interview about work and love.",
            captions="안녕하세요. 저는 천천히 말하는 편이에요.",
            stt_transcript="음... 그러니까 저는 농담을 자주 해요.",
            research_notes=["Public profile says she likes cafes."],
        )
    )

    assert "Video ID: abc123" in context
    assert "Caption evidence" in context
    assert "STT fallback evidence" in context
    assert "Deep research notes" in context
    assert "do not claim private facts" in context
