# Smart Inventory

Cloud Computing course project: a small inventory and order system built as two FastAPI
services behind an Nginx gateway, with MySQL, Redis, Docker Compose and Kubernetes (local
cluster or GKE).

Status of every feature and fix, with the evidence behind it: [docs/STATUS.md](docs/STATUS.md).
Architecture diagrams (editable Mermaid): [docs/architecture.md](docs/architecture.md).

## What it does

- **Products**: create, edit, delete (blocked when order history exists), search, sort, filter.
- **Stock**: atomic adjust (row-locked), set with optional optimistic check, low-stock list,
  inventory value statistics computed in SQL with exact decimals.
- **Orders**: create with stock reservation (all-or-nothing, idempotent with `Idempotency-Key`),
  list with pagination and full totals, status workflow, cancel/refund with exactly-once stock
  return, delete only for closed orders.
- **Access control**: login, roles `viewer` (read) and `staff` (read/write), service token
  between services.
- **Redis**: 30-second product-list cache (fails open to MySQL) and a Pub/Sub event log
  (`stock_changes`, `low_stock_alerts`). The subscriber only logs events and keeps the last few
  for `GET /api/orders/events/recent`. E-mail alerts, auto-replenishment and live browser
  updates are **planned, not implemented**.
- **Frontend**: Bootstrap + Chart.js single page, served by the gateway from the same origin.

```
browser ──► gateway (Nginx: frontend + /api proxy) ──► inventory-service ──► MySQL (shared schema)
                                              └──────► order-service ─REST─┘   Redis (cache, Pub/Sub)
```

## Quick start (Docker Compose)

Requirements: Docker with Compose v2, Python 3.10+ (only for the setup script).

```bash
python scripts/init_env.py
docker compose up -d --build --wait
```

Open http://localhost:8080 and sign in with the user names and passwords that `init_env.py`
wrote to `.env.credentials` (`admin` is staff, `viewer` is read-only). Both `.env` and
`.env.credentials` are git-ignored; never commit or zip them.

- Only the gateway is published. For debugging, `docker compose -f docker-compose.yml -f
  docker-compose.debug.yml up -d` also binds MySQL/Redis/services to 127.0.0.1.
- Set `GATEWAY_BIND=127.0.0.1` in `.env` to keep the site private on shared networks.
  Local Compose uses plain HTTP; public deployments use HTTPS (see the Kubernetes guide).
- Add users: `python scripts/hash_password.py <name> <staff|viewer>` and append the line to
  `AUTH_USERS` in `.env`, then `docker compose up -d`.
- Stop: `docker compose down` (keeps data) or `docker compose down -v` (deletes the database volume).

Upgrading an existing installation: the migration adopts the old Compose and old Kubernetes
schemas in place (tested, see STATUS). The old Compose stack used **MySQL 5.7**. MySQL 8.4 cannot
open a 5.7 data directory directly, so back up first and restore into the new stack:

```bash
docker compose exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysqldump -uroot --single-transaction smart_inventory' > backup.sql
```

Run that against the **old** stack before switching. Then start the new stack with an empty
volume, load `backup.sql` into it, and run `docker compose up -d` so the migration converts it.

## Configuration

One contract for Compose (`.env`) and Kubernetes (ConfigMap + Secret):

| Variable | Secret | Used by | Meaning |
|---|---|---|---|
| `DB_HOST`, `DB_PORT`, `DB_NAME` | no | services, migrate | MySQL location |
| `DB_USER`, `DB_PASSWORD` | yes | services, migrate | least-privilege app account (DML only) |
| `MYSQL_ROOT_PASSWORD` | yes | mysql, migrate | admin account, never given to the services |
| `REDIS_HOST`, `REDIS_PORT` | no | inventory, order | Redis location |
| `INVENTORY_BASE_URL` | no | order | e.g. `http://inventory-service:8001` |
| `AUTH_SECRET` (>= 32 chars) | yes | both services | signs login tokens |
| `SERVICE_TOKEN` (>= 24 chars) | yes | both services | order-service to inventory-service calls |
| `AUTH_USERS` | yes | inventory | `name:role:pbkdf2-hash,...` |
| `CORS_ALLOWED_ORIGINS` | no | both services | empty = same-origin only (default) |
| `ENABLE_API_DOCS` | no | both services | Swagger at `/api/inventory/docs`, `/api/orders/docs` |
| `SEED_DEMO_DATA` | no | migrate | insert 3 demo products into an empty database |

Missing values or values still containing `CHANGE_ME` stop the service with an error that
names the variable and never prints the value.

## Database schema and migrations

`db/migrate.py` is the single source of the schema. It runs as a one-off container (Compose
`migrate` service, Kubernetes `db-migrate` Job), never inside the app replicas. It:

- creates a fresh schema, or converts the legacy Compose / legacy Kubernetes schemas in place;
- checks before every change, so re-running it changes nothing;
- creates the DML-only application account and sets its password (password rotation);
- backfills reservation records for pre-existing orders.

