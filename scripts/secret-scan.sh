#!/usr/bin/env bash
# Secret scanning with gitleaks (Docker image, pinned).
#   bash scripts/secret-scan.sh              tracked files of the working tree (what a commit/ZIP would contain)
#   bash scripts/secret-scan.sh some.zip     contents of a ZIP
#   bash scripts/secret-scan.sh --history    full git history (findings are redacted)
set -euo pipefail
export MSYS_NO_PATHCONV=1
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
hp() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else echo "$1"; fi; }
IMAGE="ghcr.io/gitleaks/gitleaks:v8.28.0"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT

if [[ "${1:-}" == "--history" ]]; then
  docker run --rm -v "$(hp "$ROOT"):/repo:ro" "$IMAGE" git /repo --redact --no-banner -v || exit 1
  exit 0
elif [[ -n "${1:-}" ]]; then
  ZIP="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"  # resolve before changing directory
  (cd "$WORK" && unzip -q "$(hp "$ZIP")")
else
  # Copy only tracked + new non-ignored files, so local .env files are not "found".
  (cd "$ROOT" && git ls-files -z --cached --others --exclude-standard | tar --null -T - -cf - | tar -xf - -C "$WORK")
fi
docker run --rm -v "$(hp "$WORK"):/scan:ro" "$IMAGE" dir /scan --redact --no-banner -v
echo "secret scan: no leaks found"
