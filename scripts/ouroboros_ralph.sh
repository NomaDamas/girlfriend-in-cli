#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

FORCE_INTERVIEW="${FORCE_INTERVIEW:-0}"
CONTEXT="${1:-Stabilize and harden the girlfriend_generator terminal-only romance simulation CLI without ontology drift.}"

PYTHONPATH=src python3 - <<'PY'
from pathlib import Path
import subprocess

from girlfriend_generator.ouroboros_support import bundled_repo_paths, detect_ontology_instability

root = Path.cwd()
paths = bundled_repo_paths(root)
if not paths["seed"].exists():
    raise SystemExit("Missing .codex/ralph-seed.yaml")

result = subprocess.run(
    ["git", "status", "--porcelain"],
    check=True,
    capture_output=True,
    text=True,
)
changed_paths = []
for line in result.stdout.splitlines():
    if not line:
        continue
    changed_paths.append(line[3:])
reasons = detect_ontology_instability(changed_paths)
flag = root / ".codex" / "ontology-unstable.flag"
if reasons:
    flag.write_text("\n".join(reasons) + "\n", encoding="utf-8")
    print("unstable")
else:
    if flag.exists():
        flag.unlink()
    print("stable")
PY

STABILITY="$(PYTHONPATH=src python3 - <<'PY'
from pathlib import Path
flag = Path(".codex/ontology-unstable.flag")
print("unstable" if flag.exists() else "stable")
PY
)"

ouroboros status health
bash scripts/ouroboros_capture_evidence.sh

if [[ "$FORCE_INTERVIEW" == "1" || "$STABILITY" == "unstable" ]]; then
  echo "Ontology instability detected. Launching Ouroboros interview..."
  ouroboros init start --orchestrator --runtime codex "$CONTEXT"
else
  echo "Ontology stable. Launching Ralph workflow..."
  ouroboros run workflow .codex/ralph-seed.yaml --runtime codex --sequential
fi
