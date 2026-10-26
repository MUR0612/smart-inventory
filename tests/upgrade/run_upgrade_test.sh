#!/usr/bin/env bash
# Upgrade test: load a legacy schema + data into a fresh MySQL, start the new
# stack on top of it, and check that migration adopts it, is re-runnable, and
# that the app account ends up with DML-only rights.
#   bash tests/upgrade/run_upgrade_test.sh legacy_compose|legacy_k8s [port]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VARIANT="${1:?usage: run_upgrade_test.sh legacy_compose|legacy_k8s [port]}"
PORT="${2:-18181}"
PROJECT="si-upgrade-${VARIANT//_/-}"
WORK="$(mktemp -d)"
PY="${PYTHON:-python}"
trap 'docker compose -p "$PROJECT" --env-file "$WORK/test.env" down -v >/dev/null 2>&1 || true; rm -rf "$WORK"' EXIT

"$PY" "$ROOT/scripts/init_env.py" --env-file "$WORK/test.env" --credentials-file "$WORK/test.credentials" \
  --gateway-port "$PORT" --force >/dev/null
sed -i 's/^GATEWAY_BIND=.*/GATEWAY_BIND=127.0.0.1/; s/^SEED_DEMO_DATA=.*/SEED_DEMO_DATA=false/' "$WORK/test.env"
dc() { docker compose -p "$PROJECT" --env-file "$WORK/test.env" -f "$ROOT/docker-compose.yml" "$@"; }

echo "== start MySQL and load $VARIANT fixture"
dc up -d --wait mysql
dc exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -e "CREATE DATABASE smart_inventory"'
dc exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot smart_inventory' < "$ROOT/tests/upgrade/$VARIANT.sql"

echo "== start the new stack (runs the migration)"
dc up -d --build --wait --wait-timeout 300
dc logs migrate | grep -E "migrate:" || true

echo "== re-run migration: must be a no-op"
rerun="$(dc run --rm --no-deps migrate 2>&1)"
echo "$rerun" | grep -E "migrate:"
if echo "$rerun" | grep -qE "applying|added|converting"; then echo "FAIL: migration re-run changed the schema"; exit 1; fi

echo "== application account privileges"
grants="$(dc exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -N -e "SHOW GRANTS FOR inventory_app@\"%\""')"
echo "$grants"
echo "$grants" | grep -q "GRANT SELECT, INSERT, UPDATE, DELETE ON \`smart_inventory\`.\*" || { echo "FAIL: DML grant missing"; exit 1; }
if echo "$grants" | grep -qE "ALL PRIVILEGES|CREATE|DROP|ALTER|GRANT OPTION"; then echo "FAIL: excess privileges"; exit 1; fi

echo "== legacy data behaves under the new rules"
"$PY" "$ROOT/tests/upgrade/verify_upgrade.py" "http://127.0.0.1:$PORT" "$WORK/test.credentials"
"$PY" "$ROOT/tests/smoke_test.py" --base-url "http://127.0.0.1:$PORT" --credentials-file "$WORK/test.credentials"
echo "UPGRADE TEST PASSED: $VARIANT"
