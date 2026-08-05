#!/usr/bin/env python3
"""Generate and benchmark equivalent datasets in several storage layouts."""

from __future__ import annotations

import hashlib
import json
import shutil
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "processed"
RESULTS_DIR = ROOT / "results"
FIGURE_DIR = RESULTS_DIR / "figures"
ROW_COUNT = 60_000
SEED = 12
REPEATS = 5

CSV_PATH = DATA_DIR / "12-orders.csv"
JSONL_PATH = DATA_DIR / "12-orders.jsonl"
PARQUET_PATH = DATA_DIR / "12-orders.parquet"
PARTITION_ROOT = DATA_DIR / "12-orders-partitioned"

ORDER_SCHEMA = pa.schema(
    [
        pa.field("order_id", pa.string(), nullable=False),
        pa.field("order_timestamp", pa.timestamp("ns"), nullable=False),
        pa.field("customer_id", pa.string(), nullable=False),
        pa.field("product_id", pa.string(), nullable=False),
        pa.field("region", pa.string(), nullable=False),
        pa.field("channel", pa.string(), nullable=False),
        pa.field("quantity", pa.int32(), nullable=False),
        pa.field("unit_price", pa.float64(), nullable=False),
        pa.field("discount_rate", pa.float64(), nullable=False),
        pa.field("net_amount", pa.float64(), nullable=False),
        pa.field("order_year", pa.int16(), nullable=False),
        pa.field("order_month", pa.int8(), nullable=False),
    ]
)


def generate_orders() -> pd.DataFrame:
    """Create a deterministic, typed analytical order table."""
    rng = np.random.default_rng(SEED)
    start = np.datetime64("2025-01-01T00:00:00")
    seconds = rng.integers(0, 365 * 24 * 60 * 60, size=ROW_COUNT)
    timestamps = start + seconds.astype("timedelta64[s]")
    quantity = rng.integers(1, 8, size=ROW_COUNT, dtype=np.int32)
    unit_price = np.round(rng.lognormal(mean=3.4, sigma=0.65, size=ROW_COUNT), 2)
    discount = rng.choice([0.0, 0.05, 0.10, 0.15], ROW_COUNT, p=[0.65, 0.18, 0.12, 0.05])
    ts = pd.to_datetime(timestamps)
    frame = pd.DataFrame(
        {
            "order_id": [f"ORD-{i:07d}" for i in range(1, ROW_COUNT + 1)],
            "order_timestamp": ts,
            "customer_id": [f"CUS-{i:05d}" for i in rng.integers(1, 12_001, ROW_COUNT)],
            "product_id": [f"PRD-{i:04d}" for i in rng.integers(1, 751, ROW_COUNT)],
            "region": rng.choice(["central", "coastal", "lake", "northern", "southern"], ROW_COUNT),
            "channel": rng.choice(["web", "mobile", "partner"], ROW_COUNT, p=[0.49, 0.38, 0.13]),
            "quantity": quantity,
            "unit_price": unit_price,
            "discount_rate": discount,
        }
    )
    frame["net_amount"] = np.round(quantity * unit_price * (1 - discount), 2)
    frame["order_year"] = ts.year.astype("int16")
    frame["order_month"] = ts.month.astype("int8")
    return frame.sort_values("order_timestamp", kind="stable").reset_index(drop=True)


def arrow_table(frame: pd.DataFrame) -> pa.Table:
    return pa.Table.from_pandas(frame, schema=ORDER_SCHEMA, preserve_index=False, safe=True)


def write_datasets(frame: pd.DataFrame) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    if PARTITION_ROOT.exists():
        shutil.rmtree(PARTITION_ROOT)

    frame.to_csv(CSV_PATH, index=False, date_format="%Y-%m-%dT%H:%M:%S")
    frame.to_json(JSONL_PATH, orient="records", lines=True, date_format="iso")
    table = arrow_table(frame)
    pq.write_table(table, PARQUET_PATH, compression="snappy", row_group_size=10_000)
    ds.write_dataset(
        table,
        PARTITION_ROOT,
        format=ds.ParquetFileFormat(),
        partitioning=ds.partitioning(
            pa.schema([pa.field("order_year", pa.int16()), pa.field("order_month", pa.int8())]),
            flavor="hive",
        ),
        file_options=ds.ParquetFileFormat().make_write_options(compression="snappy"),
        basename_template="part-{i}.parquet",
        existing_data_behavior="delete_matching",
    )


def median_seconds(reader) -> float:
    measurements = []
    for _ in range(REPEATS):
        start = time.perf_counter()
        reader()
        measurements.append(time.perf_counter() - start)
    return statistics.median(measurements)


