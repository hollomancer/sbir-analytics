"""Tests for validation schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError


pytestmark = pytest.mark.fast

from src.validators.schemas import (
    CompletenessCheck,
    UniquenessCheck,
    ValidationConfig,
    ValidationResult,
    ValueRangeCheck,
)


pytestmark = pytest.mark.fast


class TestValidationResultModel:
    """Tests for ValidationResult model."""

    def test_valid_validation_result(self):
        """Test creating a valid ValidationResult."""
        result = ValidationResult(
            is_valid=True,
            field="award_amount",
            value=500000.0,
            expected="positive number",
            message="Award amount is valid",
            severity="low",
        )
        assert result.is_valid is True
        assert result.field == "award_amount"
        assert result.value == 500000.0
        assert result.expected == "positive number"
        assert result.message == "Award amount is valid"
        assert result.severity == "low"

    def test_validation_result_default_severity(self):
        """Test ValidationResult has default severity of 'medium'."""
        result = ValidationResult(
            is_valid=False,
            field="email",
            value="invalid-email",
            expected="valid email format",
            message="Email format is invalid",
        )
        assert result.severity == "medium"

    def test_validation_result_with_complex_value(self):
        """Test ValidationResult can store complex value types."""
        result = ValidationResult(
            is_valid=False,
            field="nested_data",
            value={"key": "value", "list": [1, 2, 3]},
            expected={"key": "expected_value"},
            message="Nested data does not match expected structure",
        )
        assert isinstance(result.value, dict)
        assert result.value["list"] == [1, 2, 3]

    def test_validation_result_with_none_values(self):
        """Test ValidationResult accepts None for value and expected."""
        result = ValidationResult(
            is_valid=False,
            field="optional_field",
            value=None,
            expected="some value",
            message="Field is missing",
        )
        assert result.value is None

    def test_validation_result_validate_assignment(self):
        """Test ValidationResult validates on assignment."""
        result = ValidationResult(
            is_valid=True,
            field="test",
            value="test_value",
            expected="test_expected",
            message="Test message",
        )
        # Should allow assignment
        result.is_valid = False
        assert result.is_valid is False


class TestCompletenessCheckModel:
    """Tests for CompletenessCheck model."""

    def test_valid_completeness_check(self):
        """Test creating a valid CompletenessCheck with all fields."""
        check = CompletenessCheck(
            required_fields=["award_id", "company_name", "award_amount"],
            threshold=0.95,
        )
        assert check.required_fields == ["award_id", "company_name", "award_amount"]
        assert check.threshold == 0.95

    def test_completeness_check_defaults(self):
        """Test CompletenessCheck default values."""
        check = CompletenessCheck()
        assert check.required_fields == []
        assert check.threshold == 0.95

    @pytest.mark.parametrize(
        "threshold,should_pass",
        [
            (0.0, True),
            (0.5, True),
            (1.0, True),
            (-0.1, False),
            (1.5, False),
        ],
        ids=["min_bound", "mid_range", "max_bound", "negative_invalid", "above_one_invalid"],
    )
    def test_threshold_validator(self, threshold, should_pass):
        """Test threshold validator accepts 0.0-1.0 range."""
        if should_pass:
            check = CompletenessCheck(threshold=threshold)
            assert check.threshold == threshold
        else:
            with pytest.raises(ValidationError):
                CompletenessCheck(threshold=threshold)

    @pytest.mark.parametrize(
        "fields",
        [[], ["award_id"], ["field1", "field2", "field3"]],
        ids=["empty", "single", "multiple"],
    )
    def test_completeness_check_required_fields(self, fields):
        """Test CompletenessCheck with various required_fields configurations."""
        check = CompletenessCheck(required_fields=fields)
        assert check.required_fields == fields


class TestUniquenessCheckModel:
    """Tests for UniquenessCheck model."""

    def test_valid_uniqueness_check(self):
        """Test creating a valid UniquenessCheck with all fields."""
        check = UniquenessCheck(
            fields=["award_id", "duns"],
            case_sensitive=True,
        )
        assert check.fields == ["award_id", "duns"]
        assert check.case_sensitive is True

    def test_uniqueness_check_defaults(self):
        """Test UniquenessCheck default values."""
        check = UniquenessCheck()
        assert check.fields == []
        assert check.case_sensitive is True

    @pytest.mark.parametrize(
        "case_sensitive",
        [True, False],
        ids=["case_sensitive", "case_insensitive"],
    )
    def test_uniqueness_check_case_sensitivity(self, case_sensitive):
        """Test UniquenessCheck with different case_sensitive settings."""
        check = UniquenessCheck(
            fields=["company_name"],
            case_sensitive=case_sensitive,
        )
        assert check.case_sensitive is case_sensitive

    @pytest.mark.parametrize(
        "fields",
        [[], ["award_id"], ["field1", "field2", "field3", "field4"]],
        ids=["empty", "single", "multiple"],
    )
    def test_uniqueness_check_fields(self, fields):
        """Test UniquenessCheck with various field configurations."""
        check = UniquenessCheck(fields=fields)
        assert check.fields == fields


class TestValueRangeCheckModel:
    """Tests for ValueRangeCheck model."""

    def test_valid_value_range_check_with_min_max(self):
        """Test creating a valid ValueRangeCheck with min and max."""
        check = ValueRangeCheck(
            field="award_amount",
            min_value=0.0,
            max_value=10000000.0,
        )
        assert check.field == "award_amount"
        assert check.min_value == 0.0
        assert check.max_value == 10000000.0
        assert check.allowed_values is None

    def test_value_range_check_with_allowed_values(self):
        """Test ValueRangeCheck with allowed_values."""
        check = ValueRangeCheck(
            field="phase",
            allowed_values=["Phase I", "Phase II", "Phase III"],
        )
        assert check.field == "phase"
        assert check.allowed_values == ["Phase I", "Phase II", "Phase III"]
        assert check.min_value is None
        assert check.max_value is None

    @pytest.mark.parametrize(
        "min_val,max_val",
        [
            (None, None),
            (1983.0, None),
            (None, 2026.0),
            (0.0, 10000000.0),
        ],
        ids=["neither", "min_only", "max_only", "both"],
    )
    def test_value_range_check_min_max_combinations(self, min_val, max_val):
        """Test ValueRangeCheck with various min/max combinations."""
        check = ValueRangeCheck(field="test_field", min_value=min_val, max_value=max_val)
        assert check.min_value == min_val
        assert check.max_value == max_val

    @pytest.mark.parametrize(
        "allowed,should_pass",
        [
            (["SBIR", "STTR"], True),
            (["only_value"], True),
            (["string", 123, 45.6, True], True),
            (None, True),
            ([], False),
        ],
        ids=["multiple", "single", "mixed_types", "none", "empty_invalid"],
    )
    def test_allowed_values_validator(self, allowed, should_pass):
        """Test allowed_values validator accepts non-empty lists or None."""
        if should_pass:
            check = ValueRangeCheck(field="test", allowed_values=allowed)
            assert check.allowed_values == allowed
        else:
            with pytest.raises(ValidationError) as exc_info:
                ValueRangeCheck(field="test", allowed_values=allowed)
            assert "allowed_values cannot be empty" in str(exc_info.value)


class TestValidationConfigModel:
    """Tests for ValidationConfig model."""

    def test_valid_validation_config(self):
        """Test creating a valid ValidationConfig."""
        config = ValidationConfig(
            completeness={"required_fields": 0.95, "recommended_fields": 0.80},
            uniqueness={"award_id": 1.0, "combination": 0.99},
            value_ranges={
                "award_amount": {"min": 0, "max": 10000000},
                "award_year": {"min": 1983, "max": 2026},
            },
        )
        assert config.completeness == {
            "required_fields": 0.95,
            "recommended_fields": 0.80,
        }
        assert config.uniqueness == {"award_id": 1.0, "combination": 0.99}
        assert config.value_ranges["award_amount"]["min"] == 0

    def test_validation_config_defaults(self):
        """Test ValidationConfig default values."""
        config = ValidationConfig()
        assert config.completeness == {}
        assert config.uniqueness == {}
        assert config.value_ranges == {}

    def test_validation_config_partial(self):
        """Test ValidationConfig with some fields set."""
        config = ValidationConfig(
            completeness={"all_fields": 0.90},
        )
        assert config.completeness == {"all_fields": 0.90}
        assert config.uniqueness == {}
        assert config.value_ranges == {}

    def test_validation_config_empty_dicts(self):
        """Test ValidationConfig with explicitly empty dicts."""
        config = ValidationConfig(
            completeness={},
            uniqueness={},
            value_ranges={},
        )
        assert config.completeness == {}
        assert config.uniqueness == {}
        assert config.value_ranges == {}

    def test_validation_config_complex_value_ranges(self):
        """Test ValidationConfig with complex value_ranges."""
        config = ValidationConfig(
            value_ranges={
                "phase": {"allowed": ["Phase I", "Phase II", "Phase III"]},
                "amount": {"min": 0, "max": 1000000, "unit": "USD"},
                "score": {"min": 0.0, "max": 1.0, "precision": 2},
            },
        )
        assert "phase" in config.value_ranges
        assert "amount" in config.value_ranges
        assert "score" in config.value_ranges
        assert config.value_ranges["phase"]["allowed"] == [
            "Phase I",
            "Phase II",
            "Phase III",
        ]

    def test_validation_config_nested_structure(self):
        """Test ValidationConfig with deeply nested structures."""
        config = ValidationConfig(
            value_ranges={
                "complex": {
                    "nested": {
                        "deep": {
                            "value": 123,
                        }
                    }
                }
            },
        )
        assert config.value_ranges["complex"]["nested"]["deep"]["value"] == 123

    def test_validation_config_validate_assignment(self):
        """Test ValidationConfig validates on assignment."""
        config = ValidationConfig()
        # Should allow assignment
        config.completeness = {"new_field": 0.85}
        assert config.completeness == {"new_field": 0.85}

    def test_validation_config_numeric_keys(self):
        """Test ValidationConfig with numeric string keys."""
        config = ValidationConfig(
            completeness={"1": 0.95, "2": 0.90},
        )
        assert config.completeness["1"] == 0.95
        assert config.completeness["2"] == 0.90


class TestSchemaIntegration:
    """Integration tests for schema models working together."""

    def test_create_full_validation_workflow(self):
        """Test creating a complete validation workflow with all schemas."""
        # Create validation result
        result = ValidationResult(
            is_valid=False,
            field="award_amount",
            value=-1000,
            expected="positive number",
            message="Award amount must be positive",
            severity="high",
        )

        # Create completeness check
        completeness = CompletenessCheck(
            required_fields=["award_id", "company_name", "award_amount"],
            threshold=0.95,
        )

        # Create uniqueness check
        uniqueness = UniquenessCheck(
            fields=["award_id"],
            case_sensitive=True,
        )

        # Create value range check
        value_range = ValueRangeCheck(
            field="award_amount",
            min_value=0.0,
            max_value=10000000.0,
        )

        # Create validation config
        config = ValidationConfig(
            completeness={"required": 0.95},
            uniqueness={"award_id": 1.0},
            value_ranges={
                "award_amount": {"min": 0, "max": 10000000},
            },
        )

        # Assert all schemas are created correctly
        assert result.is_valid is False
        assert completeness.threshold == 0.95
        assert uniqueness.case_sensitive is True
        assert value_range.min_value == 0.0
        assert config.completeness["required"] == 0.95

    def test_validation_result_for_completeness_check(self):
        """Test ValidationResult describing completeness check failure."""
        check = CompletenessCheck(
            required_fields=["field1", "field2", "field3"],
            threshold=0.90,
        )

        result = ValidationResult(
            is_valid=False,
            field="completeness",
            value=0.75,
            expected=check.threshold,
            message=f"Completeness {0.75} below threshold {check.threshold}",
            severity="high",
        )

        assert result.is_valid is False
        assert result.value == 0.75
        assert result.expected == 0.90

    def test_validation_result_for_uniqueness_check(self):
        """Test ValidationResult describing uniqueness check failure."""
        check = UniquenessCheck(
            fields=["award_id"],
            case_sensitive=True,
        )

        result = ValidationResult(
            is_valid=False,
            field="award_id",
            value="duplicate-id-123",
            expected="unique value",
            message=f"Field {check.fields[0]} has duplicate values",
            severity="critical",
        )

        assert result.is_valid is False
        assert "duplicate" in result.message.lower()

    def test_validation_result_for_value_range_check(self):
        """Test ValidationResult describing value range check failure."""
        check = ValueRangeCheck(
            field="award_year",
            min_value=1983,
            max_value=2026,
        )

        result = ValidationResult(
            is_valid=False,
            field=check.field,
            value=2030,
            expected=f"between {check.min_value} and {check.max_value}",
            message=f"Value 2030 exceeds maximum {check.max_value}",
            severity="medium",
        )

        assert result.is_valid is False
        assert result.value == 2030
        assert "exceeds maximum" in result.message
