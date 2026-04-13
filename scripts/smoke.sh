#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python3 -m compileall src
python3 -m pytest

tmpdir="$ROOT_DIR/.tmp/smoke"
rm -rf "$tmpdir"
mkdir -p "$tmpdir"
trap 'rm -rf "$tmpdir"' EXIT

python3 -m venv --system-site-packages "$tmpdir/venv"
source "$tmpdir/venv/bin/activate"
if python - <<'PY' >/dev/null 2>&1
import importlib.util
raise SystemExit(0 if importlib.util.find_spec("wheel") else 1)
PY
then
  if python -m pip install --no-build-isolation -e . >/dev/null 2>&1; then
    INSTALL_MODE="pip editable runtime install (--no-build-isolation)"
  else
    python setup.py develop >/dev/null 2>&1
    INSTALL_MODE="setuptools develop fallback"
  fi
else
  python setup.py develop >/dev/null 2>&1
  INSTALL_MODE="setuptools develop (offline-safe default)"
fi

cd "$tmpdir"
mygf --help >/dev/null
python -m girlfriend_generator --help >/dev/null
mygf --list-personas >/dev/null
python -m girlfriend_generator --list-personas >/dev/null
GIRLFRIEND_GENERATOR_ROOT="$ROOT_DIR" python - <<'PY'
from pathlib import Path

from girlfriend_generator.engine import ConversationSession
from girlfriend_generator.paths import (
    ROOT_ENV_VAR,
    bundled_persona_dir,
    bundled_session_dir,
    project_root,
    resolve_persona_path,
    resolve_session_dir,
)
from girlfriend_generator.personas import load_persona
from girlfriend_generator.session_io import export_session

root = project_root()
assert root is not None
assert str(root) == __import__("os").environ[ROOT_ENV_VAR]
assert bundled_session_dir() == root / "sessions"
assert bundled_session_dir().parent == root
assert (root / "personas").is_dir()
assert Path.cwd() != root

persona_path = sorted(bundled_persona_dir().glob("*.json"))[0]
assert resolve_persona_path(Path("personas") / persona_path.name) == persona_path
assert resolve_session_dir(Path("sessions/smoke-check")) == root / "sessions" / "smoke-check"
persona = load_persona(persona_path)
session = ConversationSession(persona=persona)
session.bootstrap()
session.add_user_message("smoke export")
json_path, markdown_path = export_session(bundled_session_dir(), persona, session.messages)
assert json_path.parent == bundled_session_dir()
assert markdown_path.parent == bundled_session_dir()
json_path.unlink()
markdown_path.unlink()
PY

printf 'Install mode: %s\n' "$INSTALL_MODE"
printf 'Smoke checks passed.\n'
