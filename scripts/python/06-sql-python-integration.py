"""Build and query a small SQLite database for DSDP Chapter 06."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
DATABASE_PATH = REPO_ROOT / "data" / "processed" / "06-retail.db"
CUSTOMERS_PATH = REPO_ROOT / "data" / "raw" / "06-customers.csv"
ORDERS_PATH = REPO_ROOT / "data" / "raw" / "06-orders.csv"
SCHEMA_PATH = REPO_ROOT / "queries" / "06-create-retail-schema.sql"
QUERY_PATH = REPO_ROOT / "queries" / "06-segment-revenue.sql"
RESULT_PATH = REPO_ROOT / "results" / "06-segment-revenue.csv"
SUMMARY_PATH = REPO_ROOT / "results" / "06-sql-python-summary.json"
FIGURE_PATH = REPO_ROOT / "results" / "figures" / "06-segment-revenue.png"

START_DATE = "2026-01-01"
END_DATE = "2026-04-01"

def prepare_directories() -> None:
    """Create output directories used by this chapter."""
    for path in (DATABASE_PATH.parent, RESULT_PATH.parent, FIGURE_PATH.parent):
        path.mkdir(parents=True, exist_ok=True)


def rebuild_database() -> sqlite3.Connection:
    """Create a clean chapter database and return an open connection."""
    DATABASE_PATH.unlink(missing_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.execute("PRAGMA foreign_keys = ON")

    with connection:
        connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        customers = pd.read_csv(CUSTOMERS_PATH).itertuples(index=False, name=None)
        orders = pd.read_csv(ORDERS_PATH).itertuples(index=False, name=None)
        connection.executemany(
            """
            INSERT INTO customers (customer_id, customer_name, segment)
            VALUES (?, ?, ?)
            """,
            customers,
        )
        connection.executemany(
            """
            INSERT INTO orders
                (order_id, customer_id, order_date, status, order_total)
            VALUES (?, ?, ?, ?, ?)
            """,
            orders,
        )
    return connection


def load_segment_revenue(
    connection: sqlite3.Connection, start_date: str, end_date: str
) -> pd.DataFrame:
    """Return completed-order revenue grouped by customer segment."""
    return pd.read_sql_query(
        QUERY_PATH.read_text(encoding="utf-8"),
        connection,
        params={"start_date": start_date, "end_date": end_date},
    )


def validate_result(
    connection: sqlite3.Connection,
    result: pd.DataFrame,
    start_date: str,
    end_date: str,
) -> dict[str, object]:
    """Validate the reporting contract and return reconciliation metadata."""
    required_columns = {
        "segment",
        "completed_orders",
        "revenue",
        "average_order_value",
    }
    missing = required_columns.difference(result.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    if result.empty:
        raise ValueError("Reporting query returned no rows")
    if result["segment"].duplicated().any():
        raise ValueError("Each segment must occur once")
    if result["revenue"].lt(0).any():
        raise ValueError("Revenue cannot be negative")

    control_total = connection.execute(
        """
        SELECT ROUND(SUM(order_total), 2)
        FROM orders
        WHERE status = 'completed'
          AND order_date >= ?
          AND order_date < ?
        """,
        (start_date, end_date),
    ).fetchone()[0]
    reported_total = round(float(result["revenue"].sum()), 2)
    reconciled = reported_total == float(control_total)
    if not reconciled:
        raise ValueError(
            f"Revenue mismatch: report={reported_total}, control={control_total}"
        )

    return {
        "reported_revenue": reported_total,
        "control_revenue": float(control_total),
        "reconciled": reconciled,
    }


def save_plot(result: pd.DataFrame) -> None:
    """Save a horizontal bar chart of revenue by customer segment."""
    plot_data = result.sort_values("revenue", ascending=True)
    colors = ["#3f7cac", "#5aa9a6", "#f2b134"]

    fig, ax = plt.subplots(figsize=(9, 5.5))
    bars = ax.barh(plot_data["segment"], plot_data["revenue"], color=colors)
    ax.set_title("Completed-order revenue by customer segment", loc="left")
    ax.set_xlabel("Revenue (sample currency units)")
    ax.set_ylabel("")
    ax.grid(axis="x", alpha=0.25)
    ax.set_axisbelow(True)

    for bar, revenue, orders in zip(
        bars,
        plot_data["revenue"],
        plot_data["completed_orders"],
        strict=True,
    ):
        ax.text(
            bar.get_width() + 65,
            bar.get_y() + bar.get_height() / 2,
            f"{revenue:,.2f}  ({orders} orders)",
            va="center",
            fontsize=9,
        )

    ax.set_xlim(0, float(plot_data["revenue"].max()) * 1.32)
    fig.text(
        0.01,
        0.01,
        f"Completed orders from {START_DATE} (inclusive) to {END_DATE} (exclusive)",
        fontsize=8,
        color="#555555",
    )
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(FIGURE_PATH, dpi=180, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    """Run the reproducible SQL–Python integration workflow."""
    prepare_directories()
    connection = rebuild_database()
    try:
        result = load_segment_revenue(connection, START_DATE, END_DATE)
        reconciliation = validate_result(
            connection, result, START_DATE, END_DATE
        )
        customer_count = connection.execute(
            "SELECT COUNT(*) FROM customers"
        ).fetchone()[0]
        order_count = connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    finally:
        connection.close()

    result.to_csv(RESULT_PATH, index=False)
    save_plot(result)

    summary = {
        "chapter_id": "DSDP-006",
        "database": str(DATABASE_PATH.relative_to(REPO_ROOT)),
        "reporting_window": {
            "start_inclusive": START_DATE,
            "end_exclusive": END_DATE,
        },
        "source_rows": {
            "customers": customer_count,
            "orders": order_count,
        },
        "result_rows": len(result),
        **reconciliation,
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print(result.to_string(index=False))
    print(f"\nCSV: {RESULT_PATH.relative_to(REPO_ROOT)}")
    print(f"Summary: {SUMMARY_PATH.relative_to(REPO_ROOT)}")
    print(f"Figure: {FIGURE_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
