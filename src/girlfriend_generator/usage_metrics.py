"""Local-first usage metrics for product decisions.

The metrics file intentionally stores coarse session metadata only. It never
stores transcript text, user prompts, assistant replies, or API keys.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


_STATE_DIR_ENV = "GIRLFRIEND_IN_CLI_HOME"
_DEFAULT_DIRNAME = ".girlfriend-in-cli"
_FILENAME = "usage_metrics.json"
_SCHEMA_VERSION = 1
_MAX_EVENTS = 200


def state_dir() -> Path:
    override = os.environ.get(_STATE_DIR_ENV)
    if override:
        return Path(override).expanduser()
    return Path.home() / _DEFAULT_DIRNAME


def metrics_path() -> Path:
    return state_dir() / _FILENAME


def _utc_iso(now: datetime | None = None) -> str:
    return (now or datetime.now(tz=timezone.utc)).isoformat()


def _empty_metrics() -> dict:
    return {
        "version": _SCHEMA_VERSION,
        "total_active_seconds": 0.0,
        "sessions_total": 0,
        "sessions_resumed": 0,
        "events": [],
    }


def load_metrics(path: Path | None = None) -> dict:
    target = path or metrics_path()
    if not target.exists():
        return _empty_metrics()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_metrics()
    if not isinstance(payload, dict):
        return _empty_metrics()
    metrics = _empty_metrics()
    metrics.update(payload)
    if not isinstance(metrics.get("events"), list):
        metrics["events"] = []
    metrics["total_active_seconds"] = float(metrics.get("total_active_seconds") or 0.0)
    metrics["sessions_total"] = int(metrics.get("sessions_total") or 0)
    metrics["sessions_resumed"] = int(metrics.get("sessions_resumed") or 0)
    return metrics


def save_metrics(metrics: dict, path: Path | None = None) -> None:
    target = path or metrics_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")


def record_event(
    event_type: str,
    metadata: dict[str, object] | None = None,
    *,
    path: Path | None = None,
    now: datetime | None = None,
) -> None:
    metrics = load_metrics(path)
    event = {
        "type": event_type,
        "at": _utc_iso(now),
        "metadata": _safe_metadata(metadata or {}),
    }
    metrics["events"] = [*metrics.get("events", []), event][-_MAX_EVENTS:]
    save_metrics(metrics, path)


def record_app_launch(*, path: Path | None = None) -> None:
    record_event("app_launched", path=path)


def _safe_metadata(metadata: dict[str, object]) -> dict[str, object]:
    allowed = {
        "persona_name",
        "persona_path",
        "provider_name",
        "provider_model",
        "performance_mode",
        "resumed",
        "duration_seconds",
    }
    return {key: value for key, value in metadata.items() if key in allowed}


@dataclass
class UsageSession:
    persona_name: str
    persona_path: str
    provider_name: str
    provider_model: str | None
    performance_mode: str
    resumed: bool
    path: Path | None = None
    clock: Callable[[], float] = time.monotonic
    started_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    _started_monotonic: float = 0.0
    _finished: bool = False

    def __post_init__(self) -> None:
        self._started_monotonic = self.clock()
        metrics = load_metrics(self.path)
        metrics["sessions_total"] = int(metrics.get("sessions_total") or 0) + 1
        if self.resumed:
            metrics["sessions_resumed"] = int(metrics.get("sessions_resumed") or 0) + 1
        metrics["events"] = [
            *metrics.get("events", []),
            {
                "type": "session_started" if not self.resumed else "session_resumed",
                "at": _utc_iso(self.started_at),
                "metadata": self._metadata(),
            },
        ][-_MAX_EVENTS:]
        save_metrics(metrics, self.path)

    def finish(self, *, ended_at: datetime | None = None) -> float:
        if self._finished:
            return 0.0
        self._finished = True
        duration = max(0.0, self.clock() - self._started_monotonic)
        metrics = load_metrics(self.path)
        metrics["total_active_seconds"] = round(
            float(metrics.get("total_active_seconds") or 0.0) + duration,
            3,
        )
        metrics["events"] = [
            *metrics.get("events", []),
            {
                "type": "session_ended",
                "at": _utc_iso(ended_at),
                "metadata": {**self._metadata(), "duration_seconds": round(duration, 3)},
            },
        ][-_MAX_EVENTS:]
        save_metrics(metrics, self.path)
        return duration

    def _metadata(self) -> dict[str, object]:
        return _safe_metadata(
            {
                "persona_name": self.persona_name,
                "persona_path": self.persona_path,
                "provider_name": self.provider_name,
                "provider_model": self.provider_model or "",
                "performance_mode": self.performance_mode,
                "resumed": self.resumed,
            }
        )


def start_session(
    *,
    persona_name: str,
    persona_path: str,
    provider_name: str,
    provider_model: str | None,
    performance_mode: str,
    resumed: bool,
    path: Path | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> UsageSession:
    return UsageSession(
        persona_name=persona_name,
        persona_path=persona_path,
        provider_name=provider_name,
        provider_model=provider_model,
        performance_mode=performance_mode,
        resumed=resumed,
        path=path,
        clock=clock,
    )
