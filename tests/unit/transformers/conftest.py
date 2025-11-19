"""Shared fixtures for transformer tests."""

from decimal import Decimal

import numpy as np
import pandas as pd
import pytest


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
def sample_scenario_results_df():
    """Sample scenario results DataFrame for testing."""
    np.random.seed(42)
    return pd.DataFrame(
        {
            "scenario_id": range(1, 101),
            "individual_income_tax_rate": np.random.uniform(0.18, 0.26, 100),
            "corporate_income_tax_rate": np.random.uniform(0.15, 0.21, 100),
            "economic_multiplier": np.random.uniform(1.7, 2.3, 100),
            "discount_rate": np.random.uniform(0.01, 0.07, 100),
            "total_tax_receipt": np.random.uniform(100000, 200000, 100),
        }
    )

