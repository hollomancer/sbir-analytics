import csv
from pathlib import Path
from datetime import date

import pytest

from src.quality.uspto_validators import (
    validate_rf_id_uniqueness_from_iterator,
    validate_rf_id_uniqueness,
    ValidatorResult,
    iter_rows_from_path,
)


def test_validate_rf_id_uniqueness_from_iterator_all_unique():
    rows = [
        {"rf_id": "r1", "other": 1},
        {"rf_id": "r2", "other": 2},
        {"rf_id": "r3", "other": 3},
    ]

    result: ValidatorResult = validate_rf_id_uniqueness_from_iterator(iter(rows))

    assert result.success is True
    assert result.summary["total_rows"] == 3
    assert result.summary["duplicate_rf_id_values"] == 0
    assert result.summary["missing_rf_id_count"] == 0
    assert result.details["duplicate_samples"] == []


def test_validate_rf_id_uniqueness_from_iterator_with_duplicates_and_missing():
    rows = [
        {"rf_id": "r1"},
        {"rf_id": "r2"},
        {"rf_id": "r1"},  # duplicate
        {"id": "alt1"},  # alternative id field - should be ignored if rf_id is preferred
        {"rf_id": ""},  # empty counts as missing
        {},  # missing rf_id
        {"rf_id": "r3"},
        {"record_id": "r2"},  # record_id exists but rf_id already had r2
    ]

    # Use iterator; function should find duplicate 'r1' and treat empty/missing rf_id
    result: ValidatorResult = validate_rf_id_uniqueness_from_iterator(iter(rows))

    assert result.success is False
    assert result.summary["total_rows"] == len(rows)
    # at least one duplicate value detected
    assert result.summary["duplicate_rf_id_values"] >= 1
    # missing rf_id counted
    assert result.summary["missing_rf_id_count"] >= 2
    # duplicate_samples returns a list (may be empty if dedup bounding removed items)
    assert isinstance(result.details["duplicate_samples"], list)


def _write_csv(path: Path, headers, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def test_validate_rf_id_uniqueness_on_csv(tmp_path: Path):
    csv_file = tmp_path / "sample_assignments.csv"
    headers = ["rf_id", "file_id", "grant_doc_num"]
    rows = [
        {"rf_id": "A1", "file_id": "F1", "grant_doc_num": "G1"},
        {"rf_id": "A2", "file_id": "F1", "grant_doc_num": "G2"},
        {"rf_id": "A1", "file_id": "F2", "grant_doc_num": "G3"},  # duplicate A1
        {"rf_id": "", "file_id": "F3", "grant_doc_num": "G4"},  # empty -> missing
        {"file_id": "F4", "grant_doc_num": "G5"},  # missing rf_id entirely
    ]
    _write_csv(csv_file, headers, rows)

    # Use file-based validator
    result = validate_rf_id_uniqueness(csv_file, chunk_size=2)

    assert isinstance(result, ValidatorResult)
    assert result.summary["total_rows"] == len(rows)
    # duplicates should be detected (A1)
    assert result.summary["duplicate_rf_id_values"] >= 1
    # missing rf_id count at least 2 (empty and missing)
    assert result.summary["missing_rf_id_count"] >= 2
    # details contain duplicate examples mapping
    assert "duplicate_examples_counts" in result.details


def test_iter_rows_from_path_csv_and_parquet_and_dta_availability(tmp_path: Path):
    """
    Smoke test for iter_rows_from_path wrapper.
    This test writes a small CSV and ensures the iterator yields the expected rows.
    It does not require pyarrow/pyreadstat; parquet/dta readers are exercised elsewhere
    when those libs are available in the environment.
    """
    csv_file = tmp_path / "rows.csv"
    headers = ["rf_id", "value"]
    rows = [{"rf_id": "X1", "value": "a"}, {"rf_id": "X2", "value": "b"}]
    _write_csv(csv_file, headers, rows)

    yielded = list(iter_rows_from_path(csv_file, chunk_size=1))
    assert len(yielded) == len(rows)
    assert yielded[0]["rf_id"] == "X1"
    assert yielded[1]["rf_id"] == "X2"
