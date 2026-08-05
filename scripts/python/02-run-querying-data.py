#!/usr/bin/env python3
"""Build the Chapter 02 SQLite database, export query results, and plot them."""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_FILE = ROOT / "scripts/sql/02-create-retail-database.sql"
QUERY_FILE = ROOT / "scripts/sql/02-querying-data.sql"
DATABASE = ROOT / "data/processed/02-retail.db"
RESULT_DIR = ROOT / "results/02-querying-data"
FIGURE = ROOT / "results/figures/02-order-value-by-segment.png"

QUERIES = {
    "01-customers": """
        SELECT customer_id, customer_name, segment, country
        FROM customers ORDER BY customer_id
    """,
    "02-distinct-segments-countries": """
        SELECT DISTINCT segment, country
        FROM customers ORDER BY segment, country
    """,
    "03-order-values": """
        SELECT order_id,
               ROUND(quantity * unit_price_at_order, 2) AS gross_value,
               ROUND(quantity * unit_price_at_order * discount_rate, 2) AS discount_value,
               ROUND(quantity * unit_price_at_order * (1 - discount_rate), 2) AS net_value
        FROM orders ORDER BY order_id
    """,
    "04-unshipped-orders": """
        SELECT order_id, status, shipped_date,
               COALESCE(shipped_date, 'not shipped') AS shipping_date
        FROM orders WHERE shipped_date IS NULL ORDER BY order_id
    """,
    "05-top-active-products": """
        SELECT product_id, product_name, unit_price
        FROM products WHERE is_active = 1
        ORDER BY unit_price DESC, product_id ASC LIMIT 3
    """,
    "06-priority-orders": """
        SELECT order_id, customer_id, product_id, order_date, status,
               ROUND(quantity * unit_price_at_order * (1 - discount_rate), 2) AS net_value
        FROM orders
        WHERE status IN ('completed', 'shipped')
          AND order_date BETWEEN '2026-01-01' AND '2026-02-15'
          AND quantity * unit_price_at_order * (1 - discount_rate) >= 100
        ORDER BY net_value DESC, order_id ASC
    """,
}


def export_query(connection: sqlite3.Connection, name: str, sql: str) -> list[sqlite3.Row]:
    cursor = connection.execute(sql)
    rows = cursor.fetchall()
    output = RESULT_DIR / f"{name}.csv"
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([column[0] for column in cursor.description])
        writer.writerows(rows)
    return rows


def create_figure(connection: sqlite3.Connection) -> None:
    rows = connection.execute(
        """
        SELECT c.segment,
               ROUND(o.quantity * o.unit_price_at_order * (1 - o.discount_rate), 2) AS net_value
        FROM orders AS o
        JOIN customers AS c ON c.customer_id = o.customer_id
        WHERE o.status = 'completed'
        ORDER BY c.segment, net_value
        """
    ).fetchall()
    segments = ["Consumer", "Business", "Enterprise"]
    values = [[row["net_value"] for row in rows if row["segment"] == segment] for segment in segments]

    plt.style.use("seaborn-v0_8-whitegrid")
    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    boxes = ax.boxplot(values, tick_labels=segments, patch_artist=True, widths=0.55)
    for box, color in zip(boxes["boxes"], ["#2A9D8F", "#E9C46A", "#E76F51"]):
        box.set_facecolor(color)
        box.set_alpha(0.82)
    for position, group in enumerate(values, start=1):
        offsets = [position + (index - (len(group) - 1) / 2) * 0.035 for index in range(len(group))]
        ax.scatter(offsets, group, color="#243447", s=28, zorder=3)
    ax.set_title("Completed order value by customer segment", loc="left", weight="bold")
    ax.set_xlabel("Customer segment")
    ax.set_ylabel("Net order value (USD)")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(FIGURE, dpi=180, bbox_inches="tight")
    plt.close(fig)


def validate(connection: sqlite3.Connection, exported: dict[str, list[sqlite3.Row]]) -> None:
    assert connection.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 8
    assert connection.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 7
    assert connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 18
    assert len(exported["05-top-active-products"]) == 3
    priority = exported["06-priority-orders"]
    assert len(priority) == 8
    assert priority[0]["order_id"] == 1006
    assert priority[0]["net_value"] == 2182.4
    assert all(priority[index]["net_value"] >= priority[index + 1]["net_value"] for index in range(len(priority) - 1))
    assert QUERY_FILE.exists(), "The executable teaching-query file is missing."


def main() -> None:
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    FIGURE.parent.mkdir(parents=True, exist_ok=True)
    if DATABASE.exists():
        DATABASE.unlink()

    with sqlite3.connect(DATABASE) as connection:
        connection.row_factory = sqlite3.Row
        connection.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))
        exported = {name: export_query(connection, name, sql) for name, sql in QUERIES.items()}
        create_figure(connection)
        validate(connection, exported)

    print(f"Database created: {DATABASE.relative_to(ROOT)}")
    print(f"Exported {len(QUERIES)} query result files: {RESULT_DIR.relative_to(ROOT)}")
    print(f"Figure created: {FIGURE.relative_to(ROOT)}")
    print("All validation checks passed.")


if __name__ == "__main__":
    main()

