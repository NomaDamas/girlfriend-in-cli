from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import (
    ContextEvidence,
    InitiativeProfile,
    NudgePolicy,
    Persona,
    ProfileImage,
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
        core_personality=payload.get("core_personality")
        or payload.get("identity", {}).get("core_personality", "")
        or payload.get("background")
        or payload.get("identity", {}).get("background", ""),
        dynamic_personality_seed=payload.get("dynamic_personality")
        or payload.get("relationship", {}).get("dynamic_personality", "")
        or payload.get("situation")
        or payload.get("summary", ""),
        profile_image=_profile_image_from_payload(payload.get("profile_image")),
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


def _profile_image_from_payload(value: Any) -> ProfileImage | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        if value.startswith(("http://", "https://")):
            return ProfileImage(url=value, source="user_uploaded")
        return ProfileImage(cached_path=value, source="user_uploaded")
    if not isinstance(value, dict):
        raise ValueError("profile_image must be an object, URL/path string, or null.")

    url = str(value.get("url", "") or "")
    cached_path = str(value.get("cached_path", "") or value.get("path", "") or "")
    source = str(value.get("source", "") or "user_uploaded")
    style = str(value.get("style", "") or "real")
    if source not in {"auto_fetched", "user_uploaded", "generated"}:
        raise ValueError("profile_image.source must be auto_fetched, user_uploaded, or generated.")
    if style not in {"real", "anime", "illustration"}:
        raise ValueError("profile_image.style must be real, anime, or illustration.")
    if not url and not cached_path:
        return None
    return ProfileImage(
        url=url,
        source=source,
        cached_path=cached_path,
        style=style,
    )


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
