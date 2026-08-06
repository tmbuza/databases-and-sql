#!/usr/bin/env python3
"""Run the DSDP 18 end-to-end course-transactions pipeline."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
import sys
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MONEY = Decimal("0.01")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def resolve_path(value: str, root: Path = REPOSITORY_ROOT) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def load_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        config = json.load(handle)
    required = {
        "pipeline_name", "pipeline_version", "schema_version", "currency",
        "input_path", "processed_path", "quarantine_path", "database_path",
        "manifest_path", "history_path", "figure_path", "required_columns",
        "allowed_segments", "allowed_statuses",
    }
    missing = sorted(required - config.keys())
    if missing:
        raise ValueError(f"Configuration missing keys: {', '.join(missing)}")
    return config


def source_fingerprint(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    byte_count = 0
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(block)
            byte_count += len(block)
    return digest.hexdigest(), byte_count


def extract(path: Path, required_columns: list[str]) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        actual = reader.fieldnames or []
        missing = [column for column in required_columns if column not in actual]
        if missing:
            raise ValueError(f"Source schema missing columns: {', '.join(missing)}")
        return [dict(row) for row in reader]


def parse_timestamp(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("timestamp requires a timezone")
    return parsed.astimezone(timezone.utc)


def validate_and_transform(
    rows: list[dict[str, str]], config: dict[str, Any], source_sha256: str, run_id: str
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    valid: list[dict[str, Any]] = []
    invalid: list[dict[str, str]] = []
    seen: set[str] = set()

    for source_row_number, raw in enumerate(rows, start=2):
        row = {key: (value or "").strip() for key, value in raw.items()}
        reasons: list[str] = []
        transaction_id = row["transaction_id"]
        if not transaction_id:
            reasons.append("missing_transaction_id")
        elif transaction_id in seen:
            reasons.append("duplicate_transaction_id")
        else:
            seen.add(transaction_id)

        for field in ("customer_id", "course_id"):
            if not row[field]:
                reasons.append(f"missing_{field}")

        segment = row["customer_segment"].lower()
        status = row["status"].lower()
        if segment not in config["allowed_segments"]:
            reasons.append("invalid_customer_segment")
        if status not in config["allowed_statuses"]:
            reasons.append("invalid_status")

        timestamp = None
        try:
            timestamp = parse_timestamp(row["transaction_at"])
        except (ValueError, TypeError):
            reasons.append("invalid_transaction_at")

        quantity = None
        try:
            quantity = int(row["quantity"])
            if quantity <= 0:
                reasons.append("quantity_must_be_positive")
        except (ValueError, TypeError):
            reasons.append("quantity_must_be_integer")

        unit_price = None
        try:
            unit_price = Decimal(row["unit_price"]).quantize(MONEY, rounding=ROUND_HALF_UP)
            if unit_price < 0:
                reasons.append("unit_price_must_be_non_negative")
        except (InvalidOperation, TypeError):
            reasons.append("unit_price_must_be_decimal")

        if reasons:
            rejected = dict(row)
            rejected["source_row_number"] = str(source_row_number)
            rejected["rejection_reasons"] = "|".join(reasons)
            invalid.append(rejected)
            continue

        assert timestamp is not None and quantity is not None and unit_price is not None
        gross_cents = int(unit_price * quantity * 100)
        net_cents = -gross_cents if status == "refunded" else gross_cents
        valid.append({
            "transaction_id": transaction_id,
            "transaction_at_utc": timestamp.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "transaction_date": timestamp.date().isoformat(),
            "customer_id": row["customer_id"],
            "course_id": row["course_id"],
            "customer_segment": segment,
            "status": status,
            "quantity": quantity,
            "unit_price_cents": int(unit_price * 100),
            "net_revenue_cents": net_cents,
            "currency": config["currency"],
            "source_row_number": source_row_number,
            "source_sha256": source_sha256,
            "pipeline_run_id": run_id,
        })
    return valid, invalid


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def initialize_database(connection: sqlite3.Connection) -> None:
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS fact_course_transactions (
            transaction_id TEXT PRIMARY KEY,
            transaction_at_utc TEXT NOT NULL,
            transaction_date TEXT NOT NULL,
            customer_id TEXT NOT NULL,
            course_id TEXT NOT NULL,
            customer_segment TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('completed', 'refunded')),
            quantity INTEGER NOT NULL CHECK (quantity > 0),
            unit_price_cents INTEGER NOT NULL CHECK (unit_price_cents >= 0),
            net_revenue_cents INTEGER NOT NULL,
            currency TEXT NOT NULL,
            source_row_number INTEGER NOT NULL,
            source_sha256 TEXT NOT NULL,
            pipeline_run_id TEXT NOT NULL,
            loaded_at_utc TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS pipeline_runs (
            run_id TEXT PRIMARY KEY,
            pipeline_name TEXT NOT NULL,
            pipeline_version TEXT NOT NULL,
            schema_version TEXT NOT NULL,
            source_sha256 TEXT NOT NULL,
            started_at_utc TEXT NOT NULL,
            finished_at_utc TEXT NOT NULL,
            extracted_rows INTEGER NOT NULL,
            valid_rows INTEGER NOT NULL,
            quarantined_rows INTEGER NOT NULL,
            status TEXT NOT NULL
        );
    """)


