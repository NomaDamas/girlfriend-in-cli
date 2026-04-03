from __future__ import annotations

from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent
PACKAGE_PERSONA_DIR = PACKAGE_ROOT / "assets" / "personas"


def project_root() -> Path | None:
    for candidate in (PACKAGE_ROOT, *PACKAGE_ROOT.parents):
        if (candidate / "pyproject.toml").exists() and (candidate / "personas").is_dir():
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
