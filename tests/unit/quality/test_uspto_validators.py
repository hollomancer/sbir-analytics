"""Unit tests for USPTO data validators.

Tests cover:
- RF ID uniqueness validation
- Referential integrity checks
- Field completeness validation
- Date field validation
- Duplicate record detection
- USPTO validation orchestration
"""

import csv
import gzip
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.quality.uspto_validators import (
    USPTODataQualityValidator,
    USPTOValidationConfig,
    ValidatorResult,
    validate_date_fields,
    validate_duplicate_records,
    validate_field_completeness,
    validate_referential_integrity,
    validate_rf_id_uniqueness,
    validate_rf_id_uniqueness_from_iterator,
)

pytestmark = pytest.mark.fast


@pytest.fixture
def sample_csv_file(tmp_path):
    """Create a sample CSV file for testing."""
    csv_file = tmp_path / "test.csv"
    with open(csv_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["rf_id", "name", "date"])
        writer.writeheader()
        writer.writerow({"rf_id": "001", "name": "Test 1", "date": "2020-01-01"})
        writer.writerow({"rf_id": "002", "name": "Test 2", "date": "2020-01-02"})
        writer.writerow({"rf_id": "003", "name": "Test 3", "date": "2020-01-03"})
    return csv_file


@pytest.fixture
def sample_rows():
    """Create sample row dictionaries."""
    return [
        {"rf_id": "001", "name": "Alice", "amount": "100"},
        {"rf_id": "002", "name": "Bob", "amount": "200"},
        {"rf_id": "003", "name": "Charlie", "amount": "300"},
    ]


@pytest.fixture
def duplicate_rows():
    """Create rows with duplicate rf_id."""
    return [
        {"rf_id": "001", "name": "Alice"},
        {"rf_id": "002", "name": "Bob"},
        {"rf_id": "001", "name": "Alice Duplicate"},
    ]


class TestValidatorResult:
    """Tests for ValidatorResult dataclass."""

    def test_result_creation(self):
        """Test creating a validator result."""
        result = ValidatorResult(
            success=True,
            summary={"total_rows": 100},
            details={"sample": []},
        )

        assert result.success is True
        assert result.summary["total_rows"] == 100
        assert "sample" in result.details


class TestRfIdUniqueness:
    """Tests for RF ID uniqueness validation."""

    def test_unique_rf_ids_from_iterator(self, sample_rows):
        """Test uniqueness validation with all unique IDs."""
        result = validate_rf_id_uniqueness_from_iterator(sample_rows)

        assert result.success is True
        assert result.summary["total_rows"] == 3
        assert result.summary["duplicate_rf_id_values"] == 0
        assert result.summary["unique_rf_id_values"] == 3

    def test_duplicate_rf_ids_from_iterator(self, duplicate_rows):
        """Test uniqueness validation with duplicates."""
        result = validate_rf_id_uniqueness_from_iterator(duplicate_rows)

        assert result.success is False
        assert result.summary["duplicate_rf_id_values"] == 1
        assert len(result.details["duplicate_samples"]) > 0

    def test_missing_rf_ids_from_iterator(self):
        """Test with missing rf_id values."""
        rows = [
            {"rf_id": "001", "name": "Alice"},
            {"rf_id": None, "name": "Bob"},
            {"rf_id": "", "name": "Charlie"},
        ]

        result = validate_rf_id_uniqueness_from_iterator(rows)

        assert result.summary["missing_rf_id_count"] == 2
        assert result.summary["total_rf_ids_found"] == 1

    def test_rf_id_uniqueness_from_file(self, sample_csv_file):
        """Test RF ID uniqueness validation from file."""
        result = validate_rf_id_uniqueness(sample_csv_file)

        assert result.success is True
        assert result.summary["total_rows"] == 3
        assert result.summary["duplicate_rf_id_values"] == 0

    def test_rf_id_uniqueness_missing_file(self, tmp_path):
        """Test with non-existent file."""
        missing_file = tmp_path / "missing.csv"

        with pytest.raises(FileNotFoundError):
            validate_rf_id_uniqueness(missing_file)

    def test_rf_id_custom_field_names(self):
        """Test with custom rf_id field names."""
        rows = [
            {"record_id": "001", "name": "Alice"},
            {"record_id": "002", "name": "Bob"},
        ]

        result = validate_rf_id_uniqueness_from_iterator(
            rows, rf_id_field_names=["record_id"]
        )

        assert result.success is True
        assert result.summary["total_rf_ids_found"] == 2


