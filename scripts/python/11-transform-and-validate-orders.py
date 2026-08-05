#!/usr/bin/env python3
"""Transform imperfect order records and enforce data-quality gates."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = ROOT / "data" / "processed"
RESULTS_DIR = ROOT / "results"
FIGURES_DIR = RESULTS_DIR / "figures"

REQUIRED_COLUMNS = {
    "order_id",
    "customer_id",
    "product_id",
    "order_timestamp",
    "quantity",
    "unit_price",
    "status",
    "reported_total",
}
ALLOWED_STATUSES = {"pending", "paid", "shipped", "cancelled"}
THRESHOLDS = {
    "completeness": 0.95,
    "validity": 0.70,
    "uniqueness": 0.90,
    "consistency": 0.95,
    "acceptance_rate": 0.70,
    "published_completeness": 1.00,
    "published_uniqueness": 1.00,
}


def example_orders() -> pd.DataFrame:
    """Return deterministic input containing representative quality defects."""
    rows = [
        ("O-1001", " C-01 ", "P-10", "2026-07-01T08:15:00Z", 2, 15.00, "PAID", 30.00),
        ("O-1002", "C-02", "P-11", "2026-07-01T09:02:00Z", 1, 42.50, "shipped", 42.50),
        ("O-1003", "C-03", "P-10", "2026-07-01T10:10:00Z", 3, 15.00, "Paid ", 45.00),
        ("O-1004", "C-04", "P-12", "2026-07-01T11:45:00Z", 4, 8.25, "pending", 33.00),
        ("O-1005", "C-05", "P-13", "2026-07-02T07:30:00Z", 1, 120.00, "cancelled", 120.00),
        ("O-1006", "C-06", "P-14", "2026-07-02T08:20:00Z", 5, 5.50, "shipped", 27.50),
        ("O-1007", "C-07", "P-15", "2026-07-02T09:40:00Z", 2, 17.75, "paid", 35.50),
        ("O-1008", "C-08", "P-16", "2026-07-02T10:05:00Z", 1, 9.99, "pending", 9.99),
        ("O-1009", "C-09", "P-17", "2026-07-02T10:15:00Z", 2, 12.00, "returned", 24.00),
        ("O-1010", "", "P-18", "2026-07-02T10:20:00Z", 1, 7.00, "paid", 7.00),
        ("O-1011", "C-11", "P-19", "not-a-date", 1, 18.00, "paid", 18.00),
        ("O-1012", "C-12", "P-20", "2026-07-02T12:00:00Z", 0, 11.00, "paid", 0.00),
        ("O-1013", "C-13", None, "2026-07-02T12:20:00Z", 1, 14.00, "shipped", 14.00),
        ("O-1014", "C-14", "P-22", "2026-07-02T13:00:00Z", 2, -3.00, "paid", -6.00),
        ("O-1015", "C-15", "P-23", "2026-07-02T13:30:00Z", 2, 20.00, "paid", 39.00),
        ("O-1016", "C-16", "P-24", "2026-07-02T14:00:00Z", 1, 6.50, "pending", 6.50),
        ("O-1017", "C-17", "P-25", "2026-07-02T14:10:00Z", 3, 3.00, "paid", 9.00),
        ("O-1017", "C-18", "P-26", "2026-07-02T14:20:00Z", 1, 4.00, "paid", 4.00),
        ("O-1019", "C-19", "P-27", "2026-07-02T15:00:00Z", 2, 10.00, "shipped", 20.00),
        ("O-1020", "C-20", "P-28", "2026-07-02T15:30:00Z", 1, 25.00, "paid", 25.00),
        ("O-1021", "C-21", "P-29", "2026-07-03T08:00:00Z", 2, 6.00, "paid", 12.00),
        ("O-1022", "C-22", "P-30", "2026-07-03T08:15:00Z", 1, 31.00, "shipped", 31.00),
        ("O-1023", "C-23", "P-31", "2026-07-03T08:30:00Z", 4, 2.50, "pending", 10.00),
        ("O-1024", "C-24", "P-32", "2026-07-03T09:00:00Z", 2, 19.50, "paid", 39.00),
        ("O-1025", "C-25", "P-33", "2026-07-03T09:20:00Z", 1, 55.00, "shipped", 55.00),
        ("O-1026", "C-26", "P-34", "2026-07-03T09:45:00Z", 3, 7.25, "paid", 21.75),
        ("O-1027", "C-27", "P-35", "2026-07-03T10:00:00Z", 2, 13.00, "pending", 26.00),
        ("O-1028", "C-28", "P-36", "2026-07-03T10:30:00Z", 1, 16.00, "paid", 16.00),
        ("O-1029", "C-29", "P-37", "2026-07-03T11:00:00Z", 5, 4.00, "shipped", 20.00),
        ("O-1030", "C-30", "P-38", "2026-07-03T11:15:00Z", 2, 22.00, "paid", 44.00),
    ]
    columns = [
        "order_id", "customer_id", "product_id", "order_timestamp",
        "quantity", "unit_price", "status", "reported_total",
    ]
    return pd.DataFrame(rows, columns=columns)


def stage_orders(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalize representations without inventing corrections."""
    missing = REQUIRED_COLUMNS.difference(raw.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    staged = raw.copy()
    for column in ["order_id", "customer_id", "product_id", "status"]:
        staged[column] = staged[column].astype("string").str.strip()
        staged[column] = staged[column].mask(staged[column].eq(""), pd.NA)
    staged["status"] = staged["status"].str.lower()
    staged["order_timestamp"] = pd.to_datetime(staged["order_timestamp"], errors="coerce", utc=True)
    for column in ["quantity", "unit_price", "reported_total"]:
        staged[column] = pd.to_numeric(staged[column], errors="coerce")
    staged["expected_total"] = (staged["quantity"] * staged["unit_price"]).round(2)
    return staged


def evaluate_rules(staged: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, pd.Series]]:
    """Evaluate row rules and attach issue labels."""
    rules = {
        "missing_order_id": staged["order_id"].isna(),
        "duplicate_order_id": staged["order_id"].duplicated(keep=False),
        "missing_customer_id": staged["customer_id"].isna(),
        "missing_product_id": staged["product_id"].isna(),
        "invalid_timestamp": staged["order_timestamp"].isna(),
        "nonpositive_quantity": staged["quantity"].isna() | (staged["quantity"] <= 0),
        "negative_unit_price": staged["unit_price"].isna() | (staged["unit_price"] < 0),
        "invalid_status": ~staged["status"].isin(ALLOWED_STATUSES),
        "inconsistent_total": staged["reported_total"].isna()
        | ~np.isclose(staged["reported_total"], staged["expected_total"], atol=0.01),
    }
    evaluated = staged.copy()
    evaluated["quality_issues"] = [
        "|".join(name for name, failed in rules.items() if bool(failed.iloc[index]))
        for index in range(len(evaluated))
    ]
    evaluated["is_valid"] = evaluated["quality_issues"].eq("")
    return evaluated, rules


