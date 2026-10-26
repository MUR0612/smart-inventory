# Resume and portfolio wording (evidence-based)

Rules used here:

- Every claim links to code or to a recorded test in [STATUS.md](STATUS.md).
- No invented numbers. The figures below were measured once in a **local** environment
  (Docker Compose / k3s in Docker on one laptop) and must be presented as such.
- Nothing here says "production", "users", "zero downtime in the cloud" or "deployed on GKE":
  none of that has happened.
- **Personal contribution is not known from the repository.** The original code and this
  remediation (done with an AI assistant from a review brief, see README) must not be presented
  as solely your own work. Edit the `[...]` parts to match what you personally designed, wrote and
  verified, and remove bullets that you did not do.

## Suggested bullets

- Built a two-service inventory/order system (FastAPI, MySQL, Redis) behind an Nginx gateway for
  a Cloud Computing course, deployable with Docker Compose and Kubernetes. [Your part: ...]
- Made stock reservation safe under concurrency and partial failure: row-locked atomic updates,
  all-or-nothing multi-item reservations, idempotent reserve/release/commit, and a
  recorded-intent saga with background reconciliation between services. Verified with
  concurrent tests on MySQL 8.4 (e.g. 20 parallel decrements on stock 1: exactly one succeeds,
  over 5 rounds) and fault-injection tests (timeouts after commit, DB failure, retries).
- Hardened the deployment: removed committed credentials, least-privilege DB account, token
  login with read/write roles, service-to-service token, XSS-safe frontend with a strict CSP,
  only the gateway exposed, non-root containers.
- Kubernetes: StatefulSet MySQL on a 10 GiB PVC (data survived pod deletion in a test),
  liveness/readiness separation (a 90-second database outage caused no restarts), HPA on CPU,
  and a one-off migration Job. In a local k3s test, a rolling restart of all three deployments
  plus a rollback completed with 0 failed requests out of 19,404. The first measurement found 28
  failures, which led to adding a preStop drain.
- Wrote the test suite: 66 unit tests, 25 integration and 4 fault-injection tests through the
  gateway, frontend XSS regression tests, and schema upgrade tests from two legacy schemas.

## Do not claim (until there is evidence)

- GKE deployment, HTTPS on a real domain, autoscaling or rollout behaviour in the cloud.
- Cost figures (the 2 x e2-standard-2 cluster is a plan, not a bill).
- Load or performance numbers beyond the local test conditions above.
- E-mail alerts, auto-replenishment or real-time dashboards (not implemented).
- Payment processing (`PAID` is a manual status).
