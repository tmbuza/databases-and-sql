#!/usr/bin/env python3
"""Build and analyze the deterministic SQLite dataset for DBSQL Chapter 03."""

from __future__ import annotations

import csv
import os
import sqlite3
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/dsdp03-matplotlib")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


DATABASE_PATH = Path("data/processed/03-retail.db")
RESULTS_DIR = Path("results")
FIGURES_DIR = RESULTS_DIR / "figures"

ORDERS = [
    (1001, "2026-01-03", "East", "Electronics", "Online", "Completed", 2, 320.00, 0.10),
    (1002, "2026-01-05", "North", "Office", "Retail", "Completed", 5, 24.00, None),
    (1003, "2026-01-07", "West", "Furniture", "Partner", "Returned", 1, 480.00, 0.05),
    (1004, "2026-01-09", "South", "Electronics", "Online", "Completed", 3, 85.00, None),
    (1005, "2026-01-12", "East", "Office", "Retail", "Cancelled", 4, 18.50, 0.00),
    (1006, "2026-01-14", "North", "Furniture", "Online", "Completed", 1, 760.00, 0.15),
    (1007, "2026-01-18", "West", "Electronics", "Retail", "Completed", 2, 210.00, 0.05),
    (1008, "2026-01-20", "South", "Office", "Partner", "Returned", 6, 12.00, None),
    (1009, "2026-01-24", "East", "Furniture", "Online", "Completed", 2, 410.00, 0.10),
    (1010, "2026-01-28", "North", "Electronics", "Partner", "Cancelled", 1, 550.00, 0.20),
    (1011, "2026-02-02", "West", "Office", "Online", "Completed", 8, 15.00, None),
    (1012, "2026-02-04", "South", "Furniture", "Retail", "Completed", 1, 620.00, 0.05),
    (1013, "2026-02-08", "East", "Electronics", "Partner", "Returned", 1, 300.00, 0.10),
    (1014, "2026-02-11", "North", "Office", "Online", "Completed", 3, 42.00, 0.05),
    (1015, "2026-02-15", "West", "Furniture", "Retail", "Completed", 2, 350.00, None),
    (1016, "2026-02-18", "South", "Electronics", "Online", "Cancelled", 2, 145.00, 0.10),
    (1017, "2026-02-21", "East", "Office", "Partner", "Completed", 10, 9.50, 0.00),
    (1018, "2026-02-25", "North", "Furniture", "Retail", "Returned", 1, 890.00, 0.15),
    (1019, "2026-03-02", "West", "Electronics", "Online", "Completed", 4, 125.00, 0.10),
    (1020, "2026-03-05", "South", "Office", "Retail", "Completed", 7, 22.00, None),
    (1021, "2026-03-09", "East", "Furniture", "Partner", "Completed", 1, 540.00, 0.05),
    (1022, "2026-03-12", "North", "Electronics", "Online", "Completed", 2, 275.00, None),
    (1023, "2026-03-16", "West", "Office", "Partner", "Cancelled", 5, 17.00, 0.05),
    (1024, "2026-03-20", "South", "Furniture", "Online", "Completed", 2, 390.00, 0.10),
]

CATEGORY_QUERY = """
SELECT
    category,
    COUNT(*) AS completed_order_lines,
    SUM(quantity) AS units_sold,
    ROUND(AVG(unit_price), 2) AS average_unit_price,
    ROUND(SUM(quantity * unit_price * (1 - COALESCE(discount_rate, 0))), 2)
        AS net_revenue
FROM orders
WHERE status = 'Completed'
GROUP BY category
ORDER BY net_revenue DESC;
"""

REGION_STATUS_QUERY = """
SELECT
    region,
    COUNT(*) AS all_order_lines,
    SUM(CASE WHEN status = 'Completed' THEN 1 ELSE 0 END) AS completed_lines,
    SUM(CASE WHEN status = 'Returned' THEN 1 ELSE 0 END) AS returned_lines,
    SUM(CASE WHEN status = 'Cancelled' THEN 1 ELSE 0 END) AS cancelled_lines,
    ROUND(
        100.0 * SUM(CASE WHEN status = 'Returned' THEN 1 ELSE 0 END) / COUNT(*),
        1
    ) AS return_rate_percent
FROM orders
GROUP BY region
ORDER BY region;
"""


