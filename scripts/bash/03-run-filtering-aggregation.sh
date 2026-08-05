#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "$script_dir/../.." && pwd)"
cd "$project_root"

if ! command -v python >/dev/null 2>&1; then
  echo "ERROR: Python is not available on PATH." >&2
  exit 1
fi

python scripts/python/03-filtering-aggregation-and-grouping.py
