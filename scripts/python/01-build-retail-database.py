#!/usr/bin/env python3
"""Build and validate the Chapter 01 SQLite demonstration database."""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

import matplotlib.pyplot as plt


REPO_ROOT = Path(__file__).resolve().parents[2]
CUSTOMERS_CSV = REPO_ROOT / "data/raw/01-customers.csv"
ORDERS_CSV = REPO_ROOT / "data/raw/01-orders.csv"
SCHEMA_SQL = REPO_ROOT / "scripts/sql/01-create-retail-schema.sql"
DATABASE_PATH = REPO_ROOT / "data/processed/01-retail-demo.sqlite"
SUMMARY_PATH = REPO_ROOT / "results/01-table-summary.csv"
FIGURE_PATH = REPO_ROOT / "results/figures/01-relational-table-profile.png"


def read_csv(path: Path) -> list[dict[str, str]]:
    """Read a UTF-8 CSV file into dictionaries."""
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def build_database() -> None:
    """Recreate the SQLite file and load the chapter source data."""
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATABASE_PATH.unlink(missing_ok=True)

    customers = read_csv(CUSTOMERS_CSV)
    orders = read_csv(ORDERS_CSV)

    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))

        connection.executemany(
            """
            INSERT INTO customers
                (customer_id, customer_name, region, signup_date)
            VALUES
                (:customer_id, :customer_name, :region, :signup_date)
            """,
            customers,
        )
        connection.executemany(
            """
            INSERT INTO orders
                (order_id, customer_id, order_date, amount, status)
            VALUES
                (:order_id, :customer_id, :order_date, :amount, :status)
            """,
            orders,
        )

        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"Foreign-key violations detected: {violations}")


def create_summary() -> list[tuple[int, str, int, float]]:
    """Query customer-level order counts and values, then write a CSV."""
    query = """
        SELECT
            c.customer_id,
            c.customer_name,
            COUNT(o.order_id) AS order_count,
            ROUND(COALESCE(SUM(o.amount), 0), 2) AS total_amount
        FROM customers AS c
        LEFT JOIN orders AS o
            ON c.customer_id = o.customer_id
        GROUP BY c.customer_id, c.customer_name
        ORDER BY c.customer_id
    """
    with sqlite3.connect(DATABASE_PATH) as connection:
        rows = connection.execute(query).fetchall()

    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SUMMARY_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["customer_id", "customer_name", "order_count", "total_amount"])
        writer.writerows(rows)
    return rows


def create_figure(rows: list[tuple[int, str, int, float]]) -> None:
    """Plot the relationship profile and total table row counts."""
    names = [row[1] for row in rows]
    order_counts = [row[2] for row in rows]
    customer_count = len(rows)
    total_orders = sum(order_counts)

    plt.style.use("seaborn-v0_8-whitegrid")
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.8))

    axes[0].barh(names, order_counts, color="#2A6F97")
    axes[0].invert_yaxis()
    axes[0].set_xlabel("Orders")
    axes[0].set_title("Orders per customer")
    axes[0].set_xticks(range(0, max(order_counts) + 1))

    axes[1].bar(
        ["customers", "orders"],
        [customer_count, total_orders],
        color=["#61A5C2", "#014F86"],
    )
    axes[1].set_ylabel("Rows")
    axes[1].set_title("Rows by table")
    axes[1].set_ylim(0, total_orders + 1)

    fig.suptitle("Chapter 01 relational database profile", fontweight="bold")
    fig.tight_layout()
    FIGURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURE_PATH, dpi=180, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    build_database()
    rows = create_summary()
    create_figure(rows)
    print(f"Database written to {DATABASE_PATH.relative_to(REPO_ROOT)}")
    print(f"Summary written to {SUMMARY_PATH.relative_to(REPO_ROOT)}")
    print(f"Figure written to {FIGURE_PATH.relative_to(REPO_ROOT)}")
    print(f"Validated {len(rows)} customers and {sum(row[2] for row in rows)} orders")


if __name__ == "__main__":
    main()