def calculate_metrics(evaluated: pd.DataFrame, rules: dict[str, pd.Series]) -> dict[str, float]:
    """Calculate stable, documented data-quality metrics."""
    required = ["order_id", "customer_id", "product_id", "order_timestamp", "quantity", "unit_price", "status", "reported_total"]
    completeness = 1.0 - evaluated[required].isna().to_numpy().mean()
    duplicate_rows = rules["duplicate_order_id"].sum()
    consistent_rows = (~rules["inconsistent_total"]).sum()
    valid_rows = evaluated["is_valid"].sum()
    total = len(evaluated)
    return {
        "completeness": float(completeness),
        "validity": float(valid_rows / total),
        "uniqueness": float(1 - duplicate_rows / total),
        "consistency": float(consistent_rows / total),
        "acceptance_rate": float(valid_rows / total),
    }


def save_dashboard(metrics: dict[str, float]) -> None:
    """Plot quality metrics and the thresholds used for release."""
    names = list(metrics)
    values = [metrics[name] for name in names]
    thresholds = [THRESHOLDS[name] for name in names]
    labels = [name.replace("_", " ").title() for name in names]

    fig, ax = plt.subplots(figsize=(10, 5.8))
    x = np.arange(len(names))
    colors = ["#167D8D" if value >= threshold else "#D95F59" for value, threshold in zip(values, thresholds)]
    bars = ax.bar(x, values, color=colors, width=0.62)
    ax.scatter(x, thresholds, color="#172A3A", marker="_", s=700, linewidths=3, label="Release threshold", zorder=3)
    ax.bar_label(bars, labels=[f"{value:.1%}" for value in values], padding=4, fontsize=10)
    ax.set_xticks(x, labels, rotation=15, ha="right")
    ax.set_ylim(0, 1.12)
    ax.set_ylabel("Score")
    ax.set_title("Chapter 11 Data-Quality Gate", loc="left", weight="bold", fontsize=15)
    ax.grid(axis="y", alpha=0.2)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, loc="lower left")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "11-data-quality-dashboard.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    """Run the complete transformation, validation, and publication workflow."""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    run_time = datetime.now(timezone.utc).replace(microsecond=0)
    run_id = run_time.strftime("DSDP11-%Y%m%dT%H%M%SZ")

    raw = example_orders()
    staged = stage_orders(raw)
    evaluated, rules = evaluate_rules(staged)
    clean = evaluated.loc[evaluated["is_valid"]].drop(columns=["is_valid", "quality_issues"]).copy()
    quarantine = evaluated.loc[~evaluated["is_valid"]].drop(columns=["is_valid"]).copy()
    for frame in [clean, quarantine]:
        frame["transformation_run_id"] = run_id
        frame["transformed_at_utc"] = run_time.isoformat()

    metrics = calculate_metrics(evaluated, rules)
    published_completeness = float(1 - clean[list(REQUIRED_COLUMNS)].isna().to_numpy().mean())
    published_uniqueness = float(1 - clean["order_id"].duplicated(keep=False).mean())
    gate_checks = {
        "acceptance_rate": metrics["acceptance_rate"] >= THRESHOLDS["acceptance_rate"],
        "published_completeness": published_completeness >= THRESHOLDS["published_completeness"],
        "published_uniqueness": published_uniqueness >= THRESHOLDS["published_uniqueness"],
    }
    decision = "pass" if all(gate_checks.values()) else "fail"

    clean.to_csv(PROCESSED_DIR / "11-orders-clean.csv", index=False)
    quarantine.to_csv(PROCESSED_DIR / "11-orders-quarantine.csv", index=False)
    pd.DataFrame(
        [{"metric": name, "value": value, "threshold": THRESHOLDS[name]} for name, value in metrics.items()]
    ).to_csv(RESULTS_DIR / "11-data-quality-metrics.csv", index=False)
    summary = {
        "chapter_id": "DSDP-011",
        "run_id": run_id,
        "input_rows": len(raw),
        "published_rows": len(clean),
        "quarantined_rows": len(quarantine),
        "metrics": metrics,
        "published_metrics": {"completeness": published_completeness, "uniqueness": published_uniqueness},
        "thresholds": THRESHOLDS,
        "gate_checks": gate_checks,
        "decision": decision,
    }
    (RESULTS_DIR / "11-data-quality-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    save_dashboard(metrics)

    print(json.dumps(summary, indent=2))
    return 0 if decision == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
