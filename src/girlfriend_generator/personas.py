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
    if not directory.is_dir():
        return []
    return sorted(
        path
        for path in directory.iterdir()
        if path.suffix.lower() in {".json", ".yaml", ".yml"}
    )


def load_persona(path: Path) -> Persona:
    payload = _load_payload(path)
    return persona_from_pack(payload)


def persona_from_pack(payload: dict[str, Any]) -> Persona:
    persona = Persona(
        name=payload.get("name") or payload.get("display_name") or "persona",
        age=int(payload.get("age", 25)),
        relationship_mode=payload.get("relationship_mode")
        or payload.get("relationship", {}).get("mode", "crush"),
        background=payload.get("background")
        or payload.get("identity", {}).get("background", "컴파일된 성인 페르소나"),
        situation=payload.get("situation") or payload.get("summary", "컴파일된 관계 컨텍스트"),
        texting_style=payload.get("texting_style")
        or ", ".join(payload.get("style", {}).get("tone_keywords", []))
        or "짧고 리듬감 있는 톤",
        interests=list(payload.get("interests") or payload.get("identity", {}).get("interests", [])),
        soft_spots=list(payload.get("soft_spots") or payload.get("relationship", {}).get("soft_spots", [])),
        boundaries=list(payload.get("boundaries") or payload.get("identity", {}).get("boundaries", [])),
        greeting=payload.get("greeting")
        or payload.get("style", {}).get("sample_lines", ["안녕"])[0],
        accent_color=payload.get("accent_color", "magenta"),
        provider_system_hint=payload.get("provider_system_hint", ""),
        context_summary=payload.get("context_summary") or payload.get("summary", ""),
        style_profile=StyleProfile(
            **payload.get(
                "style_profile",
                {"signature_phrases": payload.get("style", {}).get("sample_lines", [])[:3]},
            )
        ),
        initiative_profile=InitiativeProfile(
            **payload.get(
                "initiative_profile",
                {"follow_up_templates": payload.get("style", {}).get("sample_lines", [])[:2]},
            )
        ),
        evidence=[
            ContextEvidence(
                source_type=item.get("kind", item.get("source_type", "evidence")),
                label=item.get("source_id", item.get("label", "source")),
                value=item.get("value", item.get("url", "")),
                confidence=float(item.get("reliability", item.get("confidence", 0.6))),
                tags=list(item.get("style_signals", item.get("tags", []))),
            )
            for item in payload.get("source_evidence", payload.get("evidence", []))
        ],
        typing=TypingProfile(**payload.get("typing", {})),
        nudge_policy=NudgePolicy(
            **payload.get(
                "nudge_policy",
                {"templates": ["왜 답장 안 해?", "나 기다리고 있었는데."]},
            )
        ),
        difficulty=payload.get("difficulty", "normal"),
        special_mode=payload.get("special_mode", ""),
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
