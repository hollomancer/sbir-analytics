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
    property_rate: float          # Property tax rate as fraction of gross operating surplus
                                  # (property_tax / GOS — consistent with NIPA convention)
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
# Property: property_tax / gross operating surplus (GOS-based, consistent
#   with NIPA convention).  Derived by scaling effective assessed-value
#   rates (Tax Foundation / Census Bureau) by the national GOS/value ratio:
#     factor = NIPA national rate (0.125) / national avg effective rate (0.011)
#             ≈ 11.36
#   This aligns with how FiscalTaxEstimator applies the rate to GOS.
# -----------------------------------------------------------------------

_STATE_RATES_2024: dict[str, StateTaxRates] = {
    # No income tax states
    "AK": StateTaxRates("AK", 0.000, 0.018, 0.136, has_income_tax=False),
    "FL": StateTaxRates("FL", 0.000, 0.072, 0.102, has_income_tax=False),
    "NV": StateTaxRates("NV", 0.000, 0.082, 0.068, has_income_tax=False),
    "NH": StateTaxRates("NH", 0.000, 0.000, 0.216, has_income_tax=False, has_sales_tax=False),
    "SD": StateTaxRates("SD", 0.000, 0.064, 0.136, has_income_tax=False),
    "TN": StateTaxRates("TN", 0.000, 0.096, 0.080, has_income_tax=False),
    "TX": StateTaxRates("TX", 0.000, 0.082, 0.193, has_income_tax=False),
    "WA": StateTaxRates("WA", 0.000, 0.103, 0.114, has_income_tax=False),
    "WY": StateTaxRates("WY", 0.000, 0.054, 0.068, has_income_tax=False),
    # No sales tax states (but have income tax)
    "DE": StateTaxRates("DE", 0.066, 0.000, 0.068, has_sales_tax=False),
    "MT": StateTaxRates("MT", 0.059, 0.000, 0.091, has_sales_tax=False),
    "OR": StateTaxRates("OR", 0.099, 0.000, 0.114, has_sales_tax=False),
    # All other states (income + sales + property)
    "AL": StateTaxRates("AL", 0.050, 0.092, 0.045),
    "AZ": StateTaxRates("AZ", 0.025, 0.084, 0.080),
    "AR": StateTaxRates("AR", 0.044, 0.095, 0.068),
    "CA": StateTaxRates("CA", 0.133, 0.087, 0.091),
    "CO": StateTaxRates("CO", 0.044, 0.078, 0.057),
    "CT": StateTaxRates("CT", 0.069, 0.064, 0.239),
    "DC": StateTaxRates("DC", 0.105, 0.060, 0.068),
    "GA": StateTaxRates("GA", 0.055, 0.074, 0.102),
    "HI": StateTaxRates("HI", 0.110, 0.045, 0.034),
    "ID": StateTaxRates("ID", 0.058, 0.060, 0.080),
    "IL": StateTaxRates("IL", 0.049, 0.088, 0.250),
    "IN": StateTaxRates("IN", 0.030, 0.070, 0.102),
    "IA": StateTaxRates("IA", 0.060, 0.069, 0.182),
    "KS": StateTaxRates("KS", 0.057, 0.087, 0.159),
    "KY": StateTaxRates("KY", 0.040, 0.060, 0.102),
    "LA": StateTaxRates("LA", 0.044, 0.098, 0.068),
    "ME": StateTaxRates("ME", 0.075, 0.055, 0.159),
    "MD": StateTaxRates("MD", 0.058, 0.060, 0.125),
    "MA": StateTaxRates("MA", 0.090, 0.063, 0.136),
    "MI": StateTaxRates("MI", 0.043, 0.060, 0.170),
    "MN": StateTaxRates("MN", 0.099, 0.078, 0.125),
    "MS": StateTaxRates("MS", 0.050, 0.071, 0.091),
    "MO": StateTaxRates("MO", 0.048, 0.082, 0.114),
    "NE": StateTaxRates("NE", 0.064, 0.070, 0.193),
    "NJ": StateTaxRates("NJ", 0.109, 0.066, 0.273),
    "NM": StateTaxRates("NM", 0.059, 0.079, 0.091),
    "NY": StateTaxRates("NY", 0.109, 0.088, 0.193),
    "NC": StateTaxRates("NC", 0.045, 0.070, 0.091),
    "ND": StateTaxRates("ND", 0.025, 0.069, 0.114),
    "OH": StateTaxRates("OH", 0.035, 0.072, 0.182),
    "OK": StateTaxRates("OK", 0.048, 0.086, 0.102),
    "PA": StateTaxRates("PA", 0.031, 0.063, 0.170),
    "RI": StateTaxRates("RI", 0.060, 0.070, 0.182),
    "SC": StateTaxRates("SC", 0.064, 0.074, 0.068),
    "UT": StateTaxRates("UT", 0.047, 0.073, 0.068),
    "VT": StateTaxRates("VT", 0.088, 0.063, 0.216),
    "VA": StateTaxRates("VA", 0.058, 0.058, 0.091),
    "WV": StateTaxRates("WV", 0.055, 0.065, 0.068),
    "WI": StateTaxRates("WI", 0.076, 0.055, 0.205),
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
