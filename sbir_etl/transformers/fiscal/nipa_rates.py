"""BEA NIPA-derived effective tax rates for fiscal impact estimation.

Fetches National Income and Product Accounts tables from the BEA API to
compute effective federal, state, and local tax rates grounded in actual
government receipt data.  Falls back to hardcoded baseline rates (sourced
from the same NIPA tables) when the BEA API is unavailable.

BEA NIPA table mapping:
    T30200  Table 3.2   Federal government current receipts
    T30300  Table 3.3   State/local government current receipts
    T10500  Table 1.5   Gross domestic income (compensation, profits)

Rate calculation:
    federal_income_rate    = personal_current_taxes / compensation_of_employees
    federal_payroll_rate   = social_insurance_contributions / compensation_of_employees
    federal_corporate_rate = taxes_on_corporate_income / corporate_profits
    federal_excise_rate    = taxes_on_production_imports / personal_consumption
    state_local_rate       = state_local_receipts / gross_domestic_income
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger


@dataclass(frozen=True)
class NIPATaxRates:
    """Effective tax rates derived from BEA NIPA tables.

    All rates are expressed as decimals (e.g., 0.14 = 14%).
    """

    year: int

    # Federal rates
    federal_income_rate: float       # Personal income tax / compensation
    federal_payroll_rate: float      # Social insurance / compensation
    federal_corporate_rate: float    # Corporate income tax / corporate profits
    federal_excise_rate: float       # Excise + production taxes / consumption

    # State & local (combined)
    state_local_income_rate: float   # State/local income tax / compensation
    state_local_sales_rate: float    # State/local sales tax / consumption
    state_local_property_rate: float # Property tax / gross operating surplus
    state_local_other_rate: float    # Other state/local / gross domestic income

    # Metadata
    source: str = "nipa_baseline"    # "nipa_api" or "nipa_baseline"

    @property
    def total_federal_rate(self) -> float:
        """Approximate total federal effective rate on income."""
        return self.federal_income_rate + self.federal_payroll_rate

    @property
    def total_state_local_rate(self) -> float:
        """Approximate total state/local effective rate."""
        return (
            self.state_local_income_rate
            + self.state_local_sales_rate
            + self.state_local_property_rate
            + self.state_local_other_rate
        )


# -----------------------------------------------------------------------
# Baseline rates from BEA NIPA tables (2022 data, the most recent
# complete year at time of writing).  These serve as fallbacks when the
# BEA API is unavailable or the API key is not configured.
#
# Sources:
#   Table 3.2, line items 2,3,5,7  (federal receipts)
#   Table 3.3, line items 2,5,7,9  (state/local receipts)
#   Table 1.5, line items 2,9,14   (gross domestic income components)
#
# Calculation methodology:
#   federal_income_rate  = T3.2 personal_taxes / T1.5 compensation
#       ≈ 2,627B / 13,541B ≈ 0.194
#   federal_payroll_rate = T3.2 social_insurance / T1.5 compensation
#       ≈ 1,655B / 13,541B ≈ 0.122
#   federal_corporate_rate = T3.2 corp_income_tax / T1.5 corp_profits
#       ≈ 425B / 2,800B ≈ 0.152
#   federal_excise_rate  = T3.2 prod_import_taxes / T1.5 PCE proxy
#       ≈ 155B / 17,700B ≈ 0.009
#   state_local_income_rate  = T3.3 personal_taxes / T1.5 compensation
#       ≈ 574B / 13,541B ≈ 0.042
#   state_local_sales_rate   = T3.3 sales_taxes / T1.5 PCE proxy
#       ≈ 610B / 17,700B ≈ 0.034
#   state_local_property_rate = T3.3 property_taxes / T1.5 GOS
#       ≈ 650B / 5,200B ≈ 0.125
#   state_local_other_rate   = T3.3 other / T1.5 GDI
#       ≈ 200B / 25,500B ≈ 0.008
# -----------------------------------------------------------------------

_BASELINE_RATES: dict[int, NIPATaxRates] = {
    2022: NIPATaxRates(
        year=2022,
        federal_income_rate=0.194,
        federal_payroll_rate=0.122,
        federal_corporate_rate=0.152,
        federal_excise_rate=0.009,
        state_local_income_rate=0.042,
        state_local_sales_rate=0.034,
        state_local_property_rate=0.125,
        state_local_other_rate=0.008,
        source="nipa_baseline",
    ),
    2021: NIPATaxRates(
        year=2021,
        federal_income_rate=0.178,
        federal_payroll_rate=0.120,
        federal_corporate_rate=0.119,
        federal_excise_rate=0.009,
        state_local_income_rate=0.040,
        state_local_sales_rate=0.033,
        state_local_property_rate=0.120,
        state_local_other_rate=0.008,
        source="nipa_baseline",
    ),
    2020: NIPATaxRates(
        year=2020,
        federal_income_rate=0.162,
        federal_payroll_rate=0.124,
        federal_corporate_rate=0.098,
        federal_excise_rate=0.009,
        state_local_income_rate=0.037,
        state_local_sales_rate=0.031,
        state_local_property_rate=0.122,
        state_local_other_rate=0.008,
        source="nipa_baseline",
    ),
}

# Default to 2022 for years we don't have explicit data for
_DEFAULT_YEAR = 2022

# BEA NIPA table IDs for API fetching
NIPA_TABLES = {
    "federal_receipts": "T30200",      # Table 3.2
    "state_local_receipts": "T30300",   # Table 3.3
    "gross_domestic_income": "T10500",  # Table 1.5
}

# Line numbers within each NIPA table for specific data series
_FEDERAL_RECEIPT_LINES = {
    "personal_current_taxes": "2",
    "taxes_on_production_imports": "5",
    "taxes_on_corporate_income": "7",
    "contributions_social_insurance": "11",
}

_STATE_LOCAL_RECEIPT_LINES = {
    "personal_current_taxes": "2",
    "taxes_on_production_imports": "5",
    "taxes_on_corporate_income": "7",
    "contributions_social_insurance": "9",
    # Note: property taxes are included in "taxes on production and imports"
    # for state/local. Sales taxes are part of the same line.
}

_GDI_LINES = {
    "compensation_of_employees": "2",
    "taxes_on_production_imports": "7",
    "net_operating_surplus": "9",
    "corporate_profits": "14",
}


class NIPARateProvider:
    """Provides effective tax rates from BEA NIPA data.

    Tries the BEA API first; falls back to hardcoded baseline rates
    derived from the same NIPA tables.
    """

    def __init__(
        self,
        bea_api_key: str | None = None,
        cache_dir: str | Path | None = None,
    ):
        self._api_key = bea_api_key
        self._cache_dir = Path(cache_dir) if cache_dir else None
        self._cache: dict[int, NIPATaxRates] = {}

    def get_rates(self, year: int | None = None) -> NIPATaxRates:
        """Get effective tax rates for a given year.

        Args:
            year: NIPA data year. If None, uses most recent available.

        Returns:
            NIPATaxRates with effective rates for the year.
        """
        year = year or _DEFAULT_YEAR

        # Check in-memory cache
        if year in self._cache:
            return self._cache[year]

        # Try API fetch
        if self._api_key:
            try:
                rates = self._fetch_from_api(year)
                self._cache[year] = rates
                return rates
            except Exception as e:
                logger.warning(f"BEA NIPA API fetch failed for {year}: {e}, using baseline")

        # Fall back to baseline
        rates = self._get_baseline(year)
        self._cache[year] = rates
        return rates

    def _get_baseline(self, year: int) -> NIPATaxRates:
        """Return hardcoded baseline rates for the given year."""
        if year in _BASELINE_RATES:
            return _BASELINE_RATES[year]

        # Use nearest available year
        available = sorted(_BASELINE_RATES.keys())
        nearest = min(available, key=lambda y: abs(y - year))
        logger.info(f"No NIPA baseline for {year}, using {nearest}")
        rates = _BASELINE_RATES[nearest]
        # Return with the requested year but note it's from a different year
        return NIPATaxRates(
            year=year,
            federal_income_rate=rates.federal_income_rate,
            federal_payroll_rate=rates.federal_payroll_rate,
            federal_corporate_rate=rates.federal_corporate_rate,
            federal_excise_rate=rates.federal_excise_rate,
            state_local_income_rate=rates.state_local_income_rate,
            state_local_sales_rate=rates.state_local_sales_rate,
            state_local_property_rate=rates.state_local_property_rate,
            state_local_other_rate=rates.state_local_other_rate,
            source=f"nipa_baseline_{nearest}",
        )

    def _fetch_from_api(self, year: int) -> NIPATaxRates:
        """Fetch NIPA tables from BEA API and compute rates.

        Requires BEA_API_KEY to be set.
        """
        from ..bea_api_client import BEAApiClient

        client = BEAApiClient(api_key=self._api_key)
        try:
            federal = self._fetch_nipa_table(client, "T30200", year)
            state_local = self._fetch_nipa_table(client, "T30300", year)
            gdi = self._fetch_nipa_table(client, "T10500", year)
        finally:
            client.close()

        # Extract values by line number
        def _val(df: pd.DataFrame, line: str) -> float:
            row = df[df["LineNumber"] == line]
            if row.empty:
                return 0.0
            val_str = row.iloc[0].get("DataValue", "0")
            try:
                return float(str(val_str).replace(",", ""))
            except (ValueError, TypeError):
                return 0.0

        # Federal receipts (Table 3.2)
        personal_taxes = _val(federal, "2")
        prod_import_taxes_fed = _val(federal, "5")
        corp_income_tax = _val(federal, "7")
        social_insurance = _val(federal, "11")

        # State/local receipts (Table 3.3)
        sl_personal_taxes = _val(state_local, "2")
        sl_prod_import_taxes = _val(state_local, "5")

        # GDI components (Table 1.5)
        compensation = _val(gdi, "2")
        corp_profits = _val(gdi, "14")
        net_operating_surplus = _val(gdi, "9")

        # Guard against division by zero
        if compensation <= 0:
            raise ValueError(f"NIPA compensation = {compensation} for {year}")

        # Estimate PCE as ~70% of GDP (rough proxy when we don't fetch Table 1.1.5)
        pce_proxy = compensation * 1.3

        rates = NIPATaxRates(
            year=year,
            federal_income_rate=personal_taxes / compensation if compensation else 0.18,
            federal_payroll_rate=social_insurance / compensation if compensation else 0.12,
            federal_corporate_rate=corp_income_tax / corp_profits if corp_profits else 0.15,
            federal_excise_rate=prod_import_taxes_fed / pce_proxy if pce_proxy else 0.009,
            state_local_income_rate=sl_personal_taxes / compensation if compensation else 0.04,
            state_local_sales_rate=sl_prod_import_taxes / pce_proxy if pce_proxy else 0.034,
            state_local_property_rate=0.125,  # Stable, use baseline (not in these tables)
            state_local_other_rate=0.008,     # Small, use baseline
            source="nipa_api",
        )

        # Sanity check: rates should be in plausible ranges
        _validate_rates(rates)
        logger.info(
            f"NIPA rates for {year}: fed_income={rates.federal_income_rate:.3f} "
            f"payroll={rates.federal_payroll_rate:.3f} "
            f"corp={rates.federal_corporate_rate:.3f} "
            f"sl_income={rates.state_local_income_rate:.3f}"
        )
        return rates

    def _fetch_nipa_table(
        self, client: Any, table_name: str, year: int
    ) -> pd.DataFrame:
        """Fetch a single NIPA table via the BEA API."""
        data = client._request({
            "method": "GetData",
            "DataSetName": "NIPA",
            "TableName": table_name,
            "Frequency": "A",
            "Year": str(year),
        })
        return client._rows_to_dataframe(data)


def _validate_rates(rates: NIPATaxRates) -> None:
    """Warn if any rate is outside plausible bounds."""
    checks = [
        ("federal_income_rate", rates.federal_income_rate, 0.05, 0.30),
        ("federal_payroll_rate", rates.federal_payroll_rate, 0.08, 0.18),
        ("federal_corporate_rate", rates.federal_corporate_rate, 0.03, 0.30),
        ("federal_excise_rate", rates.federal_excise_rate, 0.001, 0.03),
        ("state_local_income_rate", rates.state_local_income_rate, 0.01, 0.10),
        ("state_local_sales_rate", rates.state_local_sales_rate, 0.01, 0.08),
    ]
    for name, value, low, high in checks:
        if not (low <= value <= high):
            logger.warning(
                f"NIPA rate {name}={value:.4f} outside expected range [{low}, {high}]"
            )