class TestReferentialIntegrity:
    """Tests for referential integrity validation."""

    def test_valid_referential_integrity(self, tmp_path):
        """Test when all child FKs reference valid parent PKs."""
        # Create parent file
        parent_file = tmp_path / "parent.csv"
        with open(parent_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["rf_id", "data"])
            writer.writeheader()
            writer.writerow({"rf_id": "001", "data": "Parent 1"})
            writer.writerow({"rf_id": "002", "data": "Parent 2"})

        # Create child file
        child_file = tmp_path / "child.csv"
        with open(child_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["rf_id", "child_data"])
            writer.writeheader()
            writer.writerow({"rf_id": "001", "child_data": "Child 1"})
            writer.writerow({"rf_id": "002", "child_data": "Child 2"})

        result = validate_referential_integrity(child_file, parent_file)

        assert result.success is True
        assert result.summary["orphaned_records"] == 0

    def test_orphaned_records(self, tmp_path):
        """Test detection of orphaned child records."""
        # Parent file
        parent_file = tmp_path / "parent.csv"
        with open(parent_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["rf_id"])
            writer.writeheader()
            writer.writerow({"rf_id": "001"})

        # Child file with orphaned record
        child_file = tmp_path / "child.csv"
        with open(child_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["rf_id"])
            writer.writeheader()
            writer.writerow({"rf_id": "001"})
            writer.writerow({"rf_id": "999"})  # Orphaned

        result = validate_referential_integrity(child_file, parent_file)

        assert result.success is False
        assert result.summary["orphaned_records"] == 1
        assert len(result.details["orphaned_sample"]) == 1

    def test_multiple_parent_files(self, tmp_path):
        """Test referential integrity with multiple parent files."""
        # Parent files
        parent1 = tmp_path / "parent1.csv"
        with open(parent1, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["rf_id"])
            writer.writeheader()
            writer.writerow({"rf_id": "001"})

        parent2 = tmp_path / "parent2.csv"
        with open(parent2, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["rf_id"])
            writer.writeheader()
            writer.writerow({"rf_id": "002"})

        # Child file
        child_file = tmp_path / "child.csv"
        with open(child_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["rf_id"])
            writer.writeheader()
            writer.writerow({"rf_id": "001"})
            writer.writerow({"rf_id": "002"})

        result = validate_referential_integrity(child_file, [parent1, parent2])

        assert result.success is True
        assert result.summary["parent_files_count"] == 2


class TestFieldCompleteness:
    """Tests for field completeness validation."""

    def test_complete_fields(self, sample_csv_file):
        """Test when all required fields are complete."""
        result = validate_field_completeness(
            sample_csv_file,
            required_fields=["rf_id", "name"],
            completeness_threshold=0.95,
        )

        assert result.success is True
        assert result.summary["failed_fields_count"] == 0

    def test_incomplete_fields(self, tmp_path):
        """Test when fields are below completeness threshold."""
        csv_file = tmp_path / "incomplete.csv"
        with open(csv_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["rf_id", "name"])
            writer.writeheader()
            writer.writerow({"rf_id": "001", "name": "Alice"})
            writer.writerow({"rf_id": "002", "name": ""})  # Missing
            writer.writerow({"rf_id": "003", "name": None})  # Missing

        result = validate_field_completeness(
            csv_file,
            required_fields=["name"],
            completeness_threshold=0.95,
        )

        assert result.success is False
        assert result.summary["failed_fields_count"] == 1
        assert "name" in result.details["failed_fields"]

    def test_custom_threshold(self, tmp_path):
        """Test with custom completeness threshold."""
        csv_file = tmp_path / "partial.csv"
        with open(csv_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["rf_id", "name"])
            writer.writeheader()
            writer.writerow({"rf_id": "001", "name": "Alice"})
            writer.writerow({"rf_id": "002", "name": ""})

        # 50% complete should pass 50% threshold
        result = validate_field_completeness(
            csv_file, required_fields=["name"], completeness_threshold=0.50
        )

        assert result.success is True


class TestDateFields:
    """Tests for date field validation."""

    def test_valid_dates(self, tmp_path):
        """Test validation of valid dates."""
        csv_file = tmp_path / "dates.csv"
        with open(csv_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["rf_id", "date"])
            writer.writeheader()
            writer.writerow({"rf_id": "001", "date": "2020-01-01"})
            writer.writerow({"rf_id": "002", "date": "2021-06-15"})

        result = validate_date_fields(csv_file, date_fields=["date"])

        assert result.success is True
        assert result.summary["total_invalid_dates"] == 0

    def test_invalid_date_format(self, tmp_path):
        """Test detection of invalid date formats."""
        csv_file = tmp_path / "bad_dates.csv"
        with open(csv_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["rf_id", "date"])
            writer.writeheader()
            writer.writerow({"rf_id": "001", "date": "not-a-date"})
            writer.writerow({"rf_id": "002", "date": "2020-01-01"})

        result = validate_date_fields(csv_file, date_fields=["date"])

        assert result.success is False
        assert result.summary["total_invalid_dates"] > 0

    def test_out_of_range_dates(self, tmp_path):
        """Test detection of dates outside valid range."""
        csv_file = tmp_path / "range_dates.csv"
        with open(csv_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["rf_id", "date"])
            writer.writeheader()
            writer.writerow({"rf_id": "001", "date": "1500-01-01"})  # Too old
            writer.writerow({"rf_id": "002", "date": "2020-01-01"})

        result = validate_date_fields(
            csv_file, date_fields=["date"], min_year=1790, max_year=2100
        )

        assert result.success is False
        assert result.summary["total_invalid_dates"] > 0


