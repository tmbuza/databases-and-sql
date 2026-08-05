#!/usr/bin/env python3
"""Create and validate the DSDP Chapter 04 relational join examples."""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import matplotlib.pyplot as plt


DATABASE_PATH = Path("data/processed/04-joins-demo.sqlite")
TABLE_DIR = Path("results/tables")
FIGURE_DIR = Path("results/figures")


def build_database(connection: sqlite3.Connection) -> None:
    """Create deterministic example tables with known edge cases."""
    connection.executescript(
        """
        PRAGMA foreign_keys = OFF;
        DROP TABLE IF EXISTS order_items;
        DROP TABLE IF EXISTS products;
        DROP TABLE IF EXISTS orders;
        DROP TABLE IF EXISTS customers;

        CREATE TABLE customers (
            customer_id INTEGER PRIMARY KEY,
            customer_name TEXT NOT NULL,
            region TEXT NOT NULL
        );

        CREATE TABLE orders (
            order_id INTEGER PRIMARY KEY,
            customer_id INTEGER,
            order_date TEXT NOT NULL,
            status TEXT NOT NULL
        );

        CREATE TABLE products (
            product_id INTEGER PRIMARY KEY,
            product_name TEXT NOT NULL,
            category TEXT NOT NULL
        );

        CREATE TABLE order_items (
            order_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL CHECK (quantity > 0),
            unit_price REAL NOT NULL CHECK (unit_price >= 0),
            PRIMARY KEY (order_id, product_id)
        );
        """
    )
    connection.executemany(
        "INSERT INTO customers VALUES (?, ?, ?)",
        [
            (1, "Amina", "East"),
            (2, "Baraka", "North"),
            (3, "Chausiku", "East"),
            (4, "Daudi", "South"),
            (5, "Ester", "West"),
        ],
    )
    connection.executemany(
        "INSERT INTO orders VALUES (?, ?, ?, ?)",
        [
            (101, 1, "2026-07-01", "completed"),
            (102, 1, "2026-07-08", "completed"),
            (103, 2, "2026-07-09", "cancelled"),
            (104, 3, "2026-07-11", "completed"),
            (105, 3, "2026-07-14", "completed"),
            (106, 4, "2026-07-18", "completed"),
            (107, 999, "2026-07-20", "completed"),
        ],
    )
    connection.executemany(
        "INSERT INTO products VALUES (?, ?, ?)",
        [
            (201, "Notebook", "Stationery"),
            (202, "Pen set", "Stationery"),
            (203, "USB drive", "Electronics"),
            (204, "Desk lamp", "Office"),
        ],
    )
    connection.executemany(
        "INSERT INTO order_items VALUES (?, ?, ?, ?)",
        [
            (101, 201, 2, 4.50),
            (101, 202, 1, 6.00),
            (102, 203, 2, 15.00),
            (103, 204, 1, 25.00),
            (104, 201, 3, 4.50),
            (104, 203, 1, 15.00),
            (105, 202, 2, 6.00),
            (106, 204, 2, 25.00),
            (107, 201, 1, 4.50),
        ],
    )
    connection.commit()


def scalar(connection: sqlite3.Connection, query: str) -> int:
    """Return a single integer query result."""
    return int(connection.execute(query).fetchone()[0])


def write_query_csv(
    connection: sqlite3.Connection, query: str, destination: Path
) -> None:
    """Execute a query and save its header and rows as CSV."""
    cursor = connection.execute(query)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([column[0] for column in cursor.description])
        writer.writerows(cursor.fetchall())


def collect_diagnostics(connection: sqlite3.Connection) -> dict[str, int]:
    """Measure join inputs, outputs, nulls, and unmatched records."""
    diagnostics = {
        "customers": scalar(connection, "SELECT COUNT(*) FROM customers"),
        "orders": scalar(connection, "SELECT COUNT(*) FROM orders"),
        "inner_join_rows": scalar(
            connection,
            """SELECT COUNT(*) FROM customers AS c
               JOIN orders AS o ON c.customer_id = o.customer_id""",
        ),
        "left_join_rows": scalar(
            connection,
            """SELECT COUNT(*) FROM customers AS c
               LEFT JOIN orders AS o ON c.customer_id = o.customer_id""",
        ),
        "orphan_orders": scalar(
            connection,
            """SELECT COUNT(*) FROM orders AS o
               WHERE NOT EXISTS (
                   SELECT 1 FROM customers AS c
                   WHERE c.customer_id = o.customer_id
               )""",
        ),
        "customers_without_orders": scalar(
            connection,
            """SELECT COUNT(*) FROM customers AS c
               WHERE NOT EXISTS (
                   SELECT 1 FROM orders AS o
                   WHERE o.customer_id = c.customer_id
               )""",
        ),
        "null_order_customer_keys": scalar(
            connection, "SELECT COUNT(*) FROM orders WHERE customer_id IS NULL"
        ),
    }
    assert diagnostics["customers"] == 5
    assert diagnostics["orders"] == 7
    assert diagnostics["inner_join_rows"] == 6
    assert diagnostics["left_join_rows"] == 7
    assert diagnostics["orphan_orders"] == 1
    assert diagnostics["customers_without_orders"] == 1
    return diagnostics


