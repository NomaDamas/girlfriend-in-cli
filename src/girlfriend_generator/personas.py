from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import (
    ContextEvidence,
    InitiativeProfile,
    NudgePolicy,
    Persona,
    StyleProfile,
    TypingProfile,
)


def discover_personas(directory: Path) -> list[Path]:
    return sorted(
        path
        for path in directory.iterdir()
        if path.suffix.lower() in {".json", ".yaml", ".yml"}
    )


def load_persona(path: Path) -> Persona:
    payload = _load_payload(path)
    persona = Persona(
        name=payload["name"],
        age=int(payload["age"]),
        relationship_mode=payload["relationship_mode"],
        background=payload["background"],
        situation=payload["situation"],
        texting_style=payload["texting_style"],
        interests=list(payload.get("interests", [])),
        soft_spots=list(payload.get("soft_spots", [])),
        boundaries=list(payload.get("boundaries", [])),
        greeting=payload["greeting"],
        accent_color=payload.get("accent_color", "magenta"),
        provider_system_hint=payload.get("provider_system_hint", ""),
        context_summary=payload.get("context_summary", ""),
        style_profile=StyleProfile(**payload.get("style_profile", {})),
        initiative_profile=InitiativeProfile(**payload.get("initiative_profile", {})),
        evidence=[ContextEvidence(**item) for item in payload.get("evidence", [])],
        typing=TypingProfile(**payload.get("typing", {})),
        nudge_policy=NudgePolicy(**payload["nudge_policy"]),
    )
    persona.validate()
    return persona


def _load_payload(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    if suffix in {".yaml", ".yml"}:
        try:
            import yaml
        except ImportError as exc:
            raise RuntimeError(
                "YAML personas require PyYAML. Install it or use JSON personas."
            ) from exc
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    raise ValueError(f"Unsupported persona format: {path.suffix}")
