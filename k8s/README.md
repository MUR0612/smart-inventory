# Kubernetes deployment

One layout, two targets:

```
k8s/base/              shared manifests (namespace, config, MySQL StatefulSet + PVC, Redis,
                       migration Job, inventory/order services, gateway, HPA)
k8s/overlays/local/    local cluster: locally built images, HTTP ingress (ingress-nginx by default)
k8s/overlays/gke/      GKE: Artifact Registry images, GCE ingress, static IP, Google-managed TLS
k8s/local-only/        metrics-server with --kubelet-insecure-tls, for Docker Desktop ONLY
deploy/deploy.sh       the only deployment entry point (render / validate / build / push / secret / apply / cleanup)
```

The browser only talks to the **gateway** (Nginx serving the frontend and proxying `/api/*`
unchanged). The Ingress has a single backend, the gateway Service, so there is no path rewriting
and the same gateway config runs in Docker Compose and Kubernetes. Service names (`mysql`,
`redis`, `inventory-service`, `order-service`) and environment variable names are the same as in
`docker-compose.yml`.

What runs where:

| Component | Kind | Notes |
|---|---|---|
| gateway | Deployment (2 replicas) + Service | `/healthz` used by probes and the GKE load balancer |
| inventory-service, order-service | Deployment + Service + HPA (1-4 pods, 60% CPU) | liveness `/api/<svc>/livez`, readiness `/api/<svc>/readyz` (MySQL + schema version) |
| mysql | StatefulSet (1 replica) + headless Service + 10 GiB PVC | data survives pod deletion; **not** a backup, **not** HA |
| redis | Deployment + Service | cache and demo event channel, no persistence |
| db-migrate | Job | runs `db/migrate.py` once per deploy; also creates the DML-only app account |

## Configuration and secrets

`smart-inventory-config` (ConfigMap, committed) holds non-secret values. The Secret
`smart-inventory-secret` is **never committed**; `deploy.sh secret` creates it from your local
`.env` (keys `DB_USER, DB_PASSWORD, MYSQL_ROOT_PASSWORD, AUTH_SECRET, SERVICE_TOKEN, AUTH_USERS`).
Apps only receive the keys they need (never the MySQL root password). `apply` refuses to run if
the Secret is missing, and the services refuse to start with missing or placeholder values.

## Validate without a cluster (no cost)

```bash
bash deploy/deploy.sh validate local
```

```bash
PROJECT_ID=my-project REGION=australia-southeast1 REPOSITORY=smart-inventory DOMAIN=inventory.example.com IMAGE_TAG=dryrun bash deploy/deploy.sh validate gke
```

`validate` renders to `dist/k8s-<env>.yaml`, fails if placeholders remain, runs kubeconform
offline, and adds `kubectl apply --dry-run=server` when a cluster is reachable. GKE custom
resources (ManagedCertificate, FrontendConfig, BackendConfig) have no offline schema and are
reported as skipped; only a real GKE cluster validates them.

## Local cluster (Docker Desktop Kubernetes, kind, k3s, minikube)

```bash
python scripts/init_env.py
bash deploy/deploy.sh build local
bash deploy/deploy.sh secret .env
bash deploy/deploy.sh apply local
```

- kind / k3s / minikube do not see Docker Desktop images automatically: load them first
  (`kind load docker-image ...`, `k3s ctr images import`, `minikube image load ...`).
- The ingress uses `ingressClassName: nginx` (ingress-nginx). For another controller:
  `INGRESS_CLASS=traefik bash deploy/deploy.sh apply local` (k3s ships Traefik).
- HPA needs a metrics API. k3s and GKE include one. On Docker Desktop, metrics-server only works
  with kubelet TLS verification disabled: `kubectl apply -f k8s/local-only/metrics-server-insecure-tls.yaml`.
  Never apply anything from `k8s/local-only/` to a shared or cloud cluster.

## GKE (billable: confirm budget and region before each step)