def validate_revenue(connection: sqlite3.Connection) -> None:
    """Confirm that a unique product lookup does not change line revenue."""
    before = connection.execute(
        "SELECT SUM(quantity * unit_price) FROM order_items"
    ).fetchone()[0]
    after = connection.execute(
        """SELECT SUM(oi.quantity * oi.unit_price)
           FROM order_items AS oi
           JOIN products AS p ON oi.product_id = p.product_id"""
    ).fetchone()[0]
    if abs(before - after) > 1e-9:
        raise RuntimeError("Revenue changed across the many-to-one product join.")


def plot_diagnostics(diagnostics: dict[str, int]) -> None:
    """Save a compact plot comparing input and join row counts."""
    labels = ["Customers", "Orders", "Inner join", "Left join"]
    values = [
        diagnostics["customers"],
        diagnostics["orders"],
        diagnostics["inner_join_rows"],
        diagnostics["left_join_rows"],
    ]
    colors = ["#264653", "#2A9D8F", "#E9C46A", "#E76F51"]
    figure, axis = plt.subplots(figsize=(9, 5.2))
    bars = axis.bar(labels, values, color=colors, width=0.68)
    axis.bar_label(bars, padding=4, fontsize=11, fontweight="bold")
    axis.set_ylabel("Rows")
    axis.set_title("Join counts reflect preservation and matching rules")
    axis.set_ylim(0, max(values) + 2.2)
    axis.spines[["top", "right"]].set_visible(False)
    axis.grid(axis="y", alpha=0.22)
    note = (
        f"Unmatched: {diagnostics['orphan_orders']} orphan order; "
        f"{diagnostics['customers_without_orders']} customer without orders"
    )
    figure.text(0.5, 0.015, note, ha="center", fontsize=10, color="#444444")
    figure.tight_layout(rect=(0, 0.05, 1, 1))
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    figure.savefig(
        FIGURE_DIR / "04-join-cardinality-diagnostics.png",
        dpi=300,
        bbox_inches="tight",
    )
    plt.close(figure)


def main() -> None:
    """Build data, execute analyses, validate joins, and save outputs."""
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DATABASE_PATH) as connection:
        build_database(connection)
        diagnostics = collect_diagnostics(connection)
        validate_revenue(connection)
        write_query_csv(
            connection,
            """
            WITH order_totals AS (
                SELECT o.order_id, o.customer_id,
                       SUM(oi.quantity * oi.unit_price) AS order_revenue
                FROM orders AS o
                JOIN order_items AS oi ON o.order_id = oi.order_id
                WHERE o.status = 'completed'
                GROUP BY o.order_id, o.customer_id
            )
            SELECT c.customer_id, c.customer_name, c.region,
                   COUNT(ot.order_id) AS completed_orders,
                   ROUND(COALESCE(SUM(ot.order_revenue), 0), 2) AS revenue
            FROM customers AS c
            LEFT JOIN order_totals AS ot ON c.customer_id = ot.customer_id
            GROUP BY c.customer_id, c.customer_name, c.region
            ORDER BY revenue DESC, c.customer_id
            """,
            TABLE_DIR / "04-customer-revenue-summary.csv",
        )
        write_query_csv(
            connection,
            """
            SELECT o.order_id, o.customer_id, o.order_date, o.status
            FROM orders AS o
            WHERE NOT EXISTS (
                SELECT 1 FROM customers AS c
                WHERE c.customer_id = o.customer_id
            )
            ORDER BY o.order_id
            """,
            TABLE_DIR / "04-unmatched-orders.csv",
        )

    (TABLE_DIR / "04-join-diagnostics.json").write_text(
        json.dumps(diagnostics, indent=2) + "\n", encoding="utf-8"
    )
    plot_diagnostics(diagnostics)
    print(json.dumps(diagnostics, indent=2))
    print(f"Database: {DATABASE_PATH}")
    print(f"Tables: {TABLE_DIR}")
    print(f"Figure: {FIGURE_DIR / '04-join-cardinality-diagnostics.png'}")


if __name__ == "__main__":
    main()
