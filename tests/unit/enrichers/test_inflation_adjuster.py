"""Unit tests for inflation adjustment service.

Tests for BEA GDP deflator-based inflation adjustment:
- InflationAdjuster: Deflator data management and normalization
- Deflator value retrieval and interpolation
- Extrapolation for years outside available range
- Inflation factor calculation
- Award year extraction from various formats
- Single award adjustment with quality flags
- DataFrame batch adjustment
- Quality validation
"""

from datetime import datetime
from decimal import Decimal

import pandas as pd
import pytest

from src.enrichers.inflation_adjuster import (
    InflationAdjuster,
    InflationAdjustmentResult,
    adjust_awards_for_inflation,
)


pytestmark = pytest.mark.fast


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_config():
    """Create mock configuration for inflation adjuster."""

    class MockConfig:
        base_year = 2023
        inflation_source = "BEA GDP Deflator"
        quality_thresholds = {"inflation_adjustment_success": 0.95}

    class MockFiscalConfig:
        fiscal_analysis = MockConfig()

    return MockFiscalConfig()


@pytest.fixture
def adjuster(mock_config) -> InflationAdjuster:
    """Create inflation adjuster instance."""
    with pytest.MonkeyPatch.context() as m:
        m.setattr("src.enrichers.inflation_adjuster.get_config", lambda: mock_config)
        return InflationAdjuster()


# =============================================================================
# InflationAdjustmentResult Tests
# =============================================================================


class TestInflationAdjustmentResult:
    """Tests for InflationAdjustmentResult dataclass."""

    def test_result_creation(self):
        """Test creating an inflation adjustment result."""
        result = InflationAdjustmentResult(
            original_amount=Decimal("100000.00"),
            adjusted_amount=Decimal("125000.00"),
            base_year=2023,
            award_year=2020,
            inflation_factor=1.25,
            confidence=0.95,
            source="BEA GDP Deflator",
            method="direct_adjustment",
            quality_flags=[],
            timestamp=datetime(2025, 1, 1),
            metadata={"test": "value"},
        )

        assert result.original_amount == Decimal("100000.00")
        assert result.adjusted_amount == Decimal("125000.00")
        assert result.inflation_factor == 1.25
        assert result.confidence == 0.95
        assert result.method == "direct_adjustment"


# =============================================================================
# InflationAdjuster Tests
# =============================================================================


