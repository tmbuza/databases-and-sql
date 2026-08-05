#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

python_bin="${PYTHON_BIN:-python3}"
export MPLCONFIGDIR="${MPLCONFIGDIR:-${TMPDIR:-/tmp}/dsdp-matplotlib}"
mkdir -p "$MPLCONFIGDIR"

"$python_bin" scripts/python/12-benchmark-storage-formats.py
