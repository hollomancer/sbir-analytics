"""Unit tests for fiscal tax estimator (v2 — NIPA-based rates)."""

from decimal import Decimal

import pandas as pd
import pytest

pytestmark = pytest.mark.fast

from sbir_etl.transformers.fiscal.nipa_rates import NIPARateProvider
from sbir_etl.transformers.fiscal.taxes import FiscalTaxEstimator, TaxEstimationStats


@pytest.fixture
def estimator():
    """Create a FiscalTaxEstimator using baseline NIPA rates."""
    return FiscalTaxEstimator()


class TestFiscalTaxEstimator:
    """Test FiscalTaxEstimator with NIPA rates."""

    def test_estimate_taxes_from_components(self, estimator, sample_components_df):
        """Test tax estimation produces all expected columns."""
        result_df = estimator.estimate_taxes_from_components(sample_components_df)

        assert len(result_df) == 2

        # Federal columns
        assert "individual_income_tax" in result_df.columns
        assert "payroll_tax" in result_df.columns
        assert "corporate_income_tax" in result_df.columns
        assert "excise_tax" in result_df.columns
        assert "federal_tax_total" in result_df.columns

        # State/local columns (new in v2)
        assert "state_local_income_tax" in result_df.columns
        assert "state_local_sales_tax" in result_df.columns
        assert "state_local_property_tax" in result_df.columns
        assert "state_local_other_tax" in result_df.columns
        assert "state_local_tax_total" in result_df.columns

        # Totals
        assert "total_tax_receipt" in result_df.columns
        assert "tax_impact" in result_df.columns  # backward compat alias

        # Metadata
        assert "rate_source" in result_df.columns
        assert "nipa_baseline" in result_df["rate_source"].iloc[0]

        # All taxes positive
        assert all(result_df["total_tax_receipt"] > 0)

    def test_federal_total_equals_sum(self, estimator, sample_components_df):
        """Federal total should equal sum of federal components."""
        result_df = estimator.estimate_taxes_from_components(sample_components_df)

        for _, row in result_df.iterrows():
            expected = (
                row["individual_income_tax"]
                + row["payroll_tax"]
                + row["corporate_income_tax"]
                + row["excise_tax"]
            )
            assert abs(expected - row["federal_tax_total"]) < 0.01

    def test_total_equals_federal_plus_state_local(self, estimator, sample_components_df):
        """Total tax should equal federal + state/local."""
        result_df = estimator.estimate_taxes_from_components(sample_components_df)

        for _, row in result_df.iterrows():
            expected = row["federal_tax_total"] + row["state_local_tax_total"]
            assert abs(expected - row["total_tax_receipt"]) < 0.01

    def test_tax_impact_backward_compat(self, estimator, sample_components_df):
        """tax_impact column should equal total_tax_receipt."""
        result_df = estimator.estimate_taxes_from_components(sample_components_df)
        assert all(result_df["tax_impact"] == result_df["total_tax_receipt"])

    def test_empty_dataframe(self, estimator):
        """Empty input should return empty output."""
        result_df = estimator.estimate_taxes_from_components(pd.DataFrame())
        assert len(result_df) == 0

    def test_missing_component_columns(self, estimator):
        """Missing component columns should default to 0."""
        df = pd.DataFrame([{"state": "CA", "wage_impact": 100000}])
        result_df = estimator.estimate_taxes_from_components(df)
        assert len(result_df) == 1
        assert result_df["individual_income_tax"].iloc[0] > 0
        assert result_df["corporate_income_tax"].iloc[0] == 0.0

    def test_year_from_fiscal_year_column(self, estimator, sample_components_df):
        """Rate year should be derived from fiscal_year column."""
        result_df = estimator.estimate_taxes_from_components(sample_components_df)
        # sample_components_df has fiscal_year=2023, nearest baseline is 2022
        assert result_df["rate_year"].iloc[0] == 2023

    def test_explicit_year_override(self, estimator, sample_components_df):
        """Explicit year parameter should override fiscal_year column."""
        result_df = estimator.estimate_taxes_from_components(sample_components_df, year=2020)
        assert result_df["rate_year"].iloc[0] == 2020

    def test_reasonable_effective_rate_on_1m(self, estimator):
        """$1M economic activity should produce $200-500K total taxes."""
        df = pd.DataFrame([{
            "state": "CA",
            "bea_sector": "54",
            "fiscal_year": 2022,
            "wage_impact": 600_000.0,
            "proprietor_income_impact": 150_000.0,
            "gross_operating_surplus": 100_000.0,
            "consumption_impact": 150_000.0,
        }])
        result_df = estimator.estimate_taxes_from_components(df)
        total = result_df["total_tax_receipt"].iloc[0]
        assert 200_000 < total < 500_000, f"Total tax on $1M = ${total:,.0f}"


class TestTaxEstimationStats:
    def test_get_statistics(self, estimator, sample_components_df):
        """Stats should aggregate correctly."""
        tax_df = estimator.estimate_taxes_from_components(sample_components_df)
        stats = estimator.get_estimation_statistics(tax_df)

        assert isinstance(stats, TaxEstimationStats)
        assert stats.total_tax_receipts > 0
        assert stats.total_state_local_tax > 0
        assert stats.num_estimates == 2
        assert stats.avg_effective_rate > 0

    def test_empty_statistics(self, estimator):
        """Stats on empty df should return zeros."""
        stats = estimator.get_estimation_statistics(pd.DataFrame())
        assert stats.total_tax_receipts == Decimal("0")
        assert stats.num_estimates == 0


class TestCustomRateProvider:
    def test_uses_injected_provider(self):
        """Estimator should use injected NIPARateProvider."""
        provider = NIPARateProvider()
        estimator = FiscalTaxEstimator(rate_provider=provider)
        assert estimator.rate_provider is provider
