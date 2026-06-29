"""Tests for NIPA-derived effective tax rates."""

from unittest.mock import patch

import pytest

from sbir_etl.transformers.fiscal.nipa_rates import (
    NIPARateProvider,
    NIPATaxRates,
    _BASELINE_RATES,
    _validate_rates,
)


class TestNIPATaxRates:
    def test_baseline_2022_exists(self):
        assert 2022 in _BASELINE_RATES

    def test_baseline_rates_in_plausible_range(self):
        for year, rates in _BASELINE_RATES.items():
            assert 0.10 < rates.federal_income_rate < 0.25, f"{year} income rate"
            assert 0.08 < rates.federal_payroll_rate < 0.18, f"{year} payroll rate"
            assert 0.05 < rates.federal_corporate_rate < 0.25, f"{year} corporate rate"
            assert 0.001 < rates.federal_excise_rate < 0.03, f"{year} excise rate"
            assert 0.02 < rates.state_local_income_rate < 0.08, f"{year} SL income"
            assert 0.02 < rates.state_local_sales_rate < 0.06, f"{year} SL sales"

    def test_total_federal_rate(self):
        rates = _BASELINE_RATES[2022]
        total = rates.total_federal_rate
        # Federal income + payroll should be ~30-35% of compensation
        assert 0.25 < total < 0.40

    def test_total_state_local_rate(self):
        rates = _BASELINE_RATES[2022]
        total = rates.total_state_local_rate
        assert 0.10 < total < 0.30

    def test_frozen_dataclass(self):
        rates = _BASELINE_RATES[2022]
        with pytest.raises(AttributeError):
            rates.federal_income_rate = 0.5


class TestNIPARateProvider:
    def test_returns_baseline_without_api_key(self):
        provider = NIPARateProvider()
        rates = provider.get_rates(2022)
        assert rates.source == "nipa_baseline"
        assert rates.year == 2022
        assert rates.federal_income_rate == _BASELINE_RATES[2022].federal_income_rate

    def test_returns_nearest_year_for_missing(self):
        provider = NIPARateProvider()
        rates = provider.get_rates(2019)
        assert rates.year == 2019
        assert "baseline" in rates.source

    def test_returns_nearest_year_for_future(self):
        provider = NIPARateProvider()
        rates = provider.get_rates(2025)
        assert rates.year == 2025
        assert "baseline" in rates.source

    def test_caches_results(self):
        provider = NIPARateProvider()
        rates1 = provider.get_rates(2022)
        rates2 = provider.get_rates(2022)
        assert rates1 is rates2

    def test_default_year(self):
        provider = NIPARateProvider()
        rates = provider.get_rates()
        assert rates.year == 2022

    def test_api_fallback_on_error(self):
        provider = NIPARateProvider(bea_api_key="fake-key")
        # API will fail but should fall back to baseline
        with patch.object(provider, "_fetch_from_api", side_effect=Exception("API down")):
            rates = provider.get_rates(2022)
            assert "baseline" in rates.source


