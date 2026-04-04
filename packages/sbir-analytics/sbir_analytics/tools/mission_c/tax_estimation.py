"""
Federal tax receipt estimation from SBIR economic impacts.

The only genuinely new tool in Mission C. Combines:
- BEA-sector-mapped awards (from naics_to_bea_crosswalk)
- BEA I-O economic multipliers (from stateio_multipliers)
- IRS SOI effective tax rates by sector

Two-track estimation:
    Track A: Multiplier-based → what SBIR investment *should produce* in receipts
    Track B: Observable FPDS revenue → verified government expenditures (from Mission B)

Calibration: Where both tracks cover the same companies, the divergence
measures Track A's reliability.

Data source: IRS Statistics of Income (irs.gov/statistics)
Access method: PDF + spreadsheet
Refresh cadence: Annual
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from ..base import BaseTool, DataSourceRef, ToolMetadata, ToolResult


# IRS SOI effective tax rates by broad sector (2022 data)
# Source: IRS Statistics of Income, Corporate Income Tax Returns
DEFAULT_EFFECTIVE_TAX_RATES = {
    "Manufacturing": 0.18,
    "Information": 0.16,
    "Professional, Scientific, and Technical Services": 0.20,
    "Health Care": 0.19,
    "Finance and Insurance": 0.17,
    "Mining": 0.15,
    "Utilities": 0.14,
    "Construction": 0.19,
    "Wholesale Trade": 0.18,
    "Retail Trade": 0.17,
    "Transportation": 0.16,
    "Real Estate": 0.12,
    "Agriculture": 0.14,
    "Other": 0.18,
}

# Payroll tax rates (FICA)
PAYROLL_TAX_RATE = 0.153  # Combined employer + employee (Social Security + Medicare)
# Approximate individual income tax effective rate for SBIR-relevant income levels
INDIVIDUAL_INCOME_TAX_RATE = 0.22


class TaxEstimationTool(BaseTool):
    """Estimate federal tax receipts attributable to SBIR investments.

    Combines multiplier-derived economic impacts with IRS effective tax rates
    to produce fiscal return estimates by vintage year, agency, and tech area.
    """

    name = "tax_estimation"
    version = "1.0.0"

    def execute(
        self,
        metadata: ToolMetadata,
        *,
        awards_df: pd.DataFrame | None = None,
        multipliers_df: pd.DataFrame | None = None,
        fpds_revenue: pd.DataFrame | None = None,
        commercialization_scores: pd.DataFrame | None = None,
        effective_tax_rates: dict[str, float] | None = None,
        discount_rate: float = 0.03,
        assessment_year: int = 2026,
        **kwargs: Any,
    ) -> ToolResult:
        """Estimate fiscal returns from SBIR investments (Track A + Track B).

        Args:
            metadata: Pre-initialized metadata to populate
            awards_df: Awards with bea_sector, state, award_amount, fiscal_year
            multipliers_df: BEA I-O multipliers (state, bea_sector, output_multiplier)
            fpds_revenue: Per-company FPDS revenue (from Mission B, Track B)
            commercialization_scores: Observable scores for confidence weighting
            effective_tax_rates: Override IRS effective rates by sector
            discount_rate: Discount rate for NPV calculation (default 3%)
            assessment_year: Reference year for NPV discounting

        Returns:
            ToolResult with Track A estimates, Track B observations, calibration
        """
        metadata.upstream_tools.extend([
            "naics_to_bea_crosswalk", "stateio_multipliers",
            "compute_observable_commercialization",
        ])

        tax_rates = effective_tax_rates or DEFAULT_EFFECTIVE_TAX_RATES

        # =====================================================================
        # Track A: Multiplier-based estimation
        # =====================================================================
        track_a_results: list[dict[str, Any]] = []

        if awards_df is not None and not awards_df.empty:
            df = awards_df.copy()

            # Required columns
            sector_col = next(
                (c for c in ["bea_sector", "sector"] if c in df.columns), None,
            )
            state_col = next(
                (c for c in ["state", "company_state"] if c in df.columns), None,
            )
            amount_col = next(
                (c for c in ["award_amount", "amount"] if c in df.columns), None,
            )
            fy_col = next(
                (c for c in ["fiscal_year", "award_year", "fy"] if c in df.columns), None,
            )
            company_col = next(
                (c for c in ["canonical_id", "company"] if c in df.columns), None,
            )

            # Build multiplier lookup
            mult_lookup: dict[tuple[str, str], dict] = {}
            if multipliers_df is not None and not multipliers_df.empty:
                for _, row in multipliers_df.iterrows():
                    key = (str(row.get("state", "")), str(row.get("bea_sector", "")))
                    mult_lookup[key] = {
                        "output": float(row.get("output_multiplier", 1.0)),
                        "employment": float(row.get("employment_multiplier", 1.0)),
                        "value_added": float(row.get("value_added_multiplier", 1.0)),
                    }

            # Compute per-award fiscal estimates
            for _, row in df.iterrows():
                award_amount = float(row.get(amount_col, 0)) if amount_col else 0.0
                sector = str(row.get(sector_col, "Other")) if sector_col else "Other"
                state = str(row.get(state_col, "")) if state_col else ""
                fy = row.get(fy_col) if fy_col else None
                company = row.get(company_col) if company_col else None

                # Get multiplier
                mult = mult_lookup.get((state, sector), {"output": 1.0, "employment": 1.0, "value_added": 1.0})
                output_impact = award_amount * mult["output"]
                value_added = award_amount * mult["value_added"]

                # Estimate tax components
                corp_tax_rate = tax_rates.get(sector, tax_rates.get("Other", 0.18))

                # Wage component (approximation: 60% of value added goes to wages)
                wage_share = 0.60
                wages = value_added * wage_share
                corporate_surplus = value_added * 0.25

                # Tax estimates
                individual_income_tax = wages * INDIVIDUAL_INCOME_TAX_RATE
                payroll_tax = wages * PAYROLL_TAX_RATE
                corporate_income_tax = corporate_surplus * corp_tax_rate
                total_tax = individual_income_tax + payroll_tax + corporate_income_tax

                # NPV discounting: discount tax receipts to present value
                # Years from assessment reference point (latest FY in data)
                fy_int = int(fy) if fy is not None else assessment_year
                years_from_present = max(0, assessment_year - fy_int)
                discount_factor = 1.0 / ((1.0 + discount_rate) ** years_from_present)
                discounted_tax = total_tax * discount_factor

                track_a_results.append({
                    "company_id": company,
                    "fiscal_year": fy,
                    "state": state,
                    "bea_sector": sector,
                    "award_amount": round(award_amount, 2),
                    "output_multiplier": round(mult["output"], 4),
                    "output_impact": round(output_impact, 2),
                    "value_added": round(value_added, 2),
                    "estimated_wages": round(wages, 2),
                    "individual_income_tax": round(individual_income_tax, 2),
                    "payroll_tax": round(payroll_tax, 2),
                    "corporate_income_tax": round(corporate_income_tax, 2),
                    "total_estimated_tax": round(total_tax, 2),
                    "discounted_tax": round(discounted_tax, 2),
                    "discount_factor": round(discount_factor, 6),
                    "effective_tax_rate_used": corp_tax_rate,
                })

        track_a_df = pd.DataFrame(track_a_results) if track_a_results else pd.DataFrame()

        # =====================================================================
        # Track B: Observable FPDS revenue (arrives pre-computed from Mission B)
        # =====================================================================
        track_b_summary: dict[str, Any] = {}
        if fpds_revenue is not None and not fpds_revenue.empty:
            amount_col_b = next(
                (c for c in ["fpds_total_revenue", "obligation_amount", "amount"]
                 if c in fpds_revenue.columns),
                None,
            )
            if amount_col_b:
                track_b_summary = {
                    "total_fpds_revenue": float(fpds_revenue[amount_col_b].sum()),
                    "companies_with_revenue": int((fpds_revenue[amount_col_b] > 0).sum()),
                    "total_companies": len(fpds_revenue),
                }
            metadata.data_sources.append(
                DataSourceRef(
                    name="FPDS-NG Revenue (Mission B)",
                    url="https://usaspending.gov/download_center",
                    record_count=len(fpds_revenue),
                    access_method="upstream_mission_b",
                )
            )

        # =====================================================================
        # Calibration: Track A vs Track B divergence
        # =====================================================================
        calibration: dict[str, Any] = {}
        if not track_a_df.empty and fpds_revenue is not None and not fpds_revenue.empty:
            # Compare where both tracks have data for the same company
            company_col_a = "company_id"
            company_col_b = next(
                (c for c in ["company_id", "canonical_id", "company"] if c in fpds_revenue.columns),
                None,
            )
            if company_col_b:
                a_by_company = track_a_df.groupby(company_col_a)["total_estimated_tax"].sum()
                b_col = next(
                    (c for c in ["fpds_total_revenue", "obligation_amount"] if c in fpds_revenue.columns),
                    None,
                )
                if b_col:
                    # Aggregate FPDS revenue per company before comparison
                    b_by_company = fpds_revenue.groupby(company_col_b)[b_col].sum()
                    overlap = a_by_company.index.intersection(b_by_company.index)
                    if len(overlap) > 0:
                        a_vals = a_by_company.loc[overlap]
                        b_vals = b_by_company.loc[overlap]
                        calibration = {
                            "overlapping_companies": len(overlap),
                            "track_a_total": float(a_vals.sum()),
                            "track_b_total": float(b_vals.sum()),
                            "median_ratio": float((a_vals / b_vals.replace(0, float("nan"))).median()) if len(overlap) > 0 else None,
                        }

        # =====================================================================
        # Aggregate summary
        # =====================================================================
        summary: dict[str, Any] = {
            "track_a": {
                "total_estimated_tax_receipts": float(track_a_df["total_estimated_tax"].sum()) if not track_a_df.empty else 0.0,
                "total_discounted_tax_receipts": float(track_a_df["discounted_tax"].sum()) if not track_a_df.empty and "discounted_tax" in track_a_df.columns else 0.0,
                "total_sbir_investment": float(track_a_df["award_amount"].sum()) if not track_a_df.empty else 0.0,
                "implied_roi": round(
                    float(track_a_df["total_estimated_tax"].sum()) /
                    float(track_a_df["award_amount"].sum()), 4
                ) if not track_a_df.empty and track_a_df["award_amount"].sum() > 0 else None,
                "npv_roi": round(
                    float(track_a_df["discounted_tax"].sum()) /
                    float(track_a_df["award_amount"].sum()), 4
                ) if not track_a_df.empty and "discounted_tax" in track_a_df.columns and track_a_df["award_amount"].sum() > 0 else None,
                "discount_rate": discount_rate,
                "awards_estimated": len(track_a_df),
            },
            "track_b": track_b_summary,
            "calibration": calibration,
            "methodology_note": (
                "Track A uses sector-level economic multipliers (BEA I-O) and IRS effective "
                "tax rates. Track B uses verified FPDS contract revenue. Where both tracks "
                "cover the same companies, the divergence measures Track A's reliability. "
                "BEA I-O data ends 2020; post-2020 estimates use extrapolation."
            ),
            "limitation_disclosure": (
                "No private-sector revenue visibility. Companies commercializing entirely "
                "outside federal markets are invisible to Track B. Track A captures them "
                "only via sector-level multiplier estimates. IRS SOI sector granularity is "
                "coarse (2-digit NAICS level)."
            ),
        }

        metadata.record_count = len(track_a_df)
        metadata.data_sources.append(
            DataSourceRef(
                name="IRS Statistics of Income",
                url="https://irs.gov/statistics",
                version="2022",
                record_count=len(tax_rates),
                access_method="effective_tax_rates",
            )
        )

        return ToolResult(
            data={
                "track_a_estimates": track_a_df,
                "track_b_observed": track_b_summary,
                "calibration": calibration,
                "summary": summary,
            },
            metadata=metadata,
        )