class TestDuplicateRecords:
    """Tests for duplicate record detection."""

    def test_unique_records(self, sample_csv_file):
        """Test when all records are unique."""
        result = validate_duplicate_records(sample_csv_file, key_fields=["rf_id"])

        assert result.success is True
        assert result.summary["duplicate_records"] == 0

    def test_duplicate_detection(self, tmp_path):
        """Test detection of duplicate records."""
        csv_file = tmp_path / "duplicates.csv"
        with open(csv_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["rf_id", "name"])
            writer.writeheader()
            writer.writerow({"rf_id": "001", "name": "Alice"})
            writer.writerow({"rf_id": "001", "name": "Alice"})  # Duplicate
            writer.writerow({"rf_id": "002", "name": "Bob"})

        result = validate_duplicate_records(csv_file, key_fields=["rf_id"])

        assert result.success is False
        assert result.summary["duplicate_records"] == 1

    def test_composite_key_duplicates(self, tmp_path):
        """Test duplicate detection with composite keys."""
        csv_file = tmp_path / "composite.csv"
        with open(csv_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["rf_id", "doc_num"])
            writer.writeheader()
            writer.writerow({"rf_id": "001", "doc_num": "A"})
            writer.writerow({"rf_id": "001", "doc_num": "B"})  # Different, not duplicate
            writer.writerow({"rf_id": "001", "doc_num": "A"})  # Duplicate

        result = validate_duplicate_records(csv_file, key_fields=["rf_id", "doc_num"])

        assert result.success is False
        assert result.summary["duplicate_records"] == 1


class TestUSPTOValidationConfig:
    """Tests for USPTO validation configuration."""

    def test_default_config(self):
        """Test default configuration values."""
        config = USPTOValidationConfig()

        assert config.chunk_size == 10000
        assert config.sample_limit == 20
        assert config.completeness_threshold == 0.95
        assert "assignments" in config.required_fields
        assert "assignments" in config.date_fields

    def test_custom_config(self, tmp_path):
        """Test custom configuration."""
        config = USPTOValidationConfig(
            chunk_size=5000,
            sample_limit=10,
            completeness_threshold=0.90,
            fail_output_dir=tmp_path / "failures",
        )

        assert config.chunk_size == 5000
        assert config.sample_limit == 10
        assert config.completeness_threshold == 0.90


class TestUSPTODataQualityValidator:
    """Tests for USPTO validation orchestrator."""

    def test_validator_initialization(self, tmp_path):
        """Test validator initialization."""
        config = USPTOValidationConfig(
            fail_output_dir=tmp_path / "fail",
            report_output_dir=tmp_path / "reports",
        )
        validator = USPTODataQualityValidator(config)

        assert validator.config == config
        assert validator.config.fail_output_dir.exists()
        assert validator.config.report_output_dir.exists()

    def test_validator_run_empty_input(self, tmp_path):
        """Test validator with empty input."""
        config = USPTOValidationConfig(
            fail_output_dir=tmp_path / "fail",
            report_output_dir=tmp_path / "reports",
        )
        validator = USPTODataQualityValidator(config)

        report = validator.run({})

        assert report["overall_success"] is True
        assert "tables" in report
        assert "summary" in report

    def test_validator_run_with_files(self, tmp_path):
        """Test validator with actual files."""
        # Create sample assignments file
        assignments_file = tmp_path / "assignments.csv"
        with open(assignments_file, "w", newline="") as f:
            writer = csv.DictWriter(
                f, fieldnames=["rf_id", "record_dt", "cname", "last_update_dt"]
            )
            writer.writeheader()
            writer.writerow({
                "rf_id": "001",
                "record_dt": "2020-01-01",
                "cname": "Test Company",
                "last_update_dt": "2020-01-02",
            })

        config = USPTOValidationConfig(
            fail_output_dir=tmp_path / "fail",
            report_output_dir=tmp_path / "reports",
        )
        validator = USPTODataQualityValidator(config)

        report = validator.run({"assignments": [assignments_file]})

        assert "tables" in report
        assert "assignments" in report["tables"]
        assert "summary" in report

    def test_validator_report_generation(self, tmp_path):
        """Test that validator generates reports."""
        config = USPTOValidationConfig(
            fail_output_dir=tmp_path / "fail",
            report_output_dir=tmp_path / "reports",
        )
        validator = USPTODataQualityValidator(config)

        report = validator.run({}, write_report=True)

        assert "report_path" in report
        assert Path(report["report_path"]).exists()

    def test_validator_failure_sample_writing(self, tmp_path):
        """Test that validator writes failure samples."""
        # Create file with duplicates
        dup_file = tmp_path / "duplicates.csv"
        with open(dup_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["rf_id", "record_dt", "cname"])
            writer.writeheader()
            writer.writerow({"rf_id": "001", "record_dt": "2020-01-01", "cname": "Test"})
            writer.writerow({"rf_id": "001", "record_dt": "2020-01-01", "cname": "Test"})

        config = USPTOValidationConfig(
            fail_output_dir=tmp_path / "fail",
            report_output_dir=tmp_path / "reports",
        )
        validator = USPTODataQualityValidator(config)

        report = validator.run({"assignments": [dup_file]})

        # Check if failure samples were written
        assert len(report["failure_samples"]) > 0
