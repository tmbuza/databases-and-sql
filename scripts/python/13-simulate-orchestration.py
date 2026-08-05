#!/usr/bin/env python3
"""Simulate an observable, retry-aware daily pipeline orchestration history."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from random import Random

import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"
FIGURES = RESULTS / "figures"
TASKS = ("extract", "validate", "transform", "publish")


@dataclass
class Event:
    run_id: str
    logical_date: str
    task: str
    attempt: int
    state: str
    duration_seconds: float
    retryable: bool
    idempotency_key: str


@dataclass
class Run:
    run_id: str
    logical_date: str
    state: str
    duration_seconds: float
    attempts: int
    retries: int
    failed_task: str


def failure_plan(logical_date: str, task: str, attempt: int) -> tuple[bool, bool]:
    """Return (failed, retryable) for deterministic teaching scenarios."""
    if logical_date == "2026-07-31" and task == "extract" and attempt == 1:
        return True, True
    if logical_date == "2026-08-03" and task == "publish" and attempt == 1:
        return True, True
    if logical_date == "2026-08-04" and task == "validate" and attempt == 1:
        return True, False
    return False, False


def simulate() -> tuple[list[Run], list[Event]]:
    rng = Random(13)
    start = date(2026, 7, 29)
    runs: list[Run] = []
    events: list[Event] = []

    for offset in range(7):
        logical_date = (start + timedelta(days=offset)).isoformat()
        run_id = f"daily-orders-{logical_date}"
        run_duration = 0.0
        attempts = 0
        retries = 0
        failed_task = ""

        for task_index, task in enumerate(TASKS):
            max_attempts = 3 if task in {"extract", "publish"} else 1
            task_succeeded = False

            for attempt in range(1, max_attempts + 1):
                attempts += 1
                base = (38, 10, 26, 12)[task_index]
                duration = round(base + rng.uniform(-4, 8), 2)
                run_duration += duration
                failed, retryable = failure_plan(logical_date, task, attempt)
                state = "failed" if failed else "succeeded"
                events.append(
                    Event(
                        run_id=run_id,
                        logical_date=logical_date,
                        task=task,
                        attempt=attempt,
                        state=state,
                        duration_seconds=duration,
                        retryable=retryable,
                        idempotency_key=f"daily-orders:{logical_date}:{task}",
                    )
                )

                if not failed:
                    task_succeeded = True
                    break
                if retryable and attempt < max_attempts:
                    retries += 1
                    backoff = 15 * (2 ** (attempt - 1))
                    run_duration += backoff
                else:
                    failed_task = task
                    break

            if not task_succeeded:
                break

        runs.append(
            Run(
                run_id=run_id,
                logical_date=logical_date,
                state="failed" if failed_task else "succeeded",
                duration_seconds=round(run_duration, 2),
                attempts=attempts,
                retries=retries,
                failed_task=failed_task,
            )
        )

    return runs, events


def write_csv(path: Path, rows: list[object]) -> None:
    records = [asdict(row) for row in rows]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=records[0].keys())
        writer.writeheader()
        writer.writerows(records)


def write_summary(runs: list[Run], events: list[Event]) -> dict[str, object]:
    successful = sum(run.state == "succeeded" for run in runs)
    runs_with_retries = sum(run.retries > 0 for run in runs)
    durations = sorted(run.duration_seconds for run in runs)
    summary = {
        "workflow_id": "daily_orders_pipeline",
        "logical_intervals": len(runs),
        "successful_runs": successful,
        "failed_runs": len(runs) - successful,
        "success_rate": round(successful / len(runs), 4),
        "runs_with_retries": runs_with_retries,
        "retry_run_rate": round(runs_with_retries / len(runs), 4),
        "task_attempts": len(events),
        "median_run_duration_seconds": durations[len(durations) // 2],
        "maximum_run_duration_seconds": max(durations),
        "failed_intervals": [run.logical_date for run in runs if run.state == "failed"],
    }
    with (RESULTS / "13-orchestration-summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
        handle.write("\n")
    return summary


def plot_runs(runs: list[Run]) -> None:
    labels = [run.logical_date[5:] for run in runs]
    durations = [run.duration_seconds for run in runs]
    colors = ["#247BA0" if run.state == "succeeded" else "#D1495B" for run in runs]

    fig, ax = plt.subplots(figsize=(10, 5.8))
    bars = ax.barh(labels, durations, color=colors, edgecolor="white", height=0.68)
    ax.invert_yaxis()
    ax.set_title("Daily pipeline orchestration history", loc="left", weight="bold")
    ax.set_xlabel("Run duration (seconds, including retry backoff)")
    ax.set_ylabel("Logical date (2026)")
    ax.grid(axis="x", alpha=0.25)
    ax.set_axisbelow(True)

    for bar, run in zip(bars, runs):
        annotation = run.state
        if run.retries:
            annotation += f" · {run.retries} retry"
        if run.failed_task:
            annotation += f" at {run.failed_task}"
        ax.text(
            bar.get_width() + 2,
            bar.get_y() + bar.get_height() / 2,
            annotation,
            va="center",
            fontsize=9,
        )

    ax.set_xlim(0, max(durations) * 1.38)
    fig.text(
        0.01,
        0.01,
        "Blue = succeeded; red = failed. Simulated deterministic teaching data.",
        fontsize=8,
        color="#555555",
    )
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(FIGURES / "13-orchestration-run-history.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    runs, events = simulate()
    write_csv(RESULTS / "13-orchestration-runs.csv", runs)
    write_csv(RESULTS / "13-orchestration-events.csv", events)
    summary = write_summary(runs, events)
    plot_runs(runs)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