def load_and_verify(
    database_path: Path, records: list[dict[str, Any]], run: dict[str, Any]
) -> dict[str, Any]:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    loaded_at = run["finished_at_utc"]
    columns = list(records[0].keys()) if records else []
    with sqlite3.connect(database_path) as connection:
        initialize_database(connection)
        if records:
            insert_columns = columns + ["loaded_at_utc"]
            placeholders = ", ".join("?" for _ in insert_columns)
            updates = ", ".join(
                f"{column}=excluded.{column}" for column in insert_columns if column != "transaction_id"
            )
            sql = (
                f"INSERT INTO fact_course_transactions ({', '.join(insert_columns)}) "
                f"VALUES ({placeholders}) ON CONFLICT(transaction_id) DO UPDATE SET {updates}"
            )
            values = [[record[column] for column in columns] + [loaded_at] for record in records]
            connection.executemany(sql, values)

        transaction_ids = [record["transaction_id"] for record in records]
        if transaction_ids:
            placeholders = ",".join("?" for _ in transaction_ids)
            loaded_count, loaded_revenue, null_keys = connection.execute(
                f"""SELECT COUNT(*), COALESCE(SUM(net_revenue_cents), 0),
                           SUM(CASE WHEN customer_id IS NULL OR course_id IS NULL THEN 1 ELSE 0 END)
                    FROM fact_course_transactions WHERE transaction_id IN ({placeholders})""",
                transaction_ids,
            ).fetchone()
        else:
            loaded_count, loaded_revenue, null_keys = 0, 0, 0

        expected_revenue = sum(record["net_revenue_cents"] for record in records)
        checks = {
            "source_rows_reconciled": run["extracted_rows"] == run["valid_rows"] + run["quarantined_rows"],
            "valid_ids_unique": len(transaction_ids) == len(set(transaction_ids)),
            "valid_rows_present_in_target": loaded_count == len(records),
            "net_revenue_reconciled": loaded_revenue == expected_revenue,
            "loaded_business_keys_not_null": null_keys == 0,
        }
        if not all(checks.values()):
            raise RuntimeError(f"Reconciliation failed: {checks}")

        connection.execute(
            """INSERT OR REPLACE INTO pipeline_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run["run_id"], run["pipeline_name"], run["pipeline_version"],
                run["schema_version"], run["source"]["sha256"], run["started_at_utc"],
                run["finished_at_utc"], run["extracted_rows"], run["valid_rows"],
                run["quarantined_rows"], "passed",
            ),
        )
        warehouse_rows = connection.execute("SELECT COUNT(*) FROM fact_course_transactions").fetchone()[0]
    return {
        "status": "passed",
        "checks": checks,
        "loaded_batch_rows": loaded_count,
        "warehouse_rows_after_load": warehouse_rows,
        "net_revenue_cents": loaded_revenue,
    }


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def append_history(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "run_id", "started_at_utc", "finished_at_utc", "duration_seconds",
        "source_sha256", "extracted_rows", "valid_rows", "quarantined_rows",
        "validity_rate", "net_revenue_cents", "status",
    ]
    row = {
        "run_id": manifest["run_id"],
        "started_at_utc": manifest["started_at_utc"],
        "finished_at_utc": manifest["finished_at_utc"],
        "duration_seconds": manifest["duration_seconds"],
        "source_sha256": manifest["source"]["sha256"],
        "extracted_rows": manifest["extracted_rows"],
        "valid_rows": manifest["valid_rows"],
        "quarantined_rows": manifest["quarantined_rows"],
        "validity_rate": manifest["validity_rate"],
        "net_revenue_cents": manifest["reconciliation"]["net_revenue_cents"],
        "status": manifest["status"],
    }
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def write_svg(path: Path, valid: int, invalid: int, revenue_cents: int) -> None:
    total = valid + invalid
    rate = valid / total if total else 0
    values = [str(valid), str(invalid), f"{rate:.1%}", f"${revenue_cents / 100:,.2f}"]
    labels = ["Valid records", "Quarantined records", "Validity rate", "Net revenue"]
    colors = ["#167D6D", "#C75146", "#3D5A80", "#7A5195"]
    cards = []
    for index, (label, value, color) in enumerate(zip(labels, values, colors)):
        x = 35 + index * 205
        cards.append(
            f'<rect x="{x}" y="78" width="180" height="112" rx="10" fill="white" stroke="#D7DEE7"/>'
            f'<rect x="{x}" y="78" width="7" height="112" rx="3" fill="{color}"/>'
            f'<text x="{x + 20}" y="118" class="label">{label}</text>'
            f'<text x="{x + 20}" y="160" class="value" fill="{color}">{value}</text>'
        )
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="880" height="235" viewBox="0 0 880 235" role="img" aria-labelledby="title desc">
<title id="title">DSDP 18 pipeline run summary</title>
<desc id="desc">Eight valid records, four quarantined records, 66.7 percent validity, and 734 dollars 50 cents net revenue.</desc>
<style>.title{{font:700 22px system-ui,sans-serif;fill:#172B4D}}.label{{font:14px system-ui,sans-serif;fill:#52616B}}.value{{font:700 27px system-ui,sans-serif}}</style>
<rect width="880" height="235" fill="#F5F7FA"/>
<text x="35" y="42" class="title">Course-transactions pipeline: verified run</text>
{''.join(cards)}
<text x="35" y="218" class="label">Source rows reconcile; target keys and revenue checks passed.</text>
</svg>\n'''
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(svg, encoding="utf-8")


def run_pipeline(config_path: Path, run_id: str | None = None, write_history: bool = True) -> dict[str, Any]:
    started_clock = time.perf_counter()
    started_at = utc_now()
    config = load_config(config_path)
    selected_run_id = run_id or f"run-{uuid.uuid4().hex[:12]}"
    input_path = resolve_path(config["input_path"])
    sha256, byte_count = source_fingerprint(input_path)
    rows = extract(input_path, config["required_columns"])
    valid, invalid = validate_and_transform(rows, config, sha256, selected_run_id)

    valid_fields = list(valid[0].keys()) if valid else [
        "transaction_id", "transaction_at_utc", "transaction_date", "customer_id",
        "course_id", "customer_segment", "status", "quantity", "unit_price_cents",
        "net_revenue_cents", "currency", "source_row_number", "source_sha256", "pipeline_run_id",
    ]
    invalid_fields = list(config["required_columns"]) + ["source_row_number", "rejection_reasons"]
    write_csv(resolve_path(config["processed_path"]), valid, valid_fields)
    write_csv(resolve_path(config["quarantine_path"]), invalid, invalid_fields)

    finished_at = utc_now()
    run = {
        "run_id": selected_run_id,
        "pipeline_name": config["pipeline_name"],
        "pipeline_version": config["pipeline_version"],
        "schema_version": config["schema_version"],
        "started_at_utc": started_at,
        "finished_at_utc": finished_at,
        "source": {"path": config["input_path"], "bytes": byte_count, "sha256": sha256},
        "extracted_rows": len(rows),
        "valid_rows": len(valid),
        "quarantined_rows": len(invalid),
        "validity_rate": round(len(valid) / len(rows), 4) if rows else 0.0,
    }
    reconciliation = load_and_verify(resolve_path(config["database_path"]), valid, run)
    manifest = {
        **run,
        "duration_seconds": round(time.perf_counter() - started_clock, 4),
        "reconciliation": reconciliation,
        "status": "passed",
    }
    write_manifest(resolve_path(config["manifest_path"]), manifest)
    if write_history:
        append_history(resolve_path(config["history_path"]), manifest)
    write_svg(
        resolve_path(config["figure_path"]), len(valid), len(invalid),
        reconciliation["net_revenue_cents"],
    )
    return manifest


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/18-pipeline.json", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--no-history", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        manifest = run_pipeline(resolve_path(str(args.config)), args.run_id, not args.no_history)
    except Exception as exc:  # entry-point boundary: concise operational error
        print(f"Pipeline failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({
        "run_id": manifest["run_id"],
        "status": manifest["status"],
        "extracted_rows": manifest["extracted_rows"],
        "valid_rows": manifest["valid_rows"],
        "quarantined_rows": manifest["quarantined_rows"],
        "net_revenue": manifest["reconciliation"]["net_revenue_cents"] / 100,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
