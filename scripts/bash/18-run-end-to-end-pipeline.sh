#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
REPOSITORY_ROOT="$(CDPATH= cd -- "${SCRIPT_DIR}/../.." && pwd)"

cd "${REPOSITORY_ROOT}"
python scripts/python/18-run-end-to-end-pipeline.py \
  --config configs/18-pipeline.json "$@"
