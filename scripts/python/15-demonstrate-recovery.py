#!/usr/bin/env python3
"""Demonstrate duplicate-prone retries, idempotent writes, and checkpoint recovery."""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from pathlib import Path

import matplotlib.pyplot as plt


BASE_ORDERS = [
    (f"ORD-{i:03d}", f"2026-08-{i:02d}", f"CUST-{(i % 4) + 1:02d}", 25.0 + 7.5 * i, "2026-08-06T00:00:00Z")
    for i in range(1, 11)
]


def connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        DROP TABLE IF EXISTS naive_orders;
        DROP TABLE IF EXISTS curated_orders;
        DROP TABLE IF EXISTS recovery_checkpoint;

        CREATE TABLE naive_orders (
            load_id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT NOT NULL,
            order_date TEXT NOT NULL,
            customer_id TEXT NOT NULL,
            amount REAL NOT NULL,
            source_updated_at TEXT NOT NULL
        );

        CREATE TABLE curated_orders (
            order_id TEXT PRIMARY KEY,
            order_date TEXT NOT NULL,
            customer_id TEXT NOT NULL,
            amount REAL NOT NULL CHECK (amount >= 0),
            source_updated_at TEXT NOT NULL
        );

        CREATE TABLE recovery_checkpoint (
            pipeline_name TEXT PRIMARY KEY,
            last_committed_position INTEGER NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('running', 'failed', 'succeeded'))
        );
        """
    )


def naive_insert(connection: sqlite3.Connection, rows: list[tuple]) -> None:
    connection.executemany(
        "INSERT INTO naive_orders (order_id, order_date, customer_id, amount, source_updated_at) VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    connection.commit()


def upsert(connection: sqlite3.Connection, rows: list[tuple]) -> None:
    connection.executemany(
        """
        INSERT INTO curated_orders (order_id, order_date, customer_id, amount, source_updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(order_id) DO UPDATE SET
            order_date = excluded.order_date,
            customer_id = excluded.customer_id,
            amount = excluded.amount,
            source_updated_at = excluded.source_updated_at
        WHERE excluded.source_updated_at >= curated_orders.source_updated_at
        """,
        rows,
    )


def update_checkpoint(connection: sqlite3.Connection, position: int, status: str) -> None:
    connection.execute(
        """
        INSERT INTO recovery_checkpoint (pipeline_name, last_committed_position, status)
        VALUES ('daily_orders', ?, ?)
        ON CONFLICT(pipeline_name) DO UPDATE SET
            last_committed_position = excluded.last_committed_position,
            status = excluded.status
        """,
        (position, status),
    )


def checkpoint(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        "SELECT last_committed_position FROM recovery_checkpoint WHERE pipeline_name = 'daily_orders'"
    ).fetchone()
    return int(row[0]) if row else 0


def recover_in_chunks(connection: sqlite3.Connection, rows: list[tuple], chunk_size: int, fail_after: int | None) -> None:
    start = checkpoint(connection)
    committed_chunks = 0
    for offset in range(start, len(rows), chunk_size):
        chunk = rows[offset : offset + chunk_size]
        new_position = offset + len(chunk)
        with connection:
            upsert(connection, chunk)
            update_checkpoint(connection, new_position, "running")
        committed_chunks += 1
        if fail_after is not None and committed_chunks == fail_after:
            with connection:
                update_checkpoint(connection, new_position, "failed")
            raise RuntimeError("simulated worker failure after a durable chunk")
    with connection:
        update_checkpoint(connection, len(rows), "succeeded")


def scalar(connection: sqlite3.Connection, query: str) -> int:
    return int(connection.execute(query).fetchone()[0])


def write_verification(path: Path, checks: list[tuple[str, int, int]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["check", "expected", "observed", "passed"])
        for name, expected, observed in checks:
            writer.writerow([name, expected, observed, str(expected == observed).lower()])


def plot_comparison(path: Path, values: dict[str, int]) -> None:
    labels = ["Naive retry", "Idempotent retry", "Recovered batch"]
    row_counts = [values["naive_rows_after_retry"], values["idempotent_rows_after_retry"], values["recovered_rows"]]
    expected = [6, 6, values["expected_recovered_rows"]]
    colors = ["#C94C4C", "#287D8E", "#3A7D44"]

    fig, ax = plt.subplots(figsize=(9, 5.2))
    bars = ax.bar(labels, row_counts, color=colors, width=0.62)
    ax.scatter(labels, expected, marker="_", s=900, linewidths=3, color="#202124", label="Expected rows")
    ax.bar_label(bars, padding=4, fontsize=11)
    ax.set_ylabel("Rows in target")
    ax.set_title("Retry and recovery outcomes")
    ax.set_ylim(0, max(row_counts) + 3)
    ax.grid(axis="y", alpha=0.2)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=Path("results/15-recovery-demo.sqlite"))
    parser.add_argument("--summary", type=Path, default=Path("results/15-recovery-summary.json"))
    parser.add_argument("--verification", type=Path, default=Path("results/15-recovery-verification.csv"))
    parser.add_argument("--figure", type=Path, default=Path("results/figures/15-recovery-comparison.png"))
    args = parser.parse_args()
    for path in (args.database, args.summary, args.verification, args.figure):
        path.parent.mkdir(parents=True, exist_ok=True)
    if args.database.exists():
        args.database.unlink()

    connection = connect(args.database)
    create_schema(connection)

    retry_batch = BASE_ORDERS[:6]
    naive_insert(connection, retry_batch)
    naive_insert(connection, retry_batch)
    naive_count = scalar(connection, "SELECT COUNT(*) FROM naive_orders")

    with connection:
        upsert(connection, retry_batch)
    with connection:
        upsert(connection, retry_batch)
    idempotent_count = scalar(connection, "SELECT COUNT(*) FROM curated_orders")

    connection.execute("DELETE FROM curated_orders")
    connection.commit()
    failure_observed = False
    try:
        recover_in_chunks(connection, BASE_ORDERS, chunk_size=3, fail_after=1)
    except RuntimeError:
        failure_observed = True
    checkpoint_after_failure = checkpoint(connection)
    recover_in_chunks(connection, BASE_ORDERS, chunk_size=3, fail_after=None)
    recovered_count = scalar(connection, "SELECT COUNT(*) FROM curated_orders")
    duplicate_keys = scalar(
        connection,
        "SELECT COUNT(*) FROM (SELECT order_id FROM curated_orders GROUP BY order_id HAVING COUNT(*) > 1)",
    )
    final_checkpoint = checkpoint(connection)
    connection.close()

    summary = {
        "naive_rows_after_retry": naive_count,
        "idempotent_rows_after_retry": idempotent_count,
        "failure_observed": failure_observed,
        "checkpoint_after_failure": checkpoint_after_failure,
        "recovered_rows": recovered_count,
        "expected_recovered_rows": len(BASE_ORDERS),
        "duplicate_business_keys_after_recovery": duplicate_keys,
        "checkpoint_after_recovery": final_checkpoint,
    }
    args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    checks = [
        ("naive_retry_exposes_duplicates", 12, naive_count),
        ("idempotent_retry_preserves_cardinality", 6, idempotent_count),
        ("first_chunk_was_checkpointed", 3, checkpoint_after_failure),
        ("recovery_is_complete", len(BASE_ORDERS), recovered_count),
        ("recovery_has_no_duplicate_business_keys", 0, duplicate_keys),
        ("checkpoint_reaches_source_end", len(BASE_ORDERS), final_checkpoint),
    ]
    write_verification(args.verification, checks)
    plot_comparison(args.figure, summary)

    if not failure_observed or not all(expected == observed for _, expected, observed in checks):
        raise SystemExit("recovery verification failed")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

