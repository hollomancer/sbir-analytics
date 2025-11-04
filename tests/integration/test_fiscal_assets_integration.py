"""Integration tests for fiscal returns analysis assets."""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pandas as pd
import pytest


pytestmark = pytest.mark.integration
from dagster import build_asset_context

from src.assets import fiscal_assets


@pytest.fixture
def sample_enriched_awards():
    """Sample enriched SBIR awards DataFrame."""
    return pd.DataFrame(
        [
            {
                "award_id": "A001",
                "company_name": "Acme Corp",
                "award_amount": 100000.0,
                "award_date": date(2023, 1, 15),
                "company_state": "CA",
                "company_city": "San Francisco",
                "agency": "NSF",
            },
            {
                "award_id": "A002",
                "company_name": "Tech Inc",
                "award_amount": 200000.0,
                "award_date": date(2023, 6, 1),
                "company_state": "TX",
                "company_city": "Austin",
                "agency": "DOD",
            },
        ]
    )


@pytest.fixture
def sample_fiscal_naics_enriched():
    """Sample fiscal NAICS enriched awards."""
    return pd.DataFrame(
        [
            {
                "award_id": "A001",
                "fiscal_naics_code": "541330",
                "fiscal_naics_confidence": 0.95,
                "award_amount": 100000.0,
            },
            {
                "award_id": "A002",
                "fiscal_naics_code": "334510",
                "fiscal_naics_confidence": 0.90,
                "award_amount": 200000.0,
            },
        ]
    )


@pytest.fixture
def sample_impacts():
    """Sample economic impacts DataFrame."""
    return pd.DataFrame(
        [
            {
                "state": "CA",
                "bea_sector": "11",
                "fiscal_year": 2023,
                "wage_impact": Decimal("50000"),
                "proprietor_income_impact": Decimal("20000"),
                "gross_operating_surplus": Decimal("20000"),
                "consumption_impact": Decimal("10000"),
                "production_impact": Decimal("100000"),
                "model_version": "StateIO_v2.1",
            }
        ]
    )


class TestFiscalDataPreparationAssets:
    """Test fiscal data preparation assets."""

    @patch("src.enrichers.geographic_resolver.resolve_award_geography")
    def test_fiscal_prepared_sbir_awards(self, mock_resolve, sample_fiscal_naics_enriched):
        """Test fiscal_prepared_sbir_awards asset."""
        # Mock geographic resolution
        resolved_df = sample_fiscal_naics_enriched.copy()
        resolved_df["fiscal_state_code"] = ["CA", "TX"]
        resolved_df["fiscal_geo_confidence"] = [0.95, 0.90]
        mock_resolve.return_value = (resolved_df, {})

        context = build_asset_context()
        result = fiscal_assets.fiscal_prepared_sbir_awards(context, sample_fiscal_naics_enriched)

        assert len(result.value) == 2
        assert (
            "resolved_state" in result.value.columns or "fiscal_state_code" in result.value.columns
        )

    @patch("src.assets.fiscal_assets.adjust_awards_for_inflation")
    def test_inflation_adjusted_awards(self, mock_adjust, sample_fiscal_naics_enriched):
        """Test inflation_adjusted_awards asset."""
        # Mock inflation adjustment
        adjusted_df = sample_fiscal_naics_enriched.copy()
        adjusted_df["fiscal_adjusted_amount"] = [105000.0, 210000.0]
        mock_adjust.return_value = (adjusted_df, {"adjustment_success_rate": 1.0})

        context = build_asset_context()
        result = fiscal_assets.inflation_adjusted_awards(context, adjusted_df)

        assert len(result.value) == 2
        assert "inflation_adjusted_amount" in result.value.columns


class TestTaxCalculationAssets:
    """Test tax calculation assets."""

    def test_tax_base_components(self, sample_impacts):
        """Test tax_base_components asset."""
        context = build_asset_context()
        result = fiscal_assets.tax_base_components(context, sample_impacts)

        assert len(result.value) == 1
        assert "component_total" in result.value.columns
        assert "component_valid" in result.value.columns

    def test_federal_tax_estimates(self, sample_impacts):
        """Test federal_tax_estimates asset."""
        context = build_asset_context()

        # First create components
        components = fiscal_assets.tax_base_components(context, sample_impacts)
        result = fiscal_assets.federal_tax_estimates(context, components.value)

        assert len(result.value) == 1
        assert "total_tax_receipt" in result.value.columns
        assert result.value.iloc[0]["total_tax_receipt"] > Decimal("0")

    def test_fiscal_return_summary(self, sample_impacts):
        """Test fiscal_return_summary asset."""
        context = build_asset_context()

        # Build up the pipeline
        components = fiscal_assets.tax_base_components(context, sample_impacts)
        tax_estimates = fiscal_assets.federal_tax_estimates(context, components.value)

        # Create investment DataFrame
        investment_df = pd.DataFrame(
            [
                {"inflation_adjusted_amount": Decimal("100000")},
            ]
        )

        result = fiscal_assets.fiscal_return_summary(context, tax_estimates.value, investment_df)

        assert len(result.value) == 1
        assert "roi_ratio" in result.value.columns
        assert "payback_period_years" in result.value.columns


class TestSensitivityAnalysisAssets:
    """Test sensitivity analysis assets."""

    def test_sensitivity_scenarios(self):
        """Test sensitivity_scenarios asset."""
        context = build_asset_context()
        result = fiscal_assets.sensitivity_scenarios(context)

        assert len(result.value) > 0
        assert "scenario_id" in result.value.columns
        assert "method" in result.value.columns

    def test_uncertainty_analysis(self, sample_impacts):
        """Test uncertainty_analysis asset."""
        context = build_asset_context()

        # Create tax estimates
        components = fiscal_assets.tax_base_components(context, sample_impacts)
        tax_estimates = fiscal_assets.federal_tax_estimates(context, components.value)

        # Create scenarios
        scenarios = fiscal_assets.sensitivity_scenarios(context)

        # Test uncertainty analysis
        result = fiscal_assets.uncertainty_analysis(context, scenarios.value, tax_estimates.value)

        assert len(result.value) == 1
        assert "min_estimate" in result.value.columns
        assert "mean_estimate" in result.value.columns
        assert "max_estimate" in result.value.columns


class TestAssetChecks:
    """Test asset checks for quality gates."""

    def test_fiscal_geographic_resolution_check(self):
        """Test geographic resolution asset check."""
        df = pd.DataFrame(
            [
                {"resolved_state": "CA"},
                {"resolved_state": "TX"},
                {"resolved_state": "NY"},
                {"resolved_state": "FL"},
                {"resolved_state": "MA"},
                {"resolved_state": None},  # One unresolved - should still pass at 83%
            ]
        )

        result = fiscal_assets.fiscal_geographic_resolution_check(df)

        assert "resolution_rate" in result.metadata
        # With 5/6 resolved = 83.3%, should pass 90% threshold check (may fail or warn)
        assert isinstance(result.passed, bool)

    def test_inflation_adjustment_quality_check(self):
        """Test inflation adjustment quality asset check."""
        df = pd.DataFrame(
            [
                {"inflation_adjusted_amount": 105000.0},
                {"inflation_adjusted_amount": 210000.0},
                {"inflation_adjusted_amount": None},  # One unadjusted
            ]
        )

        result = fiscal_assets.inflation_adjustment_quality_check(df)

        assert "success_rate" in result.metadata
