"""Tests for the DSDP 14 observable-pipeline example."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/python/14-monitor-observable-pipeline.py"
SPEC = importlib.util.spec_from_file_location("observable_pipeline", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def healthy_run() -> dict[str, object]:
    return {
        "status": "success",
        "input_rows": 1000,
        "valid_row_rate": 0.995,
        "freshness_lag_minutes": 20.0,
        "duration_seconds": 40.0,
    }


def test_healthy_run_passes_all_slos() -> None:
    assert MODULE.evaluate_run(healthy_run()) == []


@pytest.mark.parametrize(
    ("field", "value", "expected_check"),
    [
        ("input_rows", 799, "volume"),
        ("valid_row_rate", 0.979, "quality"),
        ("freshness_lag_minutes", 60.1, "freshness"),
        ("duration_seconds", 90.1, "duration"),
        ("status", "failed", "status"),
    ],
)
def test_each_slo_breach_is_detected(field: str, value: object, expected_check: str) -> None:
    run = healthy_run()
    run[field] = value
    assert MODULE.evaluate_run(run) == [expected_check]


def test_simulation_is_reproducible_and_contains_four_incidents() -> None:
    first = MODULE.simulate_runs()
    second = MODULE.simulate_runs()
    assert first == second
    assert len(first) == 30
    assert sum(int(run["alert_count"]) > 0 for run in first) == 4


def test_row_accounting_is_consistent() -> None:
    for run in MODULE.simulate_runs():
        assert int(run["input_rows"]) == int(run["output_rows"]) + int(run["rejected_rows"])

