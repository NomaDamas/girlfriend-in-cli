"""YouTube source normalization for persona generation.

This module is intentionally adapter-shaped: it validates YouTube URLs and
combines metadata, captions, STT transcripts, and research notes into a compact
prompt context without downloading media or storing raw audio locally.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlparse


YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "music.youtube.com",
}


@dataclass(frozen=True)
class YouTubeSource:
    url: str
    video_id: str


@dataclass(frozen=True)
class YouTubeIngestInput:
    url: str
    title: str = ""
    description: str = ""
    channel: str = ""
    captions: str = ""
    stt_transcript: str = ""
    research_notes: list[str] = field(default_factory=list)


def parse_youtube_url(url: str) -> YouTubeSource:
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower()
    if host not in YOUTUBE_HOSTS:
        raise ValueError("Not a supported YouTube URL.")

    video_id = ""
    if host == "youtu.be":
        video_id = parsed.path.strip("/").split("/", 1)[0]
    elif parsed.path == "/watch":
        video_id = parse_qs(parsed.query).get("v", [""])[0]
    elif parsed.path.startswith("/shorts/") or parsed.path.startswith("/embed/"):
        video_id = parsed.path.strip("/").split("/", 1)[1]

    if not video_id:
        raise ValueError("YouTube URL must point to a specific video.")
    return YouTubeSource(url=url.strip(), video_id=video_id)


def is_youtube_url(value: str) -> bool:
    try:
        parse_youtube_url(value)
        return True
    except ValueError:
        return False


def build_youtube_persona_context(source: YouTubeIngestInput) -> str:
    parsed = parse_youtube_url(source.url)
    blocks = [
        "=== YouTube persona source ===",
        f"URL: {parsed.url}",
        f"Video ID: {parsed.video_id}",
    ]
    if source.title:
        blocks.append(f"Title: {source.title}")
    if source.channel:
        blocks.append(f"Channel: {source.channel}")
    if source.description:
        blocks.append("Description:\n" + _trim(source.description, 1200))
    if source.captions:
        blocks.append("Caption evidence:\n" + _trim(source.captions, 3500))
    if source.stt_transcript:
        blocks.append("STT fallback evidence:\n" + _trim(source.stt_transcript, 3500))
    if source.research_notes:
        blocks.append("Deep research notes:\n" + "\n".join(f"- {_trim(note, 600)}" for note in source.research_notes))
    blocks.append(
        "Synthesis instructions: infer speaking rhythm, repeated phrases, humor, warmth, "
        "teasing, directness, and texting style from the evidence above. Keep source "
        "attribution in context_summary; do not claim private facts."
    )
    return "\n\n".join(blocks)


def _trim(value: str, limit: int) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."
