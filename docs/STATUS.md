# Implementation status and evidence

Remediation of the review brief dated 2026-10-26 (branch `fix/brief-remediation`). Every item
lists what changed, then each acceptance check marked **Passed**, **Failed** or **Not run**,
with the command used. Nothing marked "Not run" may be described as done or verified.

The original five-phase plan (`專案過程.docx`) is a plan, not a completion record. It is kept
unchanged as a historical document; this file is the record of what exists and what was checked.

## Test environments used

| ID | Environment |
|---|---|
| E1 | Windows 11, Python 3.14 venv: unit tests with SQLite + fakes |
| E2 | Docker image `python:3.12-slim-trixie` (same base as the services): `scripts/test-unit.sh` |
| E3 | Docker Desktop 28.5.1, Compose: MySQL 8.4, Redis 7.4, all services through the gateway (`scripts/test-compose.sh`) |
| E4 | k3s v1.35.9 in Docker (single node, Traefik ingress, local-path storage, metrics-server), overlay `local` deployed with `deploy/deploy.sh` |
| E5 | Node 24 + jsdom 30.1.1 (frontend tests), in-app Chromium browser against E3 |

All runs: 2026-10-26. **GKE / any cloud: Not run** (no paid resources were created).

Totals in the final run: unit 36 (inventory) + 30 (order) **Passed** (E1 and E2); frontend 2 **Passed** (E5);
integration 25 + fault injection 4 **Passed** (E3); integration 25 **Passed** through the k3s ingress (E4,
fault tests skipped there because they drive Docker Compose); smoke **Passed** on E3 and E4; upgrade
tests legacy_compose and legacy_k8s **Passed** (E3).

---

## P0

### SEC-01 Committed credentials
Changed: `.env` untracked (`git rm --cached`), `.gitignore`, `.env.example` (placeholders only),
`scripts/init_env.py` (random secrets), no credentials in Compose/SQL/YAML, DML-only app account
created by `db/migrate.py`, `.dockerignore`, `scripts/package.sh` (ZIP from `git archive`),
`scripts/secret-scan.sh` (gitleaks), owner checklist in [SECURITY.md](SECURITY.md).

| Check | Result |
|---|---|
| `git ls-files .env` prints nothing | **Passed** |
| Secret scan of tracked files (`bash scripts/secret-scan.sh`) | **Passed** (no leaks after renaming two test variables that were false positives) |
| Stack starts from self-created settings (`init_env.py` + Compose) | **Passed** (E3) |
| App account privileges after migration (`SHOW GRANTS`) = `SELECT, INSERT, UPDATE, DELETE` only, legacy `ALL PRIVILEGES` revoked | **Passed** (upgrade test, E3) |
| Secret scan of the delivery ZIP (`scripts/package.sh`: `git archive` of HEAD, then gitleaks) | **Passed** (no leaks; ZIP has no `.git`, `.env` or credentials files) |
| History scan (`secret-scan.sh --history`) | Run: 4 findings in `8e22b62` (k8s/configmap.yaml, POWERSHELL_TESTING_GUIDE.md); manual review lists more (SECURITY.md §1) |
| Rotation of the leaked passwords | **Not done** (owner action) |
| History rewrite / force push | **Not done** (needs owner decision; steps in SECURITY.md) |

### SEC-02 Authentication and authorisation
Changed: `shared/smart_shared/auth.py`, `inventory-service/app/routers/auth.py`, dependencies on
every router, service token for reservations, gateway strips `X-Service-Token` and rate-limits
login, frontend login/logout and role-based buttons.

| Check | Result |
|---|---|
| Anonymous cannot read orders/customer data or write anything (401) | **Passed** (E1 unit, E3/E4 integration) |
| Viewer can read, cannot write (403) | **Passed** (E1, E3, E4) |
| Staff can read/write; forged and expired tokens rejected | **Passed** (E1) |
| Service token works only on reservation/read endpoints; users cannot reserve | **Passed** (E1) |
| Gateway strips the service token from outside requests | **Passed** (E3, E4) |
| Login rate limit returns 429 | **Passed** (E3, E4) |

### SEC-03 Stored XSS
Changed: `frontend/app.js` rewritten: DOM built with `createElement`/`textContent`/`new Option`, no
`innerHTML` with data, no inline handlers; `index.html` without inline scripts/handlers, pinned CDN
assets with SRI; CSP without `unsafe-inline` in the gateway.

| Check | Result |
|---|---|
| HTML/event-handler payloads in product name/SKU, customer name, address, notes shown as text in dashboard alerts, product list, stock list, product dropdown, order list, order details and reports; nothing executes | **Passed** (E5 browser: `window.__xss` undefined, 0 injected elements, 0 CSP violations) |
| Automated regression test (`tests/frontend/xss.test.mjs`) | **Passed**; it **fails** when rendering is switched back to HTML insertion (mutation check done) |

