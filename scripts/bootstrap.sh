#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

printf '\nEnvironment ready.\n'
printf 'Run: source .venv/bin/activate && girlfriend-generator --persona personas/han-seo-jin-crush.json\n'
