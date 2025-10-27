import csv
from pathlib import Path

from src.quality.uspto_validators import (
    USPTODataQualityValidator,
    USPTOValidationConfig,
    ValidatorResult,
    iter_rows_from_path,
    validate_referential_integrity,
    validate_rf_id_uniqueness,
    validate_rf_id_uniqueness_from_iterator,
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


def test_validate_referential_integrity_handles_multiple_parents(tmp_path: Path):
    parent1 = tmp_path / "parent1.csv"
    parent2 = tmp_path / "parent2.csv"
    child = tmp_path / "child.csv"

    headers = ["rf_id", "record_dt", "cname"]
    _write_csv(parent1, headers, [{"rf_id": "R1", "record_dt": "2020-01-01", "cname": "A"}])
    _write_csv(parent2, headers, [{"rf_id": "R2", "record_dt": "2020-01-02", "cname": "B"}])

    child_headers = ["rf_id", "ee_name"]
    _write_csv(
        child,
        child_headers,
        [
            {"rf_id": "R1", "ee_name": "Company"},
            {"rf_id": "R3", "ee_name": "Ghost"},
        ],
    )

    result = validate_referential_integrity(child, [parent1, parent2])
    assert result.summary["parent_files_count"] == 2
    assert result.summary["orphaned_records"] == 1
    assert result.success is False


def test_uspto_data_quality_validator_generates_report(tmp_path: Path):
    assignment_file = tmp_path / "assignment.csv"
    assignee_file = tmp_path / "assignee.csv"

    assignment_headers = ["rf_id", "record_dt", "cname"]
    _write_csv(
        assignment_file,
        assignment_headers,
        [
            {"rf_id": "R1", "record_dt": "2020-01-01", "cname": "Firm"},
            {"rf_id": "R2", "record_dt": "2020-02-01", "cname": "Firm"},
        ],
    )

    assignee_headers = ["rf_id", "ee_name"]
    _write_csv(
        assignee_file,
        assignee_headers,
        [
            {"rf_id": "R1", "ee_name": "Company"},
            {"rf_id": "R3", "ee_name": "Ghost"},
        ],
    )

    config = USPTOValidationConfig(
        chunk_size=10,
        sample_limit=5,
        completeness_threshold=0.5,
        fail_output_dir=tmp_path / "fail",
        report_output_dir=tmp_path / "reports",
    )
    validator = USPTODataQualityValidator(config)

    report = validator.run(
        {
            "assignments": [assignment_file],
            "assignees": [assignee_file],
            "assignors": [],
            "documentids": [],
            "conveyances": [],
        }
    )

    assignee_checks = report["tables"]["assignees"][str(assignee_file)]["checks"]
    assert assignee_checks["referential_integrity"]["success"] is False
    assert report["summary"]["total_checks"] >= 3
    assert report["overall_success"] is False

    failure_samples = report.get("failure_samples", [])
    assert failure_samples, "Expected failure samples to be recorded"

    report_path = report.get("report_path")
    if report_path:
        assert Path(report_path).exists()
