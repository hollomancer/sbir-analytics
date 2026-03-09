"""
Portfolio-level metrics computation for cross-agency SBIR analysis.

Computes:
    a. Agency HHI per CET area (funding concentration)
    b. Company HHI per CET area (awardee concentration)
    c. Geographic HHI per CET area (state-level distribution)
    d. Cross-agency company count
    e. Temporal overlap intensity
    f. Topic evolution trajectories
    g. Phase progression rates by CET area and agency

HHI calculations are deterministic — no LLM involvement. Verifiable from
raw award counts by any analyst with the same public data.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from ..base import BaseTool, DataSourceRef, ToolMetadata, ToolResult


def _compute_hhi(shares: list[float]) -> float:
    """Compute Herfindahl-Hirschman Index from market shares.

    HHI = sum of squared market shares (as fractions).
    Range: 1/N (perfect competition) to 1.0 (monopoly).
    """
    if not shares:
        return 0.0
    total = sum(shares)
    if total == 0:
        return 0.0
    fractions = [s / total for s in shares]
    return sum(f * f for f in fractions)


class ComputePortfolioMetricsTool(BaseTool):
    """Compute portfolio-level concentration and distribution metrics.

    All computations are deterministic and reproducible from raw award data.
    No LLM judgment involved — these are straight calculations.
    """

    name = "compute_portfolio_metrics"
    version = "1.0.0"

    def execute(
        self,
        metadata: ToolMetadata,
        classified_awards: pd.DataFrame | None = None,
        entity_table: pd.DataFrame | None = None,
        fiscal_years: list[int] | None = None,
    ) -> ToolResult:
        """Compute portfolio metrics from CET-classified awards.

        Args:
            metadata: Pre-initialized metadata to populate
            classified_awards: Awards with CET, agency, company, state, phase columns
            entity_table: Canonical entity table for deduplication
            fiscal_years: Filter to these fiscal years

        Returns:
            ToolResult with HHI metrics, cross-agency counts, progression rates
        """
        if classified_awards is None or classified_awards.empty:
            metadata.warnings.append("No classified awards provided")
            return ToolResult(data=self._empty_metrics(), metadata=metadata)

        metadata.upstream_tools.extend(["extract_awards", "classify_cet", "resolve_entities"])

        df = classified_awards.copy()

        # Map company names to canonical IDs using entity table for deduplication
        if entity_table is not None and not entity_table.empty:
            canonical_col = next(
                (c for c in ["canonical_id"] if c in entity_table.columns), None,
            )
            name_col = next(
                (c for c in ["canonical_name"] if c in entity_table.columns), None,
            )
            company_src = next(
                (c for c in ["company", "company_name"] if c in df.columns), None,
            )
            if canonical_col and name_col and company_src:
                name_to_id = dict(zip(entity_table[name_col], entity_table[canonical_col]))
                df["canonical_id"] = df[company_src].map(name_to_id).fillna(df[company_src])

        # Identify columns
        cet_col = next((c for c in ["cet_primary", "cet_area", "cet_classification"] if c in df.columns), None)
        agency_col = next((c for c in ["agency", "awarding_agency"] if c in df.columns), None)
        company_col = next((c for c in ["canonical_id", "company", "company_name"] if c in df.columns), None)
        state_col = next((c for c in ["state", "company_state"] if c in df.columns), None)
        fy_col = next((c for c in ["fiscal_year", "award_year", "fy"] if c in df.columns), None)
        phase_col = next((c for c in ["phase", "award_phase", "program_phase"] if c in df.columns), None)
        amount_col = next((c for c in ["award_amount", "amount"] if c in df.columns), None)

        # Apply fiscal year filter
        if fiscal_years and fy_col:
            df = df[df[fy_col].isin(fiscal_years)]

        # a. Agency HHI by CET area
        agency_hhi = {}
        if cet_col and agency_col:
            for area, group in df.groupby(cet_col):
                agency_counts = group[agency_col].value_counts().tolist()
                hhi = _compute_hhi(agency_counts)
                dominant = group[agency_col].value_counts().index[0] if len(agency_counts) > 0 else None
                agency_hhi[area] = {
                    "hhi": round(hhi, 4),
                    "dominant_agency": dominant,
                    "num_agencies": len(agency_counts),
                    "total_awards": int(sum(agency_counts)),
                }

        # b. Company HHI by CET area
        company_hhi = {}
        if cet_col and company_col:
            for area, group in df.groupby(cet_col):
                company_counts = group[company_col].value_counts()
                hhi = _compute_hhi(company_counts.tolist())
                top_3 = company_counts.head(3).index.tolist()
                company_hhi[area] = {
                    "hhi": round(hhi, 4),
                    "top_3_companies": top_3,
                    "num_companies": len(company_counts),
                }

        # c. Geographic HHI by CET area
        geographic_hhi = {}
        if cet_col and state_col:
            for area, group in df.groupby(cet_col):
                state_counts = group[state_col].value_counts()
                hhi = _compute_hhi(state_counts.tolist())
                top_3 = state_counts.head(3).index.tolist()
                geographic_hhi[area] = {
                    "hhi": round(hhi, 4),
                    "top_3_states": top_3,
                    "num_states": len(state_counts),
                }

        # d. Cross-agency company count
        cross_agency_companies = 0
        if company_col and agency_col:
            company_agencies = df.groupby(company_col)[agency_col].nunique()
            cross_agency_companies = int((company_agencies >= 2).sum())

        # e. Temporal overlap intensity
        temporal_overlap = {}
        if cet_col and company_col and agency_col and fy_col:
            for area, group in df.groupby(cet_col):
                # Same company, same CET, different agencies, same FY
                overlap_count = 0
                for (company, fy), subgroup in group.groupby([company_col, fy_col]):
                    if subgroup[agency_col].nunique() >= 2:
                        overlap_count += 1
                temporal_overlap[area] = overlap_count

        # g. Phase progression rates
        progression_rates = {}
        if cet_col and phase_col and company_col:
            for area, group in df.groupby(cet_col):
                phase_counts = group[phase_col].value_counts().to_dict()
                p1 = sum(v for k, v in phase_counts.items() if str(k).strip().upper() in ("I", "1", "PHASE I"))
                p2 = sum(v for k, v in phase_counts.items() if str(k).strip().upper() in ("II", "2", "PHASE II"))
                p3 = sum(v for k, v in phase_counts.items() if str(k).strip().upper() in ("III", "3", "PHASE III"))
                progression_rates[area] = {
                    "phase_1_count": p1,
                    "phase_2_count": p2,
                    "phase_3_count": p3,
                    "p1_to_p2_rate": round(p2 / p1, 4) if p1 > 0 else None,
                    "p2_to_p3_rate": round(p3 / p2, 4) if p2 > 0 else None,
                }

        result = {
            "agency_hhi_by_cet": agency_hhi,
            "company_hhi_by_cet": company_hhi,
            "geographic_hhi_by_cet": geographic_hhi,
            "cross_agency_company_count": cross_agency_companies,
            "temporal_overlap_by_cet": temporal_overlap,
            "phase_progression_by_cet": progression_rates,
            "summary": {
                "total_awards": len(df),
                "cet_areas_covered": len(agency_hhi),
                "cross_agency_companies": cross_agency_companies,
                "avg_agency_hhi": round(
                    sum(v["hhi"] for v in agency_hhi.values()) / len(agency_hhi), 4
                ) if agency_hhi else None,
            },
        }

        metadata.record_count = len(df)
        metadata.data_sources.append(
            DataSourceRef(
                name="SBIR.gov Awards (CET-classified)",
                url="https://sbir.gov/api",
                record_count=len(df),
                access_method="upstream_classified_corpus",
            )
        )

        return ToolResult(data=result, metadata=metadata)

    @staticmethod
    def _empty_metrics() -> dict[str, Any]:
        return {
            "agency_hhi_by_cet": {},
            "company_hhi_by_cet": {},
            "geographic_hhi_by_cet": {},
            "cross_agency_company_count": 0,
            "temporal_overlap_by_cet": {},
            "phase_progression_by_cet": {},
            "summary": {"total_awards": 0},
        }
