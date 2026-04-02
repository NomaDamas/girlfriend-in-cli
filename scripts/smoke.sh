#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python3 -m compileall src
pytest
PYTHONPATH=src python3 -m girlfriend_generator --help >/dev/null
PYTHONPATH=src python3 -m girlfriend_generator --list-personas >/dev/null

printf 'Smoke checks passed.\n'
