#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python3 -m venv --system-site-packages .venv
source .venv/bin/activate

if python - <<'PY' >/dev/null 2>&1
import importlib.util
raise SystemExit(0 if importlib.util.find_spec("wheel") else 1)
PY
then
  if python -m pip install --no-build-isolation -e ".[dev]" >/dev/null 2>&1; then
    INSTALL_MODE="pip editable install (--no-build-isolation)"
  else
    python setup.py develop >/dev/null 2>&1
    INSTALL_MODE="setuptools develop fallback"
  fi
else
  python setup.py develop >/dev/null 2>&1
  INSTALL_MODE="setuptools develop (offline-safe default)"
fi

python - <<'PY'
import importlib.util
import sys

if importlib.util.find_spec("rich") is None:
    sys.stderr.write("Missing required dependency: rich\n")
    raise SystemExit(1)

if importlib.util.find_spec("pytest") is None:
    sys.stderr.write("Note: pytest is not installed in this environment.\n")
PY

mygf --help >/dev/null
python -m girlfriend_generator --help >/dev/null
mygf --list-personas >/dev/null

printf '\nEnvironment ready.\n'
printf 'Install mode: %s\n' "$INSTALL_MODE"
printf 'Run: source .venv/bin/activate && mygf\n'
