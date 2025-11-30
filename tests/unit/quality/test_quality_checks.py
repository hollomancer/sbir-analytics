"""Unit tests for quality checks module.

Tests cover:
- Completeness validation with thresholds
- Uniqueness checks with case sensitivity
- Value range validation
- SBIR awards comprehensive validation
"""

from unittest.mock import Mock, patch

import pandas as pd
import pytest


pytestmark = pytest.mark.fast

from src.models import QualitySeverity
from src.quality.checks import (
    check_completeness,
    check_uniqueness,
    check_value_ranges,
    validate_sbir_awards,
)


pytestmark = pytest.mark.fast


@pytest.fixture
def sample_dataframe():
    """Create a sample DataFrame for testing."""
    return pd.DataFrame(
        {
            "award_id": ["A001", "A002", "A003", "A004"],
            "company_name": ["Company A", "Company B", None, "Company D"],
            "award_amount": [100000, 150000, 200000, 250000],
            "year": [2020, 2021, 2022, 2023],
        }
    )


@pytest.fixture
def empty_dataframe():
    """Create an empty DataFrame."""
    return pd.DataFrame()


@pytest.fixture
def dataframe_with_duplicates():
    """Create a DataFrame with duplicate values."""
    return pd.DataFrame(
        {
            "award_id": ["A001", "A002", "A001", "A003"],
            "company_name": ["Company A", "Company B", "Company A", "Company C"],
        }
    )


class TestCheckCompleteness:
    """Tests for completeness validation."""

    def test_all_fields_complete(self, sample_dataframe):
        """Test when all required fields are complete."""
        issues = check_completeness(sample_dataframe, ["award_id", "award_amount"], threshold=0.95)

        assert len(issues) == 0

    def test_field_below_threshold(self, sample_dataframe):
        """Test when a field is below completeness threshold."""
        # company_name has 1 null out of 4 = 75% complete
        issues = check_completeness(sample_dataframe, ["company_name"], threshold=0.95)

        assert len(issues) == 1
        assert issues[0].field == "company_name"
        assert issues[0].severity == QualitySeverity.MEDIUM
        assert "75.0%" in issues[0].message
        assert issues[0].rule == "completeness_check"

    def test_missing_field(self, sample_dataframe):
        """Test when required field doesn't exist."""
        issues = check_completeness(sample_dataframe, ["missing_field"], threshold=0.95)

        assert len(issues) == 1
        assert issues[0].field == "missing_field"
        assert issues[0].severity == QualitySeverity.CRITICAL
        assert "missing from dataset" in issues[0].message

    def test_custom_threshold(self, sample_dataframe):
        """Test with custom completeness threshold."""
        # company_name 75% complete should pass 70% threshold
        issues = check_completeness(sample_dataframe, ["company_name"], threshold=0.70)

        assert len(issues) == 0

    def test_empty_dataframe(self, empty_dataframe):
        """Test completeness check on empty DataFrame."""
        issues = check_completeness(empty_dataframe, ["award_id"], threshold=0.95)

        # Empty df has completeness_ratio of 0, should fail
        assert len(issues) == 1
        assert issues[0].severity == QualitySeverity.CRITICAL

    def test_multiple_fields(self, sample_dataframe):
        """Test completeness check on multiple fields."""
        issues = check_completeness(
            sample_dataframe, ["award_id", "company_name", "award_amount"], threshold=0.95
        )

        # Only company_name should fail
        assert len(issues) == 1
        assert issues[0].field == "company_name"


