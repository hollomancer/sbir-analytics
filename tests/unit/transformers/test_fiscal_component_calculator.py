"""Unit tests for fiscal component calculator."""

from decimal import Decimal

import pandas as pd
import pytest

from src.transformers.fiscal_component_calculator import (
    ComponentValidationResult,
    FiscalComponentCalculator,
)


@pytest.fixture
def sample_impacts_df():
    """Sample economic impacts DataFrame for testing."""
    return pd.DataFrame(
        [
            {
                "state": "CA",
                "bea_sector": "11",
                "fiscal_year": 2023,
                "shock_amount": Decimal("100000"),
                "wage_impact": Decimal("50000"),
                "proprietor_income_impact": Decimal("20000"),
                "gross_operating_surplus": Decimal("20000"),
                "consumption_impact": Decimal("10000"),
                "production_impact": Decimal("100000"),
            },
            {
                "state": "TX",
                "bea_sector": "21",
                "fiscal_year": 2023,
                "shock_amount": Decimal("200000"),
                "wage_impact": Decimal("100000"),
                "proprietor_income_impact": Decimal("40000"),
                "gross_operating_surplus": Decimal("40000"),
                "consumption_impact": Decimal("20000"),
                "production_impact": Decimal("200000"),
            },
        ]
    )


@pytest.fixture
def calculator():
    """Create a FiscalComponentCalculator instance."""
    return FiscalComponentCalculator()


class TestFiscalComponentCalculator:
    """Test FiscalComponentCalculator class."""

    def test_extract_components(self, calculator, sample_impacts_df):
        """Test component extraction from impacts DataFrame."""
        result_df = calculator.extract_components(sample_impacts_df)

        assert len(result_df) == 2
        assert "component_total" in result_df.columns
        assert "component_valid" in result_df.columns
        assert "component_quality_flags" in result_df.columns

        # Check component totals are calculated correctly
        assert result_df.iloc[0]["component_total"] == Decimal("100000")
        assert result_df.iloc[1]["component_total"] == Decimal("200000")

        # Check validation passed
        assert (
            result_df.iloc[0]["component_valid"] is True
        )  # Use == instead of is for boolean comparison
        assert result_df.iloc[1]["component_valid"] is True

    def test_extract_components_empty_df(self, calculator):
        """Test component extraction with empty DataFrame."""
        empty_df = pd.DataFrame()
        result_df = calculator.extract_components(empty_df)

        assert len(result_df) == 0

    def test_extract_components_missing_columns(self, calculator):
        """Test component extraction with missing component columns."""
        impacts_df = pd.DataFrame(
            [
                {
                    "state": "CA",
                    "bea_sector": "11",
                    "fiscal_year": 2023,
                    "shock_amount": Decimal("100000"),
                }
            ]
        )

        result_df = calculator.extract_components(impacts_df)

        assert len(result_df) == 1
        assert result_df.iloc[0]["component_total"] == Decimal("0")

    def test_validate_aggregate_components(self, calculator, sample_impacts_df):
        """Test aggregate component validation."""
        components_df = calculator.extract_components(sample_impacts_df)
        validation_result = calculator.validate_aggregate_components(components_df)

        assert isinstance(validation_result, ComponentValidationResult)
        assert validation_result.is_valid is True
        assert validation_result.total_computed == Decimal("300000")
        assert validation_result.total_expected == Decimal("300000")
        assert len(validation_result.component_breakdown) == 4

    def test_validate_aggregate_components_empty(self, calculator):
        """Test aggregate validation with empty DataFrame."""
        empty_df = pd.DataFrame()
        validation_result = calculator.validate_aggregate_components(empty_df)

        assert validation_result.is_valid is False
        assert "empty_dataframe" in validation_result.quality_flags

    def test_component_vs_production_mismatch(self, calculator):
        """Test component validation detects production mismatch."""
        impacts_df = pd.DataFrame(
            [
                {
                    "state": "CA",
                    "bea_sector": "11",
                    "fiscal_year": 2023,
                    "wage_impact": Decimal("50000"),
                    "proprietor_income_impact": Decimal("20000"),
                    "gross_operating_surplus": Decimal("20000"),
                    "consumption_impact": Decimal("10000"),
                    "production_impact": Decimal(
                        "30000"
                    ),  # Much lower than components (100k vs 30k = 233% difference)
                }
            ]
        )

        result_df = calculator.extract_components(impacts_df)
        # Component should be invalid due to large mismatch (>50% difference)
        assert result_df.iloc[0]["component_valid"] is False  # Use == for boolean comparison

    def test_negative_components(self, calculator):
        """Test validation rejects negative components."""
        impacts_df = pd.DataFrame(
            [
                {
                    "state": "CA",
                    "bea_sector": "11",
                    "fiscal_year": 2023,
                    "wage_impact": Decimal("-10000"),  # Negative
                    "proprietor_income_impact": Decimal("20000"),
                    "gross_operating_surplus": Decimal("20000"),
                    "consumption_impact": Decimal("10000"),
                }
            ]
        )

        result_df = calculator.extract_components(impacts_df)
        assert result_df.iloc[0]["component_valid"] is False  # Use == for boolean comparison
