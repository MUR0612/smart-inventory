#!/usr/bin/env bash
# Build the submission ZIP from COMMITTED files only (git archive): no .git,
# no .env, no credentials, no local data. Then secret-scan the result.
set -euo pipefail
export MSYS_NO_PATHCONV=1
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
[[ -z "$(git status --porcelain)" ]] || { echo "error: commit or stash changes first (the ZIP contains HEAD only)"; exit 1; }
mkdir -p dist
NAME="smart-inventory-$(git rev-parse --short=12 HEAD)"
git archive --format=zip --prefix="$NAME/" -o "dist/$NAME.zip" HEAD
echo "created dist/$NAME.zip"
if unzip -l "dist/$NAME.zip" | grep -E "/\.env$|\.credentials$|/\.git/"; then echo "error: forbidden file in ZIP"; exit 1; fi
bash "$ROOT/scripts/secret-scan.sh" "dist/$NAME.zip"