Each service's readiness check waits for the schema version it needs.

## API overview

All paths go through the gateway. Every endpoint except health checks and login needs
`Authorization: Bearer <token>`.

| Method and path | Role | Notes |
|---|---|---|
| `POST /api/auth/login` | anyone | `{username, password}` -> token; rate-limited |
| `GET /api/inventory/products`, `/products/{id}`, `/stock`, `/stock/{id}`, `/low-stock`, `/stats` | viewer | prices are decimal strings |
| `POST/PUT/DELETE /api/inventory/products[/{id}]` | staff | validated; duplicate SKU 409 |
| `POST /api/inventory/stock/{id}/adjust` `{adjustment}` | staff | negative allowed, never below 0 |
| `POST /api/inventory/stock/{id}/set` `{stock, expected_stock?}` | staff | physical count |
| `/api/inventory/reservations[...]` | service token only | reserve / release / commit |
| `GET /api/orders?skip&limit&status` | viewer | `{items, total, skip, limit}`, limit <= 200 |
| `GET /api/orders/stats`, `/{id}`, `/{id}/workflow`, `/events/recent` | viewer | |
| `POST /api/orders` (+ `Idempotency-Key`) | staff | 201 new, 200 replay |
| `PATCH /api/orders/{id}/status` `{status}`, `POST /api/orders/{id}/cancel` | staff | one state machine |
| `DELETE /api/orders/{id}` | staff | closed orders only |
| `POST /api/orders/admin/reconcile` | staff | retry pending stock work now |
| `GET /api/<inventory|orders>/livez`, `/readyz`, `/healthz`; `GET /healthz` (gateway) | anyone | |

## Tests

```bash
bash scripts/test-unit.sh
pip install -r tests/requirements.txt
bash scripts/test-compose.sh
python tests/smoke_test.py --base-url http://localhost:8080 --credentials-file .env.credentials
bash deploy/deploy.sh validate local
bash tests/upgrade/run_upgrade_test.sh legacy_compose
bash tests/upgrade/run_upgrade_test.sh legacy_k8s
bash scripts/secret-scan.sh
```

| Command | What it covers |
|---|---|
| `test-unit.sh` | unit tests in Docker (SQLite + fakes) and frontend XSS tests (Node/jsdom) |
| `test-compose.sh` | disposable stack: smoke, integration, fault injection (MySQL, Redis, inventory outages, published ports) |
| `smoke_test.py` | quick end-to-end check of a running stack; adds `SMOKE-` products/orders, exits 1 on failure |
| `deploy.sh validate` | renders and validates Kubernetes manifests without a cluster |
| `run_upgrade_test.sh` | old Compose / old Kubernetes schemas with existing orders upgraded in place |
| `secret-scan.sh` | gitleaks on tracked files (add `--history` for the full history) |

The integration tests also run against Kubernetes: set `BASE_URL` to the ingress address and
`CREDENTIALS_FILE`. What was actually run, where, and with what result is recorded in
[docs/STATUS.md](docs/STATUS.md).

## Deployment

Kubernetes (local cluster or GKE) uses `deploy/deploy.sh`. Read [k8s/README.md](k8s/README.md)
before deploying anything billable. It covers prerequisites, HTTPS, the autoscaling and rollout
demos, cost and cleanup. GKE has **not** been deployed or verified with this version of the code.

## Submission package

```bash
bash scripts/package.sh
```

This builds `dist/smart-inventory-<commit>.zip` from committed files only (no `.git`, `.env` or
local data) and secret-scans it.

## Known limitations

- One shared MySQL schema for both services (foreign keys from order data to products). This is a
  deliberate course-scale trade-off; see [docs/architecture.md](docs/architecture.md).
- Cross-service consistency uses a recorded-intent + idempotent-retry saga, not a distributed
  transaction. Pending stock work is retried every 30 s; `inventory_sync` and `sync_error` show it.
- Redis Pub/Sub is a non-durable event log; the cache can be up to 30 s stale only if Redis fails
  during a write.
- Access control is minimal (two roles, no token revocation, no MFA): [docs/SECURITY.md](docs/SECURITY.md).
- Single MySQL instance: the PVC keeps data across pod restarts but is not a backup or HA.
- Order timestamps written by the old code mix Sydney local time and UTC and were not converted;
  new data is stored in UTC and returned with an explicit offset.
- `PAID` is a manual status change; there is no payment provider integration.

## Credentials in git history

Earlier commits contain real-looking database credentials. They must be rotated, and history
cleanup is optional. See [docs/SECURITY.md](docs/SECURITY.md) §1.

## AI assistance

The October 2026 remediation (security fixes, consistency redesign, tests, deployment and
documentation) was carried out with an AI coding assistant (Claude) working from a written
review brief. The project author still needs to review it before submission. Check your course's
rules on AI use and declare it in your submission accordingly. The original rubric was not
available when this was written.
