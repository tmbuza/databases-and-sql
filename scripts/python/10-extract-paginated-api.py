#!/usr/bin/env python3
"""Demonstrate resilient cursor-paginated API extraction without network access."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw" / "10-api-extract"
RESULTS_DIR = ROOT / "results"
FIGURES_DIR = RESULTS_DIR / "figures"
WINDOW_START = "2026-08-05T00:00:00Z"
WINDOW_END = "2026-08-06T00:00:00Z"
RUN_ID = "dsdp10-demo-20260806"
MAX_ATTEMPTS = 4


class APIError(RuntimeError):
    """Represent a response that the extraction client must classify."""

    def __init__(self, status: int, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


@dataclass
class RequestMetric:
    page: str
    requests: int = 0
    retries: int = 0
    rate_limits: int = 0
    server_errors: int = 0


class DemoEventsAPI:
    """Return deterministic pages and transient failures for client testing."""

    def __init__(self) -> None:
        self.attempts: dict[str, int] = {}
        self.pages: dict[str, dict[str, Any]] = {
            "START": {
                "items": [
                    {"event_id": "E101", "customer_id": "C001", "event_type": "ticket_opened", "updated_at": "2026-08-05T02:15:00Z"},
                    {"event_id": "E102", "customer_id": "C003", "event_type": "chat_started", "updated_at": "2026-08-05T06:40:00Z"},
                ],
                "next_cursor": "CURSOR-2",
            },
            "CURSOR-2": {
                "items": [
                    {"event_id": "E103", "customer_id": "C002", "event_type": "ticket_updated", "updated_at": "2026-08-05T10:05:00Z"},
                    {"event_id": "E104", "customer_id": "C005", "event_type": "chat_closed", "updated_at": "2026-08-05T13:30:00Z"},
                ],
                "next_cursor": "CURSOR-3",
            },
            "CURSOR-3": {
                "items": [
                    {"event_id": "E104", "customer_id": "C005", "event_type": "chat_closed", "updated_at": "2026-08-05T13:30:00Z"},
                    {"event_id": "E105", "customer_id": "C004", "event_type": "ticket_resolved", "updated_at": "2026-08-05T21:10:00Z"},
                ],
                "next_cursor": None,
            },
        }

    def request(self, cursor: str | None, window_start: str, window_end: str) -> dict[str, Any]:
        if (window_start, window_end) != (WINDOW_START, WINDOW_END):
            raise APIError(400, "unsupported demonstration window")
        key = cursor or "START"
        self.attempts[key] = self.attempts.get(key, 0) + 1
        if key == "CURSOR-2" and self.attempts[key] == 1:
            raise APIError(429, "demonstration rate limit", retry_after=0.25)
        if key == "CURSOR-3" and self.attempts[key] == 1:
            raise APIError(503, "demonstration temporary outage")
        if key not in self.pages:
            raise APIError(400, "unknown cursor")
        return self.pages[key]


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def request_with_retry(
    api: DemoEventsAPI,
    cursor: str | None,
    metric: RequestMetric,
    sleeper: Callable[[float], None],
) -> dict[str, Any]:
    retryable = {429, 500, 502, 503, 504}
    for attempt in range(1, MAX_ATTEMPTS + 1):
        metric.requests += 1
        try:
            return api.request(cursor, WINDOW_START, WINDOW_END)
        except APIError as error:
            if error.status not in retryable or attempt == MAX_ATTEMPTS:
                raise
            metric.retries += 1
            metric.rate_limits += int(error.status == 429)
            metric.server_errors += int(error.status >= 500)
            delay = error.retry_after if error.retry_after is not None else min(2 ** (attempt - 1), 8)
            sleeper(delay)
    raise AssertionError("retry loop ended unexpectedly")


def validate_and_deduplicate(records: list[dict[str, Any]]) -> tuple[pd.DataFrame, int]:
    frame = pd.DataFrame(records)
    required = {"event_id", "customer_id", "event_type", "updated_at"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"missing response fields: {sorted(missing)}")
    if frame["event_id"].isna().any():
        raise ValueError("event_id contains null values")
    frame["updated_at"] = pd.to_datetime(frame["updated_at"], utc=True, errors="raise")
    start = pd.Timestamp(WINDOW_START)
    end = pd.Timestamp(WINDOW_END)
    outside = ~frame["updated_at"].between(start, end, inclusive="left")
    if outside.any():
        raise ValueError("response contains records outside the requested window")
    before = len(frame)
    frame = frame.sort_values(["updated_at", "event_id"]).drop_duplicates("event_id", keep="last")
    duplicates_removed = before - len(frame)
    return frame.reset_index(drop=True), duplicates_removed


def main() -> None:
    started = perf_counter()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    api = DemoEventsAPI()
    pages: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    metrics: list[RequestMetric] = []
    planned_waits: list[float] = []
    seen_cursors: set[str] = set()
    cursor: str | None = None

    while True:
        page_name = cursor or "START"
        if page_name in seen_cursors:
            raise ValueError(f"cursor cycle detected at {page_name}")
        seen_cursors.add(page_name)
        metric = RequestMetric(page=page_name)
        payload = request_with_retry(api, cursor, metric, planned_waits.append)
        if not isinstance(payload.get("items"), list):
            raise ValueError("API response items must be a list")
        pages.append({"cursor": cursor, "response": payload})
        records.extend(payload["items"])
        metrics.append(metric)
        cursor = payload.get("next_cursor")
        if cursor is None:
            break

    frame, duplicates_removed = validate_and_deduplicate(records)
    frame["source_system"] = "demo-support-api"
    frame["source_object"] = "/v1/events"
    frame["extraction_window_start"] = WINDOW_START
    frame["extraction_window_end"] = WINDOW_END
    frame["run_id"] = RUN_ID
    frame["extracted_at_utc"] = datetime.now(timezone.utc).isoformat()

    atomic_write_text(RAW_DIR / "pages.json", json.dumps(pages, indent=2) + "\n")
    csv_text = frame.to_csv(index=False)
    atomic_write_text(RAW_DIR / "events.csv", csv_text)

    checkpoint = {
        "source": "demo-support-api:/v1/events",
        "committed_through_exclusive": WINDOW_END,
        "last_run_id": RUN_ID,
        "published_path": "data/raw/10-api-extract/events.csv",
    }
    atomic_write_text(RESULTS_DIR / "10-api-checkpoint.json", json.dumps(checkpoint, indent=2) + "\n")

    metric_frame = pd.DataFrame([vars(metric) for metric in metrics])
    audit = pd.DataFrame([{
        "run_id": RUN_ID,
        "window_start": WINDOW_START,
        "window_end_exclusive": WINDOW_END,
        "pages": len(pages),
        "requests": int(metric_frame["requests"].sum()),
        "retries": int(metric_frame["retries"].sum()),
        "rate_limit_responses": int(metric_frame["rate_limits"].sum()),
        "server_error_responses": int(metric_frame["server_errors"].sum()),
        "planned_backoff_seconds": sum(planned_waits),
        "records_received": len(records),
        "records_published": len(frame),
        "duplicates_removed": duplicates_removed,
        "duration_ms": round((perf_counter() - started) * 1000, 2),
        "status": "passed",
    }])
    audit.to_csv(RESULTS_DIR / "10-api-extraction-audit.csv", index=False)

    plt.style.use("seaborn-v0_8-whitegrid")
    figure, axis = plt.subplots(figsize=(8.5, 4.8))
    positions = range(len(metric_frame))
    axis.bar([x - 0.18 for x in positions], metric_frame["requests"], width=0.36, label="Requests", color="#155e75")
    axis.bar([x + 0.18 for x in positions], metric_frame["retries"], width=0.36, label="Retries", color="#d97706")
    axis.set_xticks(list(positions), metric_frame["page"])
    axis.set(title="DSDP 10 paginated API extraction", xlabel="Page cursor", ylabel="Count")
    axis.set_ylim(0, max(metric_frame["requests"]) + 1)
    axis.legend(frameon=False)
    figure.text(0.5, 0.01, f"{len(frame)} unique events published · {duplicates_removed} duplicate removed", ha="center", fontsize=9)
    figure.tight_layout(rect=(0, 0.04, 1, 1))
    figure.savefig(FIGURES_DIR / "10-api-extraction-observability.png", dpi=180)
    plt.close(figure)

    print(audit.to_string(index=False))
    print(f"\nExtract:    {(RAW_DIR / 'events.csv').relative_to(ROOT)}")
    print(f"Pages:      {(RAW_DIR / 'pages.json').relative_to(ROOT)}")
    print(f"Checkpoint: {(RESULTS_DIR / '10-api-checkpoint.json').relative_to(ROOT)}")
    print(f"Plot:       {(FIGURES_DIR / '10-api-extraction-observability.png').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
