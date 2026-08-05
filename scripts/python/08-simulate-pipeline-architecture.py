#!/usr/bin/env python3
"""Simulate a layered daily data pipeline and write reproducible artifacts."""

from __future__ import annotations

import csv
import json
import random
from collections import defaultdict
from pathlib import Path
from statistics import mean

import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"
FIGURES = RESULTS / "figures"
SEED = 808
RUNS = 30
STAGES = (
    ("extract", 1_100.0, 0.08),
    ("validate", 3_600.0, 0.02),
    ("transform", 2_100.0, 0.03),
    ("load", 2_800.0, 0.04),
    ("publish", 8_000.0, 0.01),
)


def simulate() -> tuple[list[dict], list[dict]]:
    rng = random.Random(SEED)
    runs: list[dict] = []
    stage_events: dict[str, list[dict]] = defaultdict(list)

    for day in range(1, RUNS + 1):
        source_rows = max(20_000, int(rng.gauss(52_000 + day * 350, 5_500)))
        rejected_rows = int(source_rows * max(0.0005, rng.gauss(0.004, 0.0015)))
        accepted_rows = source_rows - rejected_rows
        total_seconds = 0.0
        total_retries = 0
        succeeded = True

        for stage, base_rate, transient_probability in STAGES:
            rows_for_stage = source_rows if stage in {"extract", "validate"} else accepted_rows
            duration = max(1.0, rows_for_stage / base_rate * rng.uniform(0.82, 1.22))
            retries = 0
            while rng.random() < transient_probability and retries < 2:
                retries += 1
                duration += rng.uniform(3.0, 10.0) * (2 ** (retries - 1))
            if retries == 2 and rng.random() < 0.08:
                succeeded = False
            total_seconds += duration
            total_retries += retries
            stage_events[stage].append(
                {"duration_seconds": duration, "retries": retries, "succeeded": succeeded}
            )
            if not succeeded:
                break

        runs.append(
            {
                "run_day": day,
                "status": "succeeded" if succeeded else "failed",
                "source_rows": source_rows,
                "accepted_rows": accepted_rows if succeeded else 0,
                "rejected_rows": rejected_rows,
                "acceptance_rate": accepted_rows / source_rows,
                "duration_seconds": round(total_seconds, 2),
                "retries": total_retries,
            }
        )

    stage_summary = []
    for stage, _, _ in STAGES:
        events = stage_events[stage]
        stage_summary.append(
            {
                "stage": stage,
                "mean_duration_seconds": round(mean(e["duration_seconds"] for e in events), 2),
                "retry_rate": round(sum(e["retries"] > 0 for e in events) / len(events), 4),
                "attempts_observed": len(events),
            }
        )
    return runs, stage_summary


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def plot(runs: list[dict], stages: list[dict], path: Path) -> None:
    days = [r["run_day"] for r in runs]
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8))

    axes[0].plot(days, [r["duration_seconds"] for r in runs], color="#2166ac", marker="o", ms=3)
    axes[0].axhline(120, color="#b2182b", linestyle="--", linewidth=1, label="120 s target")
    axes[0].set(title="End-to-end duration", xlabel="Run day", ylabel="Seconds")
    axes[0].legend(frameon=False)

    axes[1].bar(days, [r["accepted_rows"] for r in runs], color="#4d9221", label="Accepted")
    axes[1].bar(days, [r["rejected_rows"] for r in runs], bottom=[r["accepted_rows"] for r in runs], color="#c51b7d", label="Rejected")
    axes[1].set(title="Processed record volume", xlabel="Run day", ylabel="Rows")
    axes[1].legend(frameon=False)

    names = [s["stage"].title() for s in stages]
    latency = [s["mean_duration_seconds"] for s in stages]
    retry_pct = [100 * s["retry_rate"] for s in stages]
    axes[2].barh(names, latency, color="#8073ac")
    axes[2].set(title="Mean stage latency", xlabel="Seconds")
    for index, (value, retries) in enumerate(zip(latency, retry_pct)):
        axes[2].text(value + 0.4, index, f"{retries:.0f}% retry", va="center", fontsize=8)

    fig.suptitle("Daily retail pipeline: performance and quality", fontweight="bold")
    fig.tight_layout()
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    runs, stages = simulate()
    write_csv(RESULTS / "08-pipeline-run-summary.csv", runs)
    write_csv(RESULTS / "08-pipeline-stage-summary.csv", stages)

    successful = [r for r in runs if r["status"] == "succeeded"]
    summary = {
        "seed": SEED,
        "runs": len(runs),
        "successful_runs": len(successful),
        "success_rate": round(len(successful) / len(runs), 4),
        "mean_duration_seconds": round(mean(r["duration_seconds"] for r in runs), 2),
        "mean_acceptance_rate": round(mean(r["acceptance_rate"] for r in runs), 6),
        "total_retries": sum(r["retries"] for r in runs),
    }
    with (RESULTS / "08-pipeline-case-study.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
        handle.write("\n")
    plot(runs, stages, FIGURES / "08-pipeline-architecture-performance.png")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

