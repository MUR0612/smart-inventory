#!/usr/bin/env bash
# Single deployment entry point for Kubernetes (local cluster or GKE).
#
#   deploy/deploy.sh render   <local|gke>        write dist/k8s-<env>.yaml (no cluster, no cost)
#   deploy/deploy.sh validate <local|gke>        render + offline schema check (+ server dry-run if a cluster is reachable)
#   deploy/deploy.sh build    <local|gke>        build the four images (gke: tags them for Artifact Registry)
#   deploy/deploy.sh push     gke                push images to Artifact Registry
#   deploy/deploy.sh secret   <env-file>         create/update the Kubernetes Secret from a .env file
#   deploy/deploy.sh apply    <local|gke> [--yes]  apply to the CURRENT kubectl context and wait for readiness
#   deploy/deploy.sh status
#   deploy/deploy.sh cleanup  [--delete-data]    remove workloads; keeps the namespace, Secret and MySQL PVC by default
#
# GKE settings come from the environment:
#   PROJECT_ID, REGION (e.g. australia-southeast1), REPOSITORY (Artifact Registry repo),
#   DOMAIN (DNS name pointing at the static IP "smart-inventory-ip"), IMAGE_TAG (default: git commit)
# This script never creates or deletes clusters, static IPs or registries; see k8s/README.md.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAMESPACE="smart-inventory"
IMAGES=(inventory-service order-service gateway db-migrate)
DIST="$ROOT/dist"

# Git Bash on Windows: stop MSYS rewriting arguments, convert host paths explicitly.
export MSYS_NO_PATHCONV=1
host_path() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else echo "$1"; fi; }

die() { echo "error: $*" >&2; exit 1; }
log() { echo "==> $*"; }
need() { command -v "$1" >/dev/null 2>&1 || die "'$1' is required but not installed"; }

dockerfile_for() {
  case "$1" in
    db-migrate) echo "db/Dockerfile" ;;
    gateway) echo "gateway/Dockerfile" ;;
    *) echo "$1/Dockerfile" ;;
  esac
}

image_tag() {
  if [[ -n "${IMAGE_TAG:-}" ]]; then echo "$IMAGE_TAG"; return; fi
  local sha
  sha="$(git -C "$ROOT" rev-parse --short=12 HEAD 2>/dev/null)" || die "set IMAGE_TAG (not a git checkout)"
  if [[ -n "$(git -C "$ROOT" status --porcelain 2>/dev/null)" ]]; then
    die "working tree has uncommitted changes; commit first or set IMAGE_TAG explicitly (tags must be immutable)"
  fi
  echo "$sha"
}

