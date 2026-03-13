"""
Observable commercialization benchmark (enhanced Benchmark 2).

Replaces CCR self-reported sales with three observable public signals:
    1. Federal revenue prong: FPDS contract dollars per Phase II award
    2. Patent prong: Patent count / Phase II count (statutory 15% preserved)
    3. Survival prong: SAM.gov active registration + growth indicators

Same trigger thresholds as statutory benchmark:
    16+ Phase II awards across all agencies, past 10 FYs (excl. 2 most recent)

Fully computable from public data. The policy argument for observable-signal
benchmarks over self-reporting is that they are verifiable, complete for the
federal pathway, and resistant to reporting-strategy gaming.

Judgment point: Prong weighting has no statutory guidance. Agent proposes
multiple weighting schemes and shows sensitivity analysis.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from loguru import logger

from ..base import BaseTool, DataSourceRef, ToolMetadata, ToolResult


PHASE2_TRIGGER_THRESHOLD = 16
PATENT_PRONG_THRESHOLD = 0.15  # Statutory: patents >= 15% of Phase II count


class ComputeObservableCommercializationTool(BaseTool):
    """Compute three-prong observable commercialization benchmark.

    Combines FPDS federal revenue, USPTO patents, and SAM.gov entity survival
    into a composite score that replaces CCR-dependent statutory calculations.

    Produces per-company commercialization profiles that feed Mission C's
    fiscal return estimates as confidence weights.
    """

    name = "compute_observable_commercialization"
    version = "1.0.0"

    def execute(
        self,
        metadata: ToolMetadata,
        *,
        awards_df: pd.DataFrame | None = None,
        fpds_contracts: pd.DataFrame | None = None,
        patent_data: pd.DataFrame | None = None,
        sam_entities: pd.DataFrame | None = None,
        entity_table: pd.DataFrame | None = None,
        assessment_year: int = 2026,
        window_years: int = 10,
        exclude_most_recent: int = 2,
        revenue_threshold: float = 100_000.0,
        weight_revenue: float = 0.4,
        weight_patent: float = 0.35,
        weight_survival: float = 0.25,
        **kwargs: Any,
    ) -> ToolResult:
        """Compute three-prong observable commercialization score.

        Args:
            metadata: Pre-initialized metadata to populate
            awards_df: SBIR awards (company, phase, fiscal_year, amount)
            fpds_contracts: FPDS contract data linked to SBIR companies
            patent_data: Patent portfolio data per company
            sam_entities: SAM.gov entity registration data
            entity_table: Canonical entity table for company linkage
            assessment_year: Benchmark assessment year
            window_years: Measurement window length (statutory: 10)
            exclude_most_recent: FYs to exclude (statutory: 2)
            revenue_threshold: Minimum avg FPDS revenue per Phase II award
            weight_revenue: Weight for federal revenue prong
            weight_patent: Weight for patent prong
            weight_survival: Weight for survival prong

        Returns:
            ToolResult with per-company three-prong scores and profiles
        """
        metadata.upstream_tools.extend([
            "extract_awards", "extract_fpds_contracts",
            "extract_sam_entities", "resolve_entities",
        ])

        if awards_df is None or awards_df.empty:
            metadata.warnings.append("No awards data provided")
            return ToolResult(data=self._empty_result(), metadata=metadata)

        df = awards_df.copy()

        # Identify columns
        company_col = next(
            (c for c in ["canonical_id", "company", "company_name"] if c in df.columns),
            None,
        )
        phase_col = next(
            (c for c in ["phase", "award_phase"] if c in df.columns), None,
        )
        fy_col = next(
            (c for c in ["fiscal_year", "award_year", "fy"] if c in df.columns), None,
        )

        if not all([company_col, phase_col, fy_col]):
            metadata.warnings.append("Missing required columns in awards data")
            return ToolResult(data=self._empty_result(), metadata=metadata)

        # Measurement window
        end_fy = assessment_year - exclude_most_recent
        start_fy = end_fy - window_years + 1
        window = df[(df[fy_col] >= start_fy) & (df[fy_col] <= end_fy)]

        # Phase II counts per company
        def _is_phase_2(val: Any) -> bool:
            s = str(val).strip().upper()
            return s in ("II", "2", "PHASE II", "PHASE_II", "P2")

        p2_window = window[window[phase_col].apply(_is_phase_2)]
        p2_counts = p2_window.groupby(company_col).size().to_dict()

        # Filter to companies meeting trigger threshold
        qualifying = {co: cnt for co, cnt in p2_counts.items() if cnt >= PHASE2_TRIGGER_THRESHOLD}
        logger.info(
            f"Observable benchmark: {len(qualifying)} companies qualify "
            f"({PHASE2_TRIGGER_THRESHOLD}+ Phase II awards in FY{start_fy}-FY{end_fy})"
        )

        # Build FPDS revenue index
        fpds_revenue: dict[str, float] = {}
        if fpds_contracts is not None and not fpds_contracts.empty:
            fpds_co_col = next(
                (c for c in ["canonical_id", "vendor_uei", "vendor_name"] if c in fpds_contracts.columns),
                None,
            )
            amount_col = next(
                (c for c in ["obligation_amount", "amount", "federal_action_obligation"]
                 if c in fpds_contracts.columns),
                None,
            )
            if fpds_co_col and amount_col:
                fpds_revenue = (
                    fpds_contracts.groupby(fpds_co_col)[amount_col]
                    .sum()
                    .to_dict()
                )
            metadata.data_sources.append(
                DataSourceRef(
                    name="FPDS-NG (via USAspending.gov)",
                    url="https://usaspending.gov/download_center",
                    record_count=len(fpds_contracts),
                    access_method="upstream_tool",
                )
            )

        # Build patent index
        patent_counts: dict[str, int] = {}
        if patent_data is not None and not patent_data.empty:
            pat_co_col = next(
                (c for c in ["canonical_id", "assignee_name", "company"] if c in patent_data.columns),
                None,
            )
            if pat_co_col:
                patent_counts = patent_data.groupby(pat_co_col).size().to_dict()
            metadata.data_sources.append(
                DataSourceRef(
                    name="USPTO / PatentsView",
                    url="https://patentsview.org/download",
                    record_count=len(patent_data),
                    access_method="upstream_tool",
                )
            )

        # Build SAM.gov survival index
        sam_active: dict[str, bool] = {}
        sam_growth: dict[str, bool] = {}
        if sam_entities is not None and not sam_entities.empty:
            sam_co_col = next(
                (c for c in ["canonical_id", "unique_entity_id", "uei"] if c in sam_entities.columns),
                None,
            )
            status_col = next(
                (c for c in ["registration_status", "status"] if c in sam_entities.columns),
                None,
            )
            if sam_co_col and status_col:
                for _, row in sam_entities.iterrows():
                    co_id = row[sam_co_col]
                    is_active = str(row[status_col]).upper() == "ACTIVE"
                    sam_active[co_id] = is_active
            metadata.data_sources.append(
                DataSourceRef(
                    name="SAM.gov Entity Data",
                    url="https://sam.gov",
                    record_count=len(sam_entities),
                    access_method="upstream_tool",
                )
            )

        # Compute three-prong scores
        results: list[dict[str, Any]] = []
        for company, p2_count in qualifying.items():
            # Prong 1: Federal revenue
            total_revenue = fpds_revenue.get(company, 0.0)
            avg_revenue_per_p2 = total_revenue / p2_count if p2_count > 0 else 0.0
            revenue_prong = min(avg_revenue_per_p2 / revenue_threshold, 1.0) if revenue_threshold > 0 else 0.0
            revenue_pass = avg_revenue_per_p2 >= revenue_threshold

            # Prong 2: Patent portfolio
            patents = patent_counts.get(company, 0)
            patent_ratio = patents / p2_count if p2_count > 0 else 0.0
            patent_prong = min(patent_ratio / PATENT_PRONG_THRESHOLD, 1.0) if PATENT_PRONG_THRESHOLD > 0 else 0.0
            patent_pass = patent_ratio >= PATENT_PRONG_THRESHOLD

            # Prong 3: Entity survival
            is_active = sam_active.get(company, False)
            has_growth = sam_growth.get(company, False)
            survival_prong = (0.7 if is_active else 0.0) + (0.3 if has_growth else 0.0)
            survival_pass = is_active

            # Composite score (weighted)
            composite = (
                weight_revenue * revenue_prong +
                weight_patent * patent_prong +
                weight_survival * survival_prong
            )

            # Overall pass: at least 2 of 3 prongs passing
            prongs_passing = sum([revenue_pass, patent_pass, survival_pass])
            overall_status = "passing" if prongs_passing >= 2 else "failing"

            results.append({
                "company_id": company,
                "phase_2_count": p2_count,
                "measurement_window": f"FY{start_fy}-FY{end_fy}",
                # Revenue prong
                "fpds_total_revenue": round(total_revenue, 2),
                "avg_revenue_per_p2": round(avg_revenue_per_p2, 2),
                "revenue_prong_score": round(revenue_prong, 4),
                "revenue_prong_pass": revenue_pass,
                # Patent prong
                "patent_count": patents,
                "patent_ratio": round(patent_ratio, 4),
                "patent_prong_score": round(patent_prong, 4),
                "patent_prong_pass": patent_pass,
                # Survival prong
                "sam_active": is_active,
                "survival_prong_score": round(survival_prong, 4),
                "survival_prong_pass": survival_pass,
                # Composite
                "composite_score": round(composite, 4),
                "prongs_passing": prongs_passing,
                "overall_status": overall_status,
                # Weights used
                "weights": {
                    "revenue": weight_revenue,
                    "patent": weight_patent,
                    "survival": weight_survival,
                },
            })

        results_df = pd.DataFrame(results) if results else pd.DataFrame()

        # Summary
        passing = [r for r in results if r["overall_status"] == "passing"]
        summary = {
            "assessment_year": assessment_year,
            "measurement_window": f"FY{start_fy}-FY{end_fy}",
            "qualifying_companies": len(qualifying),
            "passing": len(passing),
            "failing": len(qualifying) - len(passing),
            "avg_composite_score": round(
                sum(r["composite_score"] for r in results) / len(results), 4
            ) if results else None,
            "revenue_data_coverage": len([c for c in qualifying if c in fpds_revenue]) / len(qualifying) if qualifying else 0,
            "patent_data_coverage": len([c for c in qualifying if c in patent_counts]) / len(qualifying) if qualifying else 0,
            "sam_data_coverage": len([c for c in qualifying if c in sam_active]) / len(qualifying) if qualifying else 0,
            "limitation_note": (
                "Observable benchmark cannot see private-market-only commercialization. "
                "FPDS captures federal pathway only. Patent prong preserves statutory 15% threshold."
            ),
        }

        metadata.record_count = len(results_df)
        metadata.data_sources.append(
            DataSourceRef(
                name="SBIR.gov Awards",
                url="https://sbir.gov/api",
                record_count=len(window),
                access_method="statutory_benchmark_calculation",
            )
        )

        return ToolResult(
            data={"results": results_df, "summary": summary},
            metadata=metadata,
        )

    @staticmethod
    def _empty_result() -> dict[str, Any]:
        return {
            "results": pd.DataFrame(),
            "summary": {"qualifying_companies": 0},
        }
