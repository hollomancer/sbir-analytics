"""Unit tests for fiscal tax estimator."""

from decimal import Decimal

import pandas as pd
import pytest


pytestmark = pytest.mark.fast

from src.transformers.fiscal.taxes import FiscalTaxEstimator, TaxEstimationStats


@pytest.fixture
def sample_components_df():
    """Sample components DataFrame for testing."""
    return pd.DataFrame(
        [
            {
                "state": "CA",
                "bea_sector": "11",
                "fiscal_year": 2023,
                "wage_impact": Decimal("100000"),
                "proprietor_income_impact": Decimal("50000"),
                "gross_operating_surplus": Decimal("30000"),
                "consumption_impact": Decimal("20000"),
            },
            {
                "state": "TX",
                "bea_sector": "21",
                "fiscal_year": 2023,
                "wage_impact": Decimal("200000"),
                "proprietor_income_impact": Decimal("100000"),
                "gross_operating_surplus": Decimal("60000"),
                "consumption_impact": Decimal("40000"),
            },
        ]
    )


@pytest.fixture
def estimator():
    """Create a FiscalTaxEstimator instance."""
    return FiscalTaxEstimator()


class TestFiscalTaxEstimator:
    """Test FiscalTaxEstimator class."""

    def test_estimate_individual_income_tax(self, estimator):
        """Test individual income tax estimation."""
        wage = Decimal("100000")
        proprietor = Decimal("50000")

        tax = estimator.estimate_individual_income_tax(wage, proprietor)

        assert tax >= Decimal("0")
        assert tax < (wage + proprietor)  # Tax should be less than income

    def test_estimate_individual_income_tax_zero(self, estimator):
        """Test individual income tax with zero income."""
        tax = estimator.estimate_individual_income_tax(Decimal("0"), Decimal("0"))
        assert tax == Decimal("0")

    def test_estimate_payroll_tax(self, estimator):
        """Test payroll tax estimation."""
        wage = Decimal("100000")
        tax = estimator.estimate_payroll_tax(wage)

        assert tax >= Decimal("0")
        # Payroll tax should be around 15% (SS + Medicare, both sides)
        assert tax > Decimal("10000")  # At least 10%
        assert tax < Decimal("20000")  # Less than 20%

    def test_estimate_payroll_tax_zero(self, estimator):
        """Test payroll tax with zero wages."""
        tax = estimator.estimate_payroll_tax(Decimal("0"))
        assert tax == Decimal("0")

    def test_estimate_corporate_income_tax(self, estimator):
        """Test corporate income tax estimation."""
        gos = Decimal("100000")
        tax = estimator.estimate_corporate_income_tax(gos)

        assert tax >= Decimal("0")
        # Effective rate is ~18%
        assert tax > Decimal("15000")
        assert tax < Decimal("21000")

    def test_estimate_corporate_income_tax_zero(self, estimator):
        """Test corporate income tax with zero GOS."""
        tax = estimator.estimate_corporate_income_tax(Decimal("0"))
        assert tax == Decimal("0")

    def test_estimate_excise_tax(self, estimator):
        """Test excise tax estimation."""
        consumption = Decimal("100000")
        tax = estimator.estimate_excise_tax(consumption)

        assert tax >= Decimal("0")
        # General rate is 3%
        assert tax == Decimal("3000")

    def test_estimate_excise_tax_zero(self, estimator):
        """Test excise tax with zero consumption."""
        tax = estimator.estimate_excise_tax(Decimal("0"))
        assert tax == Decimal("0")

    def test_estimate_taxes_from_components(self, estimator, sample_components_df):
        """Test tax estimation from components DataFrame."""
        result_df = estimator.estimate_taxes_from_components(sample_components_df)

        assert len(result_df) == 2
        assert "individual_income_tax" in result_df.columns
        assert "payroll_tax" in result_df.columns
        assert "corporate_income_tax" in result_df.columns
        assert "excise_tax" in result_df.columns
        assert "total_tax_receipt" in result_df.columns

        # Check taxes are positive
        assert all(result_df["total_tax_receipt"] > 0)

        # Check total equals sum of components
        for _idx, row in result_df.iterrows():
            computed_total = (
                row["individual_income_tax"]
                + row["payroll_tax"]
                + row["corporate_income_tax"]
                + row["excise_tax"]
            )
            assert abs(computed_total - row["total_tax_receipt"]) < Decimal("0.01")

    def test_estimate_taxes_from_components_empty(self, estimator):
        """Test tax estimation with empty DataFrame."""
        empty_df = pd.DataFrame()
        result_df = estimator.estimate_taxes_from_components(empty_df)

        assert len(result_df) == 0

    def test_get_estimation_statistics(self, estimator, sample_components_df):
        """Test tax estimation statistics."""
        tax_estimates_df = estimator.estimate_taxes_from_components(sample_components_df)
        stats = estimator.get_estimation_statistics(tax_estimates_df)

        assert isinstance(stats, TaxEstimationStats)
        assert stats.total_tax_receipts > 0
        assert stats.num_estimates == 2
        assert stats.avg_effective_rate > 0
