"""Generate deterministic run metadata and an observability dashboard for DSDP 14."""

from __future__ import annotations

import csv
import json
import random
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"
FIGURES = RESULTS / "figures"

SLOS = {
    "minimum_input_rows": 800,
    "minimum_valid_row_rate": 0.98,
    "maximum_freshness_lag_minutes": 60.0,
    "maximum_duration_seconds": 90.0,
}


def evaluate_run(run: dict[str, object]) -> list[str]:
    """Return every SLO name breached by a pipeline run."""
    failed: list[str] = []
    if run["status"] != "success":
        failed.append("status")
    if int(run["input_rows"]) < SLOS["minimum_input_rows"]:
        failed.append("volume")
    if float(run["valid_row_rate"]) < SLOS["minimum_valid_row_rate"]:
        failed.append("quality")
    if float(run["freshness_lag_minutes"]) > SLOS["maximum_freshness_lag_minutes"]:
        failed.append("freshness")
    if float(run["duration_seconds"]) > SLOS["maximum_duration_seconds"]:
        failed.append("duration")
    return failed


def simulate_runs(count: int = 30, seed: int = 14) -> list[dict[str, object]]:
    """Create reproducible healthy runs plus four controlled incidents."""
    rng = random.Random(seed)
    first_start = datetime(2026, 7, 8, 3, tzinfo=timezone.utc)
    runs: list[dict[str, object]] = []

    for index in range(count):
        started = first_start + timedelta(days=index)
        input_rows = max(0, round(rng.gauss(1010, 55)))
        valid_rate = min(1.0, max(0.0, rng.gauss(0.992, 0.003)))
        freshness = max(0.0, rng.gauss(21, 7))
        duration = max(1.0, rng.gauss(48, 9))

        # One clear example of each monitored incident.
        if index == 8:
            input_rows = 610
        elif index == 15:
            freshness = 132.0
        elif index == 22:
            valid_rate = 0.941
        elif index == 27:
            duration = 118.0

        output_rows = round(input_rows * valid_rate)
        run: dict[str, object] = {
            "pipeline_name": "daily-orders",
            "run_id": f"daily-orders-{started:%Y%m%dT%H%M%SZ}",
            "started_at": started.isoformat(),
            "status": "success",
            "input_rows": input_rows,
            "output_rows": output_rows,
            "rejected_rows": input_rows - output_rows,
            "valid_row_rate": round(valid_rate, 4),
            "freshness_lag_minutes": round(freshness, 1),
            "duration_seconds": round(duration, 1),
        }
        failed = evaluate_run(run)
        run["failed_checks"] = ";".join(failed)
        run["alert_count"] = len(failed)
        runs.append(run)
    return runs


def write_outputs(runs: list[dict[str, object]]) -> None:
    """Write run-level CSV and aggregate JSON outputs."""
    RESULTS.mkdir(parents=True, exist_ok=True)
    csv_path = RESULTS / "14-pipeline-run-metadata.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(runs[0]))
        writer.writeheader()
        writer.writerows(runs)

    alerts = Counter()
    for run in runs:
        alerts.update(filter(None, str(run["failed_checks"]).split(";")))

    summary = {
        "pipeline_name": "daily-orders",
        "runs_observed": len(runs),
        "healthy_runs": sum(int(run["alert_count"]) == 0 for run in runs),
        "alerting_runs": sum(int(run["alert_count"]) > 0 for run in runs),
        "alerts_by_check": dict(sorted(alerts.items())),
        "slos": SLOS,
    }
    (RESULTS / "14-monitoring-summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )


def plot_dashboard(runs: list[dict[str, object]]) -> None:
    """Plot four monitored signals with SLO lines and incident markers."""
    FIGURES.mkdir(parents=True, exist_ok=True)
    x = list(range(1, len(runs) + 1))
    alerting = [int(run["alert_count"]) > 0 for run in runs]
    colors = ["#c0392b" if is_alert else "#2471a3" for is_alert in alerting]

    panels = [
        ("duration_seconds", SLOS["maximum_duration_seconds"], "Duration (seconds)", "max"),
        ("input_rows", SLOS["minimum_input_rows"], "Input rows", "min"),
        ("valid_row_rate", SLOS["minimum_valid_row_rate"], "Valid-row rate", "min"),
        (
            "freshness_lag_minutes",
            SLOS["maximum_freshness_lag_minutes"],
            "Freshness lag (minutes)",
            "max",
        ),
    ]

    fig, axes = plt.subplots(2, 2, figsize=(12, 7.5), sharex=True)
    for ax, (field, threshold, label, direction) in zip(axes.flat, panels):
        values = [float(run[field]) for run in runs]
        ax.plot(x, values, color="#7f8c8d", linewidth=1.4, zorder=1)
        ax.scatter(x, values, c=colors, s=32, zorder=2)
        ax.axhline(threshold, color="#d35400", linestyle="--", linewidth=1.3)
        comparator = "Maximum" if direction == "max" else "Minimum"
        ax.text(
            0.99,
            0.94,
            f"{comparator} SLO: {threshold:g}",
            transform=ax.transAxes,
            ha="right",
            va="top",
            fontsize=8.5,
            color="#a04000",
        )
        ax.set_ylabel(label)
        ax.grid(alpha=0.22)

    for ax in axes[-1]:
        ax.set_xlabel("Daily pipeline run")
    fig.suptitle("Daily Orders Pipeline: 30-Run Observability Dashboard", fontsize=15)
    fig.text(
        0.5,
        0.01,
        "Blue = healthy run  |  Red = one or more SLO breaches",
        ha="center",
        fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.04, 1, 0.95))
    fig.savefig(FIGURES / "14-pipeline-observability-dashboard.png", dpi=180)
    plt.close(fig)


def main() -> None:
    runs = simulate_runs()
    write_outputs(runs)
    plot_dashboard(runs)
    print(f"Generated {len(runs)} runs; {sum(int(r['alert_count']) > 0 for r in runs)} alerting runs.")


if __name__ == "__main__":
    main()

