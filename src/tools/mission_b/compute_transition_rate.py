"""
Statutory Phase I → Phase II transition rate benchmark calculation.

Benchmark 1: Phase I → Phase II Transition Rate
    15 USC 638, as amended by P.L. 117-183 §8

Triggers:
    - 21+ Phase I awards across all agencies, past 5 FYs (excl. most recent)
    - Increased standard at 51+ Phase I awards

Fully computable from public SBIR.gov award data. No CCR dependency.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from loguru import logger

from ..base import BaseTool, DataSourceRef, ToolMetadata, ToolResult


# Statutory thresholds
STANDARD_THRESHOLD = 21   # Phase I awards to trigger benchmark
INCREASED_THRESHOLD = 51  # Phase I awards for stricter standard


class ComputeTransitionRateTool(BaseTool):
    """Compute the statutory Phase I → Phase II transition rate benchmark.

    For each company with sufficient Phase I awards in the measurement window,
    calculates the transition rate and determines pass/fail status against
    the statutory thresholds.
    """

    name = "compute_transition_rate"
    version = "1.0.0"

    def execute(
        self,
        metadata: ToolMetadata,
        awards_df: pd.DataFrame | None = None,
        entity_table: pd.DataFrame | None = None,
        assessment_year: int = 2026,
        window_years: int = 5,
        exclude_most_recent: int = 1,
        standard_min_rate: float = 0.25,
        increased_min_rate: float = 0.35,
    ) -> ToolResult:
        """Calculate transition rate benchmark for all qualifying companies.

        Args:
            metadata: Pre-initialized metadata to populate
            awards_df: SBIR awards with company, phase, fiscal_year columns
            entity_table: Canonical entity table for company deduplication
            assessment_year: The benchmark assessment year (e.g., 2026)
            window_years: Number of fiscal years in the measurement window
            exclude_most_recent: FYs to exclude from the end (statutory: 1)
            standard_min_rate: Minimum transition rate for standard threshold
            increased_min_rate: Minimum rate for increased threshold

        Returns:
            ToolResult with per-company benchmark results
        """
        if awards_df is None or awards_df.empty:
            metadata.warnings.append("No awards data provided")
            return ToolResult(data=self._empty_result(), metadata=metadata)

        metadata.upstream_tools.extend(["extract_awards", "resolve_entities"])

        df = awards_df.copy()

        # Identify columns
        company_col = next(
            (c for c in ["canonical_id", "company", "company_name"] if c in df.columns),
            None,
        )
        phase_col = next(
            (c for c in ["phase", "award_phase", "program_phase"] if c in df.columns),
            None,
        )
        fy_col = next(
            (c for c in ["fiscal_year", "award_year", "fy"] if c in df.columns),
            None,
        )

        if not all([company_col, phase_col, fy_col]):
            metadata.warnings.append(
                f"Missing required columns. Found: company={company_col}, "
                f"phase={phase_col}, fy={fy_col}"
            )
            return ToolResult(data=self._empty_result(), metadata=metadata)

        # Compute measurement window
        end_fy = assessment_year - exclude_most_recent
        start_fy = end_fy - window_years + 1
        window = df[(df[fy_col] >= start_fy) & (df[fy_col] <= end_fy)]

        logger.info(f"Measurement window: FY{start_fy}-FY{end_fy} ({len(window)} awards)")

        # Normalize phase values
        def _is_phase_1(val: Any) -> bool:
            s = str(val).strip().upper()
            return s in ("I", "1", "PHASE I", "PHASE_I", "P1")

        def _is_phase_2(val: Any) -> bool:
            s = str(val).strip().upper()
            return s in ("II", "2", "PHASE II", "PHASE_II", "P2")

        window_p1 = window[window[phase_col].apply(_is_phase_1)]
        window_p2 = window[window[phase_col].apply(_is_phase_2)]

        # Per-company counts
        p1_counts = window_p1.groupby(company_col).size().to_dict()
        p2_counts = window_p2.groupby(company_col).size().to_dict()

        all_companies = set(p1_counts.keys()) | set(p2_counts.keys())

        results: list[dict[str, Any]] = []
        for company in all_companies:
            p1 = p1_counts.get(company, 0)
            p2 = p2_counts.get(company, 0)
            transition_rate = p2 / p1 if p1 > 0 else 0.0

            # Determine threshold tier
            if p1 >= INCREASED_THRESHOLD:
                threshold_tier = "increased"
                min_rate = increased_min_rate
            elif p1 >= STANDARD_THRESHOLD:
                threshold_tier = "standard"
                min_rate = standard_min_rate
            else:
                threshold_tier = "below_threshold"
                min_rate = None

            # Pass/fail determination
            if threshold_tier == "below_threshold":
                status = "not_subject"
            elif transition_rate >= min_rate:
                status = "passing"
            else:
                status = "failing"

            results.append({
                "company_id": company,
                "phase_1_count": p1,
                "phase_2_count": p2,
                "transition_rate": round(transition_rate, 4),
                "threshold_tier": threshold_tier,
                "minimum_rate": min_rate,
                "status": status,
                "awards_to_next_threshold": max(0, STANDARD_THRESHOLD - p1) if p1 < STANDARD_THRESHOLD else max(0, INCREASED_THRESHOLD - p1) if p1 < INCREASED_THRESHOLD else 0,
                "measurement_window": f"FY{start_fy}-FY{end_fy}",
            })

        results_df = pd.DataFrame(results) if results else pd.DataFrame()

        # Summary statistics
        subject_companies = [r for r in results if r["status"] != "not_subject"]
        failing = [r for r in subject_companies if r["status"] == "failing"]

        summary = {
            "assessment_year": assessment_year,
            "measurement_window": f"FY{start_fy}-FY{end_fy}",
            "total_companies": len(all_companies),
            "subject_to_benchmark": len(subject_companies),
            "passing": len(subject_companies) - len(failing),
            "failing": len(failing),
            "standard_tier_count": len([r for r in results if r["threshold_tier"] == "standard"]),
            "increased_tier_count": len([r for r in results if r["threshold_tier"] == "increased"]),
            "below_threshold_count": len([r for r in results if r["threshold_tier"] == "below_threshold"]),
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
            "summary": {"total_companies": 0, "subject_to_benchmark": 0},
        }
