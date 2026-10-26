#!/usr/bin/env bash
# Unit tests for both services, run inside the same Python image the services use
# (no local Python setup needed), plus the frontend XSS tests if Node is installed.
set -euo pipefail
export MSYS_NO_PATHCONV=1
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT"; command -v cygpath >/dev/null 2>&1 && SRC="$(cygpath -m "$ROOT")"
IMAGE="python:3.12-slim-trixie"
for svc in inventory-service order-service; do
  echo "== unit tests: $svc"
  docker run --rm -v "$SRC:/src:ro" -w "/src/$svc" -e PYTHONDONTWRITEBYTECODE=1 "$IMAGE" sh -c \
    "pip install -q --disable-pip-version-check --root-user-action=ignore -r requirements.lock.txt -r ../tests/unit-requirements.txt \
     && python -m pytest -q -p no:cacheprovider tests"
done
if command -v npm >/dev/null 2>&1; then
  echo "== frontend tests"
  (cd "$ROOT/tests/frontend" && npm ci --silent --no-audit --no-fund && npm test)
else
  echo "== frontend tests skipped (npm not installed)"
fi