gke_settings() {
  : "${PROJECT_ID:?set PROJECT_ID}" "${REGION:?set REGION}" "${REPOSITORY:?set REPOSITORY}" "${DOMAIN:?set DOMAIN}"
  [[ "$PROJECT_ID" =~ ^[a-z][a-z0-9-]{4,28}[a-z0-9]$ ]] || die "PROJECT_ID looks invalid"
  [[ "$REGION" =~ ^[a-z]+-[a-z]+[0-9]$ ]] || die "REGION looks invalid (example: australia-southeast1)"
  [[ "$DOMAIN" =~ ^[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]] || die "DOMAIN looks invalid"
  REGISTRY="$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY"
  TAG="$(image_tag)"
}

image_ref() {  # image_ref <env> <name>
  if [[ "$1" == local ]]; then echo "smart-inventory/$2:local"; else echo "$REGISTRY/$2:$TAG"; fi
}

render() {
  local env="$1"
  local out="$DIST/k8s-$env.yaml" work="$ROOT/k8s/.render/$env"
  [[ "$env" == local || "$env" == gke ]] || die "environment must be local or gke"
  need kubectl
  rm -rf "$work" && mkdir -p "$work" "$DIST"
  {
    echo "apiVersion: kustomize.config.k8s.io/v1beta1"
    echo "kind: Kustomization"
    echo "resources: [../../overlays/$env]"
    if [[ "$env" == gke ]]; then
      gke_settings
      echo "images:"
      for name in "${IMAGES[@]}"; do
        echo "  - {name: REGION-docker.pkg.dev/PROJECT_ID/REPOSITORY/$name, newName: $REGISTRY/$name, newTag: \"$TAG\"}"
      done
      echo "patches:"
      echo "  - target: {kind: ManagedCertificate, name: smart-inventory-cert}"
      echo "    patch: '[{\"op\": \"replace\", \"path\": \"/spec/domains/0\", \"value\": \"$DOMAIN\"}]'"
    elif [[ -n "${INGRESS_CLASS:-}" ]]; then
      echo "patches:"
      echo "  - target: {kind: Ingress, name: smart-inventory}"
      echo "    patch: '[{\"op\": \"replace\", \"path\": \"/spec/ingressClassName\", \"value\": \"$INGRESS_CLASS\"}]'"
    fi
  } > "$work/kustomization.yaml"
  kubectl kustomize "$(host_path "$work")" > "$out"
  if grep -qE "PROJECT_ID|REPOSITORY/|IMAGE_TAG|\bDOMAIN\b" "$out"; then die "placeholders left in $out"; fi
  log "rendered $out"
  RENDERED="$out"
}

validate() {
  render "$1"
  need docker
  log "offline schema validation (kubeconform)"
  docker run --rm -v "$(host_path "$DIST"):/manifests:ro" ghcr.io/yannh/kubeconform:v0.6.7 \
    -strict -summary -ignore-missing-schemas "/manifests/$(basename "$RENDERED")"
  if kubectl version --request-timeout=5s >/dev/null 2>&1; then
    log "server-side dry run against context $(kubectl config current-context)"
    kubectl apply --dry-run=server -f "$(host_path "$RENDERED")" >/dev/null
    log "server dry run passed (nothing was changed)"
  else
    log "no reachable cluster: skipped server-side dry run"
  fi
}

build() {
  local env="$1"
  need docker
  [[ "$env" == gke ]] && gke_settings
  for name in "${IMAGES[@]}"; do
    log "building $(image_ref "$env" "$name")"
    docker build -f "$(host_path "$ROOT/$(dockerfile_for "$name")")" -t "$(image_ref "$env" "$name")" "$(host_path "$ROOT")"
  done
}

push() {
  [[ "${1:-}" == gke ]] || die "push is only for gke"
  need docker
  need gcloud
  gke_settings
  gcloud artifacts repositories describe "$REPOSITORY" --location "$REGION" --project "$PROJECT_ID" >/dev/null \
    || die "Artifact Registry repository $REPOSITORY not found in $REGION (create it first, see k8s/README.md)"
  for name in "${IMAGES[@]}"; do
    log "pushing $(image_ref gke "$name")"
    docker push "$(image_ref gke "$name")"
  done
}

secret() {
  local file="${1:?usage: deploy.sh secret <env-file>}"
  [[ -f "$file" ]] || die "$file not found"
  need kubectl
  local args=() key value
  for key in DB_USER DB_PASSWORD MYSQL_ROOT_PASSWORD AUTH_SECRET SERVICE_TOKEN AUTH_USERS; do
    value="$(grep -E "^$key=" "$file" | head -n1 | cut -d= -f2-)"
    [[ -n "$value" ]] || die "$key missing in $file"
    [[ "$value" != *CHANGE_ME* ]] || die "$key in $file still has the placeholder value"
    args+=("--from-literal=$key=$value")
  done
  kubectl get namespace "$NAMESPACE" >/dev/null 2>&1 || kubectl create namespace "$NAMESPACE" >/dev/null
  kubectl -n "$NAMESPACE" create secret generic smart-inventory-secret "${args[@]}" --dry-run=client -o yaml \
    | kubectl apply -f - >/dev/null
  log "secret smart-inventory-secret updated (values not shown)"
}

apply() {
  local env="$1" confirm="${2:-}"
  render "$env"
  need kubectl
  local context
  context="$(kubectl config current-context 2>/dev/null)" || die "no kubectl context configured"
  log "target context: $context"
  if [[ "$env" == gke && "$confirm" != "--yes" ]]; then
    die "applying to GKE creates billable resources (load balancer, disk). Re-run with --yes"
  fi
  kubectl -n "$NAMESPACE" get secret smart-inventory-secret >/dev/null 2>&1 \
    || die "secret smart-inventory-secret missing: run 'deploy/deploy.sh secret <env-file>' first"

  kubectl -n "$NAMESPACE" delete job db-migrate --ignore-not-found >/dev/null  # Jobs are immutable
  kubectl apply -f "$(host_path "$RENDERED")"
  log "waiting for the database migration"
  kubectl -n "$NAMESPACE" wait --for=condition=complete job/db-migrate --timeout=600s \
    || { kubectl -n "$NAMESPACE" logs job/db-migrate --tail=50 || true; die "migration did not complete"; }
  for deploy in inventory-service order-service gateway; do
    kubectl -n "$NAMESPACE" rollout status "deployment/$deploy" --timeout=300s || die "rollout of $deploy failed"
  done
  log "deployment ready in context $context"
  kubectl -n "$NAMESPACE" get ingress smart-inventory -o wide || true
  if [[ "$env" == gke ]]; then
    echo "The load balancer and certificate can take 10-60 minutes. Check with:"
    echo "  kubectl -n $NAMESPACE describe managedcertificate smart-inventory-cert"
    echo "  kubectl -n $NAMESPACE describe ingress smart-inventory   (backend health in annotations)"
  fi
}

status() {
  need kubectl
  kubectl -n "$NAMESPACE" get pods,svc,ingress,hpa,pvc,job -o wide
}

cleanup() {
  need kubectl
  log "removing workloads from namespace $NAMESPACE (context $(kubectl config current-context))"
  kubectl -n "$NAMESPACE" delete ingress,hpa,deployment,statefulset,service,job,configmap \
    -l app.kubernetes.io/part-of=smart-inventory --ignore-not-found
  if [[ "${1:-}" == "--delete-data" ]]; then
    log "deleting the MySQL volume and the namespace (data is lost)"
    kubectl -n "$NAMESPACE" delete pvc -l app=mysql --ignore-not-found
    kubectl -n "$NAMESPACE" delete pvc data-mysql-0 --ignore-not-found
    kubectl delete namespace "$NAMESPACE" --ignore-not-found
  else
    log "kept: namespace, Secret and PVC data-mysql-0 (use --delete-data to remove them)"
  fi
  echo "GKE billing continues until you also delete the cluster and the static IP (see k8s/README.md)."
}

cmd="${1:-}"; shift || true
case "$cmd" in
  render) render "${1:?environment}" ;;
  validate) validate "${1:?environment}" ;;
  build) build "${1:?environment}" ;;
  push) push "${1:-}" ;;
  secret) secret "${1:-}" ;;
  apply) apply "${1:?environment}" "${2:-}" ;;
  status) status ;;
  cleanup) cleanup "${1:-}" ;;
  *) sed -n '2,20p' "${BASH_SOURCE[0]}"; exit 1 ;;
esac
