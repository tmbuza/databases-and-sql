"""Minimal extract-transform-load workflow used by the scaffold."""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path


REQUIRED_FIELDS = {"record_id", "category", "amount"}


def extract_records(input_path: Path) -> list[dict[str, str]]:
    """Read source records without mutating the raw file."""
    with input_path.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        if not REQUIRED_FIELDS.issubset(reader.fieldnames or []):
            missing = sorted(REQUIRED_FIELDS - set(reader.fieldnames or []))
            raise ValueError(f"Missing required fields: {', '.join(missing)}")
        return list(reader)


def transform_records(records: list[dict[str, str]]) -> list[dict[str, object]]:
    """Validate and standardize source records."""
    transformed: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for row in records:
        record_id = row["record_id"].strip()
        if not record_id or record_id in seen_ids:
            raise ValueError(f"Invalid or duplicate record_id: {record_id!r}")
        amount = float(row["amount"])
        if amount < 0:
            raise ValueError(f"amount must be non-negative for {record_id}")
        seen_ids.add(record_id)
        transformed.append(
            {
                "record_id": record_id,
                "category": row["category"].strip().lower(),
                "amount": round(amount, 2),
            }
        )
    return transformed


def load_records(records: list[dict[str, object]], output_path: Path) -> None:
    """Publish records atomically to a JSON Lines file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8") as destination:
        for row in records:
            destination.write(json.dumps(row, sort_keys=True) + "\n")
    temporary_path.replace(output_path)


def run_pipeline(input_path: Path, output_path: Path, metadata_path: Path) -> dict[str, object]:
    """Run all stages and record auditable run metadata."""
    started_at = datetime.now(UTC)
    records = transform_records(extract_records(input_path))
    load_records(records, output_path)
    metadata = {
        "status": "success",
        "started_at": started_at.isoformat(),
        "completed_at": datetime.now(UTC).isoformat(),
        "input": str(input_path),
        "output": str(output_path),
        "record_count": len(records),
    }
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata
