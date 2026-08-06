#!/usr/bin/env python3
"""Generate a reproducible security, governance, and lineage evidence bundle."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"
FIGURES = RESULTS / "figures"
RUN_ID = "dsdp16-demo"


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)

    controls = pd.DataFrame(
        [
            ("access", "CTRL-ACCESS-01", "Publisher uses approved write role", True,
             "role=serving_publisher; action=write; resource=serving.daily_sales"),
            ("privacy", "CTRL-PRIVACY-01", "No direct identifiers in serving schema", True,
             "checked=email,full_name,phone; matches=0"),
            ("ownership", "CTRL-OWNER-01", "All governed datasets have owners", True,
             "owned=3; governed=3"),
            ("retention", "CTRL-RETENTION-01", "Restricted raw rows are within retention", False,
             "expired_rows=2; action=delete_and_review"),
            ("lineage", "CTRL-LINEAGE-01", "Published columns have source mappings", True,
             "mapped_columns=2; published_columns=2"),
        ],
        columns=["domain", "control_id", "control", "passed", "evidence"],
    )
    controls["status"] = controls["passed"].map({True: "PASS", False: "FAIL"})
    controls.to_csv(RESULTS / "16-control-results.csv", index=False)

    lineage = {
        "run_id": RUN_ID,
        "output_dataset": "serving.daily_sales",
        "code_version": "dsdp16-v1",
        "columns": [
            {
                "output": "order_date",
                "sources": ["source.orders.ordered_at"],
                "transformation": "convert timestamp to UTC date",
                "classification": "internal",
            },
            {
                "output": "daily_net_sales",
                "sources": ["source.orders.gross_amount", "source.orders.discount"],
                "transformation": "sum(gross_amount - discount) by order_date",
                "classification": "internal",
            },
        ],
    }
    (RESULTS / "16-column-lineage.json").write_text(
        json.dumps(lineage, indent=2) + "\n", encoding="utf-8"
    )

    events = [
        ("2026-08-06T06:00:00Z", "svc-extractor", "read", "source.orders", "allowed", "POL-READ-001"),
        ("2026-08-06T06:01:00Z", "svc-transformer", "write", "curated.orders", "allowed", "POL-WRITE-002"),
        ("2026-08-06T06:02:00Z", "svc-publisher", "publish", "serving.daily_sales", "allowed", "POL-PUBLISH-004"),
        ("2026-08-06T06:03:00Z", "governance-check", "evaluate", "raw.customer_orders", "failed", "POL-RETENTION-007"),
    ]
    with (RESULTS / "16-audit-events.jsonl").open("w", encoding="utf-8") as handle:
        for event_time, actor, action, resource, outcome, policy_id in events:
            handle.write(json.dumps({
                "event_time": event_time,
                "run_id": RUN_ID,
                "actor": actor,
                "action": action,
                "resource": resource,
                "outcome": outcome,
                "policy_id": policy_id,
            }) + "\n")

    passed = int(controls["passed"].sum())
    total = len(controls)
    summary = {
        "run_id": RUN_ID,
        "controls_total": total,
        "controls_passed": passed,
        "controls_failed": total - passed,
        "pass_rate": round(passed / total, 3),
        "overall_status": "FAIL" if passed < total else "PASS",
    }
    (RESULTS / "16-governance-summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )

    plot = controls.sort_values(["passed", "domain"], ascending=[True, True])
    colors = plot["passed"].map({True: "#2a9d8f", False: "#d1495b"})
    fig, ax = plt.subplots(figsize=(9, 5.2))
    ax.barh(plot["domain"].str.title(), 1, color=colors)
    for index, (_, row) in enumerate(plot.iterrows()):
        ax.text(0.03, index, row["status"], va="center", ha="left", color="white", fontweight="bold")
        ax.text(1.02, index, row["control_id"], va="center", ha="left", color="#333333")
    ax.set_xlim(0, 1.35)
    ax.set_xlabel("Control evaluation")
    ax.set_title("DSDP 16 governance control status")
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", alpha=0.18)
    fig.tight_layout()
    fig.savefig(FIGURES / "16-governance-control-status.png", dpi=180, bbox_inches="tight")
    plt.close(fig)

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
