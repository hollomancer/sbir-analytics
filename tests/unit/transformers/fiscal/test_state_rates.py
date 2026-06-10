"""Tests for state-level tax rates and state-aware fiscal estimation."""

import pandas as pd
import pytest

pytestmark = pytest.mark.fast

from sbir_etl.transformers.fiscal.state_rates import StateRateProvider, _STATE_RATES_2024
from sbir_etl.transformers.fiscal.taxes import FiscalTaxEstimator


class TestStateRateProvider:
    def test_all_50_states_plus_dc(self):
        provider = StateRateProvider()
        assert len(provider.states) == 51

    def test_no_income_tax_states(self):
        provider = StateRateProvider()
        no_income = provider.no_income_tax_states
        assert "TX" in no_income
        assert "FL" in no_income
        assert "WA" in no_income
        assert "AK" in no_income
        assert "NV" in no_income
        assert len(no_income) == 9

    def test_no_sales_tax_states(self):
        provider = StateRateProvider()
        no_sales = provider.no_sales_tax_states
        assert "OR" in no_sales
        assert "DE" in no_sales
        assert "MT" in no_sales
        assert "NH" in no_sales

    def test_california_rates(self):
        provider = StateRateProvider()
        ca = provider.get_rates("CA")
        assert ca is not None
        assert ca.income_rate == 0.133  # Highest in nation
        assert ca.has_income_tax is True
        assert ca.has_sales_tax is True

    def test_texas_no_income_tax(self):
        provider = StateRateProvider()
        tx = provider.get_rates("TX")
        assert tx is not None
        assert tx.income_rate == 0.0
        assert tx.has_income_tax is False
        assert tx.sales_rate > 0  # TX has sales tax

    def test_unknown_state_returns_none(self):
        provider = StateRateProvider()
        assert provider.get_rates("XX") is None

    def test_case_insensitive(self):
        provider = StateRateProvider()
        assert provider.get_rates("ca") is not None
        assert provider.get_rates("Ca") is not None

    def test_all_rates_in_plausible_range(self):
        for state, rates in _STATE_RATES_2024.items():
            assert 0.0 <= rates.income_rate <= 0.15, f"{state} income"
            assert 0.0 <= rates.sales_rate <= 0.12, f"{state} sales"
            assert 0.0 <= rates.property_rate <= 0.30, f"{state} property"


class TestStateAwareEstimation:
    def test_texas_vs_california(self):
        """TX (no income tax) should produce less state tax than CA (13.3%)."""
        estimator = FiscalTaxEstimator()

        df = pd.DataFrame([
            {"state": "CA", "bea_sector": "54", "fiscal_year": 2022,
             "wage_impact": 500_000, "proprietor_income_impact": 100_000,
             "gross_operating_surplus": 50_000, "consumption_impact": 100_000},
            {"state": "TX", "bea_sector": "54", "fiscal_year": 2022,
             "wage_impact": 500_000, "proprietor_income_impact": 100_000,
             "gross_operating_surplus": 50_000, "consumption_impact": 100_000},
        ])

        result = estimator.estimate_taxes_from_components(df)

        ca_sl = result[result["state"] == "CA"]["state_local_tax_total"].iloc[0]
        tx_sl = result[result["state"] == "TX"]["state_local_tax_total"].iloc[0]

        # CA should have much higher state/local taxes than TX
        assert ca_sl > tx_sl * 2, f"CA=${ca_sl:,.0f} should be >> TX=${tx_sl:,.0f}"

        # TX state income tax should be zero
        tx_income = result[result["state"] == "TX"]["state_local_income_tax"].iloc[0]
        assert tx_income == 0.0

        # Federal taxes should be identical (same income)
        ca_fed = result[result["state"] == "CA"]["federal_tax_total"].iloc[0]
        tx_fed = result[result["state"] == "TX"]["federal_tax_total"].iloc[0]
        assert ca_fed == tx_fed

    def test_state_rate_source_column(self):
        """When state is present, rate source should be 'state_specific'."""
        estimator = FiscalTaxEstimator()
        df = pd.DataFrame([{
            "state": "NY", "wage_impact": 100_000, "proprietor_income_impact": 0,
            "gross_operating_surplus": 0, "consumption_impact": 50_000,
        }])
        result = estimator.estimate_taxes_from_components(df)
        assert result["state_rate_source"].iloc[0] == "state_specific"

    def test_unknown_state_falls_back_to_nipa(self):
        """Unknown state should fall back to NIPA national average."""
        estimator = FiscalTaxEstimator()
        df = pd.DataFrame([{
            "state": "XX", "wage_impact": 100_000, "proprietor_income_impact": 0,
            "gross_operating_surplus": 0, "consumption_impact": 50_000,
        }])
        result = estimator.estimate_taxes_from_components(df)
        assert result["state_rate_source"].iloc[0] == "nipa_national"

    def test_no_state_column_uses_nipa(self):
        """Without state column, should use NIPA national averages."""
        estimator = FiscalTaxEstimator()
        df = pd.DataFrame([{
            "wage_impact": 100_000, "proprietor_income_impact": 0,
            "gross_operating_surplus": 0, "consumption_impact": 50_000,
        }])
        result = estimator.estimate_taxes_from_components(df)
        assert result["state_rate_source"].iloc[0] == "nipa_national"

    def test_oregon_no_sales_tax(self):
        """Oregon has no sales tax — sales tax should be zero."""
        estimator = FiscalTaxEstimator()
        df = pd.DataFrame([{
            "state": "OR", "wage_impact": 100_000, "proprietor_income_impact": 0,
            "gross_operating_surplus": 0, "consumption_impact": 100_000,
        }])
        result = estimator.estimate_taxes_from_components(df)
        assert result["state_local_sales_tax"].iloc[0] == 0.0
        # But Oregon has income tax
        assert result["state_local_income_tax"].iloc[0] > 0
