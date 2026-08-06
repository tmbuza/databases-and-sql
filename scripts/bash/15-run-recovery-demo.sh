#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

export MPLCONFIGDIR="${MPLCONFIGDIR:-${TMPDIR:-/tmp}/dsdp-matplotlib}"
mkdir -p "$MPLCONFIGDIR" results/figures

python3 scripts/python/15-demonstrate-recovery.py \
  --database results/15-recovery-demo.sqlite \
  --summary results/15-recovery-summary.json \
  --verification results/15-recovery-verification.csv \
  --figure results/figures/15-recovery-comparison.png

echo "DSDP 15 recovery demonstration completed."

