from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .models import ChatMessage, Persona


def export_session(
    session_dir: Path,
    persona: Persona,
    messages: Iterable[ChatMessage],
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
        render_markdown(persona=persona, messages=messages),
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


def render_markdown(persona: Persona, messages: list[ChatMessage]) -> str:
    lines = [
        f"# Session with {persona.name}",
        "",
        f"- Relationship mode: {persona.relationship_mode}",
        f"- Situation: {persona.situation}",
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


def slugify(value: str) -> str:
    normalized = "".join(char.lower() if char.isalnum() else "-" for char in value)
    while "--" in normalized:
        normalized = normalized.replace("--", "-")
    return normalized.strip("-") or "session"