class TestNIPAParquetCache:
    """On-disk parquet cache backing NIPARateProvider.get_rates."""

    def _provider(self, tmp_path, **kwargs):
        return NIPARateProvider(cache_path=tmp_path / "nipa_tax_rates.parquet", **kwargs)

    def test_api_fetch_persists_to_parquet(self, tmp_path):
        provider = self._provider(tmp_path, bea_api_key="fake-key")
        api_rates = NIPATaxRates(
            year=2023,
            federal_income_rate=0.20,
            federal_payroll_rate=0.13,
            federal_corporate_rate=0.16,
            federal_excise_rate=0.010,
            state_local_income_rate=0.045,
            state_local_sales_rate=0.035,
            state_local_property_rate=0.128,
            state_local_other_rate=0.009,
            source="nipa_api",
        )
        with patch.object(provider, "_fetch_from_api", return_value=api_rates):
            rates = provider.get_rates(2023)

        assert rates.source == "nipa_api"
        assert (tmp_path / "nipa_tax_rates.parquet").exists()

    def test_fresh_provider_reads_parquet_cache(self, tmp_path):
        """A second provider with the same cache_path skips the API entirely."""
        api_rates = NIPATaxRates(
            year=2023,
            federal_income_rate=0.20,
            federal_payroll_rate=0.13,
            federal_corporate_rate=0.16,
            federal_excise_rate=0.010,
            state_local_income_rate=0.045,
            state_local_sales_rate=0.035,
            state_local_property_rate=0.128,
            state_local_other_rate=0.009,
            source="nipa_api",
        )
        # Seed the cache via a first provider.
        seeder = self._provider(tmp_path, bea_api_key="fake-key")
        with patch.object(seeder, "_fetch_from_api", return_value=api_rates):
            seeder.get_rates(2023)

        # Second provider — even with an API key, the parquet hit must short-circuit
        # before `_fetch_from_api` is consulted.
        reader = self._provider(tmp_path, bea_api_key="fake-key")
        with patch.object(reader, "_fetch_from_api") as mock_fetch:
            rates = reader.get_rates(2023)

        assert rates.source == "nipa_api"
        assert rates.federal_income_rate == pytest.approx(0.20)
        mock_fetch.assert_not_called()

    def test_baseline_rates_not_written_to_cache(self, tmp_path):
        """Without an API key we serve baselines but must not pollute the cache."""
        provider = self._provider(tmp_path)
        provider.get_rates(2022)
        assert not (tmp_path / "nipa_tax_rates.parquet").exists()

    def test_write_upserts_on_year_source_key(self, tmp_path):
        """Repeated _write_parquet_cache for the same (year, source) overwrites in-place.

        The defensive upsert protects against hand-edited / partially-corrupted
        caches; normal get_rates() short-circuits on the parquet hit before
        re-writing, so this exercises the writer directly.
        """
        provider = self._provider(tmp_path)

        def _rates(income_rate: float, source: str = "nipa_api") -> NIPATaxRates:
            return NIPATaxRates(
                year=2023,
                federal_income_rate=income_rate,
                federal_payroll_rate=0.12,
                federal_corporate_rate=0.15,
                federal_excise_rate=0.009,
                state_local_income_rate=0.040,
                state_local_sales_rate=0.034,
                state_local_property_rate=0.125,
                state_local_other_rate=0.008,
                source=source,
            )

        provider._write_parquet_cache(_rates(0.18))
        provider._write_parquet_cache(_rates(0.21))

        import pandas as pd

        df = pd.read_parquet(tmp_path / "nipa_tax_rates.parquet")
        rows = df[df["year"] == 2023]
        assert len(rows) == 1
        assert rows.iloc[0]["federal_income_rate"] == pytest.approx(0.21)

    def test_write_keeps_distinct_year_source_pairs(self, tmp_path):
        """Distinct (year, source) keys coexist in the cache."""
        provider = self._provider(tmp_path)

        def _rates(year: int, source: str) -> NIPATaxRates:
            return NIPATaxRates(
                year=year,
                federal_income_rate=0.19,
                federal_payroll_rate=0.12,
                federal_corporate_rate=0.15,
                federal_excise_rate=0.009,
                state_local_income_rate=0.040,
                state_local_sales_rate=0.034,
                state_local_property_rate=0.125,
                state_local_other_rate=0.008,
                source=source,
            )

        provider._write_parquet_cache(_rates(2022, "nipa_api"))
        provider._write_parquet_cache(_rates(2023, "nipa_api"))

        import pandas as pd

        df = pd.read_parquet(tmp_path / "nipa_tax_rates.parquet")
        assert sorted(df["year"].tolist()) == [2022, 2023]


class TestValidateRates:
    def test_valid_rates_pass(self):
        rates = _BASELINE_RATES[2022]
        # Should not raise
        _validate_rates(rates)

    def test_out_of_range_warns(self):
        bad_rates = NIPATaxRates(
            year=2022,
            federal_income_rate=0.50,  # Way too high
            federal_payroll_rate=0.12,
            federal_corporate_rate=0.15,
            federal_excise_rate=0.009,
            state_local_income_rate=0.04,
            state_local_sales_rate=0.034,
            state_local_property_rate=0.125,
            state_local_other_rate=0.008,
        )
        with patch("sbir_etl.transformers.fiscal.nipa_rates.logger") as mock_logger:
            _validate_rates(bad_rates)
            mock_logger.warning.assert_called()


class TestNIPARatesIntegrationReadiness:
    """Verify the rates can be consumed by the existing FiscalTaxEstimator interface."""

    def test_rates_cover_all_tax_types(self):
        rates = _BASELINE_RATES[2022]
        # These are the components FiscalTaxEstimator needs
        assert hasattr(rates, "federal_income_rate")
        assert hasattr(rates, "federal_payroll_rate")
        assert hasattr(rates, "federal_corporate_rate")
        assert hasattr(rates, "federal_excise_rate")
        assert hasattr(rates, "state_local_income_rate")
        assert hasattr(rates, "state_local_sales_rate")
        assert hasattr(rates, "state_local_property_rate")

    def test_rates_produce_reasonable_tax_on_1m_sbir(self):
        """Sanity check: $1M SBIR award should produce ~$300-500K in total taxes."""
        rates = _BASELINE_RATES[2022]
        award = 1_000_000

        # Assume I-O multiplier decomposes $1M into:
        # ~60% compensation, ~15% proprietor income, ~10% corporate profits, ~15% consumption
        compensation = award * 0.60
        proprietor = award * 0.15
        corporate = award * 0.10
        consumption = award * 0.15

        federal_income = (compensation + proprietor) * rates.federal_income_rate
        federal_payroll = compensation * rates.federal_payroll_rate
        federal_corporate = corporate * rates.federal_corporate_rate
        federal_excise = consumption * rates.federal_excise_rate
        state_local = (
            compensation * rates.state_local_income_rate
            + consumption * rates.state_local_sales_rate
            + corporate * rates.state_local_property_rate
        )

        total = federal_income + federal_payroll + federal_corporate + federal_excise + state_local
        # Total tax on $1M should be $200K-$500K (20-50% effective)
        assert 200_000 < total < 500_000, f"Total tax on $1M = ${total:,.0f}"
