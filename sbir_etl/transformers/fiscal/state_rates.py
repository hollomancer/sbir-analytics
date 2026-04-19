"""State-level effective tax rates for fiscal impact estimation.

Provides state-specific income tax, sales tax, and property tax rates
so the fiscal pipeline can produce state-level tax receipt estimates
instead of using national NIPA averages for all states.

Sources:
    Income tax: Tax Foundation "State Individual Income Tax Rates" (annual)
    Sales tax: Tax Foundation "State and Local Sales Tax Rates" (annual)
    Property tax: Census Bureau Annual Survey of State/Local Government Finances
    No-income-tax states: AK, FL, NV, NH*, SD, TN*, TX, WA*, WY
        (* NH taxes dividends/interest only; TN phased out Hall tax 2021;
           WA taxes capital gains only as of 2022)

Rate convention:
    All rates are effective rates (decimal, e.g. 0.05 = 5%).
    Income tax rates are top marginal rates as a proxy for effective rates
    on the compensation mix produced by I-O multipliers.  For most SBIR
    spending the income lands in the middle-to-upper brackets.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StateTaxRates:
    """Tax rates for a single state."""

    state: str                    # 2-letter abbreviation
    income_rate: float            # Effective/top marginal income tax rate
    sales_rate: float             # Combined state + avg local sales tax rate
    property_rate: float          # Effective property tax rate (% of value)
    has_income_tax: bool = True
    has_sales_tax: bool = True


# -----------------------------------------------------------------------
# 2024 state tax rates
#
# Income: Tax Foundation "State Individual Income Tax Rates and Brackets"
#   Uses top marginal rate as proxy for effective rate on SBIR-generated
#   income (mostly professional/technical sector compensation).
#
# Sales: Tax Foundation "State and Local Sales Tax Rates"
#   Combined state rate + average local rate.
#
# Property: Tax Foundation / Census Bureau effective rates
#   Effective rate = total property tax / total assessed value.
#   Expressed as fraction (0.01 = 1%).
# -----------------------------------------------------------------------

_STATE_RATES_2024: dict[str, StateTaxRates] = {
    # No income tax states
    "AK": StateTaxRates("AK", 0.000, 0.018, 0.012, has_income_tax=False),
    "FL": StateTaxRates("FL", 0.000, 0.072, 0.009, has_income_tax=False),
    "NV": StateTaxRates("NV", 0.000, 0.082, 0.006, has_income_tax=False),
    "NH": StateTaxRates("NH", 0.000, 0.000, 0.019, has_income_tax=False, has_sales_tax=False),
    "SD": StateTaxRates("SD", 0.000, 0.064, 0.012, has_income_tax=False),
    "TN": StateTaxRates("TN", 0.000, 0.096, 0.007, has_income_tax=False),
    "TX": StateTaxRates("TX", 0.000, 0.082, 0.017, has_income_tax=False),
    "WA": StateTaxRates("WA", 0.000, 0.103, 0.010, has_income_tax=False),
    "WY": StateTaxRates("WY", 0.000, 0.054, 0.006, has_income_tax=False),
    # No sales tax states (but have income tax)
    "DE": StateTaxRates("DE", 0.066, 0.000, 0.006, has_sales_tax=False),
    "MT": StateTaxRates("MT", 0.059, 0.000, 0.008, has_sales_tax=False),
    "OR": StateTaxRates("OR", 0.099, 0.000, 0.010, has_sales_tax=False),
    # All other states (income + sales + property)
    "AL": StateTaxRates("AL", 0.050, 0.092, 0.004),
    "AZ": StateTaxRates("AZ", 0.025, 0.084, 0.007),
    "AR": StateTaxRates("AR", 0.044, 0.095, 0.006),
    "CA": StateTaxRates("CA", 0.133, 0.087, 0.008),
    "CO": StateTaxRates("CO", 0.044, 0.078, 0.005),
    "CT": StateTaxRates("CT", 0.069, 0.064, 0.021),
    "DC": StateTaxRates("DC", 0.105, 0.060, 0.006),
    "GA": StateTaxRates("GA", 0.055, 0.074, 0.009),
    "HI": StateTaxRates("HI", 0.110, 0.045, 0.003),
    "ID": StateTaxRates("ID", 0.058, 0.060, 0.007),
    "IL": StateTaxRates("IL", 0.049, 0.088, 0.022),
    "IN": StateTaxRates("IN", 0.030, 0.070, 0.009),
    "IA": StateTaxRates("IA", 0.060, 0.069, 0.016),
    "KS": StateTaxRates("KS", 0.057, 0.087, 0.014),
    "KY": StateTaxRates("KY", 0.040, 0.060, 0.009),
    "LA": StateTaxRates("LA", 0.044, 0.098, 0.006),
    "ME": StateTaxRates("ME", 0.075, 0.055, 0.014),
    "MD": StateTaxRates("MD", 0.058, 0.060, 0.011),
    "MA": StateTaxRates("MA", 0.090, 0.063, 0.012),
    "MI": StateTaxRates("MI", 0.043, 0.060, 0.015),
    "MN": StateTaxRates("MN", 0.099, 0.078, 0.011),
    "MS": StateTaxRates("MS", 0.050, 0.071, 0.008),
    "MO": StateTaxRates("MO", 0.048, 0.082, 0.010),
    "NE": StateTaxRates("NE", 0.064, 0.070, 0.017),
    "NJ": StateTaxRates("NJ", 0.109, 0.066, 0.024),
    "NM": StateTaxRates("NM", 0.059, 0.079, 0.008),
    "NY": StateTaxRates("NY", 0.109, 0.088, 0.017),
    "NC": StateTaxRates("NC", 0.045, 0.070, 0.008),
    "ND": StateTaxRates("ND", 0.025, 0.069, 0.010),
    "OH": StateTaxRates("OH", 0.035, 0.072, 0.016),
    "OK": StateTaxRates("OK", 0.048, 0.086, 0.009),
    "PA": StateTaxRates("PA", 0.031, 0.063, 0.015),
    "RI": StateTaxRates("RI", 0.060, 0.070, 0.016),
    "SC": StateTaxRates("SC", 0.064, 0.074, 0.006),
    "UT": StateTaxRates("UT", 0.047, 0.073, 0.006),
    "VT": StateTaxRates("VT", 0.088, 0.063, 0.019),
    "VA": StateTaxRates("VA", 0.058, 0.058, 0.008),
    "WV": StateTaxRates("WV", 0.055, 0.065, 0.006),
    "WI": StateTaxRates("WI", 0.076, 0.055, 0.018),
}


class StateRateProvider:
    """Provides state-specific tax rates.

    Falls back to national NIPA averages for unknown states.
    """

    def __init__(self, rates: dict[str, StateTaxRates] | None = None):
        self._rates = rates or _STATE_RATES_2024

    def get_rates(self, state: str) -> StateTaxRates | None:
        """Get rates for a state. Returns None if state not found."""
        return self._rates.get(state.upper())

    @property
    def states(self) -> list[str]:
        """All states with rate data."""
        return sorted(self._rates.keys())

    @property
    def no_income_tax_states(self) -> list[str]:
        """States with no income tax."""
        return [s for s, r in self._rates.items() if not r.has_income_tax]

    @property
    def no_sales_tax_states(self) -> list[str]:
        """States with no sales tax."""
        return [s for s, r in self._rates.items() if not r.has_sales_tax]
