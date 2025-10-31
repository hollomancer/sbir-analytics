"""
Economic component calculator for fiscal returns analysis.

This module transforms StateIO model outputs into federal tax base components,
validating component sums and performing reasonableness checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pandas as pd
from loguru import logger

from ..config.loader import get_config


@dataclass
class ComponentValidationResult:
    """Result of component validation check."""

    is_valid: bool
    total_computed: Decimal
    total_expected: Decimal
    difference: Decimal
    tolerance: Decimal
    component_breakdown: dict[str, Decimal]
    quality_flags: list[str]


class FiscalComponentCalculator:
    """Calculate and validate economic components from StateIO outputs.

    This calculator extracts tax base components (wage income, proprietor income,
    gross operating surplus, consumption) from economic impact data and validates
    their reasonableness and consistency.
    """

    def __init__(self, config: Any | None = None):
        """Initialize the fiscal component calculator.

        Args:
            config: Optional configuration override
        """
        self.config = config or get_config().fiscal_analysis

    def extract_components(
        self, impacts_df: pd.DataFrame
    ) -> pd.DataFrame:
        """Extract tax base components from economic impacts DataFrame.

        Args:
            impacts_df: DataFrame from economic_impacts asset with columns:
                - state, bea_sector, fiscal_year (identifiers)
                - wage_impact, proprietor_income_impact, gross_operating_surplus
                - consumption_impact, production_impact, tax_impact
                - shock_amount, model_version, confidence

        Returns:
            DataFrame with extracted components and validation results:
                - All input columns preserved
                - component_total: sum of all components
                - component_valid: validation flag
                - component_quality_flags: list of quality issues
        """
        if impacts_df.empty:
            logger.warning("Empty impacts DataFrame provided to component calculator")
            return pd.DataFrame()

        result_df = impacts_df.copy()

        # Ensure component columns exist and are numeric
        component_cols = [
            "wage_impact",
            "proprietor_income_impact",
            "gross_operating_surplus",
            "consumption_impact",
        ]

        # Convert to Decimal for precision
        for col in component_cols:
            if col not in result_df.columns:
                result_df[col] = Decimal("0")
            else:
                # Convert to Decimal, handling NaN
                result_df[col] = result_df[col].apply(
                    lambda x: Decimal(str(x)) if pd.notna(x) else Decimal("0")
                )

        # Calculate component totals
        result_df["component_total"] = (
            result_df["wage_impact"]
            + result_df["proprietor_income_impact"]
            + result_df["gross_operating_surplus"]
            + result_df["consumption_impact"]
        )

        # Validate components against production impact (if available)
        if "production_impact" in result_df.columns:
            result_df["production_impact"] = result_df["production_impact"].apply(
                lambda x: Decimal(str(x)) if pd.notna(x) else Decimal("0")
            )
            result_df["component_vs_production_diff"] = (
                result_df["production_impact"] - result_df["component_total"]
            )
            result_df["component_vs_production_pct"] = (
                (
                    result_df["component_vs_production_diff"]
                    / result_df["production_impact"]
                    * Decimal("100")
                )
                if result_df["production_impact"] != 0
                else Decimal("0")
            )

        # Validate each row
        result_df["component_valid"] = result_df.apply(
            self._validate_row_components, axis=1
        )
        result_df["component_quality_flags"] = result_df.apply(
            self._get_quality_flags, axis=1
        )

        # Add summary statistics
        total_wages = result_df["wage_impact"].sum()
        total_proprietor = result_df["proprietor_income_impact"].sum()
        total_gos = result_df["gross_operating_surplus"].sum()
        total_consumption = result_df["consumption_impact"].sum()
        total_components = result_df["component_total"].sum()

        logger.info(
            "Component extraction complete",
            extra={
                "total_wage_impact": f"${total_wages:,.2f}",
                "total_proprietor_income": f"${total_proprietor:,.2f}",
                "total_gross_operating_surplus": f"${total_gos:,.2f}",
                "total_consumption": f"${total_consumption:,.2f}",
                "total_components": f"${total_components:,.2f}",
                "num_valid": result_df["component_valid"].sum(),
                "num_invalid": (~result_df["component_valid"]).sum(),
            },
        )

        return result_df

    def _validate_row_components(self, row: pd.Series) -> bool:
        """Validate components for a single row.

        Args:
            row: Row with component values

        Returns:
            True if components are valid, False otherwise
        """
        # Check for negative components (shouldn't occur)
        components = [
            row.get("wage_impact", Decimal("0")),
            row.get("proprietor_income_impact", Decimal("0")),
            row.get("gross_operating_surplus", Decimal("0")),
            row.get("consumption_impact", Decimal("0")),
        ]

        if any(c < 0 for c in components):
            return False

        # Check component total is reasonable (should be positive)
        component_total = row.get("component_total", Decimal("0"))
        if component_total < 0:
            return False

        # If production_impact available, check components sum to reasonable proportion
        if "production_impact" in row and row["production_impact"] > 0:
            component_pct = row.get("component_vs_production_pct", Decimal("0"))
            # Components should be within 50-150% of production (allows for taxes, etc.)
            if abs(component_pct) > 50:
                return False

        return True

    def _get_quality_flags(self, row: pd.Series) -> list[str]:
        """Get quality flags for a row.

        Args:
            row: Row with component values

        Returns:
            List of quality flag strings
        """
        flags = []

        # Check for zero components
        if row.get("wage_impact", Decimal("0")) == 0:
            flags.append("zero_wage_impact")
        if row.get("proprietor_income_impact", Decimal("0")) == 0:
            flags.append("zero_proprietor_income")
        if row.get("gross_operating_surplus", Decimal("0")) == 0:
            flags.append("zero_gos")
        if row.get("consumption_impact", Decimal("0")) == 0:
            flags.append("zero_consumption")

        # Check component vs production mismatch
        if "production_impact" in row and row["production_impact"] > 0:
            diff_pct = abs(row.get("component_vs_production_pct", Decimal("0")))
            if diff_pct > 25:
                flags.append("large_component_production_mismatch")
            elif diff_pct > 10:
                flags.append("moderate_component_production_mismatch")

        # Check for very small components relative to total
        component_total = row.get("component_total", Decimal("0"))
        if component_total > 0:
            wage_pct = (
                float(row.get("wage_impact", Decimal("0")) / component_total * 100)
                if component_total > 0
                else 0
            )
            if wage_pct < 10:
                flags.append("low_wage_share")
            elif wage_pct > 80:
                flags.append("high_wage_share")

        return flags

    def validate_aggregate_components(
        self, components_df: pd.DataFrame
    ) -> ComponentValidationResult:
        """Validate aggregate components across all impacts.

        Args:
            components_df: DataFrame with component columns

        Returns:
            ComponentValidationResult with validation status
        """
        if components_df.empty:
            return ComponentValidationResult(
                is_valid=False,
                total_computed=Decimal("0"),
                total_expected=Decimal("0"),
                difference=Decimal("0"),
                tolerance=Decimal("0.01"),
                component_breakdown={},
                quality_flags=["empty_dataframe"],
            )

        # Aggregate components
        total_wages = components_df["wage_impact"].sum()
        total_proprietor = components_df["proprietor_income_impact"].sum()
        total_gos = components_df["gross_operating_surplus"].sum()
        total_consumption = components_df["consumption_impact"].sum()

        total_computed = total_wages + total_proprietor + total_gos + total_consumption

        # Compare to production impact if available
        if "production_impact" in components_df.columns:
            total_production = components_df["production_impact"].sum()
            total_expected = total_production
        else:
            total_expected = total_computed  # Use computed as expected if no production

        difference = abs(total_computed - total_expected)
        tolerance = total_expected * Decimal("0.05") if total_expected > 0 else Decimal("0.01")  # 5% tolerance

        is_valid = difference <= tolerance

        component_breakdown = {
            "wage_impact": total_wages,
            "proprietor_income_impact": total_proprietor,
            "gross_operating_surplus": total_gos,
            "consumption_impact": total_consumption,
        }

        quality_flags = []
        if not is_valid:
            quality_flags.append("aggregate_component_mismatch")
        if total_expected == 0:
            quality_flags.append("zero_production_impact")

        return ComponentValidationResult(
            is_valid=is_valid,
            total_computed=total_computed,
            total_expected=total_expected,
            difference=difference,
            tolerance=tolerance,
            component_breakdown=component_breakdown,
            quality_flags=quality_flags,
        )

