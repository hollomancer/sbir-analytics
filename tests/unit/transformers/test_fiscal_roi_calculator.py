"""Unit tests for fiscal ROI calculator."""

from decimal import Decimal

import pandas as pd
import pytest

pytestmark = pytest.mark.fast

from src.transformers.fiscal_roi_calculator import FiscalROICalculator


@pytest.fixture
def sample_tax_estimates_df():
    """Sample tax estimates DataFrame for testing."""
    return pd.DataFrame(
        [
            {
                "state": "CA",
                "bea_sector": "11",
                "fiscal_year": 2023,
                "total_tax_receipt": Decimal("50000"),
                "naics_coverage_rate": 0.95,
                "geographic_resolution_rate": 0.90,
            },
            {
                "state": "TX",
                "bea_sector": "21",
                "fiscal_year": 2023,
                "total_tax_receipt": Decimal("75000"),
                "naics_coverage_rate": 0.92,
                "geographic_resolution_rate": 0.88,
            },
        ]
    )


@pytest.fixture
def calculator():
    """Create a FiscalROICalculator instance."""
    return FiscalROICalculator()


class TestFiscalROICalculator:
    """Test FiscalROICalculator class."""

    def test_calculate_npv(self, calculator):
        """Test NPV calculation."""
        cash_flows = [Decimal("-100000"), Decimal("30000"), Decimal("30000"), Decimal("30000")]
        discount_rate = 0.03
        start_year = 2023

        npv = calculator._calculate_npv(cash_flows, discount_rate, start_year)

        # NPV should be negative (investment > returns over 3 years)
        assert npv < Decimal("0")
        assert npv > Decimal("-50000")  # But not too negative

    def test_calculate_payback_period(self, calculator):
        """Test payback period calculation."""
        investment = Decimal("100000")
        annual_returns = Decimal("30000")

        payback = calculator._calculate_payback_period(investment, annual_returns)

        assert payback is not None
        assert payback > 3.0  # More than 3 years
        assert payback < 4.0  # Less than 4 years

    def test_calculate_payback_period_no_payback(self, calculator):
        """Test payback period when returns are too low."""
        investment = Decimal("100000")
        annual_returns = Decimal("100")  # Very low returns (will never payback)

        payback = calculator._calculate_payback_period(
            investment, annual_returns, discount_rate=0.0
        )

        assert payback is None or payback > 50  # Very long or None

    def test_calculate_roi_summary(self, calculator, sample_tax_estimates_df):
        """Test ROI summary calculation."""
        sbir_investment = Decimal("200000")

        summary = calculator.calculate_roi_summary(
            sample_tax_estimates_df,
            sbir_investment,
            discount_rate=0.03,
            time_horizon_years=10,
        )

        assert summary.total_sbir_investment == sbir_investment
        assert summary.total_tax_receipts == Decimal("125000")
        assert summary.roi_ratio > 0
        assert summary.roi_ratio < 1.0  # Less than 1:1 return
        assert summary.benefit_cost_ratio == summary.roi_ratio
        assert summary.quality_score >= 0.0
        assert summary.quality_score <= 1.0

    def test_calculate_roi_summary_positive_roi(self, calculator, sample_tax_estimates_df):
        """Test ROI summary with positive ROI."""
        # Lower investment to get positive ROI
        sbir_investment = Decimal("100000")

        summary = calculator.calculate_roi_summary(
            sample_tax_estimates_df,
            sbir_investment,
            discount_rate=0.03,
            time_horizon_years=10,
        )

        assert summary.roi_ratio > 1.0  # Greater than 1:1 return
        assert summary.net_fiscal_return > Decimal("0")

    def test_calculate_roi_from_components(self, calculator, sample_tax_estimates_df):
        """Test ROI calculation from components DataFrames."""
        investment_df = pd.DataFrame(
            [
                {"inflation_adjusted_amount": Decimal("100000")},
                {"inflation_adjusted_amount": Decimal("100000")},
            ]
        )

        summary = calculator.calculate_roi_from_components(
            sample_tax_estimates_df,
            investment_df,
            discount_rate=0.03,
            time_horizon_years=10,
        )

        assert summary.total_sbir_investment == Decimal("200000")
        assert summary.total_tax_receipts == Decimal("125000")

    def test_calculate_roi_breakdowns(self, calculator, sample_tax_estimates_df):
        """Test ROI summary includes breakdowns by state, sector, fiscal year."""
        sbir_investment = Decimal("200000")

        summary = calculator.calculate_roi_summary(
            sample_tax_estimates_df,
            sbir_investment,
        )

        assert len(summary.breakdown_by_state) > 0
        assert len(summary.breakdown_by_sector) > 0
        assert "CA" in summary.breakdown_by_state
        assert "TX" in summary.breakdown_by_state
