from __future__ import annotations

from pathlib import Path
from typing import Iterable


_DRIFT_PREFIXES = (
    "app/",
    "pages/",
    "web/",
    "mobile/",
    "android/",
    "ios/",
)
_DRIFT_SUFFIXES = (
    ".tsx",
    ".jsx",
    ".dart",
    ".swift",
    ".kt",
)
_DRIFT_FILES = {
    "package.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "bun.lockb",
    "bun.lock",
    "next.config.js",
    "next.config.mjs",
    "vite.config.ts",
    "vite.config.js",
}


def detect_ontology_instability(paths: Iterable[str]) -> list[str]:
    reasons: list[str] = []
    for raw_path in paths:
        path = raw_path.strip().replace("\\", "/")
        if not path or path.startswith(".agents/") or path.startswith(".codex/"):
            continue
        if any(path.startswith(prefix) for prefix in _DRIFT_PREFIXES):
            reasons.append(f"surface drift candidate: {path}")
            continue
        if any(path.endswith(suffix) for suffix in _DRIFT_SUFFIXES):
            reasons.append(f"non-cli UI artifact detected: {path}")
            continue
        if path in _DRIFT_FILES:
            reasons.append(f"web/mobile build manifest detected: {path}")
    return reasons


def bundled_repo_paths(root: Path) -> dict[str, Path]:
    return {
        "root": root,
        "seed": root / ".codex" / "ralph-seed.yaml",
        "status": root / ".codex" / "ralph-status.md",
        "evidence_dir": root / "artifacts" / "ouroboros" / "latest",
    }
