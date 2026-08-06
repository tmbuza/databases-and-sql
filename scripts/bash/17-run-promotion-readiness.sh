#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
python_bin="${PYTHON_BIN:-python}"

cd "$repo_root"

"$python_bin" scripts/python/17-validate-promotion.py \
  --manifest config/17-release-manifest.json \
  --report results/17-promotion-readiness.json \
  --figure results/figures/17-promotion-readiness.png

echo "Wrote results/17-promotion-readiness.json"
echo "Wrote results/figures/17-promotion-readiness.png"
