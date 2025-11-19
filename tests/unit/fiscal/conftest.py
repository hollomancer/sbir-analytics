"""Shared fixtures for fiscal analysis tests."""

from decimal import Decimal

import pandas as pd
import pytest

from tests.utils.fixtures import create_sample_enriched_awards_df


@pytest.fixture
def sample_fiscal_awards_df():
    """Sample enriched awards DataFrame for fiscal analysis."""
    return create_sample_enriched_awards_df(num_awards=20)


@pytest.fixture
def sample_fiscal_impacts_df():
    """Sample fiscal impact data for testing."""
    return pd.DataFrame(
        [
            {
                "state": "CA",
                "bea_sector": "11",
                "fiscal_year": 2023,
                "wage_impact": Decimal("100000.00"),
                "consumption_impact": Decimal("50000.00"),
                "investment_impact": Decimal("25000.00"),
            },
            {
                "state": "TX",
                "bea_sector": "11",
                "fiscal_year": 2023,
                "wage_impact": Decimal("150000.00"),
                "consumption_impact": Decimal("75000.00"),
                "investment_impact": Decimal("35000.00"),
            },
        ]
    )


@pytest.fixture
def sample_tax_parameters():
    """Sample tax parameter configuration."""
    return {
        "payroll_tax_rate": 0.15,
        "income_tax_rate": 0.25,
        "excise_tax_rate": 0.05,
        "corporate_tax_rate": 0.21,
    }


@pytest.fixture
def sample_sbir_investment():
    """Sample SBIR investment amount."""
    return Decimal("1000000.00")


@pytest.fixture
def sample_discount_rate():
    """Sample discount rate for ROI calculations."""
    return Decimal("0.03")  # 3%


@pytest.fixture
def sample_fiscal_summary():
    """Sample fiscal return summary."""
    return {
        "total_tax_receipts": Decimal("250000.00"),
        "net_fiscal_return": Decimal("150000.00"),
        "roi_ratio": Decimal("0.25"),
        "payback_period_years": Decimal("4.0"),
    }

