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
  if python -m pip install --no-build-isolation -e . >"$EVIDENCE_DIR/install.txt" 2>&1; then
    INSTALL_MODE="pip editable runtime install (--no-build-isolation)"
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
python -m girlfriend_generator --help >"$EVIDENCE_DIR/module-help.txt" 2>&1
girlfriend-generator --list-personas >"$EVIDENCE_DIR/personas.txt" 2>&1
python -m girlfriend_generator --list-personas >"$EVIDENCE_DIR/module-personas.txt" 2>&1
GIRLFRIEND_GENERATOR_ROOT="$ROOT_DIR" python - <<'PY' >"$EVIDENCE_DIR/path-check.txt"
from pathlib import Path
import os

from girlfriend_generator.paths import ROOT_ENV_VAR, bundled_session_dir, project_root

root = project_root()
assert root is not None
print(f"repo_root={root}")
print(f"session_dir={bundled_session_dir()}")
print(f"cwd={Path.cwd()}")
print(f"root_env={os.environ[ROOT_ENV_VAR]}")
assert bundled_session_dir() == root / "sessions"
assert bundled_session_dir().parent == root
assert Path.cwd() != root
PY

GIRLFRIEND_GENERATOR_ROOT="$ROOT_DIR" python - <<'PY' >"$EVIDENCE_DIR/export-check.txt"
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

GIRLFRIEND_GENERATOR_ROOT="$ROOT_DIR" python - <<'PY' >"$EVIDENCE_DIR/interactive-check.txt"
from datetime import timedelta

from girlfriend_generator.api import RomanceService
from girlfriend_generator.engine import utc_now

service = RomanceService()
compiled = service.compile_context(
    {
        "name": "검증용",
        "age": 26,
        "relationship_mode": "girlfriend",
        "notes": "전시와 카페를 좋아하고 먼저 안부를 묻는 편이다.",
        "snippets": ["뭐 해?", "오늘은 좀 보고 싶네 ㅎㅎ"],
    }
)
persona_id = compiled["persona_id"]
created = service.create_session({"persona_id": persona_id})
session_id = created["session_id"]
message_result = service.post_message(
    session_id,
    {
        "text": "오늘 코딩하다가 네 생각 났어.",
        "provider": "heuristic",
    },
)
session = service.sessions[session_id]
session.nudge_due_at = utc_now() - timedelta(seconds=1)
nudge_result = service.tick(session_id, {"provider": "heuristic"})
print(f"session_id={session_id}")
print(f"reply_text={message_result['reply']['text']}")
print(f"reply_roles={[m['role'] for m in message_result['state']['messages'][-2:]]}")
print(f"nudge_event={nudge_result['event_type']}")
print(f"nudge_text={nudge_result['text']}")
assert message_result["state"]["messages"][-2]["role"] == "user"
assert message_result["state"]["messages"][-1]["role"] == "assistant"
assert nudge_result["event_type"] == "nudge"
assert nudge_result["text"]
PY

cat >"$EVIDENCE_DIR/summary.md" <<EOF
# Verification Evidence

- Install mode: ${INSTALL_MODE}
- Root compile command: \`python3 -m compileall src\`
- Root test command: \`python3 -m pytest\`
- Smoke-equivalent entrypoint checks: \`girlfriend-generator --help\`, \`python -m girlfriend_generator --help\`
- Persona discovery checks: \`girlfriend-generator --list-personas\`, \`python -m girlfriend_generator --list-personas\`
- Export locality verified under: \`${ROOT_DIR}/sessions\`
- Interactive send/reply verified in \`interactive-check.txt\`
- Idle nudge verified in \`interactive-check.txt\`

## Files

- \`compileall.txt\`
- \`pytest.txt\`
- \`install.txt\`
- \`help.txt\`
- \`module-help.txt\`
- \`personas.txt\`
- \`module-personas.txt\`
- \`path-check.txt\`
- \`export-check.txt\`
- \`interactive-check.txt\`
EOF

printf 'Evidence written to %s\n' "$EVIDENCE_DIR"
printf 'Install mode: %s\n' "$INSTALL_MODE"
