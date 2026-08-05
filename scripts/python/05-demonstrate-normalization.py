"""Compare a wide order table with a constrained normalized SQLite schema."""

from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path

import matplotlib.pyplot as plt


CUSTOMERS = [
    (1, "Asha Mrema", "asha@example.org"),
    (2, "Baraka Juma", "baraka@example.org"),
    (3, "Neema Said", "neema@example.org"),
]

PRODUCTS = [
    (101, "Database Design", 42.0),
    (102, "SQL Field Guide", 28.0),
    (103, "Pipeline Notebook", 12.5),
]

ORDERS = [
    (1001, "2026-07-02", 1),
    (1002, "2026-07-03", 2),
    (1003, "2026-07-05", 1),
    (1004, "2026-07-06", 3),
]

ORDER_ITEMS = [
    (1001, 101, 1, 40.0),
    (1001, 103, 2, 12.5),
    (1002, 102, 1, 28.0),
    (1003, 101, 1, 42.0),
    (1003, 102, 2, 27.0),
    (1004, 103, 3, 12.5),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--figure", type=Path, required=True)
    return parser.parse_args()


def make_database(schema_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(schema_path.read_text(encoding="utf-8"))
    connection.executescript(
        """
        CREATE TABLE order_lines_wide (
            order_id INTEGER, order_date TEXT, customer_id INTEGER,
            customer_name TEXT, customer_email TEXT, product_id INTEGER,
            product_name TEXT, quantity INTEGER, unit_price NUMERIC
        );
        """
    )
    return connection


def load_data(connection: sqlite3.Connection) -> None:
    connection.executemany("INSERT INTO customers VALUES (?, ?, ?)", CUSTOMERS)
    connection.executemany("INSERT INTO products VALUES (?, ?, ?)", PRODUCTS)
    connection.executemany("INSERT INTO orders VALUES (?, ?, ?)", ORDERS)
    connection.executemany("INSERT INTO order_items VALUES (?, ?, ?, ?)", ORDER_ITEMS)

    wide_rows = connection.execute(
        """
        SELECT o.order_id, o.order_date, c.customer_id, c.customer_name, c.email,
               p.product_id, p.product_name, oi.quantity, oi.unit_price
        FROM orders o
        JOIN customers c ON c.customer_id = o.customer_id
        JOIN order_items oi ON oi.order_id = o.order_id
        JOIN products p ON p.product_id = oi.product_id
        """
    ).fetchall()
    connection.executemany(
        "INSERT INTO order_lines_wide VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", wide_rows
    )
    connection.commit()


def constraint_is_enforced(connection: sqlite3.Connection, sql: str) -> bool:
    try:
        connection.execute(sql)
    except sqlite3.IntegrityError:
        connection.rollback()
        return True
    connection.rollback()
    return False


def collect_metrics(connection: sqlite3.Connection) -> list[dict[str, object]]:
    wide_customer_values = connection.execute(
        "SELECT COUNT(customer_name) FROM order_lines_wide"
    ).fetchone()[0]
    normalized_customer_values = connection.execute(
        "SELECT COUNT(customer_name) FROM customers"
    ).fetchone()[0]
    wide_product_values = connection.execute(
        "SELECT COUNT(product_name) FROM order_lines_wide"
    ).fetchone()[0]
    normalized_product_values = connection.execute(
        "SELECT COUNT(product_name) FROM products"
    ).fetchone()[0]

    wide_total = connection.execute(
        "SELECT SUM(quantity * unit_price) FROM order_lines_wide"
    ).fetchone()[0]
    normalized_total = connection.execute(
        "SELECT SUM(quantity * unit_price) FROM order_items"
    ).fetchone()[0]

    orphan_rejected = constraint_is_enforced(
        connection,
        "INSERT INTO order_items VALUES (9999, 101, 1, 42.0)",
    )
    zero_quantity_rejected = constraint_is_enforced(
        connection,
        "INSERT INTO order_items VALUES (1002, 103, 0, 12.5)",
    )

    return [
        {"metric": "stored_customer_name_values", "wide": wide_customer_values,
         "normalized": normalized_customer_values, "status": "reduced"},
        {"metric": "stored_product_name_values", "wide": wide_product_values,
         "normalized": normalized_product_values, "status": "reduced"},
        {"metric": "order_value", "wide": f"{wide_total:.2f}",
         "normalized": f"{normalized_total:.2f}",
         "status": "match" if wide_total == normalized_total else "mismatch"},
        {"metric": "orphan_order_item_rejected", "wide": "not_enforced",
         "normalized": orphan_rejected, "status": "pass" if orphan_rejected else "fail"},
        {"metric": "zero_quantity_rejected", "wide": "not_enforced",
         "normalized": zero_quantity_rejected,
         "status": "pass" if zero_quantity_rejected else "fail"},
    ]


def write_summary(rows: list[dict[str, object]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=["metric", "wide", "normalized", "status"])
        writer.writeheader()
        writer.writerows(rows)


def plot_repetition(rows: list[dict[str, object]], output_path: Path) -> None:
    comparison = rows[:2]
    labels = ["Customer names", "Product names"]
    wide = [int(row["wide"]) for row in comparison]
    normalized = [int(row["normalized"]) for row in comparison]
    positions = range(len(labels))
    width = 0.34

    fig, ax = plt.subplots(figsize=(8, 4.8))
    ax.bar([x - width / 2 for x in positions], wide, width, label="Wide table", color="#d97706")
    ax.bar([x + width / 2 for x in positions], normalized, width,
           label="Normalized schema", color="#0369a1")
    ax.set_xticks(list(positions), labels)
    ax.set_ylabel("Stored descriptive values")
    ax.set_title("Normalization reduces repeated facts")
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.2)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    args = parse_args()
    connection = make_database(args.schema)
    try:
        load_data(connection)
        metrics = collect_metrics(connection)
        write_summary(metrics, args.summary)
        plot_repetition(metrics, args.figure)
    finally:
        connection.close()

    failures = [row for row in metrics if row["status"] in {"fail", "mismatch"}]
    for row in metrics:
        print(f"{row['metric']}: wide={row['wide']}, normalized={row['normalized']} [{row['status']}]")
    if failures:
        raise SystemExit("Normalization validation failed")
    print(f"Summary written to {args.summary}")
    print(f"Figure written to {args.figure}")


if __name__ == "__main__":
    main()