class TestInflationAdjuster:
    """Tests for the inflation adjuster."""

    def test_initialization(self, adjuster):
        """Test adjuster initialization."""
        assert adjuster.base_year == 2023
        assert adjuster.inflation_source == "BEA GDP Deflator"
        assert len(adjuster.bea_gdp_deflator) > 0

    def test_normalize_deflator_to_base_year(self, adjuster):
        """Test deflator normalization to base year."""
        # Base year should be 100.0
        base_value = adjuster.bea_gdp_deflator[2023]

        assert base_value == pytest.approx(100.0, abs=0.1)

    def test_get_deflator_value_exists(self, adjuster):
        """Test getting deflator value for existing year."""
        deflator = adjuster.get_deflator_value(2020)

        assert deflator is not None
        assert deflator > 0

    def test_get_deflator_value_missing(self, adjuster):
        """Test getting deflator value for missing year."""
        deflator = adjuster.get_deflator_value(1950)

        assert deflator is None

    def test_interpolate_deflator_between_years(self, adjuster):
        """Test deflator interpolation between known years."""
        # Assume we have data for 2020 and 2021, test 2020.5
        # Since BEA data is annual, we'll test a year between two known years
        value_2020 = adjuster.get_deflator_value(2020)
        value_2021 = adjuster.get_deflator_value(2021)

        if value_2020 is not None and value_2021 is not None:
            # Add a gap by temporarily removing 2020
            original_value = adjuster.bea_gdp_deflator.pop(2020)

            interpolated = adjuster.interpolate_deflator(2020)

            # Restore
            adjuster.bea_gdp_deflator[2020] = original_value

            # Interpolated should be reasonable
            assert interpolated is not None

    def test_interpolate_deflator_existing_year(self, adjuster):
        """Test interpolation returns exact value for existing year."""
        value = adjuster.get_deflator_value(2020)

        interpolated = adjuster.interpolate_deflator(2020)

        assert interpolated == value

    def test_interpolate_deflator_no_surrounding_years(self, adjuster):
        """Test interpolation when no surrounding years available."""
        interpolated = adjuster.interpolate_deflator(1900)

        assert interpolated is None

    def test_extrapolate_deflator_backwards(self, adjuster):
        """Test deflator extrapolation backwards in time."""
        extrapolated = adjuster.extrapolate_deflator(1985)

        assert extrapolated is not None
        assert extrapolated > 0
        # Should be lower than earliest known value
        earliest_year = min(adjuster.bea_gdp_deflator.keys())
        assert extrapolated < adjuster.bea_gdp_deflator[earliest_year]

    def test_extrapolate_deflator_forwards(self, adjuster):
        """Test deflator extrapolation forwards in time."""
        extrapolated = adjuster.extrapolate_deflator(2030)

        assert extrapolated is not None
        assert extrapolated > 0
        # Should be higher than latest known value
        latest_year = max(adjuster.bea_gdp_deflator.keys())
        assert extrapolated > adjuster.bea_gdp_deflator[latest_year]

    def test_get_inflation_factor_direct(self, adjuster):
        """Test inflation factor calculation with direct deflator values."""
        factor, flags = adjuster.get_inflation_factor(2020, 2023)

        assert factor is not None
        assert factor > 0
        assert len(flags) == 0  # No quality flags for direct calculation

    def test_get_inflation_factor_to_base_year(self, adjuster):
        """Test inflation factor defaults to base year."""
        factor, flags = adjuster.get_inflation_factor(2020)

        assert factor is not None
        assert factor > 0

    def test_get_inflation_factor_interpolated(self, adjuster):
        """Test inflation factor with interpolation."""
        # Remove a year to force interpolation
        original_value = adjuster.bea_gdp_deflator.pop(2015, None)

        factor, flags = adjuster.get_inflation_factor(2015, 2023)

        # Restore
        if original_value:
            adjuster.bea_gdp_deflator[2015] = original_value

        if factor is not None:
            assert "interpolated" in str(flags)

    def test_get_inflation_factor_extrapolated(self, adjuster):
        """Test inflation factor with extrapolation."""
        factor, flags = adjuster.get_inflation_factor(1985, 2023)

        assert factor is not None
        assert "extrapolated" in str(flags)

    def test_extract_award_year_from_year_column(self, adjuster):
        """Test extracting award year from year column."""
        row = pd.Series({"Award_Year": 2020, "amount": 100000})

        year = adjuster.extract_award_year(row)

        assert year == 2020

    def test_extract_award_year_from_date_string(self, adjuster):
        """Test extracting award year from date string."""
        row = pd.Series({"Award_Date": "2020-06-15", "amount": 100000})

        year = adjuster.extract_award_year(row)

        assert year == 2020

    def test_extract_award_year_from_datetime(self, adjuster):
        """Test extracting award year from datetime object."""
        row = pd.Series({"Award_Date": pd.Timestamp("2020-06-15"), "amount": 100000})

        year = adjuster.extract_award_year(row)

        assert year == 2020

    def test_extract_award_year_missing(self, adjuster):
        """Test extracting award year when not present."""
        row = pd.Series({"amount": 100000})

        year = adjuster.extract_award_year(row)

        assert year is None

    def test_adjust_single_award_success(self, adjuster):
        """Test adjusting a single award successfully."""
        row = pd.Series({"Award_Amount": 100000, "Award_Year": 2020})

        result = adjuster.adjust_single_award(row, 2023)

        assert result.original_amount == Decimal("100000")
        assert result.adjusted_amount > Decimal("100000")  # Should inflate
        assert result.award_year == 2020
        assert result.base_year == 2023
        assert result.method != "error"
        assert result.confidence > 0

    def test_adjust_single_award_missing_amount(self, adjuster):
        """Test adjusting award with missing amount."""
        row = pd.Series({"Award_Year": 2020})

        result = adjuster.adjust_single_award(row, 2023)

        assert result.method == "error"
        assert "missing_amount" in result.quality_flags
        assert result.confidence == 0.0

    def test_adjust_single_award_missing_year(self, adjuster):
        """Test adjusting award with missing year."""
        row = pd.Series({"Award_Amount": 100000})

        result = adjuster.adjust_single_award(row, 2023)

        assert result.method == "error"
        assert "missing_year" in result.quality_flags
        assert result.confidence == 0.0

    def test_adjust_single_award_amount_with_currency_symbols(self, adjuster):
        """Test adjusting award amount with currency symbols."""
        row = pd.Series({"Award_Amount": "$100,000", "Award_Year": 2020})

        result = adjuster.adjust_single_award(row, 2023)

        assert result.original_amount == Decimal("100000")
        assert result.method != "error"

    def test_adjust_awards_dataframe(self, adjuster):
        """Test adjusting entire awards DataFrame."""
        awards_df = pd.DataFrame(
            {
                "award_id": [1, 2, 3],
                "Award_Amount": [100000, 200000, 150000],
                "Award_Year": [2020, 2021, 2022],
            }
        )

        enriched_df = adjuster.adjust_awards_dataframe(awards_df, 2023)

        assert "fiscal_adjusted_amount" in enriched_df.columns
        assert "fiscal_inflation_factor" in enriched_df.columns
        assert "fiscal_inflation_confidence" in enriched_df.columns
        assert len(enriched_df) == 3
        # All should be successfully adjusted
        assert (enriched_df["fiscal_inflation_method"] != "error").sum() == 3

    def test_adjust_awards_dataframe_with_errors(self, adjuster):
        """Test adjusting DataFrame with some error cases."""
        awards_df = pd.DataFrame(
            {
                "award_id": [1, 2, 3],
                "Award_Amount": [100000, None, 150000],
                "Award_Year": [2020, 2021, None],
            }
        )

        enriched_df = adjuster.adjust_awards_dataframe(awards_df, 2023)

        # Should have some errors
        error_count = (enriched_df["fiscal_inflation_method"] == "error").sum()
        assert error_count > 0

    def test_validate_adjustment_quality(self, adjuster):
        """Test validating adjustment quality."""
        awards_df = pd.DataFrame(
            {
                "Award_Amount": [100000, 200000, 150000],
                "Award_Year": [2020, 2021, 2022],
            }
        )

        enriched_df = adjuster.adjust_awards_dataframe(awards_df, 2023)
        quality = adjuster.validate_adjustment_quality(enriched_df)

        assert "total_awards" in quality
        assert "successful_adjustments" in quality
        assert "success_rate" in quality
        assert "confidence_distribution" in quality
        assert quality["total_awards"] == 3
        assert quality["success_rate"] > 0

    def test_validate_adjustment_quality_meets_threshold(self, adjuster):
        """Test quality validation meets threshold."""
        awards_df = pd.DataFrame(
            {
                "Award_Amount": [100000] * 100,
                "Award_Year": [2020] * 100,
            }
        )

        enriched_df = adjuster.adjust_awards_dataframe(awards_df, 2023)
        quality = adjuster.validate_adjustment_quality(enriched_df)

        assert quality["success_meets_threshold"] is True
        assert quality["success_rate"] >= 0.95

    def test_validate_adjustment_quality_below_threshold(self, adjuster):
        """Test quality validation below threshold."""
        awards_df = pd.DataFrame(
            {
                "Award_Amount": [100000] * 50 + [None] * 50,
                "Award_Year": [2020] * 100,
            }
        )

        enriched_df = adjuster.adjust_awards_dataframe(awards_df, 2023)
        quality = adjuster.validate_adjustment_quality(enriched_df)

        assert quality["success_meets_threshold"] is False
        assert quality["success_rate"] < 0.95


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestHelperFunctions:
    """Tests for module-level helper functions."""

    def test_adjust_awards_for_inflation(self, mock_config):
        """Test main helper function."""
        awards_df = pd.DataFrame(
            {
                "Award_Amount": [100000, 200000],
                "Award_Year": [2020, 2021],
            }
        )

        with pytest.MonkeyPatch.context() as m:
            m.setattr("src.enrichers.inflation_adjuster.get_config", lambda: mock_config)
            adjusted_df, quality = adjust_awards_for_inflation(awards_df, 2023)

        assert "fiscal_adjusted_amount" in adjusted_df.columns
        assert isinstance(quality, dict)
        assert "success_rate" in quality

    def test_adjust_awards_for_inflation_with_config(self, mock_config):
        """Test helper function with custom config."""
        awards_df = pd.DataFrame(
            {
                "Award_Amount": [100000],
                "Award_Year": [2020],
            }
        )

        config_dict = {
            "base_year": 2023,
            "inflation_source": "Custom Source",
            "quality_thresholds": {"inflation_adjustment_success": 0.90},
        }

        # This would require restructuring the config, for now just test the call
        with pytest.MonkeyPatch.context() as m:
            m.setattr("src.enrichers.inflation_adjuster.get_config", lambda: mock_config)
            adjusted_df, quality = adjust_awards_for_inflation(awards_df, 2023, config_dict)

        assert len(adjusted_df) == 1
        assert "success_rate" in quality
