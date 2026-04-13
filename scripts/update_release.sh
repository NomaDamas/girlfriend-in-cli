#!/usr/bin/env bash
set -euo pipefail

TAG="${1:-}"
if [[ -z "$TAG" ]]; then
  echo "usage: bash scripts/update_release.sh <tag>" >&2
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -n "$(git status --porcelain)" ]]; then
  echo "working tree is dirty; refusing to auto-update" >&2
  exit 1
fi

PREV_REF="$(git rev-parse --verify HEAD)"

cleanup_on_error() {
  git checkout --detach "$PREV_REF" >/dev/null 2>&1 || true
}
trap cleanup_on_error ERR

git fetch --tags origin
git rev-parse --verify "refs/tags/$TAG" >/dev/null
git checkout --detach "$TAG"

bash scripts/bootstrap.sh >/dev/null

trap - ERR
echo "Updated to $TAG"
