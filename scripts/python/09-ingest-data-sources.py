#!/usr/bin/env python3
"""Create deterministic source fixtures and demonstrate audited ingestion."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIR = ROOT / "data" / "raw" / "09-source-fixtures"
LANDING_DIR = ROOT / "data" / "processed" / "09-ingested"
RESULTS_DIR = ROOT / "results"
FIGURES_DIR = RESULTS_DIR / "figures"
BATCH_ID = "dsdp09-demo-20260806"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(64 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_columns(frame: pd.DataFrame, required: set[str], source: str) -> None:
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"{source}: missing columns {sorted(missing)}")


def require_unique(frame: pd.DataFrame, key: str, source: str) -> None:
    if frame[key].isna().any():
        raise ValueError(f"{source}: null values in {key}")
    if frame[key].duplicated().any():
        raise ValueError(f"{source}: duplicate values in {key}")


def add_metadata(frame: pd.DataFrame, source_system: str, source_object: str) -> pd.DataFrame:
    result = frame.copy()
    result["source_system"] = source_system
    result["source_object"] = source_object
    result["batch_id"] = BATCH_ID
    result["ingested_at_utc"] = datetime.now(timezone.utc).isoformat()
    return result


def create_fixtures() -> tuple[Path, Path, Path]:
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    customers_path = SOURCE_DIR / "customers.csv"
    events_path = SOURCE_DIR / "support-events-pages.json"
    database_path = SOURCE_DIR / "commerce.sqlite"

    customers = pd.DataFrame(
        [
            ("C001", "enterprise", "TZ"),
            ("C002", "small-business", "KE"),
            ("C003", "consumer", "UG"),
            ("C004", "enterprise", "RW"),
            ("C005", "consumer", "TZ"),
        ],
        columns=["customer_id", "segment", "country"],
    )
    customers.to_csv(customers_path, index=False)

    pages = [
        {"page": 1, "next": "page-2", "items": [
            {"event_id": "E001", "customer_id": "C001", "channel": "email", "occurred_at": "2026-08-05T08:10:00Z"},
            {"event_id": "E002", "customer_id": "C003", "channel": "chat", "occurred_at": "2026-08-05T09:20:00Z"},
        ]},
        {"page": 2, "next": None, "items": [
            {"event_id": "E003", "customer_id": "C002", "channel": "phone", "occurred_at": "2026-08-05T11:45:00Z"},
            {"event_id": "E004", "customer_id": "C005", "channel": "chat", "occurred_at": "2026-08-05T14:05:00Z"},
        ]},
    ]
    events_path.write_text(json.dumps(pages, indent=2) + "\n", encoding="utf-8")

    database_path.unlink(missing_ok=True)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "CREATE TABLE orders (order_id TEXT PRIMARY KEY, customer_id TEXT, amount REAL, status TEXT, updated_at TEXT)"
        )
        connection.executemany(
            "INSERT INTO orders VALUES (?, ?, ?, ?, ?)",
            [
                ("O001", "C001", 1250.00, "paid", "2026-08-05T07:30:00Z"),
                ("O002", "C002", 84.50, "paid", "2026-08-05T10:15:00Z"),
                ("O003", "C003", 49.99, "pending", "2026-08-05T12:00:00Z"),
                ("O004", "C005", 215.75, "paid", "2026-08-05T15:40:00Z"),
                ("O005", "C004", 890.00, "refunded", "2026-08-05T17:05:00Z"),
                ("O006", "C001", 330.20, "paid", "2026-08-05T18:25:00Z"),
            ],
        )
    return customers_path, events_path, database_path


def audit_row(source: str, source_path: Path, rows: int, elapsed_ms: float, newest: str | None = None) -> dict[str, object]:
    return {
        "batch_id": BATCH_ID,
        "source": source,
        "source_object": source_path.name,
        "rows_ingested": rows,
        "source_bytes": source_path.stat().st_size,
        "sha256": sha256(source_path),
        "newest_source_timestamp": newest or "not_applicable",
        "duration_ms": round(elapsed_ms, 2),
        "validation_status": "passed",
    }


def main() -> None:
    LANDING_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    customers_path, events_path, database_path = create_fixtures()
    audit: list[dict[str, object]] = []

    started = perf_counter()
    customers = pd.read_csv(customers_path, dtype={"customer_id": "string"})
    require_columns(customers, {"customer_id", "segment", "country"}, "customers")
    require_unique(customers, "customer_id", "customers")
    add_metadata(customers, "crm-export", customers_path.name).to_csv(LANDING_DIR / "customers.csv", index=False)
    audit.append(audit_row("customers", customers_path, len(customers), (perf_counter() - started) * 1000))

    started = perf_counter()
    pages = json.loads(events_path.read_text(encoding="utf-8"))
    records = [item for page in pages for item in page["items"]]
    events = pd.json_normalize(records)
    require_columns(events, {"event_id", "customer_id", "occurred_at"}, "events")
    require_unique(events, "event_id", "events")
    events["occurred_at"] = pd.to_datetime(events["occurred_at"], utc=True, errors="raise")
    add_metadata(events, "support-api", "/v1/events").to_csv(LANDING_DIR / "support-events.csv", index=False)
    audit.append(audit_row("events", events_path, len(events), (perf_counter() - started) * 1000, events["occurred_at"].max().isoformat()))

    started = perf_counter()
    with sqlite3.connect(database_path) as connection:
        orders = pd.read_sql_query(
            "SELECT order_id, customer_id, amount, status, updated_at FROM orders ORDER BY updated_at, order_id",
            connection,
        )
    require_columns(orders, {"order_id", "customer_id", "amount", "status", "updated_at"}, "orders")
    require_unique(orders, "order_id", "orders")
    orders["updated_at"] = pd.to_datetime(orders["updated_at"], utc=True, errors="raise")
    add_metadata(orders, "commerce-db", "main.orders").to_csv(LANDING_DIR / "orders.csv", index=False)
    audit.append(audit_row("orders", database_path, len(orders), (perf_counter() - started) * 1000, orders["updated_at"].max().isoformat()))

    audit_frame = pd.DataFrame(audit)
    audit_path = RESULTS_DIR / "09-ingestion-audit.csv"
    audit_frame.to_csv(audit_path, index=False)

    plt.style.use("seaborn-v0_8-whitegrid")
    figure, axis = plt.subplots(figsize=(8, 4.8))
    bars = axis.bar(audit_frame["source"], audit_frame["rows_ingested"], color=["#155e75", "#0f766e", "#65a30d"])
    axis.bar_label(bars, padding=3, labels=[f"{value} rows" for value in audit_frame["rows_ingested"]])
    axis.set(title="DSDP 09 ingestion audit", xlabel="Source", ylabel="Rows ingested")
    axis.set_ylim(0, max(audit_frame["rows_ingested"]) + 2)
    figure.text(0.5, 0.01, f"Batch {BATCH_ID} · all boundary validations passed", ha="center", fontsize=9)
    figure.tight_layout(rect=(0, 0.04, 1, 1))
    figure.savefig(FIGURES_DIR / "09-ingestion-audit.png", dpi=180)
    plt.close(figure)

    print(audit_frame[["source", "rows_ingested", "validation_status"]].to_string(index=False))
    print(f"\nAudit: {audit_path.relative_to(ROOT)}")
    print(f"Plot:  {(FIGURES_DIR / '09-ingestion-audit.png').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
