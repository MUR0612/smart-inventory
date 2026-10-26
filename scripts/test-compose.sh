#!/usr/bin/env bash
# Full Compose verification in a DISPOSABLE project (own volume, own random
# secrets, gateway on 127.0.0.1:18080). Your normal stack and data are not touched.
#   bash scripts/test-compose.sh            # smoke + integration + fault injection
#   KEEP=1 bash scripts/test-compose.sh     # leave the stack running afterwards
# Needs: docker, python with tests/requirements.txt installed.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT="smart-inventory-test"
PORT="${PORT:-18080}"
WORK="$(mktemp -d)"
PY="${PYTHON:-python}"
hp() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else echo "$1"; fi; }
dc() { docker compose -p "$PROJECT" --env-file "$(hp "$WORK/test.env")" -f "$(hp "$ROOT/docker-compose.yml")" "$@"; }
cleanup() { if [[ -z "${KEEP:-}" ]]; then dc down -v >/dev/null 2>&1 || true; rm -rf "$WORK"; else echo "kept: env in $WORK"; fi; }
trap cleanup EXIT

"$PY" "$ROOT/scripts/init_env.py" --env-file "$(hp "$WORK/test.env")" --credentials-file "$(hp "$WORK/test.credentials")" \
  --gateway-port "$PORT" --force >/dev/null
sed -i 's/^GATEWAY_BIND=.*/GATEWAY_BIND=127.0.0.1/' "$WORK/test.env"

echo "== build and start $PROJECT"
dc up -d --build --wait --wait-timeout 300
export BASE_URL="http://127.0.0.1:$PORT" CREDENTIALS_FILE="$(hp "$WORK/test.credentials")"
export RUN_FAULT_TESTS=1 COMPOSE_PROJECT="$PROJECT" COMPOSE_ENV_FILE="$(hp "$WORK/test.env")"
export SERVICE_TOKEN="$(grep '^SERVICE_TOKEN=' "$WORK/test.env" | cut -d= -f2-)"

echo "== smoke test"
"$PY" "$ROOT/tests/smoke_test.py" --base-url "$BASE_URL" --credentials-file "$CREDENTIALS_FILE"
echo "== integration + fault-injection tests"
"$PY" -m pytest -q -p no:cacheprovider "$(hp "$ROOT/tests/integration")"
echo "ALL COMPOSE TESTS PASSED"
