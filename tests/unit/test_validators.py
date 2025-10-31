"""Unit tests for data validation functions."""

import pandas as pd

from src.models import QualitySeverity
from src.quality.checks import (
    check_completeness,
    check_uniqueness,
    check_value_ranges,
    validate_sbir_awards,
)


class TestCheckCompleteness:
    """Test completeness validation functions."""

    def test_complete_data(self):
        """Test with completely filled data."""
        df = pd.DataFrame(
            {
                "award_id": ["A001", "A002", "A003"],
                "company_name": ["Company A", "Company B", "Company C"],
            }
        )

        issues = check_completeness(df, ["award_id", "company_name"], threshold=0.95)
        assert len(issues) == 0

    def test_missing_data_below_threshold(self):
        """Test with missing data below threshold."""
        df = pd.DataFrame(
            {
                "award_id": ["A001", "A002", None],
                "company_name": ["Company A", "Company B", "Company C"],
            }
        )

        issues = check_completeness(df, ["award_id"], threshold=0.8)
        assert len(issues) == 1
        assert issues[0].field == "award_id"
        assert "below threshold" in issues[0].message
        assert issues[0].severity == QualitySeverity.MEDIUM

    def test_missing_column(self):
        """Test with missing column."""
        df = pd.DataFrame({"award_id": ["A001", "A002", "A003"]})

        issues = check_completeness(df, ["company_name"], threshold=0.95)
        assert len(issues) == 1
        assert issues[0].field == "company_name"
        assert "missing from dataset" in issues[0].message
        assert issues[0].severity == QualitySeverity.CRITICAL

    def test_empty_dataframe(self):
        """Test with empty dataframe."""
        df = pd.DataFrame()

        issues = check_completeness(df, ["award_id"], threshold=0.95)
        assert len(issues) == 1
        assert issues[0].field == "award_id"
        assert "missing from dataset" in issues[0].message


class TestCheckUniqueness:
    """Test uniqueness validation functions."""

    def test_unique_data(self):
        """Test with unique data."""
        df = pd.DataFrame({"award_id": ["A001", "A002", "A003"]})

        issues = check_uniqueness(df, ["award_id"])
        assert len(issues) == 0

    def test_duplicate_data(self):
        """Test with duplicate data."""
        df = pd.DataFrame({"award_id": ["A001", "A002", "A001", "A003"]})

        issues = check_uniqueness(df, ["award_id"])
        assert len(issues) == 1
        assert issues[0].field == "['award_id']"
        assert "duplicates" in issues[0].message
        assert issues[0].severity == QualitySeverity.MEDIUM

    def test_case_insensitive_uniqueness(self):
        """Test case-insensitive uniqueness."""
        df = pd.DataFrame({"company_name": ["Company A", "COMPANY A", "Company B"]})

        issues = check_uniqueness(df, ["company_name"], case_sensitive=False)
        assert len(issues) == 1
        assert "duplicates" in issues[0].message

    def test_missing_field(self):
        """Test with missing field."""
        df = pd.DataFrame({"award_id": ["A001", "A002"]})

        issues = check_uniqueness(df, ["company_name"])
        assert len(issues) == 1
        assert issues[0].severity == QualitySeverity.CRITICAL
        assert "missing" in issues[0].message


