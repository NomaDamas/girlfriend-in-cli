"""Local companion milestone state.

Random Chat and other earned features need a small local record proving that
the user has reached a major relationship milestone with at least one persona.
The file stores only persona/milestone metadata, never transcript text.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


_STATE_DIR_ENV = "GIRLFRIEND_IN_CLI_HOME"
_DEFAULT_DIRNAME = ".girlfriend-in-cli"
_FILENAME = "companions_cleared.json"
_SCHEMA_VERSION = 1


def state_dir() -> Path:
    override = os.environ.get(_STATE_DIR_ENV)
    if override:
        return Path(override).expanduser()
    return Path.home() / _DEFAULT_DIRNAME


def state_path() -> Path:
    return state_dir() / _FILENAME


@dataclass(frozen=True)
class ClearedCompanion:
    persona_name: str
    milestone: str
    cleared_at: datetime
    persona_path: str = ""

    def to_dict(self) -> dict:
        return {
            "persona_name": self.persona_name,
            "milestone": self.milestone,
            "cleared_at": self.cleared_at.isoformat(),
            "persona_path": self.persona_path,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ClearedCompanion":
        raw_at = data.get("cleared_at") or ""
        try:
            cleared_at = datetime.fromisoformat(raw_at)
            if cleared_at.tzinfo is None:
                cleared_at = cleared_at.replace(tzinfo=timezone.utc)
        except ValueError:
            cleared_at = datetime.now(tz=timezone.utc)
        return cls(
            persona_name=str(data.get("persona_name", "?")),
            milestone=str(data.get("milestone", "lover")),
            cleared_at=cleared_at,
            persona_path=str(data.get("persona_path", "")),
        )


def load_cleared(path: Path | None = None) -> list[ClearedCompanion]:
    target = path or state_path()
    if not target.exists():
        return []
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items = payload.get("cleared") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return []
    return [ClearedCompanion.from_dict(item) for item in items if isinstance(item, dict)]


def has_any_cleared(path: Path | None = None) -> bool:
    return bool(load_cleared(path))


def mark_cleared(
    persona_name: str,
    milestone: str = "lover",
    persona_path: str = "",
    *,
    path: Path | None = None,
    now: datetime | None = None,
) -> ClearedCompanion:
    target = path or state_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    when = now or datetime.now(tz=timezone.utc)
    record = ClearedCompanion(
        persona_name=persona_name,
        milestone=milestone,
        cleared_at=when,
        persona_path=persona_path,
    )
    cleared = [
        item
        for item in load_cleared(target)
        if not (item.persona_name == persona_name and item.milestone == milestone)
    ]
    cleared.append(record)
    payload = {
        "version": _SCHEMA_VERSION,
        "cleared": [item.to_dict() for item in cleared],
    }
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def cleared_badge_text(path: Path | None = None) -> str:
    items = load_cleared(path)
    if not items:
        return ""
    names = [item.persona_name for item in items[:3]]
    suffix = " ..." if len(items) > 3 else ""
    return f"{len(items)} cleared · {', '.join(names)}{suffix}"
