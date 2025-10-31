"""
ROI calculator for fiscal returns analysis.

This module computes return on investment metrics for SBIR program evaluation,
including total ROI, payback period, net present value, and benefit-cost ratio
with support for multiple discount rates and time horizons.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

import pandas as pd
from loguru import logger

from ..config.loader import get_config
from ..models.fiscal_models import FiscalReturnSummary


@dataclass
class ROICalculationResult:
    """Result of ROI calculation with detailed metrics."""

    roi_ratio: float
    payback_period_years: float | None
    net_present_value: Decimal
    benefit_cost_ratio: float
    total_investment: Decimal
    total_returns: Decimal
    discount_rate: float
    time_horizon_years: int


class FiscalROICalculator:
    """Calculate return on investment metrics for SBIR fiscal returns analysis.

    This calculator aggregates tax receipts and compares them to SBIR program
    investments, computing ROI metrics with temporal discounting.
    """

    def __init__(self, config: Any | None = None):
        """Initialize the fiscal ROI calculator.

        Args:
            config: Optional configuration override
        """
        self.config = config or get_config().fiscal_analysis
        self.base_year = self.config.base_year

    def _calculate_npv(
        self,
        cash_flows: list[Decimal],
        discount_rate: float,
        start_year: int,
    ) -> Decimal:
        """Calculate net present value of cash flows.

        Args:
            cash_flows: List of cash flows by year (positive for receipts)
            discount_rate: Annual discount rate (e.g., 0.03 for 3%)
            start_year: Base year for discounting

        Returns:
            Net present value
        """
        npv = Decimal("0")
        for year_offset, cash_flow in enumerate(cash_flows):
            if cash_flow != 0:
                discount_factor = Decimal(str(1.0 + discount_rate)) ** Decimal(str(year_offset))
                present_value = cash_flow / discount_factor
                npv += present_value

        return npv

    def _calculate_payback_period(
        self,
        investment: Decimal,
        annual_returns: Decimal,
        discount_rate: float = 0.0,
    ) -> float | None:
        """Calculate payback period in years.

        Args:
            investment: Initial investment amount
            annual_returns: Annual return amount (assumed constant)
            discount_rate: Optional discount rate for discounted payback

        Returns:
            Payback period in years, or None if payback not achieved
        """
        if annual_returns <= 0:
            return None

        if discount_rate == 0.0:
            # Simple payback: investment / annual_return
            if investment <= 0:
                return 0.0
            payback_years = float(investment / annual_returns)
            return payback_years if payback_years > 0 else None

        # Discounted payback: accumulate discounted cash flows
        cumulative_pv = Decimal("0")
        for year in range(1, 100):  # Max 100 years
            discount_factor = Decimal(str(1.0 + discount_rate)) ** Decimal(str(year - 1))
            pv_this_year = annual_returns / discount_factor
            cumulative_pv += pv_this_year
            if cumulative_pv >= investment:
                return float(year)

        return None  # Payback not achieved within 100 years

    def calculate_roi_summary(
        self,
        tax_estimates_df: pd.DataFrame,
        sbir_investment: Decimal,
        discount_rate: float = 0.03,
        time_horizon_years: int = 10,
        analysis_date: datetime | None = None,
    ) -> FiscalReturnSummary:
        """Calculate comprehensive ROI summary from tax estimates and investment.

        Args:
            tax_estimates_df: DataFrame with tax estimates (must have total_tax_receipt column)
            sbir_investment: Total SBIR program investment amount
            discount_rate: Annual discount rate for NPV calculation (default: 0.03 = 3%)
            time_horizon_years: Time horizon for analysis (default: 10 years)
            analysis_date: Optional analysis date (defaults to now)

        Returns:
            FiscalReturnSummary with ROI metrics
        """
        if tax_estimates_df.empty:
            logger.warning("Empty tax estimates DataFrame provided to ROI calculator")

        # Aggregate tax receipts
        total_tax_receipts = tax_estimates_df["total_tax_receipt"].sum() if not tax_estimates_df.empty else Decimal("0")

        # Calculate basic ROI ratio
        if sbir_investment > 0:
            roi_ratio = float(total_tax_receipts / sbir_investment)
        else:
            roi_ratio = 0.0

        # Calculate benefit-cost ratio (same as ROI ratio for this analysis)
        benefit_cost_ratio = roi_ratio

        # Calculate payback period
        # Assume annual returns are total divided by time horizon
        annual_returns = total_tax_receipts / Decimal(str(time_horizon_years)) if time_horizon_years > 0 else Decimal("0")
        payback_period = self._calculate_payback_period(
            sbir_investment,
            annual_returns,
            discount_rate=discount_rate,
        )

        # Calculate NPV
        # Assume returns are distributed evenly over time horizon
        cash_flows = [annual_returns] * time_horizon_years
        # First cash flow is negative (investment)
        cash_flows[0] -= sbir_investment
        npv = self._calculate_npv(cash_flows, discount_rate, self.base_year)

        # Calculate confidence intervals (simplified: assume ±10% uncertainty)
        confidence_interval_low = total_tax_receipts * Decimal("0.90")
        confidence_interval_high = total_tax_receipts * Decimal("1.10")

        # Build breakdowns
        breakdown_by_state = {}
        breakdown_by_sector = {}
        breakdown_by_fiscal_year = {}

        if not tax_estimates_df.empty:
            if "state" in tax_estimates_df.columns:
                breakdown_by_state = (
                    tax_estimates_df.groupby("state")["total_tax_receipt"]
                    .sum()
                    .to_dict()
                )
                # Convert to Decimal
                breakdown_by_state = {
                    k: Decimal(str(v)) for k, v in breakdown_by_state.items()
                }

            if "bea_sector" in tax_estimates_df.columns:
                breakdown_by_sector = (
                    tax_estimates_df.groupby("bea_sector")["total_tax_receipt"]
                    .sum()
                    .to_dict()
                )
                breakdown_by_sector = {
                    k: Decimal(str(v)) for k, v in breakdown_by_sector.items()
                }

            if "fiscal_year" in tax_estimates_df.columns:
                breakdown_by_fiscal_year = (
                    tax_estimates_df.groupby("fiscal_year")["total_tax_receipt"]
                    .sum()
                    .to_dict()
                )
                breakdown_by_fiscal_year = {
                    int(k): Decimal(str(v)) for k, v in breakdown_by_fiscal_year.items()
                }

        # Calculate quality metrics
        coverage_metrics = {}
        if not tax_estimates_df.empty:
            if "naics_coverage_rate" in tax_estimates_df.columns:
                coverage_metrics["naics_coverage"] = float(
                    tax_estimates_df["naics_coverage_rate"].mean()
                )
            if "geographic_resolution_rate" in tax_estimates_df.columns:
                coverage_metrics["geographic_resolution"] = float(
                    tax_estimates_df["geographic_resolution_rate"].mean()
                )

        # Calculate quality score (simplified: based on coverage and ROI reasonableness)
        quality_score = 0.5  # Base score
        if coverage_metrics.get("naics_coverage", 0) > 0.85:
            quality_score += 0.2
        if coverage_metrics.get("geographic_resolution", 0) > 0.90:
            quality_score += 0.2
        if 0.5 <= roi_ratio <= 5.0:  # Reasonable ROI range
            quality_score += 0.1
        quality_score = min(quality_score, 1.0)

        quality_flags = []
        if quality_score < 0.7:
            quality_flags.append("low_quality_score")
        if roi_ratio < 0.5:
            quality_flags.append("low_roi")
        if payback_period is None:
            quality_flags.append("payback_not_achieved")

        # Analysis parameters
        analysis_parameters = {
            "discount_rate": discount_rate,
            "time_horizon_years": time_horizon_years,
            "base_year": self.base_year,
            "methodology_version": "fiscal_roi_calculator_v1.0",
        }

        # Sensitivity analysis placeholder (will be populated by sensitivity analysis asset)
        sensitivity_analysis = {}

        # Create summary
        summary = FiscalReturnSummary(
            analysis_id=str(uuid.uuid4()),
            analysis_date=analysis_date or datetime.now(),
            base_year=self.base_year,
            methodology_version="fiscal_returns_v1.0",
            total_sbir_investment=sbir_investment,
            total_tax_receipts=total_tax_receipts,
            net_fiscal_return=total_tax_receipts - sbir_investment,
            roi_ratio=roi_ratio,
            payback_period_years=payback_period,
            net_present_value=npv,
            benefit_cost_ratio=benefit_cost_ratio,
            confidence_interval_low=confidence_interval_low,
            confidence_interval_high=confidence_interval_high,
            confidence_level=0.95,
            sensitivity_analysis=sensitivity_analysis,
            coverage_metrics=coverage_metrics,
            breakdown_by_state=breakdown_by_state,
            breakdown_by_sector=breakdown_by_sector,
            breakdown_by_fiscal_year=breakdown_by_fiscal_year,
            analysis_parameters=analysis_parameters,
            quality_score=quality_score,
            quality_flags=quality_flags,
        )

        # Compute derived metrics
        summary.compute_derived_metrics()

        logger.info(
            "ROI calculation complete",
            extra={
                "roi_ratio": f"{roi_ratio:.3f}",
                "payback_period_years": payback_period,
                "npv": f"${npv:,.2f}",
                "benefit_cost_ratio": f"{benefit_cost_ratio:.3f}",
                "total_investment": f"${sbir_investment:,.2f}",
                "total_receipts": f"${total_tax_receipts:,.2f}",
            },
        )

        return summary

    def calculate_roi_from_components(
        self,
        tax_estimates_df: pd.DataFrame,
        sbir_investment_df: pd.DataFrame,
        discount_rate: float = 0.03,
        time_horizon_years: int = 10,
    ) -> FiscalReturnSummary:
        """Calculate ROI from tax estimates and SBIR investment DataFrames.

        Args:
            tax_estimates_df: DataFrame with total_tax_receipt column
            sbir_investment_df: DataFrame with award amounts (should have inflation_adjusted_amount or shock_amount)
            discount_rate: Annual discount rate
            time_horizon_years: Time horizon for analysis

        Returns:
            FiscalReturnSummary
        """
        # Calculate total SBIR investment
        investment_cols = ["inflation_adjusted_amount", "shock_amount", "award_amount"]
        sbir_investment = Decimal("0")

        for col in investment_cols:
            if col in sbir_investment_df.columns:
                sbir_investment = sbir_investment_df[col].sum()
                break

        if sbir_investment == 0:
            logger.warning("No SBIR investment amount found in investment DataFrame")

        return self.calculate_roi_summary(
            tax_estimates_df,
            sbir_investment,
            discount_rate=discount_rate,
            time_horizon_years=time_horizon_years,
        )