class TestCheckUniqueness:
    """Tests for uniqueness validation."""

    def test_unique_values(self, sample_dataframe):
        """Test when all values are unique."""
        issues = check_uniqueness(sample_dataframe, ["award_id"])

        assert len(issues) == 0

    def test_duplicate_values(self, dataframe_with_duplicates):
        """Test when duplicates are present."""
        issues = check_uniqueness(dataframe_with_duplicates, ["award_id"])

        assert len(issues) == 1
        assert issues[0].severity == QualitySeverity.MEDIUM
        assert "duplicates" in issues[0].value
        assert issues[0].rule == "uniqueness_check"

    def test_case_sensitive_uniqueness(self):
        """Test case-sensitive uniqueness check."""
        df = pd.DataFrame(
            {
                "name": ["John", "john", "Jane"],
            }
        )

        # Case-sensitive: "John" and "john" are different
        issues = check_uniqueness(df, ["name"], case_sensitive=True)
        assert len(issues) == 0

    def test_case_insensitive_uniqueness(self):
        """Test case-insensitive uniqueness check."""
        df = pd.DataFrame(
            {
                "name": ["John", "john", "Jane"],
            }
        )

        # Case-insensitive: "John" and "john" are duplicates
        issues = check_uniqueness(df, ["name"], case_sensitive=False)
        assert len(issues) == 1
        assert "duplicates" in issues[0].message

    def test_missing_fields(self, sample_dataframe):
        """Test when required fields are missing."""
        issues = check_uniqueness(sample_dataframe, ["missing_field"])

        assert len(issues) == 1
        assert issues[0].severity == QualitySeverity.CRITICAL
        assert "missing" in issues[0].message.lower()

    def test_composite_key_uniqueness(self, sample_dataframe):
        """Test uniqueness on multiple fields."""
        issues = check_uniqueness(sample_dataframe, ["award_id", "company_name"])

        assert len(issues) == 0


class TestCheckValueRanges:
    """Tests for value range validation."""

    @pytest.mark.parametrize(
        "values,min_val,max_val,expected_issues",
        [
            ([100000, 150000, 200000], 50000, 300000, 0),  # all in range
            ([10, 20, 30, 100], 50, None, 1),  # below minimum
            ([100, 200, 300, 400], None, 250, 1),  # above maximum
            ([50, 100, 150], 50, 150, 0),  # boundary values
        ],
        ids=["in_range", "below_min", "above_max", "boundary"],
    )
    def test_numeric_range_validation(self, values, min_val, max_val, expected_issues):
        """Test numeric range validation with various scenarios."""
        from tests.assertions import assert_quality_issues_count

        df = pd.DataFrame({"amount": values})
        issues = check_value_ranges(df, "amount", min_value=min_val, max_value=max_val)
        assert_quality_issues_count(issues, expected_issues)

    def test_allowed_values_validation(self):
        """Test validation against allowed values list."""
        from tests.assertions import assert_quality_issues_count

        df = pd.DataFrame({"status": ["active", "pending", "invalid", "active"]})
        issues = check_value_ranges(df, "status", allowed_values=["active", "pending", "completed"])

        assert_quality_issues_count(issues, 1)
        assert issues[0].severity == QualitySeverity.HIGH
        assert "not in allowed list" in issues[0].message

    def test_missing_field(self, sample_dataframe):
        """Test when field doesn't exist."""
        from tests.assertions import assert_quality_issues_count

        issues = check_value_ranges(sample_dataframe, "missing_field", min_value=0)
        assert_quality_issues_count(issues, 1)
        assert issues[0].severity == QualitySeverity.CRITICAL

    def test_non_numeric_field_with_range(self):
        """Test numeric range check on non-numeric field."""
        df = pd.DataFrame({"name": ["Alice", "Bob", "Charlie"]})
        issues = check_value_ranges(df, "name", min_value=0, max_value=100)

        assert len(issues) == 1
        assert issues[0].severity == QualitySeverity.LOW

    def test_allowed_values_with_nulls(self):
        """Test allowed values validation ignores nulls."""
        from tests.assertions import assert_no_quality_issues

        df = pd.DataFrame({"status": ["active", None, "pending", "active"]})
        issues = check_value_ranges(df, "status", allowed_values=["active", "pending"])
        assert_no_quality_issues(issues)


