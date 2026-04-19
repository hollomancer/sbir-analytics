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
from typing import Any

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
    ):
        """Initialize the fiscal tax estimator.

        Args:
            rate_provider: Pre-configured NIPARateProvider. If None, creates
                one using bea_api_key (or baseline rates if no key).
            state_rate_provider: Pre-configured StateRateProvider for
                state-specific rates. If None, uses built-in 2024 rates.
            bea_api_key: BEA API key for live NIPA rate fetching.
        """
        self.rate_provider = rate_provider or NIPARateProvider(bea_api_key=bea_api_key)
        self.state_rates = state_rate_provider or StateRateProvider()

    def _get_rates(self, year: int | None = None) -> NIPATaxRates:
        return self.rate_provider.get_rates(year)

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
            year: Override year for tax rates. If None, uses fiscal_year column
                or defaults to most recent NIPA year.

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

        # Determine tax rate year
        rate_year = year
        if rate_year is None and "fiscal_year" in result_df.columns:
            # Use the most common fiscal year in the data
            rate_year = int(result_df["fiscal_year"].mode().iloc[0])

        rates = self._get_rates(rate_year)

        # --- Federal taxes ---
        wage = result_df["wage_impact"]
        proprietor = result_df["proprietor_income_impact"]
        gos = result_df["gross_operating_surplus"]
        consumption = result_df["consumption_impact"]

        result_df["individual_income_tax"] = (wage + proprietor) * rates.federal_income_rate
        result_df["payroll_tax"] = wage * rates.federal_payroll_rate
        result_df["corporate_income_tax"] = gos * rates.federal_corporate_rate
        result_df["excise_tax"] = consumption * rates.federal_excise_rate

        result_df["federal_tax_total"] = (
            result_df["individual_income_tax"]
            + result_df["payroll_tax"]
            + result_df["corporate_income_tax"]
            + result_df["excise_tax"]
        )

        # --- State & local taxes ---
        # Use state-specific rates when state column is present;
        # fall back to NIPA national averages otherwise.
        has_state_col = "state" in result_df.columns
        if has_state_col:
            sl_income = []
            sl_sales = []
            sl_property = []
            sl_source = []
            for _, row in result_df.iterrows():
                st = self.state_rates.get_rates(str(row["state"]))
                if st:
                    sl_income.append(row["wage_impact"] * st.income_rate)
                    sl_sales.append(row["consumption_impact"] * st.sales_rate)
                    sl_property.append(row["gross_operating_surplus"] * st.property_rate)
                    sl_source.append("state_specific")
                else:
                    sl_income.append(row["wage_impact"] * rates.state_local_income_rate)
                    sl_sales.append(row["consumption_impact"] * rates.state_local_sales_rate)
                    sl_property.append(row["gross_operating_surplus"] * rates.state_local_property_rate)
                    sl_source.append("nipa_national")
            result_df["state_local_income_tax"] = sl_income
            result_df["state_local_sales_tax"] = sl_sales
            result_df["state_local_property_tax"] = sl_property
            result_df["state_rate_source"] = sl_source
        else:
            result_df["state_local_income_tax"] = wage * rates.state_local_income_rate
            result_df["state_local_sales_tax"] = consumption * rates.state_local_sales_rate
            result_df["state_local_property_tax"] = gos * rates.state_local_property_rate
            result_df["state_rate_source"] = "nipa_national"

        result_df["state_local_other_tax"] = (
            (wage + proprietor + gos) * rates.state_local_other_rate
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
        result_df["rate_source"] = rates.source
        result_df["rate_year"] = rates.year

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
            f"total=${total:,.0f} ({len(result_df)} rows, rates={rates.source})"
        )

        return result_df

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