class TestCheckValueRanges:
    """Test value range validation functions."""

    def test_valid_range(self):
        """Test with values in valid range."""
        df = pd.DataFrame({"award_amount": [100000, 200000, 300000]})

        issues = check_value_ranges(df, "award_amount", min_value=50000, max_value=500000)
        assert len(issues) == 0

    def test_below_minimum(self):
        """Test with values below minimum."""
        df = pd.DataFrame({"award_amount": [10000, 200000, 300000]})

        issues = check_value_ranges(df, "award_amount", min_value=50000)
        assert len(issues) == 1
        assert "below minimum" in issues[0].message
        assert issues[0].severity == QualitySeverity.MEDIUM

    def test_above_maximum(self):
        """Test with values above maximum."""
        df = pd.DataFrame({"award_amount": [100000, 200000, 600000]})

        issues = check_value_ranges(df, "award_amount", max_value=500000)
        assert len(issues) == 1
        assert "above maximum" in issues[0].message

    def test_allowed_values(self):
        """Test with allowed values list."""
        df = pd.DataFrame({"program": ["SBIR", "STTR", "INVALID"]})

        issues = check_value_ranges(df, "program", allowed_values=["SBIR", "STTR"])
        assert len(issues) == 1
        assert "not in allowed list" in issues[0].message
        assert issues[0].severity == QualitySeverity.HIGH

    def test_missing_field(self):
        """Test with missing field."""
        df = pd.DataFrame({"award_id": ["A001"]})

        issues = check_value_ranges(df, "award_amount", min_value=0)
        assert len(issues) == 1
        assert issues[0].severity == QualitySeverity.CRITICAL

    def test_non_numeric_range_check(self):
        """Test range check on non-numeric field."""
        df = pd.DataFrame({"program": ["SBIR", "STTR"]})

        issues = check_value_ranges(df, "program", min_value=0, max_value=100)
        assert len(issues) == 1
        assert "non-numeric" in issues[0].message
        assert issues[0].severity == QualitySeverity.LOW


class TestValidateAwards:
    """Test comprehensive SBIR awards validation."""

    def test_valid_dataset(self):
        """Test validation of valid dataset."""
        df = pd.DataFrame(
            {
                "award_id": ["A001", "A002", "A003"],
                "company_name": ["Company A", "Company B", "Company C"],
                "award_amount": [100000, 200000, 150000],
                "award_date": ["2023-01-01", "2023-02-01", "2023-03-01"],
                "program": ["SBIR", "SBIR", "STTR"],
            }
        )

        config = {
            "completeness": {"award_id": 0.95, "company_name": 0.95},
            "uniqueness": {"award_id": 1.0},
            "validity": {"award_amount_min": 0, "award_amount_max": 1000000},
        }

        report = validate_sbir_awards(df, config)
        assert report.passed is True
        assert report.overall_score > 0.8
        assert len(report.issues) == 0

    def test_invalid_dataset(self):
        """Test validation of invalid dataset."""
        df = pd.DataFrame(
            {
                "award_id": ["A001", "A001", None],  # Duplicates and missing
                "company_name": [None, "Company B", "Company C"],  # Missing value
                "award_amount": [100000, 200000, 2000000],  # One too high
                "award_date": ["2023-01-01", "2023-02-01", "2023-03-01"],
                "program": ["SBIR", "INVALID", "STTR"],  # Invalid program
            }
        )

        config = {
            "completeness": {"award_id": 0.95, "company_name": 0.95},
            "uniqueness": {"award_id": 1.0},
            "validity": {"award_amount_min": 0, "award_amount_max": 1000000},
        }

        report = validate_sbir_awards(df, config)
        assert report.passed is False
        assert report.overall_score < 0.8
        assert len(report.issues) > 0

    def test_empty_dataset(self):
        """Test validation of empty dataset."""
        df = pd.DataFrame()

        report = validate_sbir_awards(df)
        assert report.passed is False
        assert report.total_fields == 0
        assert report.overall_score == 1.0  # No fields to validate

    def test_default_config(self):
        """Test validation using default configuration."""
        df = pd.DataFrame(
            {
                "award_id": ["A001", "A002"],
                "company_name": ["Company A", "Company B"],
                "award_amount": [100000, 200000],
                "award_date": ["2023-01-01", "2023-02-01"],
                "program": ["SBIR", "SBIR"],
            }
        )

        # Should use configuration from get_config()
        report = validate_sbir_awards(df)
        assert isinstance(report, object)
        assert hasattr(report, "passed")