### DATA-01 Atomic stock changes
Changed: `stock.py` adjust/set lock the inventory row (`SELECT ... FOR UPDATE`) in one
transaction; reservations lock rows in product-id order; `set` supports `expected_stock`.

| Check | Result |
|---|---|
| Stock 1, 20 parallel `-1`: exactly one 200, nineteen 409, final 0, five rounds | **Passed** (E3, E4) |
| 25 parallel `+2` from 0 end at 50 (no lost update) | **Passed** (E3, E4) |
| Stock 3, 15 parallel orders: exactly 3 created, final 0 | **Passed** (E3, E4) |

### DATA-02 Order creation compensation and idempotency
Changed: inventory reservation API (`routers/reservations.py`: all-or-nothing, idempotent per id,
release tombstones, commit); order-service `order_workflow.py` (merge duplicate items, record
intent first, classify definite vs unknown failures, compensate only real reservations,
`Idempotency-Key`, reconcile loop + `/admin/reconcile`), product name/SKU snapshot in order items.

| Check | Result |
|---|---|
| Second item insufficient: no partial deduction, no order left | **Passed** (E1, E3) |
| DB failure after reservation, then retry with same key: one deduction, order created | **Passed** (E1) |
| Reserve timeout before / after the inventory commit: stock ends unchanged, order FAILED | **Passed** (E1) |
| Timeout and failed release: order stays pending; reconcile releases exactly once; a second pass changes nothing | **Passed** (E1) |
| Response building fails after commit: no release, retry returns the same order | **Passed** (E1) |
| Same request resent (sequential and 8 in parallel): one order, one deduction | **Passed** (E1, E3, E4) |
| Same key with a different body: 422 | **Passed** (E1) |

### DATA-03 Cancel, refund, delete
Changed: single `begin_transition` + `sync_inventory` path for PATCH status and POST cancel;
rules CREATED->CANCELLED (release), PAID->REFUNDED (release), PAID->SHIPPED (commit),
SHIPPED->REFUNDED (no restock); PAID->CANCELLED rejected; delete only for
CANCELLED/REFUNDED/FAILED without pending stock work. API change: cancel is now
`POST /api/orders/{id}/cancel` and `DELETE /api/orders/{id}` deletes.

| Check | Result |
|---|---|
| Illegal transitions have no stock side effect | **Passed** (E1, E3) |
| Cancel returns stock once; PATCH CANCELLED gives the same result | **Passed** (E1) |
| 10 parallel cancels: one succeeds, stock restored once | **Passed** (E3, E4) |
| Release failure during cancel is retried by reconcile, still once | **Passed** (E1) |
| Delete of open or pending orders refused | **Passed** (E1, E3) |

## P1

### ARCH-01 Gateway and same-origin frontend
Changed: relative `/api/...` URLs, Nginx gateway image (`gateway/`), only the gateway published.

| Check | Result |
|---|---|
| `app.js` contains no `localhost`, `8001`, `8002` | **Passed** (E3, E4) |
| CRUD, orders and dashboard through the gateway | **Passed** (smoke E3/E4; browser E5) |
| Only the gateway has a published port | **Passed** (E3 fault test) |
| Access from a second physical computer | **Not run** (single machine; same-origin URLs make it independent of the host) |

### ARCH-02 Single schema / migrations
Changed: `db/migrate.py` (versioned, idempotent, lock-protected) used by the Compose `migrate`
service and the Kubernetes `db-migrate` Job; `create_all()` and `mysql/init/*.sql` removed;
readiness requires the schema version.

| Check | Result |
|---|---|
| Fresh Compose database + CRUD/order/status tests | **Passed** (E3) |
| Fresh Kubernetes database (Job) + tests | **Passed** (E4) |
| Legacy Compose schema with orders upgraded in place, then smoke + legacy-order rules | **Passed** (`tests/upgrade/run_upgrade_test.sh legacy_compose`) |
| Legacy Kubernetes schema (quantity/total_amount/price, INT ids, duplicate inventory rows) upgraded | **Passed** (`run_upgrade_test.sh legacy_k8s`) |
| Re-running the migration changes nothing | **Passed** (both upgrade tests) |
| Old MySQL 5.7 data directory to 8.4 | **Not run**; documented as dump and restore (README) |

### ARCH-03 Persistent MySQL storage
Changed: StatefulSet + `volumeClaimTemplates` 10Gi (default StorageClass), one replica.

