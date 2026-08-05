#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

python_bin="${PYTHON_BIN:-python}"
input_path="data/raw/07-orders.csv"
output_path="data/processed/07-orders-curated.csv"
report_path="results/07-pipeline-run-report.json"
figure_path="results/figures/07-pipeline-stage-row-counts.png"

mkdir -p "$(dirname "$input_path")"

if [[ ! -f "$input_path" ]]; then
  printf '%s\n' \
    'order_id,order_date,customer_id,product,quantity,unit_price' \
    'ORD-1001,2026-08-01,CUST-101,Database Design Workbook,2,24.50' \
    'ORD-1002,2026-08-01,CUST-102,SQL Practice Cards,1,18.00' \
    'ORD-1003,2026-08-02,CUST-101,Pipeline Field Guide,3,31.25' \
    'ORD-1004,2026-08-03,CUST-103,Data Quality Checklist,4,12.75' \
    'ORD-1005,2026-08-04,CUST-104,ETL Patterns Poster,2,16.50' \
    > "$input_path"
fi

"$python_bin" scripts/python/07-build-reliable-pipeline.py \
  --input "$input_path" \
  --output "$output_path" \
  --report "$report_path" \
  --figure "$figure_path" \
  --run-date "2026-08-05"

