#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOSTING_DIR="${HOSTING_DIR:-/tmp/girlfriend-in-cli-hosting}"
PORT="${PORT:-8787}"
BASE_URL="http://127.0.0.1:${PORT}"

if [[ ! -d "$HOSTING_DIR" ]]; then
  echo "Missing hosting repo: $HOSTING_DIR" >&2
  exit 1
fi

cleanup() {
  if [[ -n "${SERVER_PID:-}" ]]; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

(
  cd "$HOSTING_DIR"
  PYTHONPATH=src python3 -m girlfriend_in_cli_hosting.server --port "$PORT"
) >/tmp/girlfriend_in_cli_hosting_server.log 2>&1 &
SERVER_PID=$!

python3 - <<PY
import time, urllib.request, json
base = "${BASE_URL}"
for _ in range(60):
    try:
        with urllib.request.urlopen(f"{base}/healthz") as response:
            payload = json.loads(response.read().decode("utf-8"))
            if payload.get("status") == "ok":
                break
    except Exception:
        time.sleep(0.25)
else:
    raise SystemExit("hosting server failed to become healthy")
PY

cd "$ROOT_DIR"
PYTHONPATH=src python3 -m girlfriend_generator \
  --list-remote-personas \
  --server-base-url "$BASE_URL" >/dev/null

PYTHONPATH=src python3 - <<PY
from girlfriend_generator.remote import compile_remote_persona, list_remote_personas, fetch_remote_persona_by_slug

base = "${BASE_URL}"
compiled = compile_remote_persona(
    base_url=base,
    display_name="유나",
    age=27,
    relationship_mode="girlfriend",
    context_notes="성수에서 일하는 디자이너 느낌",
    context_links=["https://instagram.com/yuna.example"],
    context_snippets=["자기야 뭐 해?"],
)
assert compiled["persona_id"]
slug = compiled["persona_pack"]["slug"]
items = list_remote_personas(base)
assert any(item["slug"] == slug for item in items)
persona = fetch_remote_persona_by_slug(base, slug)
assert persona.name == "유나"
print("Remote smoke checks passed.")
PY