| Check | Result |
|---|---|
| PVC bound | **Passed** (E4: `data-mysql-0 Bound 10Gi local-path`) |
| Data survives deleting the MySQL pod (new pod UID, product still present) | **Passed** (E4, 2026-10-26T10:39:29Z-10:39:51Z) |
| Same on GKE (`standard-rwo` PD) | **Not run** |
| Default cleanup keeps the PVC | Implemented (`deploy.sh cleanup`); **Not run** |

### ARCH-04 Configuration contract
Changed: one set of variable names and Service names for Compose and Kubernetes
(README table); `INVENTORY_BASE_URL` and `REDIS_HOST` are read from the environment; fail-fast
on missing values.

| Check | Result |
|---|---|
| Both environments resolve the services with the same names | **Passed** (E3, E4) |
| Missing/placeholder values fail with the variable name and no value | **Passed** (E1 unit test; `deploy.sh apply` without Secret fails clearly, E4) |

### ARCH-05 Ingress, routing and frontend deployment
Changed: gateway Deployment/Service in Kubernetes; Ingress has one backend (gateway), no
rewrite; separate overlays: local (ingress class configurable) and GKE (GCE class, static IP,
ManagedCertificate, FrontendConfig, BackendConfig health check `/healthz`).

| Check | Result |
|---|---|
| `/`, static files, product/order APIs and health paths through a real ingress | **Passed** (E4, Traefik) |
| Rendered manifests valid (kubeconform) | **Passed** (local 16/16; GKE 16 valid, 3 GKE CRDs not checkable offline) |
| GCE ingress, backend health and certificate on GKE | **Not run** |

### SEC-04 HTTPS, CORS, exposed ports
Changed: no CORS unless configured (no credentials); security headers and CSP; HSTS when HTTPS;
GKE overlay with managed certificate and HTTP to HTTPS redirect; debug ports only in
`docker-compose.debug.yml` on 127.0.0.1.

| Check | Result |
|---|---|
| Only the gateway exposed | **Passed** (E3) |
| Headers present (CSP, nosniff, frame deny) | **Passed** (E3) |
| Public HTTPS without mixed content | **Not run** (needs GKE + domain) |

### EVENT-01 Stock change events
| Check | Result |
|---|---|
| Event with old/new/adjustment/UTC timestamp published on adjust | **Passed** (E1) |
| Received by the order-service subscriber | **Passed** (E3, E4) |
| Publish failure is logged, request still succeeds | **Passed** (E1) |

### EVENT-02 Non-blocking subscriber
Changed: `redis.asyncio` subscriber with reconnect/back-off, lifespan start/stop, no client retries.

| Check | Result |
|---|---|
| API responsive with no events | **Passed** (all E3/E4 tests run with the subscriber active) |
| Redis restart, then subscriber reconnects and receives again | **Passed** (E3 fault test) |
| Clean shutdown | Implemented (tasks cancelled and awaited); no dedicated test |

### EVENT-03 Pub/Sub scope
Documented as an event log only (README, architecture.md); e-mail/auto-replenishment/live push
marked planned. Order correctness without Redis: **Passed** (order created while Redis was stopped, E3).

### CACHE-01 Redis failure handling
| Check | Result |
|---|---|
| Redis down: product list served from MySQL; readiness "degraded" | **Passed** (E1, E3) |
| Corrupt cache entry is not returned as an empty list | **Passed** (E1) |
| Cache recovers after Redis returns | **Passed** (E1, E3) |
| Latency with Redis down | First request about 4 s (one DNS lookup for the stopped Compose container), then about 8 ms (circuit breaker). Found during testing: redis-py's default retries made it over 30 s; retries were disabled |

### API-01 Validation
| Check | Result |
|---|---|
| Negative price/stock, NaN/Infinity (also as JSON literal), more than 2 decimals, too-long strings, bad SKU, unknown fields, `limit` > 200 rejected with 422 | **Passed** (E1, E3) |
| Exact decimals (0.10 + 0.20 = "0.30"; order total 19.99 + 3 x 0.10 = "20.29") | **Passed** (E1) |
| Duplicate SKU in parallel: one 201, nine 409 | **Passed** (E3, E4) |
| Found during testing: the default 422 handler echoed the rejected input (passwords, NaN caused a 500); replaced | **Passed** |

## P2

### OPS-01 Probes
| Check | Result |
|---|---|
| MySQL stopped: readiness 503, liveness 200, **no container restarts** | **Passed** (E3 Compose; E4: 90 s outage, restart count stayed 0, pods recovered automatically) |
| Redis down does not make the services unready | **Passed** (E3) |
| MySQL/Redis probes in manifests | Implemented; exercised during E4 deployment |

### OPS-02 Deployment scripts
Changed: all old scripts removed (`k8s/build-and-push-images.sh` also overwrote the real service
code with stub apps); single `deploy/deploy.sh` (fail-fast, path-independent, render then validate
then apply, never creates clusters, `--yes` required for GKE apply, Artifact Registry instead of the
shut-down Container Registry, immutable commit tags).

