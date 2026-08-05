#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

export MPLCONFIGDIR="${MPLCONFIGDIR:-${TMPDIR:-/tmp}/dsdp-matplotlib}"
mkdir -p "$MPLCONFIGDIR"

python_executable="${PYTHON:-python3}"
if [[ -x ".venv/bin/python" ]]; then
  python_executable=".venv/bin/python"
fi

"$python_executable" scripts/python/02-run-querying-data.py
