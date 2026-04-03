#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

EVIDENCE_DIR="${1:-$ROOT_DIR/artifacts/ouroboros/latest}"
rm -rf "$EVIDENCE_DIR"
mkdir -p "$EVIDENCE_DIR"

python3 -m compileall src | tee "$EVIDENCE_DIR/compileall.txt"
python3 -m pytest | tee "$EVIDENCE_DIR/pytest.txt"

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

python3 -m venv --system-site-packages "$tmpdir/venv"
source "$tmpdir/venv/bin/activate"

if python - <<'PY' >/dev/null 2>&1
import importlib.util
raise SystemExit(0 if importlib.util.find_spec("wheel") else 1)
PY
then
  if python -m pip install --no-build-isolation -e ".[dev]" >"$EVIDENCE_DIR/install.txt" 2>&1; then
    INSTALL_MODE="pip editable install (--no-build-isolation)"
  else
    python setup.py develop >"$EVIDENCE_DIR/install.txt" 2>&1
    INSTALL_MODE="setuptools develop fallback"
  fi
else
  python setup.py develop >"$EVIDENCE_DIR/install.txt" 2>&1
  INSTALL_MODE="setuptools develop (offline-safe default)"
fi

cd /tmp
girlfriend-generator --help >"$EVIDENCE_DIR/help.txt" 2>&1
girlfriend-generator --list-personas >"$EVIDENCE_DIR/personas.txt" 2>&1
python - <<'PY' >"$EVIDENCE_DIR/path-check.txt"
from pathlib import Path

from girlfriend_generator.paths import bundled_session_dir, project_root

root = project_root()
assert root is not None
print(f"repo_root={root}")
print(f"session_dir={bundled_session_dir()}")
print(f"cwd={Path.cwd()}")
assert bundled_session_dir() == root / "sessions"
assert bundled_session_dir().parent == root
assert Path.cwd() != root
PY

python - <<'PY' >"$EVIDENCE_DIR/export-check.txt"
from pathlib import Path

from girlfriend_generator.engine import ConversationSession
from girlfriend_generator.paths import bundled_persona_dir, bundled_session_dir
from girlfriend_generator.personas import load_persona
from girlfriend_generator.session_io import export_session

persona_path = sorted(bundled_persona_dir().glob("*.json"))[0]
persona = load_persona(persona_path)
session = ConversationSession(persona=persona)
session.bootstrap()
session.add_user_message("verification ping")
json_path, markdown_path = export_session(bundled_session_dir(), persona, session.messages)
print(f"persona={persona_path}")
print(f"json_path={json_path}")
print(f"markdown_path={markdown_path}")
assert json_path.parent == bundled_session_dir()
assert markdown_path.parent == bundled_session_dir()
json_path.unlink()
markdown_path.unlink()
PY

cat >"$EVIDENCE_DIR/summary.md" <<EOF
# Verification Evidence

- Install mode: ${INSTALL_MODE}
- Root compile command: \`python3 -m compileall src\`
- Root test command: \`python3 -m pytest\`
- Smoke-equivalent entrypoint checks: \`girlfriend-generator --help\`, \`girlfriend-generator --list-personas\`
- Export locality verified under: \`${ROOT_DIR}/sessions\`

## Files

- \`compileall.txt\`
- \`pytest.txt\`
- \`install.txt\`
- \`help.txt\`
- \`personas.txt\`
- \`path-check.txt\`
- \`export-check.txt\`
EOF

printf 'Evidence written to %s\n' "$EVIDENCE_DIR"
printf 'Install mode: %s\n' "$INSTALL_MODE"