class TestValidateSbirAwards:
    """Tests for comprehensive SBIR awards validation."""

    @patch("src.quality.checks.get_config")
    def test_valid_sbir_data(self, mock_config, sample_dataframe):
        """Test validation of valid SBIR data."""
        # Mock config
        mock_app_config = Mock()
        mock_app_config.data_quality.completeness = {"award_id": 0.95}
        mock_app_config.data_quality.uniqueness = []
        mock_app_config.data_quality.validity = {}
        mock_config.return_value = mock_app_config

        report = validate_sbir_awards(sample_dataframe)

        assert report.record_id == "sbir_awards_dataset"
        assert report.stage == "validation"
        assert report.passed is True
        assert report.total_fields >= 1

    @patch("src.quality.checks.get_config")
    def test_sbir_with_completeness_issues(self, mock_config, sample_dataframe):
        """Test validation with completeness issues."""
        mock_app_config = Mock()
        mock_app_config.data_quality.completeness = {"company_name": 0.95}
        mock_app_config.data_quality.uniqueness = []
        mock_app_config.data_quality.validity = {}
        mock_config.return_value = mock_app_config

        report = validate_sbir_awards(sample_dataframe)

        # company_name has 75% completeness (below 95% threshold)
        assert report.passed is False
        assert len(report.issues) == 1
        assert report.issues[0].field == "company_name"

    @patch("src.quality.checks.get_config")
    def test_sbir_with_uniqueness_issues(self, mock_config, dataframe_with_duplicates):
        """Test validation with uniqueness issues."""
        mock_app_config = Mock()
        mock_app_config.data_quality.completeness = {}
        mock_app_config.data_quality.uniqueness = ["award_id"]
        mock_app_config.data_quality.validity = {}
        mock_config.return_value = mock_app_config

        report = validate_sbir_awards(dataframe_with_duplicates)

        assert report.passed is False
        assert len(report.issues) == 1
        assert "duplicates" in report.issues[0].message.lower()

    @patch("src.quality.checks.get_config")
    def test_sbir_with_value_range_issues(self, mock_config):
        """Test validation with value range issues."""
        df = pd.DataFrame(
            {
                "award_amount": [100, 200, 5000000, 400],  # One very high value
            }
        )

        mock_app_config = Mock()
        mock_app_config.data_quality.completeness = {}
        mock_app_config.data_quality.uniqueness = []
        mock_app_config.data_quality.validity = {
            "award_amount_min": 0,
            "award_amount_max": 1000000,
        }
        mock_config.return_value = mock_app_config

        report = validate_sbir_awards(df)

        assert report.passed is False
        assert len(report.issues) == 1
        assert "above maximum" in report.issues[0].message

    @patch("src.quality.checks.get_config")
    def test_empty_sbir_data(self, mock_config, empty_dataframe):
        """Test validation of empty DataFrame."""
        mock_app_config = Mock()
        mock_app_config.data_quality.completeness = {}
        mock_app_config.data_quality.uniqueness = []
        mock_app_config.data_quality.validity = {}
        mock_config.return_value = mock_app_config

        report = validate_sbir_awards(empty_dataframe)

        assert report.total_fields == 0
        assert report.passed is False
        assert report.completeness_score == 1.0
        assert report.validity_score == 1.0

    def test_sbir_with_custom_config(self, sample_dataframe):
        """Test validation with custom config dict."""
        config = {
            "completeness": {"award_id": 0.95},
            "uniqueness": [],
            "validity": {},
        }

        report = validate_sbir_awards(sample_dataframe, config=config)

        assert report.passed is True
        assert report.record_id == "sbir_awards_dataset"

    @patch("src.quality.checks.get_config")
    def test_sbir_score_calculation(self, mock_config, sample_dataframe):
        """Test that scores are calculated correctly."""
        mock_app_config = Mock()
        mock_app_config.data_quality.completeness = {"award_id": 0.95}
        mock_app_config.data_quality.uniqueness = ["award_id"]
        mock_app_config.data_quality.validity = {}
        mock_config.return_value = mock_app_config

        report = validate_sbir_awards(sample_dataframe)

        assert 0.0 <= report.completeness_score <= 1.0
        assert 0.0 <= report.validity_score <= 1.0
        assert 0.0 <= report.overall_score <= 1.0
        assert report.total_fields == report.valid_fields + report.invalid_fields
