"""Tests for state-level tax rates and state-aware fiscal estimation."""

import pandas as pd
import pytest

pytestmark = pytest.mark.fast

from sbir_etl.transformers.fiscal.state_rates import (
    DEFAULT_CSV_PATH,
    StateRateProvider,
    StateTaxRates,
    _STATE_RATES_2024,
)
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

        df = pd.DataFrame(
            [
                {
                    "state": "CA",
                    "bea_sector": "54",
                    "fiscal_year": 2022,
                    "wage_impact": 500_000,
                    "proprietor_income_impact": 100_000,
                    "gross_operating_surplus": 50_000,
                    "consumption_impact": 100_000,
                },
                {
                    "state": "TX",
                    "bea_sector": "54",
                    "fiscal_year": 2022,
                    "wage_impact": 500_000,
                    "proprietor_income_impact": 100_000,
                    "gross_operating_surplus": 50_000,
                    "consumption_impact": 100_000,
                },
            ]
        )

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
        df = pd.DataFrame(
            [
                {
                    "state": "NY",
                    "wage_impact": 100_000,
                    "proprietor_income_impact": 0,
                    "gross_operating_surplus": 0,
                    "consumption_impact": 50_000,
                }
            ]
        )
        result = estimator.estimate_taxes_from_components(df)
        assert result["state_rate_source"].iloc[0] == "state_specific"

    def test_unknown_state_falls_back_to_nipa(self):
        """Unknown state should fall back to NIPA national average."""
        estimator = FiscalTaxEstimator()
        df = pd.DataFrame(
            [
                {
                    "state": "XX",
                    "wage_impact": 100_000,
                    "proprietor_income_impact": 0,
                    "gross_operating_surplus": 0,
                    "consumption_impact": 50_000,
                }
            ]
        )
        result = estimator.estimate_taxes_from_components(df)
        assert result["state_rate_source"].iloc[0] == "nipa_national"

    def test_no_state_column_uses_nipa(self):
        """Without state column, should use NIPA national averages."""
        estimator = FiscalTaxEstimator()
        df = pd.DataFrame(
            [
                {
                    "wage_impact": 100_000,
                    "proprietor_income_impact": 0,
                    "gross_operating_surplus": 0,
                    "consumption_impact": 50_000,
                }
            ]
        )
        result = estimator.estimate_taxes_from_components(df)
        assert result["state_rate_source"].iloc[0] == "nipa_national"

    def test_oregon_no_sales_tax(self):
        """Oregon has no sales tax — sales tax should be zero."""
        estimator = FiscalTaxEstimator()
        df = pd.DataFrame(
            [
                {
                    "state": "OR",
                    "wage_impact": 100_000,
                    "proprietor_income_impact": 0,
                    "gross_operating_surplus": 0,
                    "consumption_impact": 100_000,
                }
            ]
        )
        result = estimator.estimate_taxes_from_components(df)
        assert result["state_local_sales_tax"].iloc[0] == 0.0
        # But Oregon has income tax
        assert result["state_local_income_tax"].iloc[0] > 0


class TestStateRateProviderCsvLoading:
    """CSV-backed construction of StateRateProvider (Reqs 1 + 2 of #402)."""

    def _write_csv(self, path, rows):
        import csv

        with path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    def test_default_csv_file_exists_and_covers_51_states(self):
        """The committed CSV reference must cover 50 states + DC for fiscal_year=2024."""
        assert DEFAULT_CSV_PATH.exists(), f"Missing {DEFAULT_CSV_PATH}"
        provider = StateRateProvider(csv_path=DEFAULT_CSV_PATH)
        assert len(provider.states) == 51

    def test_csv_loaded_rates_match_hardcoded_baseline(self):
        """Req 1.2: initial CSV population matches `_STATE_RATES_2024` exactly."""
        csv_provider = StateRateProvider(csv_path=DEFAULT_CSV_PATH)
        for state, hardcoded in _STATE_RATES_2024.items():
            csv_rates = csv_provider.get_rates(state)
            assert csv_rates is not None, f"CSV missing {state}"
            assert csv_rates.income_rate == pytest.approx(hardcoded.income_rate), state
            assert csv_rates.sales_rate == pytest.approx(hardcoded.sales_rate), state
            assert csv_rates.property_rate == pytest.approx(hardcoded.property_rate), state
            assert csv_rates.has_income_tax is hardcoded.has_income_tax, state
            assert csv_rates.has_sales_tax is hardcoded.has_sales_tax, state

    def test_year_filter_picks_max_year_le_requested(self, tmp_path):
        """Req 2.1: with multiple years, pick max(fiscal_year ≤ requested_year)."""
        csv_path = tmp_path / "rates.csv"
        self._write_csv(
            csv_path,
            [
                {
                    "state_fips": "06",
                    "state_abbr": "CA",
                    "fiscal_year": 2022,
                    "income_rate": 0.123,
                    "sales_rate": 0.085,
                    "property_rate": 0.090,
                    "has_income_tax": True,
                    "has_sales_tax": True,
                },
                {
                    "state_fips": "06",
                    "state_abbr": "CA",
                    "fiscal_year": 2024,
                    "income_rate": 0.133,
                    "sales_rate": 0.087,
                    "property_rate": 0.091,
                    "has_income_tax": True,
                    "has_sales_tax": True,
                },
            ],
        )
        # year=2023 → pick the 2022 row (max ≤ 2023).
        ca_2023 = StateRateProvider(csv_path=csv_path, year=2023).get_rates("CA")
        assert ca_2023.income_rate == pytest.approx(0.123)
        # year=None → pick the latest available (2024).
        ca_latest = StateRateProvider(csv_path=csv_path).get_rates("CA")
        assert ca_latest.income_rate == pytest.approx(0.133)
        # year=2024 → exact match also picks 2024.
        ca_2024 = StateRateProvider(csv_path=csv_path, year=2024).get_rates("CA")
        assert ca_2024.income_rate == pytest.approx(0.133)

    def test_year_too_early_returns_state_missing(self, tmp_path):
        """A year strictly below all CSV rows yields no rate for the state."""
        csv_path = tmp_path / "rates.csv"
        self._write_csv(
            csv_path,
            [
                {
                    "state_fips": "06",
                    "state_abbr": "CA",
                    "fiscal_year": 2024,
                    "income_rate": 0.133,
                    "sales_rate": 0.087,
                    "property_rate": 0.091,
                    "has_income_tax": True,
                    "has_sales_tax": True,
                },
            ],
        )
        provider = StateRateProvider(csv_path=csv_path, year=2010)
        assert provider.get_rates("CA") is None

    def test_default_construction_uses_hardcoded_dict(self):
        """Req 2.1: csv_path=None → backwards-compatible hardcoded fallback."""
        provider = StateRateProvider()
        # Behavior assertion: the provider exposes exactly the baseline rates,
        # state-for-state — without coupling to internal storage.
        assert set(provider.states) == set(_STATE_RATES_2024.keys())
        for state, expected in _STATE_RATES_2024.items():
            actual = provider.get_rates(state)
            assert actual == expected, state

    def test_explicit_rates_override_takes_precedence(self):
        """The legacy `rates=` argument wins over csv_path (test-injection path)."""
        custom = {"AA": StateTaxRates("AA", 0.5, 0.5, 0.5)}
        provider = StateRateProvider(rates=custom, csv_path=DEFAULT_CSV_PATH)
        assert provider.states == ["AA"]