| Check | Result |
|---|---|
| `validate` mode without a cluster (no cost) | **Passed** |
| Missing Secret stops `apply` with a clear message | **Passed** (E4) |
| Re-running `apply` is safe | **Passed** (E4, applied three times) |
| Run from another working directory | Implemented (paths from the script location); not separately tested |
| `build`/`push` to Artifact Registry, `apply gke` | **Not run** |

### OPS-03 HPA and rolling updates
Changed: HPA 1-4 pods at 60% CPU (docs aligned), no `replicas` in HPA-managed Deployments,
`maxUnavailable: 0`, preStop drain, commit-hash image tags, `scripts/traffic_check.py`.

| Check | Result |
|---|---|
| Rolling restart of 3 deployments + rollback under traffic, first attempt | **Failed**: 28 of 17,807 requests failed (502/timeouts at 10:42:39Z) (E4) |
| After adding preStop drain and removing gateway upstream keepalive | **Passed**: 0 of 19,404 failed, 10:48:42Z-10:51:12Z (E4) |
| HPA scale-in when idle, scale-out under load | **Passed** (E4, timeline below) |
| Same on GKE | **Not run**, so "zero downtime" may only be claimed for this local test |

HPA run (E4, k3s metrics-server, requests 100m CPU per pod, target 60%), from Kubernetes events:

| Time (UTC) | Event |
|---|---|
| 10:39:16 | inventory 1 -> 4, order 1 -> 3 during the integration test run ("cpu ... above target") |
| 10:56:33-10:56:48 | both scale back to 1 after the 5-minute stabilisation window ("All metrics below target"); idle CPU 4-6% |
| 11:04:47 | load starts: `traffic_check.py --workers 6 --seconds 180` |
| 11:05:18 | order-service 1 -> 4 (CPU 499% of request) |
| 11:05:33 | inventory-service 1 -> 4 |
| 11:05:33-11:08:25 | both held at maxReplicas 4 with CPU still 200-380%: on this laptop the 4-pod cap, not the HPA, limits throughput |
| 11:08:25 | load ends: 23,492 requests, 0 failed |

This shows that the HPA reacts within about 30 seconds. It does not measure capacity: the load
generator, the cluster and MySQL all shared one laptop.

### OPS-04 Containers and dependencies
| Check | Result |
|---|---|
| Containers run as non-root (uid 10001 / nginx 101) | **Passed** (E3, E4 with `runAsNonRoot`, read-only root FS) |
| Reproducible builds: base images pinned by digest, full lock files | Implemented |
| `pip-audit` on all three lock files | **Passed**: no known vulnerabilities (2026-10-26) |
| HPA gets metrics without TLS bypass (k3s built-in metrics-server) | **Passed** (E4); insecure variant only in `k8s/local-only/` |

### OPS-05 Time zones, errors, logs
UTC storage (session time zone forced), explicit offsets in responses, JSON logs with request ID,
generic 500 body. Leak check of 500 responses: **Passed** (E1). Legacy Sydney/UTC mixed
timestamps: not converted (documented).

### UI-01 Events and statistics
Explicit listeners (no global `event`); totals from `/api/inventory/stats` and `/api/orders/stats`;
paginated order list. More than 100 orders counted correctly: **Passed** (E1 with 120, E3 with 105).
Failed requests show "—" instead of 0: **Passed** (E5). Cross-browser check: only Chromium (**Not run** elsewhere).

### TEST-01 Tests
See the totals above. The old PowerShell/CMD scripts were replaced by
`tests/smoke_test.py` (runs from PowerShell or bash, exits 1 on failure: **Passed**, checked with
bad credentials). Test data uses unique `IT-`/`SMOKE-` prefixes; the Compose suite runs in its own
disposable project and volume.

### DOC-01 Documentation
README, [architecture.md](architecture.md) (Mermaid source, Compose and Kubernetes/GKE, shared DB
coupling), [SECURITY.md](SECURITY.md), [k8s/README.md](../k8s/README.md), this file,
[resume-notes.md](resume-notes.md). The original `Architecture Design.png` and DOCX are not in the
repository and were not modified.

## Open items needing the owner

1. Rotate the leaked database passwords; decide on history rewrite (SECURITY.md §1).
2. Review the commits on `fix/brief-remediation` (not pushed) and merge when satisfied; rebuild the ZIP with `bash scripts/package.sh` from the final commit.
3. GKE (only with budget approval): Artifact Registry repo, cluster, static IP, DNS, then
   `deploy.sh validate/build/push/apply gke --yes`; record HTTPS, backend health, HPA and rollout
   results here.
4. Fill in personal contribution in resume-notes.md; add the AI-use statement your course requires.
