from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .models import ChatMessage, Persona


def export_session(
    session_dir: Path,
    persona: Persona,
    messages: Iterable[ChatMessage],
    relationship_state: dict | None = None,
) -> tuple[Path, Path]:
    session_dir.mkdir(parents=True, exist_ok=True)
    messages = list(messages)
    timestamp = messages[-1].created_at.strftime("%Y%m%d-%H%M%S") if messages else "empty"
    base_name = _build_unique_base_name(
        session_dir=session_dir,
        base_name=f"{timestamp}-{slugify(persona.name)}",
    )
    json_path = session_dir / f"{base_name}.json"
    markdown_path = session_dir / f"{base_name}.md"

    payload = {
        "persona": {
            "name": persona.name,
            "age": persona.age,
            "relationship_mode": persona.relationship_mode,
            "background": persona.background,
            "situation": persona.situation,
            "texting_style": persona.texting_style,
            "context_summary": persona.context_summary,
            "interests": persona.interests,
            "soft_spots": persona.soft_spots,
            "boundaries": persona.boundaries,
            "style_profile": {
                "warmth": persona.style_profile.warmth,
                "teasing": persona.style_profile.teasing,
                "directness": persona.style_profile.directness,
                "message_length": persona.style_profile.message_length,
                "emoji_level": persona.style_profile.emoji_level,
                "signature_phrases": persona.style_profile.signature_phrases,
            },
        },
        "relationship_state": relationship_state or {},
        "messages": [
            {
                "role": message.role,
                "text": message.text,
                "created_at": message.created_at.isoformat(),
            }
            for message in messages
        ],
    }
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    markdown_path.write_text(
        render_markdown(persona=persona, messages=messages, relationship_state=relationship_state),
        encoding="utf-8",
    )
    return json_path, markdown_path


def _build_unique_base_name(session_dir: Path, base_name: str) -> str:
    candidate = base_name
    suffix = 2
    while (session_dir / f"{candidate}.json").exists() or (
        session_dir / f"{candidate}.md"
    ).exists():
        candidate = f"{base_name}-{suffix}"
        suffix += 1
    return candidate


def render_markdown(persona: Persona, messages: list[ChatMessage], relationship_state: dict | None = None) -> str:
    relation = relationship_state or {}
    lines = [
        f"# Session with {persona.name}",
        "",
        f"- Relationship mode: {relation.get('label', persona.relationship_mode)}",
        f"- Relationship summary: {relation.get('summary', persona.situation)}",
        f"- Situation: {relation.get('situation', persona.situation)}",
        "",
        "## Transcript",
        "",
    ]
    for message in messages:
        timestamp = message.created_at.strftime("%H:%M:%S")
        lines.append(f"**{message.role}** `{timestamp}`")
        lines.append("")
        lines.append(message.text)
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def load_session_messages(path: Path) -> list[ChatMessage]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return _parse_messages(payload)


def load_session_snapshot(path: Path) -> tuple[list[ChatMessage], dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return _parse_messages(payload), dict(payload.get("relationship_state", {}))


def _parse_messages(payload: dict) -> list[ChatMessage]:
    messages = []
    for item in payload.get("messages", []):
        created_at = datetime.fromisoformat(item["created_at"])
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        messages.append(
            ChatMessage(
                role=item["role"],
                text=item["text"],
                created_at=created_at,
            )
        )
    return messages


def slugify(value: str) -> str:
    normalized = "".join(char.lower() if char.isalnum() else "-" for char in value)
    while "--" in normalized:
        normalized = normalized.replace("--", "-")
    return normalized.strip("-") or "session"