def directory_bytes(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*.parquet"))


def benchmark_formats() -> pd.DataFrame:
    rows = []
    specifications = [
        ("CSV", CSV_PATH, lambda: pd.read_csv(CSV_PATH, parse_dates=["order_timestamp"])),
        ("JSON Lines", JSONL_PATH, lambda: pd.read_json(JSONL_PATH, orient="records", lines=True)),
        ("Parquet (Snappy)", PARQUET_PATH, lambda: pd.read_parquet(PARQUET_PATH)),
    ]
    for name, path, reader in specifications:
        loaded = reader()
        rows.append(
            {
                "format": name,
                "row_count": len(loaded),
                "size_bytes": path.stat().st_size,
                "size_mib": path.stat().st_size / (1024**2),
                "median_read_ms": median_seconds(reader) * 1000,
                "row_count_valid": len(loaded) == ROW_COUNT,
            }
        )
    return pd.DataFrame(rows)


def benchmark_pruning(frame: pd.DataFrame) -> pd.DataFrame:
    columns = ["order_id", "order_timestamp", "net_amount", "region"]
    june_path = PARTITION_ROOT / "order_year=2025" / "order_month=6"
    if not june_path.exists():
        june_path = PARTITION_ROOT / "order_year=2025" / "order_month=06"
    all_files = list(PARTITION_ROOT.rglob("*.parquet"))
    selected_files = list(june_path.rglob("*.parquet"))
    expected_june = int((frame["order_month"] == 6).sum())

    full_projected = lambda: pd.read_parquet(PARQUET_PATH, columns=columns)
    june_partition = lambda: pd.read_parquet(june_path, columns=columns)
    full_filtered = lambda: pd.read_parquet(PARQUET_PATH, columns=columns).loc[
        lambda data: data["order_timestamp"].dt.month == 6
    ]

    results = [
        {
            "access_pattern": "full parquet, projected columns",
            "rows_returned": len(full_projected()),
            "files_considered": 1,
            "bytes_considered": PARQUET_PATH.stat().st_size,
            "median_read_ms": median_seconds(full_projected) * 1000,
        },
        {
            "access_pattern": "full parquet, then filter June",
            "rows_returned": len(full_filtered()),
            "files_considered": 1,
            "bytes_considered": PARQUET_PATH.stat().st_size,
            "median_read_ms": median_seconds(full_filtered) * 1000,
        },
        {
            "access_pattern": "June partition only",
            "rows_returned": len(june_partition()),
            "files_considered": len(selected_files),
            "bytes_considered": sum(p.stat().st_size for p in selected_files),
            "median_read_ms": median_seconds(june_partition) * 1000,
        },
    ]
    output = pd.DataFrame(results)
    output["expected_june_rows"] = expected_june
    output["row_count_valid"] = output.apply(
        lambda row: row["rows_returned"] == (ROW_COUNT if row["access_pattern"].startswith("full parquet, projected") else expected_june),
        axis=1,
    )
    output["all_partition_files"] = len(all_files)
    output["partitioned_dataset_bytes"] = directory_bytes(PARTITION_ROOT)
    return output


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(benchmark: pd.DataFrame, pruning: pd.DataFrame) -> dict:
    files = [CSV_PATH, JSONL_PATH, PARQUET_PATH, *sorted(PARTITION_ROOT.rglob("*.parquet"))]
    return {
        "dataset": "orders",
        "dataset_version": "12.1",
        "schema_version": "1.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": "scripts/python/12-benchmark-storage-formats.py",
        "seed": SEED,
        "expected_rows": ROW_COUNT,
        "partition_columns": ["order_year", "order_month"],
        "compression": "snappy",
        "validation": {
            "all_format_row_counts_valid": bool(benchmark["row_count_valid"].all()),
            "all_access_pattern_counts_valid": bool(pruning["row_count_valid"].all()),
        },
        "files": [
            {"path": str(path.relative_to(ROOT)), "size_bytes": path.stat().st_size, "sha256": sha256(path)}
            for path in files
        ],
    }


def plot_results(benchmark: pd.DataFrame) -> None:
    plt.style.use("seaborn-v0_8-whitegrid")
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.2))
    colors = ["#4C78A8", "#F58518", "#54A24B"]
    axes[0].bar(benchmark["format"], benchmark["size_mib"], color=colors)
    axes[0].set_title("Storage size")
    axes[0].set_ylabel("MiB")
    axes[1].bar(benchmark["format"], benchmark["median_read_ms"], color=colors)
    axes[1].set_title(f"Median full-read time ({REPEATS} runs)")
    axes[1].set_ylabel("Milliseconds")
    for axis in axes:
        axis.tick_params(axis="x", rotation=15)
        for container in axis.containers:
            axis.bar_label(container, fmt="%.2f", padding=3, fontsize=9)
    fig.suptitle("Equivalent order data, different physical formats", fontsize=14, fontweight="bold")
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "12-storage-format-comparison.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def write_samples(frame: pd.DataFrame) -> None:
    sample = frame.head(100)
    sample.to_csv(DATA_DIR / "12-orders-sample.csv", index=False, date_format="%Y-%m-%dT%H:%M:%S")
    pq.write_table(arrow_table(sample), DATA_DIR / "12-orders-sample.parquet", compression="snappy")


def main() -> None:
    frame = generate_orders()
    write_datasets(frame)
    benchmark = benchmark_formats()
    pruning = benchmark_pruning(frame)
    benchmark.to_csv(RESULTS_DIR / "12-storage-benchmark.csv", index=False, float_format="%.4f")
    pruning.to_csv(RESULTS_DIR / "12-partition-pruning.csv", index=False, float_format="%.4f")
    manifest = build_manifest(benchmark, pruning)
    (RESULTS_DIR / "12-storage-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    write_samples(frame)
    plot_results(benchmark)
    if not manifest["validation"]["all_format_row_counts_valid"] or not manifest["validation"]["all_access_pattern_counts_valid"]:
        raise SystemExit("Storage validation failed")
    print(benchmark.to_string(index=False))
    print("\nPartition pruning:\n" + pruning.to_string(index=False))
    print("\nStorage benchmark and validation completed successfully.")


if __name__ == "__main__":
    main()
