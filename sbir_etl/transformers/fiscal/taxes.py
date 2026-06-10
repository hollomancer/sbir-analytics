"""
Tax estimator for fiscal returns analysis.

Converts economic components (wage impact, proprietor income, gross operating
surplus, consumption) into federal, state, and local tax receipt estimates
using effective rates derived from BEA NIPA tables.

v2: Federal rates from NIPARateProvider (BEA NIPA Tables 3.2, 3.3, 1.5).
v3: State-specific rates from StateRateProvider (Tax Foundation / Census).
    When a state column is present, uses state-specific income, sales, and
    property rates instead of national NIPA averages.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pandas as pd
from loguru import logger

from .nipa_rates import NIPARateProvider, NIPATaxRates
from .state_rates import StateRateProvider


@dataclass
class TaxEstimationStats:
    """Statistics for tax estimation results."""

    total_individual_income_tax: Decimal
    total_payroll_tax: Decimal
    total_corporate_income_tax: Decimal
    total_excise_tax: Decimal
    total_state_local_tax: Decimal
    total_tax_receipts: Decimal
    num_estimates: int
    avg_effective_rate: float


class FiscalTaxEstimator:
    """Estimate federal, state, and local tax receipts from economic components.

    Uses effective tax rates from BEA NIPA tables via NIPARateProvider.
    Rates are year-specific and fall back to hardcoded baselines when the
    BEA API is unavailable.
    """

    def __init__(
        self,
        rate_provider: NIPARateProvider | None = None,
        state_rate_provider: StateRateProvider | None = None,
        bea_api_key: str | None = None,
        config: object = None,
    ):
        """Initialize the fiscal tax estimator.

        Args:
            rate_provider: Pre-configured NIPARateProvider. If None, creates
                one using bea_api_key (or baseline rates if no key).
            state_rate_provider: Pre-configured StateRateProvider for
                state-specific rates. If None, uses built-in 2024 rates.
            bea_api_key: BEA API key for live NIPA rate fetching.
            config: Deprecated. Accepted for backward compatibility but ignored.
        """
        if config is not None:
            logger.warning(
                "FiscalTaxEstimator: config= parameter is deprecated and ignored. "
                "Use rate_provider= or bea_api_key= instead."
            )
        self.rate_provider = rate_provider or NIPARateProvider(bea_api_key=bea_api_key)
        self.state_rates = state_rate_provider or StateRateProvider()

    def _get_rates(self, year: int | None = None) -> NIPATaxRates:
        return self.rate_provider.get_rates(year)

    def _build_rate_series(
        self,
        result_df: pd.DataFrame,
        year: int | None,
    ) -> dict[str, pd.Series]:
        """Return per-row rate Series keyed by rate attribute name.

        When year is given, all rows use that year's rates.
        Otherwise, each row uses the rates for its fiscal_year column.
        Falls back to the default year when no year info is available.
        """
        if year is not None or "fiscal_year" not in result_df.columns:
            rates = self._get_rates(year)
            n = len(result_df)
            idx = result_df.index
            return {
                "federal_income_rate": pd.Series([rates.federal_income_rate] * n, index=idx),
                "federal_payroll_rate": pd.Series([rates.federal_payroll_rate] * n, index=idx),
                "federal_corporate_rate": pd.Series([rates.federal_corporate_rate] * n, index=idx),
                "federal_excise_rate": pd.Series([rates.federal_excise_rate] * n, index=idx),
                "state_local_income_rate": pd.Series([rates.state_local_income_rate] * n, index=idx),
                "state_local_sales_rate": pd.Series([rates.state_local_sales_rate] * n, index=idx),
                "state_local_property_rate": pd.Series([rates.state_local_property_rate] * n, index=idx),
                "state_local_other_rate": pd.Series([rates.state_local_other_rate] * n, index=idx),
                "rate_year": pd.Series([rates.year] * n, index=idx),
                "rate_source": pd.Series([rates.source] * n, index=idx),
            }

        unique_years = {int(fy) for fy in result_df["fiscal_year"].unique()}
        year_rates = {fy: self._get_rates(fy) for fy in unique_years}
        fy_int = result_df["fiscal_year"].astype(int)

        def _attr(attr: str) -> pd.Series:
            mapping = {fy: getattr(year_rates[fy], attr) for fy in unique_years}
            return fy_int.map(mapping)

        return {
            "federal_income_rate": _attr("federal_income_rate"),
            "federal_payroll_rate": _attr("federal_payroll_rate"),
            "federal_corporate_rate": _attr("federal_corporate_rate"),
            "federal_excise_rate": _attr("federal_excise_rate"),
            "state_local_income_rate": _attr("state_local_income_rate"),
            "state_local_sales_rate": _attr("state_local_sales_rate"),
            "state_local_property_rate": _attr("state_local_property_rate"),
            "state_local_other_rate": _attr("state_local_other_rate"),
            "rate_year": _attr("year"),
            "rate_source": _attr("source"),
        }

    def estimate_taxes_from_components(
        self,
        components_df: pd.DataFrame,
        *,
        year: int | None = None,
    ) -> pd.DataFrame:
        """Estimate taxes from economic components DataFrame.

        Args:
            components_df: DataFrame with columns:
                - wage_impact, proprietor_income_impact, gross_operating_surplus,
                  consumption_impact (economic components from I-O multipliers)
                - state, bea_sector, fiscal_year (identifiers, optional)
            year: Override year for tax rates. If None, uses per-row fiscal_year
                column or defaults to most recent NIPA year.

        Returns:
            DataFrame with all input columns plus:
                Federal: individual_income_tax, payroll_tax, corporate_income_tax, excise_tax
                State/local: state_local_income_tax, state_local_sales_tax,
                    state_local_property_tax, state_local_other_tax
                Totals: federal_tax_total, state_local_tax_total, total_tax_receipt
                Metadata: tax_estimation_methodology, rate_source
        """
        if components_df.empty:
            logger.warning("Empty components DataFrame provided to tax estimator")
            return pd.DataFrame()

        result_df = components_df.copy()

        # Ensure component columns exist as floats
        component_cols = [
            "wage_impact",
            "proprietor_income_impact",
            "gross_operating_surplus",
            "consumption_impact",
        ]
        for col in component_cols:
            if col not in result_df.columns:
                result_df[col] = 0.0
            else:
                result_df[col] = pd.to_numeric(result_df[col], errors="coerce").fillna(0.0)

        # Build per-row rate Series (respects each row's fiscal_year when year is None)
        rate_s = self._build_rate_series(result_df, year)

        # --- Federal taxes ---
        wage = result_df["wage_impact"]
        proprietor = result_df["proprietor_income_impact"]
        gos = result_df["gross_operating_surplus"]
        consumption = result_df["consumption_impact"]

        # federal_income_rate is derived as personal_taxes / compensation, so apply to wages only
        result_df["individual_income_tax"] = wage * rate_s["federal_income_rate"]
        result_df["payroll_tax"] = wage * rate_s["federal_payroll_rate"]
        result_df["corporate_income_tax"] = gos * rate_s["federal_corporate_rate"]
        result_df["excise_tax"] = consumption * rate_s["federal_excise_rate"]

        result_df["federal_tax_total"] = (
            result_df["individual_income_tax"]
            + result_df["payroll_tax"]
            + result_df["corporate_income_tax"]
            + result_df["excise_tax"]
        )

        # --- State & local taxes ---
        # Use state-specific rates when state column is present;
        # fall back to per-row NIPA national averages otherwise.
        has_state_col = "state" in result_df.columns
        if has_state_col:
            state_series = result_df["state"].astype(str)
            state_rate_map = {
                state: self.state_rates.get_rates(state)
                for state in state_series.unique()
            }
            mapped = state_series.map(state_rate_map)

            income_rates = mapped.map(
                lambda st: st.income_rate if st is not None else float("nan")
            ).fillna(rate_s["state_local_income_rate"])
            sales_rates = mapped.map(
                lambda st: st.sales_rate if st is not None else float("nan")
            ).fillna(rate_s["state_local_sales_rate"])
            property_rates = mapped.map(
                lambda st: st.property_rate if st is not None else float("nan")
            ).fillna(rate_s["state_local_property_rate"])

            result_df["state_local_income_tax"] = wage * income_rates
            result_df["state_local_sales_tax"] = consumption * sales_rates
            result_df["state_local_property_tax"] = gos * property_rates
            result_df["state_rate_source"] = mapped.map(
                lambda st: "state_specific" if st is not None else "nipa_national"
            )
        else:
            result_df["state_local_income_tax"] = wage * rate_s["state_local_income_rate"]
            result_df["state_local_sales_tax"] = consumption * rate_s["state_local_sales_rate"]
            result_df["state_local_property_tax"] = gos * rate_s["state_local_property_rate"]
            result_df["state_rate_source"] = "nipa_national"

        result_df["state_local_other_tax"] = (
            (wage + proprietor + gos) * rate_s["state_local_other_rate"]
        )

        result_df["state_local_tax_total"] = (
            result_df["state_local_income_tax"]
            + result_df["state_local_sales_tax"]
            + result_df["state_local_property_tax"]
            + result_df["state_local_other_tax"]
        )

        # --- Totals ---
        result_df["total_tax_receipt"] = (
            result_df["federal_tax_total"] + result_df["state_local_tax_total"]
        )

        # Backward compat: tax_impact alias
        result_df["tax_impact"] = result_df["total_tax_receipt"]

        # --- Metadata ---
        result_df["tax_estimation_methodology"] = "nipa_effective_rates_v2"
        result_df["rate_source"] = rate_s["rate_source"]
        result_df["rate_year"] = rate_s["rate_year"]

        # shock_id for linking
        if all(c in result_df.columns for c in ["state", "bea_sector", "fiscal_year"]):
            result_df["shock_id"] = (
                result_df["state"].astype(str) + "_"
                + result_df["bea_sector"].astype(str) + "_FY"
                + result_df["fiscal_year"].astype(str)
            )
        else:
            result_df["shock_id"] = result_df.index.astype(str)

        # Log summary
        total_federal = result_df["federal_tax_total"].sum()
        total_sl = result_df["state_local_tax_total"].sum()
        total = result_df["total_tax_receipt"].sum()
        logger.info(
            f"Tax estimation complete: "
            f"federal=${total_federal:,.0f} state_local=${total_sl:,.0f} "
            f"total=${total:,.0f} ({len(result_df)} rows)"
        )

        return result_df

    # ------------------------------------------------------------------
    # Backward-compatible per-component helpers
    # Used by validation tests and downstream callers.  These delegate to
    # NIPA rates so they remain consistent with estimate_taxes_from_components.
    # ------------------------------------------------------------------

    def estimate_individual_income_tax(
        self,
        wage: Decimal,
        proprietor_income: Decimal = Decimal("0"),
        year: int | None = None,
    ) -> Decimal:
        """Estimate federal individual income tax on wage income.

        Note: rate is derived as personal_taxes / compensation (NIPA),
        so it is applied to wages only.  ``proprietor_income`` is accepted
        for backward compatibility; pass ``Decimal("0")`` if not applicable.
        Non-zero values are logged as a warning since they do not affect the result.
        """
        if proprietor_income != Decimal("0"):
            logger.warning(
                "estimate_individual_income_tax: proprietor_income is ignored "
                "(rate is applied to wages only per NIPA convention). "
                "Use estimate_taxes_from_components for full income coverage."
            )
        rates = self._get_rates(year)
        return Decimal(str(float(wage) * rates.federal_income_rate))

    def estimate_payroll_tax(
        self,
        wage: Decimal,
        year: int | None = None,
    ) -> Decimal:
        """Estimate federal payroll (social insurance) tax on wage income."""
        rates = self._get_rates(year)
        return Decimal(str(float(wage) * rates.federal_payroll_rate))

    def estimate_corporate_income_tax(
        self,
        gross_operating_surplus: Decimal,
        year: int | None = None,
    ) -> Decimal:
        """Estimate federal corporate income tax on gross operating surplus."""
        rates = self._get_rates(year)
        return Decimal(str(float(gross_operating_surplus) * rates.federal_corporate_rate))

    def estimate_excise_tax(
        self,
        consumption: Decimal,
        year: int | None = None,
    ) -> Decimal:
        """Estimate federal excise tax on consumption."""
        rates = self._get_rates(year)
        return Decimal(str(float(consumption) * rates.federal_excise_rate))

    def get_estimation_statistics(self, tax_estimates_df: pd.DataFrame) -> TaxEstimationStats:
        """Get aggregated statistics for tax estimation results."""
        if tax_estimates_df.empty:
            return TaxEstimationStats(
                total_individual_income_tax=Decimal("0"),
                total_payroll_tax=Decimal("0"),
                total_corporate_income_tax=Decimal("0"),
                total_excise_tax=Decimal("0"),
                total_state_local_tax=Decimal("0"),
                total_tax_receipts=Decimal("0"),
                num_estimates=0,
                avg_effective_rate=0.0,
            )

        total_iit = Decimal(str(tax_estimates_df["individual_income_tax"].sum()))
        total_payroll = Decimal(str(tax_estimates_df["payroll_tax"].sum()))
        total_cit = Decimal(str(tax_estimates_df["corporate_income_tax"].sum()))
        total_excise = Decimal(str(tax_estimates_df["excise_tax"].sum()))
        total_sl = Decimal(str(tax_estimates_df["state_local_tax_total"].sum()))
        total_taxes = Decimal(str(tax_estimates_df["total_tax_receipt"].sum()))

        total_economic_base = (
            tax_estimates_df["wage_impact"].sum()
            + tax_estimates_df["proprietor_income_impact"].sum()
            + tax_estimates_df["gross_operating_surplus"].sum()
            + tax_estimates_df["consumption_impact"].sum()
        )

        avg_effective_rate = (
            float(total_taxes / Decimal(str(total_economic_base)) * 100)
            if total_economic_base > 0 else 0.0
        )

        return TaxEstimationStats(
            total_individual_income_tax=total_iit,
            total_payroll_tax=total_payroll,
            total_corporate_income_tax=total_cit,
            total_excise_tax=total_excise,
            total_state_local_tax=total_sl,
            total_tax_receipts=total_taxes,
            num_estimates=len(tax_estimates_df),
            avg_effective_rate=avg_effective_rate,
        )
