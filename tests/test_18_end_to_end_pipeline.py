import csv
import importlib.util
import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/python/18-run-end-to-end-pipeline.py"
SPEC = importlib.util.spec_from_file_location("pipeline18", SCRIPT)
pipeline = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(pipeline)


def make_config(tmp_path: Path) -> Path:
    source = tmp_path / "source.csv"
    source.write_bytes((ROOT / "data/raw/18-course-transactions.csv").read_bytes())
    config = json.loads((ROOT / "configs/18-pipeline.json").read_text(encoding="utf-8"))
    config.update({
        "input_path": str(source),
        "processed_path": str(tmp_path / "processed.csv"),
        "quarantine_path": str(tmp_path / "quarantine.csv"),
        "database_path": str(tmp_path / "warehouse.sqlite"),
        "manifest_path": str(tmp_path / "manifest.json"),
        "history_path": str(tmp_path / "history.csv"),
        "figure_path": str(tmp_path / "summary.svg"),
    })
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def test_validation_counts_and_reasons(tmp_path):
    config_path = make_config(tmp_path)
    manifest = pipeline.run_pipeline(config_path, "test-validation", write_history=False)
    assert manifest["extracted_rows"] == 12
    assert manifest["valid_rows"] == 8
    assert manifest["quarantined_rows"] == 4
    assert manifest["reconciliation"]["net_revenue_cents"] == 73450
    with (tmp_path / "quarantine.csv").open(encoding="utf-8") as handle:
        rejected = list(csv.DictReader(handle))
    reasons = "|".join(row["rejection_reasons"] for row in rejected)
    assert "invalid_transaction_at" in reasons
    assert "missing_customer_id" in reasons
    assert "quantity_must_be_positive" in reasons
    assert "duplicate_transaction_id" in reasons


def test_rerun_is_idempotent_for_business_table(tmp_path):
    config_path = make_config(tmp_path)
    pipeline.run_pipeline(config_path, "test-run-one", write_history=True)
    pipeline.run_pipeline(config_path, "test-run-two", write_history=True)
    with sqlite3.connect(tmp_path / "warehouse.sqlite") as connection:
        fact_count = connection.execute("SELECT COUNT(*) FROM fact_course_transactions").fetchone()[0]
        run_count = connection.execute("SELECT COUNT(*) FROM pipeline_runs").fetchone()[0]
    assert fact_count == 8
    assert run_count == 2
    assert len((tmp_path / "history.csv").read_text(encoding="utf-8").splitlines()) == 3


def test_missing_source_column_fails_early(tmp_path):
    config_path = make_config(tmp_path)
    source = tmp_path / "source.csv"
    text = source.read_text(encoding="utf-8").replace("unit_price", "price", 1)
    source.write_text(text, encoding="utf-8")
    try:
        pipeline.run_pipeline(config_path, "test-schema-drift", write_history=False)
    except ValueError as error:
        assert "unit_price" in str(error)
    else:
        raise AssertionError("Schema drift should fail extraction")