`deploy.sh` never creates or deletes clusters, IP addresses or registries. Run these yourself,
once, after checking current prices for your region. Commands follow the current GKE docs
(Artifact Registry replaces the shut-down Container Registry; a Google-managed certificate needs a
domain you control); re-check them against Google's documentation when you deploy.

```bash
gcloud config set project PROJECT_ID
gcloud services enable container.googleapis.com artifactregistry.googleapis.com compute.googleapis.com
gcloud artifacts repositories create smart-inventory --repository-format=docker --location=REGION
gcloud auth configure-docker REGION-docker.pkg.dev
gcloud container clusters create smart-inventory --zone=ZONE --num-nodes=2 --machine-type=e2-standard-2
gcloud container clusters get-credentials smart-inventory --zone=ZONE
gcloud compute addresses create smart-inventory-ip --global
gcloud compute addresses describe smart-inventory-ip --global --format='value(address)'
```

Point a DNS A record for `DOMAIN` at that address, then (from a clean, committed checkout so the
image tag is the commit hash):

```bash
export PROJECT_ID=... REGION=... REPOSITORY=smart-inventory DOMAIN=...
bash deploy/deploy.sh validate gke
bash deploy/deploy.sh build gke
bash deploy/deploy.sh push gke
bash deploy/deploy.sh secret .env
bash deploy/deploy.sh apply gke --yes
```

After `apply`: certificate provisioning takes from minutes up to about an hour
(`kubectl -n smart-inventory describe managedcertificate smart-inventory-cert`). Check backend
health in the Ingress annotations (`kubectl -n smart-inventory describe ingress smart-inventory`)
and test `https://DOMAIN/`, `https://DOMAIN/api/inventory/readyz` and `https://DOMAIN/api/orders/readyz`.
Plain HTTP is redirected to HTTPS by the FrontendConfig. Until the certificate is `Active` the site
is not served over HTTPS; do not share the URL before then.

The 2 x e2-standard-2 cluster above is a **configuration choice, not a measured cost**. Check the
real cost in the billing console for the hours you actually ran it.

## Demonstrations (run them, keep the output)

Autoscaling (Pod HPA; node autoscaling is a separate cluster setting and is not configured here):

```bash
kubectl -n smart-inventory get hpa -w
python scripts/traffic_check.py --base-url https://DOMAIN --credentials-file .env.credentials --seconds 180 --workers 6
```

Rolling update and rollback while measuring failed requests:

```bash
python scripts/traffic_check.py --base-url https://DOMAIN --credentials-file .env.credentials --seconds 150 --workers 3
kubectl -n smart-inventory rollout restart deployment/inventory-service deployment/order-service deployment/gateway
kubectl -n smart-inventory rollout undo deployment/inventory-service
```

Run the first command in one terminal and the `kubectl` commands in a second one while it is
running. `traffic_check.py` prints every failed request and exits 1 if there was any, so "no
failed requests" is a measurement, not an assumption. Images are tagged with the commit hash
(immutable), so `rollout undo` returns to exactly the previous build. Schema changes must stay
backwards compatible for one release, because old and new pods run side by side during a rollout;
the readiness check waits for the schema version each build needs.

Persistence:

```bash
kubectl -n smart-inventory delete pod mysql-0
kubectl -n smart-inventory wait --for=condition=ready pod/mysql-0 --timeout=300s
```

Create a product before deleting the pod and check it is still there afterwards.

Recorded results from a local k3s run are in [docs/STATUS.md](../docs/STATUS.md). Nothing has
been verified on GKE yet.

## Cleanup

```bash
bash deploy/deploy.sh cleanup
```

This removes workloads but **keeps** the namespace, the Secret and the MySQL PVC (data).
`bash deploy/deploy.sh cleanup --delete-data` also deletes the PVC and namespace. To stop GKE
billing you must also delete the cluster and the static IP yourself:

```bash
gcloud container clusters delete smart-inventory --zone=ZONE
gcloud compute addresses delete smart-inventory-ip --global
```

Check the console afterwards for leftover disks and load balancers.
