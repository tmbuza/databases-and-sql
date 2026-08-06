#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
python_bin="${PYTHON_BIN:-python3}"
export MPLCONFIGDIR="${MPLCONFIGDIR:-${TMPDIR:-/tmp}/dsdp16-matplotlib}"

cd "$repo_root"
mkdir -p "$MPLCONFIGDIR"
"$python_bin" scripts/python/16-governance-lineage-demo.py

printf 'Generated DSDP 16 evidence under results/.\n'
