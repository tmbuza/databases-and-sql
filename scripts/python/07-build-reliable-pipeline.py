#!/usr/bin/env python3
"""Run the DSDP-007 example file-based data pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from time import perf_counter

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


REQUIRED_COLUMNS = {
    "order_id",
    "order_date",
    "customer_id",
    "product",
    "quantity",
    "unit_price",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--figure", type=Path, required=True)
    parser.add_argument("--run-date", type=date.fromisoformat, default=date.today())
    return parser.parse_args()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65_536), b""):
            digest.update(block)
    return digest.hexdigest()


def extract(input_path: Path) -> pd.DataFrame:
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    return pd.read_csv(input_path)


def validate(orders: pd.DataFrame) -> dict[str, int]:
    missing = sorted(REQUIRED_COLUMNS.difference(orders.columns))
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    null_keys = int(orders[["order_id", "customer_id"]].isna().any(axis=1).sum())
    duplicates = int(orders["order_id"].duplicated(keep=False).sum())
    parsed_dates = pd.to_datetime(orders["order_date"], errors="coerce")
    invalid_dates = int(parsed_dates.isna().sum())
    numeric_quantity = pd.to_numeric(orders["quantity"], errors="coerce")
    numeric_price = pd.to_numeric(orders["unit_price"], errors="coerce")
    invalid_quantity = int(
        (numeric_quantity.isna() | (numeric_quantity <= 0) | (numeric_quantity % 1 != 0)).sum()
    )
    invalid_price = int((numeric_price.isna() | (numeric_price < 0)).sum())

    checks = {
        "null_business_keys": null_keys,
        "duplicate_order_rows": duplicates,
        "invalid_dates": invalid_dates,
        "invalid_quantities": invalid_quantity,
        "invalid_prices": invalid_price,
    }
    failed = {name: count for name, count in checks.items() if count > 0}
    if failed:
        details = ", ".join(f"{name}={count}" for name, count in failed.items())
        raise ValueError(f"Data contract failed: {details}")
    return checks


def transform(orders: pd.DataFrame, run_date: date) -> pd.DataFrame:
    curated = orders.copy()
    curated["order_date"] = pd.to_datetime(curated["order_date"]).dt.strftime("%Y-%m-%d")
    curated["quantity"] = pd.to_numeric(curated["quantity"]).astype("int64")
    curated["unit_price"] = pd.to_numeric(curated["unit_price"]).astype("float64")
    curated["revenue"] = (curated["quantity"] * curated["unit_price"]).round(2)
    curated["pipeline_run_date"] = run_date.isoformat()
    return curated.sort_values("order_id").reset_index(drop=True)


def load(curated: pd.DataFrame, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    curated.to_csv(temporary_path, index=False)
    temporary_path.replace(output_path)


def plot_stage_counts(source_rows: int, output_rows: int, figure_path: Path) -> None:
    figure_path.parent.mkdir(parents=True, exist_ok=True)
    stages = ["Extracted", "Validated", "Loaded"]
    counts = [source_rows, source_rows, output_rows]
    fig, ax = plt.subplots(figsize=(8, 4.8))
    bars = ax.bar(stages, counts, color=["#355C7D", "#2A9D8F", "#E9C46A"], width=0.62)
    ax.bar_label(bars, padding=4, fontsize=11, fontweight="bold")
    ax.set_title("DSDP-007 pipeline stage row counts", loc="left", fontweight="bold")
    ax.set_ylabel("Rows")
    ax.set_ylim(0, max(counts) * 1.25 if counts else 1)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.22)
    fig.tight_layout()
    fig.savefig(figure_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def write_report(report: dict, report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = report_path.with_suffix(report_path.suffix + ".tmp")
    temporary_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    temporary_path.replace(report_path)


def main() -> int:
    args = parse_args()
    run_id = str(uuid.uuid4())
    started_at = utc_now()
    timer = perf_counter()
    report: dict = {
        "pipeline": "dsdp-007-orders",
        "run_id": run_id,
        "run_date": args.run_date.isoformat(),
        "started_at_utc": started_at.isoformat(),
        "status": "running",
        "input": str(args.input),
        "output": str(args.output),
    }

    try:
        source = extract(args.input)
        checks = validate(source)
        curated = transform(source, args.run_date)
        load(curated, args.output)
        plot_stage_counts(len(source), len(curated), args.figure)
        report.update(
            {
                "status": "success",
                "input_sha256": sha256(args.input),
                "metrics": {
                    "source_rows": int(len(source)),
                    "output_rows": int(len(curated)),
                    "distinct_customers": int(curated["customer_id"].nunique()),
                    "total_revenue": round(float(curated["revenue"].sum()), 2),
                    **checks,
                },
            }
        )
    except Exception as exc:
        report.update(
            {
                "status": "failed",
                "error": {"type": type(exc).__name__, "message": str(exc)},
            }
        )
    finally:
        report["finished_at_utc"] = utc_now().isoformat()
        report["duration_seconds"] = round(perf_counter() - timer, 4)
        write_report(report, args.report)

    if report["status"] == "failed":
        print(f"[FAIL] {report['error']['type']}: {report['error']['message']}", file=sys.stderr)
        return 1

    print(f"[PASS] Pipeline completed: {run_id}")
    print(f"[PASS] Curated data: {args.output}")
    print(f"[PASS] Run report: {args.report}")
    print(f"[PASS] Figure: {args.figure}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