def build_database() -> sqlite3.Connection:
    """Create a fresh database and return its open connection."""
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATABASE_PATH.unlink(missing_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE orders (
            order_id INTEGER PRIMARY KEY,
            order_date TEXT NOT NULL,
            region TEXT NOT NULL,
            category TEXT NOT NULL,
            sales_channel TEXT NOT NULL,
            status TEXT NOT NULL,
            quantity INTEGER NOT NULL CHECK (quantity > 0),
            unit_price REAL NOT NULL CHECK (unit_price >= 0),
            discount_rate REAL CHECK (discount_rate BETWEEN 0 AND 1),
            CHECK (region IN ('East', 'North', 'South', 'West')),
            CHECK (category IN ('Electronics', 'Furniture', 'Office')),
            CHECK (sales_channel IN ('Online', 'Retail', 'Partner')),
            CHECK (status IN ('Completed', 'Returned', 'Cancelled'))
        );
        """
    )
    connection.executemany(
        """
        INSERT INTO orders (
            order_id, order_date, region, category, sales_channel, status,
            quantity, unit_price, discount_rate
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        ORDERS,
    )
    connection.commit()
    return connection


def query_rows(connection: sqlite3.Connection, query: str) -> list[sqlite3.Row]:
    """Execute a read-only query and return all rows."""
    return connection.execute(query).fetchall()


def write_csv(path: Path, rows: list[sqlite3.Row]) -> None:
    """Write SQLite rows to CSV with query column names as the header."""
    if not rows:
        raise ValueError(f"Query for {path} returned no rows.")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.writer(output_file)
        writer.writerow(rows[0].keys())
        writer.writerows(tuple(row) for row in rows)


def validate_results(
    connection: sqlite3.Connection,
    category_rows: list[sqlite3.Row],
    region_rows: list[sqlite3.Row],
) -> list[str]:
    """Reconcile grouped results with independent database totals."""
    completed_count, completed_revenue = connection.execute(
        """
        SELECT
            COUNT(*),
            SUM(quantity * unit_price * (1 - COALESCE(discount_rate, 0)))
        FROM orders
        WHERE status = 'Completed';
        """
    ).fetchone()
    total_rows = connection.execute("SELECT COUNT(*) FROM orders;").fetchone()[0]

    grouped_completed = sum(row["completed_order_lines"] for row in category_rows)
    grouped_revenue = sum(row["net_revenue"] for row in category_rows)
    regional_total = sum(row["all_order_lines"] for row in region_rows)

    if grouped_completed != completed_count:
        raise AssertionError("Category counts do not reconcile to completed rows.")
    if abs(grouped_revenue - completed_revenue) > 0.02:
        raise AssertionError("Category revenue does not reconcile to the total.")
    if regional_total != total_rows:
        raise AssertionError("Regional counts do not reconcile to all rows.")
    for row in region_rows:
        partitioned = (
            row["completed_lines"] + row["returned_lines"] + row["cancelled_lines"]
        )
        if partitioned != row["all_order_lines"]:
            raise AssertionError(f"Status counts do not reconcile for {row['region']}.")

    return [
        f"source_order_lines={total_rows}",
        f"completed_order_lines={completed_count}",
        f"completed_net_revenue={completed_revenue:.2f}",
        "category_count_reconciliation=PASS",
        "category_revenue_reconciliation=PASS",
        "regional_status_partition=PASS",
    ]


def create_plot(category_rows: list[sqlite3.Row]) -> None:
    """Plot completed net revenue by category."""
    ordered = sorted(category_rows, key=lambda row: row["net_revenue"])
    categories = [row["category"] for row in ordered]
    revenue = [row["net_revenue"] for row in ordered]

    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    plt.style.use("seaborn-v0_8-whitegrid")
    fig, ax = plt.subplots(figsize=(8, 4.8))
    bars = ax.barh(categories, revenue, color=["#376795", "#4C9F70", "#E07A5F"])
    ax.set_title("Completed net revenue by category")
    ax.set_xlabel("Net revenue")
    ax.set_ylabel("")
    ax.bar_label(bars, labels=[f"{value:,.0f}" for value in revenue], padding=4)
    ax.spines[["top", "right", "left"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "03-net-revenue-by-category.png", dpi=160)
    plt.close(fig)


def main() -> None:
    """Create the dataset, execute summaries, validate, and save artifacts."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    connection = build_database()
    try:
        category_rows = query_rows(connection, CATEGORY_QUERY)
        region_rows = query_rows(connection, REGION_STATUS_QUERY)
        validation_lines = validate_results(connection, category_rows, region_rows)
    finally:
        connection.close()

    write_csv(RESULTS_DIR / "03-category-summary.csv", category_rows)
    write_csv(RESULTS_DIR / "03-region-status-summary.csv", region_rows)
    (RESULTS_DIR / "03-validation-summary.txt").write_text(
        "\n".join(validation_lines) + "\n", encoding="utf-8"
    )
    create_plot(category_rows)

    print(f"Database: {DATABASE_PATH}")
    print(f"Category summary: {RESULTS_DIR / '03-category-summary.csv'}")
    print(f"Region summary: {RESULTS_DIR / '03-region-status-summary.csv'}")
    print(f"Validation: {RESULTS_DIR / '03-validation-summary.txt'}")
    print(f"Figure: {FIGURES_DIR / '03-net-revenue-by-category.png'}")


if __name__ == "__main__":
    main()
