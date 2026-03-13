"""
CET coverage gap analysis for the SBIR portfolio.

Detects gaps in SBIR investment relative to the NSTC Critical and Emerging
Technology taxonomy:
    a. Zero/minimal investment: CET categories with <N awards in past 5 years
    b. Single-agency concentration: CET categories funded by only 1 agency
    c. Declining investment: CET categories losing attention year-over-year
    d. Missing mission alignment: agencies that should fund a CET area but don't

Judgment point: "should" requires interpreting agency mission against
technology taxonomy — the LLM enters here with public agency strategic plans.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from ..base import BaseTool, DataSourceRef, ToolMetadata, ToolResult


# NSTC CET taxonomy (20 categories from 2024 update)
NSTC_CET_AREAS = [
    "Advanced Computing",
    "Advanced Engineering Materials",
    "Advanced Gas Turbine Engine Technologies",
    "Advanced Manufacturing",
    "Advanced Networked Sensing and Signature Management",
    "Advanced Nuclear Energy Technologies",
    "Artificial Intelligence",
    "Autonomous Systems and Robotics",
    "Biotechnologies",
    "Communication and Networking Technologies",
    "Directed Energy",
    "Financial Technologies",
    "Human-Machine Interfaces",
    "Hypersonics",
    "Integrated Sensing and Cyber",
    "Positioning, Navigation, and Timing Technologies",
    "Quantum Information Technologies",
    "Renewable Energy Generation and Storage",
    "Semiconductors and Microelectronics",
    "Space Technologies and Systems",
]


class DetectGapsTool(BaseTool):
    """Analyze CET coverage gaps in the SBIR portfolio.

    Compares the CET-classified award universe against the NSTC taxonomy
    to identify under-investment, concentration risk, and declining attention.
    """

    name = "detect_gaps"
    version = "1.0.0"

    def execute(
        self,
        metadata: ToolMetadata,
        classified_awards: pd.DataFrame | None = None,
        cet_taxonomy: list[str] | None = None,
        lookback_years: int = 5,
        min_awards_threshold: int = 10,
        current_fiscal_year: int = 2025,
    ) -> ToolResult:
        """Detect gaps in CET coverage across the SBIR portfolio.

        Args:
            metadata: Pre-initialized metadata to populate
            classified_awards: Awards with CET classification columns
            cet_taxonomy: Override CET taxonomy list (default: NSTC 2024)
            lookback_years: Years to look back for investment analysis
            min_awards_threshold: Below this count = "minimal investment"
            current_fiscal_year: Current FY for temporal analysis

        Returns:
            ToolResult with gap analysis results
        """
        taxonomy = cet_taxonomy or NSTC_CET_AREAS

        if classified_awards is None or classified_awards.empty:
            metadata.warnings.append("No classified awards provided")
            return ToolResult(
                data=self._empty_gap_result(taxonomy),
                metadata=metadata,
            )

        metadata.upstream_tools.extend(["extract_awards", "classify_cet"])

        df = classified_awards.copy()

        # Identify CET and fiscal year columns
        cet_col = next(
            (c for c in ["cet_primary", "cet_area", "cet_classification"] if c in df.columns),
            None,
        )
        fy_col = next(
            (c for c in ["fiscal_year", "award_year", "fy"] if c in df.columns),
            None,
        )
        agency_col = next(
            (c for c in ["agency", "awarding_agency"] if c in df.columns),
            None,
        )
        amount_col = next(
            (c for c in ["award_amount", "amount", "total_amount"] if c in df.columns),
            None,
        )

        if not cet_col:
            metadata.warnings.append("No CET classification column found in awards data")
            return ToolResult(data=self._empty_gap_result(taxonomy), metadata=metadata)

        # Filter to lookback window
        start_fy = current_fiscal_year - lookback_years
        if fy_col:
            df_window = df[df[fy_col] >= start_fy]
        else:
            df_window = df

        # a. Zero/minimal investment
        cet_counts = df_window[cet_col].value_counts().to_dict()
        unfunded_areas = []
        minimal_areas = []
        for area in taxonomy:
            count = cet_counts.get(area, 0)
            if count == 0:
                last_funded = None
                if fy_col:
                    area_awards = df[df[cet_col] == area]
                    if not area_awards.empty:
                        last_funded = int(area_awards[fy_col].max())
                unfunded_areas.append({
                    "area": area,
                    "award_count": 0,
                    "last_funded_fy": last_funded,
                    "nstc_priority": True,
                })
            elif count < min_awards_threshold:
                minimal_areas.append({
                    "area": area,
                    "award_count": count,
                    "threshold": min_awards_threshold,
                })

        # b. Single-agency concentration
        single_agency_deps = []
        if agency_col:
            for area in taxonomy:
                area_df = df_window[df_window[cet_col] == area]
                if area_df.empty:
                    continue
                agencies = area_df[agency_col].nunique()
                if agencies == 1:
                    sole_agency = area_df[agency_col].iloc[0]
                    single_agency_deps.append({
                        "area": area,
                        "sole_agency": sole_agency,
                        "award_count": len(area_df),
                        "total_amount": float(area_df[amount_col].sum()) if amount_col else None,
                    })

        # c. Declining investment
        declining = []
        if fy_col:
            for area in taxonomy:
                area_df = df_window[df_window[cet_col] == area]
                if len(area_df) < 3:
                    continue

                yearly = area_df.groupby(fy_col).size()
                if len(yearly) < 2:
                    continue

                # Simple linear trend
                years = yearly.index.values.astype(float)
                counts = yearly.values.astype(float)
                if len(years) >= 2:
                    slope = float(
                        (len(years) * (years * counts).sum() - years.sum() * counts.sum()) /
                        (len(years) * (years ** 2).sum() - years.sum() ** 2 + 1e-10)
                    )
                    if slope < -0.5:  # Meaningful decline
                        peak_fy = int(years[counts.argmax()])
                        declining.append({
                            "area": area,
                            "trend_slope": round(slope, 3),
                            "peak_fy": peak_fy,
                            "current_count": int(counts[-1]) if len(counts) > 0 else 0,
                            "peak_count": int(counts.max()),
                        })

        # d. Mission misalignment — placeholder for LLM judgment
        # This is a genuine decision point requiring interpretation of
        # agency missions against technology taxonomy
        mission_misalignment: list[dict] = []
        metadata.confidence = None  # No LLM judgment exercised in this run

        result = {
            "unfunded_cet_areas": unfunded_areas,
            "minimal_investment_areas": minimal_areas,
            "single_agency_dependencies": single_agency_deps,
            "declining_investment": declining,
            "mission_misalignment": mission_misalignment,
            "summary": {
                "taxonomy_size": len(taxonomy),
                "unfunded_count": len(unfunded_areas),
                "minimal_count": len(minimal_areas),
                "single_agency_count": len(single_agency_deps),
                "declining_count": len(declining),
                "lookback_years": lookback_years,
                "start_fy": start_fy,
                "total_awards_in_window": len(df_window),
            },
        }

        metadata.record_count = len(taxonomy)
        metadata.data_sources.append(
            DataSourceRef(
                name="NSTC CET Taxonomy",
                url="https://whitehouse.gov",
                version="2024",
                record_count=len(taxonomy),
                access_method="digitized_pdf",
            )
        )

        return ToolResult(data=result, metadata=metadata)

    @staticmethod
    def _empty_gap_result(taxonomy: list[str]) -> dict[str, Any]:
        return {
            "unfunded_cet_areas": [{"area": a, "award_count": 0, "last_funded_fy": None, "nstc_priority": True} for a in taxonomy],
            "minimal_investment_areas": [],
            "single_agency_dependencies": [],
            "declining_investment": [],
            "mission_misalignment": [],
            "summary": {"taxonomy_size": len(taxonomy), "unfunded_count": len(taxonomy)},
        }
