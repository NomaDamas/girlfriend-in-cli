from __future__ import annotations

import os
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent
PACKAGE_PERSONA_DIR = PACKAGE_ROOT / "assets" / "personas"
ROOT_ENV_VAR = "GIRLFRIEND_GENERATOR_ROOT"


def _is_project_root(candidate: Path) -> bool:
    return (candidate / "pyproject.toml").exists() and (candidate / "personas").is_dir()


def _configured_project_root() -> Path | None:
    raw = os.environ.get(ROOT_ENV_VAR)
    if not raw:
        return None
    candidate = Path(raw).expanduser().resolve()
    return candidate if _is_project_root(candidate) else None


def project_root() -> Path | None:
    configured_root = _configured_project_root()
    if configured_root is not None:
        return configured_root
    for candidate in (PACKAGE_ROOT, *PACKAGE_ROOT.parents):
        if _is_project_root(candidate):
            return candidate
    return None


def bundled_persona_dir() -> Path:
    root = project_root()
    if root is not None:
        project_personas = root / "personas"
        if project_personas.is_dir():
            return project_personas
    if PACKAGE_PERSONA_DIR.is_dir():
        return PACKAGE_PERSONA_DIR
    return Path.cwd() / "personas"


def bundled_session_dir() -> Path:
    root = project_root()
    if root is not None:
        return root / "sessions"
    return Path.cwd() / "sessions"


def resolve_persona_path(path: Path) -> Path:
    candidate = path.expanduser()
    if candidate.is_absolute():
        return candidate

    cwd_candidate = (Path.cwd() / candidate).resolve()
    if cwd_candidate.exists():
        return cwd_candidate

    root = project_root()
    if root is not None:
        root_candidate = (root / candidate).resolve()
        if root_candidate.exists():
            return root_candidate

        bundled_candidate = (bundled_persona_dir() / candidate.name).resolve()
        if bundled_candidate.exists():
            return bundled_candidate

    return cwd_candidate


def resolve_session_dir(path: Path | None) -> Path:
    if path is None:
        return bundled_session_dir()

    candidate = path.expanduser()
    if candidate.is_absolute():
        return candidate

    root = project_root()
    if root is not None:
        return (root / candidate).resolve()
    return (Path.cwd() / candidate).resolve()
