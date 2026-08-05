#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

export MPLCONFIGDIR="${TMPDIR:-/tmp}/dsdp-06-matplotlib"
mkdir -p "$MPLCONFIGDIR"

if [[ -x ".venv/bin/python" ]]; then
  python_command=".venv/bin/python"
else
  python_command="python3"
fi

"$python_command" scripts/python/06-sql-python-integration.py
