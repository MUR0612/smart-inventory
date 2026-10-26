# Security notes

## 1. Credentials that were committed (owner action required)

Until October 2026 the repository contained database credentials in plain text. They are removed
from the current tree, but **they remain in git history and in any earlier ZIP**, and the history
is on the GitHub remote (`origin/master`). Treat every one of them as compromised. Nobody has
tested whether they still work (and nobody should, by logging in with them).

| Where (history only) | Commits | What |
|---|---|---|
| `.env` | `8e22b62`, `b0c4bc7` | MySQL root and app passwords, DB URL |
| `docker-compose.yml` | `8e22b62`, `b0c4bc7` | `DB_URL` with the MySQL **root** password |
| `mysql/init/01-users.sql` | `b0c4bc7` | `inventory_user` password |
| `k8s/configmap.yaml` | `8e22b62` | Secret values (base64 is encoding, not encryption) plus plaintext comments |
| `k8s/inventory-service.yaml`, `k8s/order-service.yaml` | `8e22b62` | `DB_URL` with the `inventory_user` password |
| `POWERSHELL_TESTING_GUIDE.md`, `README.md`, `k8s/README.md` | `8e22b62`, `a69c3e3` | example credentials; check whether they match real ones |

`bash scripts/secret-scan.sh --history` (gitleaks) flags only part of this list: short,
low-entropy passwords are not detected. The table above comes from a manual review.

Owner checklist (none of this has been done yet):

1. **Rotate**: change every password above anywhere it is still used (local MySQL volumes, any
   Cloud SQL / GKE / VM instance, other services where the same password was reused). New
   deployments of this code already generate fresh random secrets (`scripts/init_env.py`).
2. **Stop using old environments**: an old local volume still has the old passwords. Either run the
   migration with new `.env` values (it resets the app account password, see §3), or recreate
   the volume after a backup.
3. **Clean history (optional, after rotation)**: rotation is what actually protects you; rewriting
   history only reduces further exposure. It changes every commit hash and needs a force push,
   so coordinate with anyone who has a clone and the course submission. With
   [git-filter-repo](https://github.com/newren/git-filter-repo):

   ```bash
   git clone --mirror https://github.com/MUR0612/smart-inventory.git smart-inventory-mirror
   cd smart-inventory-mirror
   git filter-repo --invert-paths --path .env --path mysql/init/01-users.sql --path k8s/configmap.yaml
   git filter-repo --replace-text ../replacements.txt
   ```

   The first `filter-repo` drops whole files. The second redacts the remaining passwords in
   `docker-compose.yml`, `k8s/*.yaml` and the docs. Put one `old-password==>REDACTED` line per
   password in `replacements.txt`, keep that file outside the repository, and delete it afterwards.
   Then review with `bash scripts/secret-scan.sh --history`, `git push --force --mirror`, and ask
   GitHub support to purge cached views if the repository was ever public. Old ZIPs and forks are
   not affected by this; delete or replace them separately.

## 2. Secrets handling now

- `.env` is git-ignored and untracked; `.env.example` contains placeholders only, and the
  services and the migration refuse to start with a missing or `CHANGE_ME` value. The error names
  the variable, never its value.
- Kubernetes: the Secret is created from `.env` by `deploy/deploy.sh secret` and is not part of
  any manifest. Apps get only the keys they need; only MySQL and the migration Job see the root password.
- Submission ZIP: `bash scripts/package.sh` builds it from committed files with `git archive`
  (no `.git`, no `.env`, no local data) and runs gitleaks on the result.
- Logs: JSON lines with a request ID. Tokens, passwords and connection strings are not logged;
  failed logins are logged without the username; 500 responses contain only a request ID.

## 3. Database accounts

- `MYSQL_ROOT_PASSWORD` is used only by the MySQL container and the one-off migration.
- The services connect as `DB_USER` with `SELECT, INSERT, UPDATE, DELETE` on the schema only.
  The migration revokes anything else on every run (the old init script had granted
  `ALL PRIVILEGES`), and resets that account's password to `DB_PASSWORD`. Rotating it means
  changing `.env` (and the Kubernetes Secret), re-running the migration, then restarting the apps.

## 4. Access control (SEC-02): what it is and is not

Implemented: login with PBKDF2-hashed passwords from `AUTH_USERS`; HS256 tokens (8 h) checked
by both services; roles `viewer` (read-only, including customer data) and `staff` (all writes);
anonymous requests get 401 everywhere except health checks and the login endpoint; separate
service token for order-service to inventory-service, stripped by the gateway; login rate limit
(10/min per IP, burst 5) in Nginx.

Not implemented (state these limits in demos): no user database or self-service password
change, no token revocation (rotate `AUTH_SECRET` to log everyone out), no MFA, no per-record
permissions or audit trail beyond the order notes. The token is kept in `sessionStorage`, so an
XSS bug would expose it. That is why all rendering uses `textContent` and the CSP forbids inline
scripts.

## 5. Transport, CORS, exposure

- Local Compose is plain HTTP and binds the gateway to `GATEWAY_BIND` (use `127.0.0.1` on shared
  networks). It is labelled as local-only.
- Public deployment (GKE overlay): HTTPS via a Google-managed certificate, HTTP to HTTPS redirect, HSTS
  set by the gateway when the original request was HTTPS. Not verified on GKE yet.
- CORS is off by default (same origin). `CORS_ALLOWED_ORIGINS` enables it for listed origins
  only, without credentials.
- Only the gateway is exposed; MySQL/Redis/services have no published ports (checked by
  `tests/integration/test_faults.py::test_only_the_gateway_is_published`).
- Containers run as non-root with read-only root filesystems in Kubernetes.
- `k8s/local-only/` contains a metrics-server variant that disables kubelet TLS verification for
  Docker Desktop. It is not referenced by any overlay and must not be applied to cloud clusters
  (GKE provides metrics itself).
