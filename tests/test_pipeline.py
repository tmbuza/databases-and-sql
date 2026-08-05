import json
from pathlib import Path

import pytest

from data_pipelines.pipeline import run_pipeline, transform_records


def test_transform_records_standardizes_values() -> None:
    actual = transform_records(
        [{"record_id": " A-1 ", "category": " Retail ", "amount": "10.125"}]
    )
    assert actual == [{"record_id": "A-1", "category": "retail", "amount": 10.12}]


def test_transform_records_rejects_duplicate_ids() -> None:
    rows = [
        {"record_id": "A-1", "category": "retail", "amount": "10"},
        {"record_id": "A-1", "category": "retail", "amount": "20"},
    ]
    with pytest.raises(ValueError, match="duplicate"):
        transform_records(rows)


def test_run_pipeline_writes_output_and_metadata(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    output = tmp_path / "trusted.jsonl"
    metadata = tmp_path / "run.json"
    source.write_text("record_id,category,amount\nA-1,Retail,10\n", encoding="utf-8")

    result = run_pipeline(source, output, metadata)

    assert result["record_count"] == 1
    assert json.loads(output.read_text(encoding="utf-8"))["record_id"] == "A-1"
    assert json.loads(metadata.read_text(encoding="utf-8"))["status"] == "success"
