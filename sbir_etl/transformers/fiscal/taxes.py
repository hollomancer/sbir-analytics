"""
Federal tax estimator for fiscal returns analysis.

This module converts economic components into federal tax receipt estimates,
supporting individual income tax, payroll tax, corporate income tax, and excise taxes
using configurable effective tax rates and progressive rate structures.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pandas as pd
from loguru import logger

from ...config.loader import get_config


@dataclass
class TaxEstimationStats:
    """Statistics for tax estimation results."""

    total_individual_income_tax: Decimal
    total_payroll_tax: Decimal
    total_corporate_income_tax: Decimal
    total_excise_tax: Decimal
    total_tax_receipts: Decimal
    num_estimates: int
    avg_effective_rate: float


class FiscalTaxEstimator:
    """Estimate federal tax receipts from economic components.

    This estimator transforms wage impacts, proprietor income, gross operating
    surplus, and consumption into federal tax receipts using configurable tax rates.
    """

    def __init__(self, config: Any | None = None):
        """Initialize the fiscal tax estimator.

        Args:
            config: Optional configuration override
        """
        self.config = config or get_config().fiscal_analysis
        self.tax_params = self.config.tax_parameters

    def _get_individual_income_tax_rate(
        self, income: Decimal, progressive_rates: dict[str, float]
    ) -> float:
        """Calculate effective individual income tax rate using progressive brackets.

        Args:
            income: Taxable income amount
            progressive_rates: Progressive rate brackets (e.g., {"22_percent": 0.22})

        Returns:
            Effective tax rate (0.0-1.0)
        """
        # Use average effective rate if income is very small or progressive calculation not needed
        if income < Decimal("10000"):
            return self.tax_params.individual_income_tax.get("effective_rate", 0.22)

        # For larger amounts, use bracket-based calculation
        # Simplified: apply highest bracket that applies
        # In practice, this would apply each bracket to its income range
        income_float = float(income)

        # Sort brackets by rate (ascending)
        sorted(
            progressive_rates.items(),
            key=lambda x: x[1],
        )

        # Apply progressive brackets (simplified calculation)
        # Use the effective rate as base, with slight adjustment for high income
        base_rate = self.tax_params.individual_income_tax.get("effective_rate", 0.22)

        # Adjust upward for high income (top brackets)
        if income_float > 500000:
            base_rate = min(base_rate + 0.05, 0.37)  # Cap at 37%
        elif income_float > 200000:
            base_rate = min(base_rate + 0.03, 0.35)  # Cap at 35%

        return base_rate

    def estimate_individual_income_tax(
        self, wage_impact: Decimal, proprietor_income: Decimal
    ) -> Decimal:
        """Estimate individual income tax from wage and proprietor income.

        Args:
            wage_impact: Wage income generated
            proprietor_income: Proprietor income generated

        Returns:
            Estimated individual income tax receipts
        """
        taxable_income = wage_impact + proprietor_income
        if taxable_income <= 0:
            return Decimal("0")

        # Get progressive rates
        progressive_rates = self.tax_params.individual_income_tax.get("progressive_rates", {})

        # Calculate effective rate
        effective_rate = self._get_individual_income_tax_rate(taxable_income, progressive_rates)

        # Apply standard deduction if configured
        standard_deduction = Decimal(
            str(self.tax_params.individual_income_tax.get("standard_deduction", 13850))
        )
        adjusted_income = max(Decimal("0"), taxable_income - standard_deduction)

        tax_receipt = adjusted_income * Decimal(str(effective_rate))

        return tax_receipt

    def estimate_payroll_tax(self, wage_impact: Decimal) -> Decimal:
        """Estimate payroll taxes (Social Security + Medicare) from wage income.

        Args:
            wage_impact: Wage income generated

        Returns:
            Estimated payroll tax receipts
        """
        if wage_impact <= 0:
            return Decimal("0")

        # Get payroll tax rates
        ss_rate = Decimal(str(self.tax_params.payroll_tax.get("social_security_rate", 0.062)))
        medicare_rate = Decimal(str(self.tax_params.payroll_tax.get("medicare_rate", 0.0145)))
        unemployment_rate = Decimal(
            str(self.tax_params.payroll_tax.get("unemployment_rate", 0.006))
        )

        # Apply Social Security wage base limit
        wage_base_limit = Decimal(str(self.tax_params.payroll_tax.get("wage_base_limit", 160200)))
        taxable_wages = min(wage_impact, wage_base_limit)

        # Calculate taxes (employee + employer portions = 2x for full tax)
        ss_tax = taxable_wages * ss_rate * Decimal("2")  # Both sides
        medicare_tax = wage_impact * medicare_rate * Decimal("2")  # Both sides, no cap
        unemployment_tax = taxable_wages * unemployment_rate  # FUTA typically employer only

        total_payroll_tax = ss_tax + medicare_tax + unemployment_tax

        return total_payroll_tax

    def estimate_corporate_income_tax(self, gross_operating_surplus: Decimal) -> Decimal:
        """Estimate corporate income tax from gross operating surplus.

        Args:
            gross_operating_surplus: Corporate profits generated

        Returns:
            Estimated corporate income tax receipts
        """
        if gross_operating_surplus <= 0:
            return Decimal("0")

        # Use effective rate (accounts for deductions, credits)
        effective_rate = Decimal(
            str(self.tax_params.corporate_income_tax.get("effective_rate", 0.18))
        )

        tax_receipt = gross_operating_surplus * effective_rate

        return tax_receipt

    def estimate_excise_tax(self, consumption_impact: Decimal) -> Decimal:
        """Estimate excise taxes from consumption expenditures.

        Args:
            consumption_impact: Consumer spending generated

        Returns:
            Estimated excise tax receipts
        """
        if consumption_impact <= 0:
            return Decimal("0")

        # Use general excise tax rate
        general_rate = Decimal(str(self.tax_params.excise_tax.get("general_rate", 0.03)))

        tax_receipt = consumption_impact * general_rate

        return tax_receipt

    def estimate_taxes_from_components(self, components_df: pd.DataFrame) -> pd.DataFrame:
        """Estimate federal taxes from economic components DataFrame.

        Args:
            components_df: DataFrame with component columns:
                - wage_impact, proprietor_income_impact, gross_operating_surplus, consumption_impact
                - state, bea_sector, fiscal_year (identifiers)
                - model_version, confidence (metadata)

        Returns:
            DataFrame with tax estimates:
                - All input columns preserved
                - individual_income_tax, payroll_tax, corporate_income_tax, excise_tax
                - total_tax_receipt (sum of all tax types)
                - tax_estimation_methodology: methodology string
        """
        if components_df.empty:
            logger.warning("Empty components DataFrame provided to tax estimator")
            return pd.DataFrame()

        result_df = components_df.copy()

        # Ensure component columns are Decimal
        component_cols = [
            "wage_impact",
            "proprietor_income_impact",
            "gross_operating_surplus",
            "consumption_impact",
        ]

        for col in component_cols:
            if col not in result_df.columns:
                result_df[col] = Decimal("0")
            else:
                result_df[col] = result_df[col].apply(
                    lambda x: Decimal(str(x)) if pd.notna(x) else Decimal("0")
                )

        # Estimate each tax type
        result_df["individual_income_tax"] = result_df.apply(
            lambda row: self.estimate_individual_income_tax(
                row.get("wage_impact", Decimal("0")),
                row.get("proprietor_income_impact", Decimal("0")),
            ),
            axis=1,
        )

        result_df["payroll_tax"] = result_df.apply(
            lambda row: self.estimate_payroll_tax(row.get("wage_impact", Decimal("0"))),
            axis=1,
        )

        result_df["corporate_income_tax"] = result_df.apply(
            lambda row: self.estimate_corporate_income_tax(
                row.get("gross_operating_surplus", Decimal("0"))
            ),
            axis=1,
        )

        result_df["excise_tax"] = result_df.apply(
            lambda row: self.estimate_excise_tax(row.get("consumption_impact", Decimal("0"))),
            axis=1,
        )

        # Calculate total tax receipt
        result_df["total_tax_receipt"] = (
            result_df["individual_income_tax"]
            + result_df["payroll_tax"]
            + result_df["corporate_income_tax"]
            + result_df["excise_tax"]
        )

        # Add methodology metadata
        result_df["tax_estimation_methodology"] = "fiscal_tax_estimator_v1.0"
        result_df["tax_parameter_version"] = "config_v2023"

        # Create shock_id for linking to EconomicShock
        if (
            "state" in result_df.columns
            and "bea_sector" in result_df.columns
            and "fiscal_year" in result_df.columns
        ):
            result_df["shock_id"] = (
                result_df["state"].astype(str)
                + "_"
                + result_df["bea_sector"].astype(str)
                + "_FY"
                + result_df["fiscal_year"].astype(str)
            )
        else:
            result_df["shock_id"] = result_df.index.astype(str)

        # Log summary
        total_iit = result_df["individual_income_tax"].sum()
        total_payroll = result_df["payroll_tax"].sum()
        total_cit = result_df["corporate_income_tax"].sum()
        total_excise = result_df["excise_tax"].sum()
        total_taxes = result_df["total_tax_receipt"].sum()

        logger.info(
            "Tax estimation complete",
            extra={
                "total_individual_income_tax": f"${total_iit:,.2f}",
                "total_payroll_tax": f"${total_payroll:,.2f}",
                "total_corporate_income_tax": f"${total_cit:,.2f}",
                "total_excise_tax": f"${total_excise:,.2f}",
                "total_tax_receipts": f"${total_taxes:,.2f}",
                "num_estimates": len(result_df),
            },
        )

        return result_df

    def get_estimation_statistics(self, tax_estimates_df: pd.DataFrame) -> TaxEstimationStats:
        """Get statistics for tax estimation results.

        Args:
            tax_estimates_df: DataFrame with tax estimates

        Returns:
            TaxEstimationStats with aggregated statistics
        """
        if tax_estimates_df.empty:
            return TaxEstimationStats(
                total_individual_income_tax=Decimal("0"),
                total_payroll_tax=Decimal("0"),
                total_corporate_income_tax=Decimal("0"),
                total_excise_tax=Decimal("0"),
                total_tax_receipts=Decimal("0"),
                num_estimates=0,
                avg_effective_rate=0.0,
            )

        total_iit = tax_estimates_df["individual_income_tax"].sum()
        total_payroll = tax_estimates_df["payroll_tax"].sum()
        total_cit = tax_estimates_df["corporate_income_tax"].sum()
        total_excise = tax_estimates_df["excise_tax"].sum()
        total_taxes = tax_estimates_df["total_tax_receipt"].sum()

        # Calculate average effective rate
        total_economic_base = (
            tax_estimates_df.get("wage_impact", pd.Series([Decimal("0")])).sum()
            + tax_estimates_df.get("proprietor_income_impact", pd.Series([Decimal("0")])).sum()
            + tax_estimates_df.get("gross_operating_surplus", pd.Series([Decimal("0")])).sum()
            + tax_estimates_df.get("consumption_impact", pd.Series([Decimal("0")])).sum()
        )

        avg_effective_rate = (
            float(total_taxes / total_economic_base * 100) if total_economic_base > 0 else 0.0
        )

        return TaxEstimationStats(
            total_individual_income_tax=total_iit,
            total_payroll_tax=total_payroll,
            total_corporate_income_tax=total_cit,
            total_excise_tax=total_excise,
            total_tax_receipts=total_taxes,
            num_estimates=len(tax_estimates_df),
            avg_effective_rate=avg_effective_rate,
        )
