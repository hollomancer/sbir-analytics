"""
All-phase, subset-taxonomy technology-relevance census (e.g. drone
manufacturing) over SBIR/STTR awards.

Thin ToolResult adapter around the shared, config-driven engine in
sbir_etl.utils.tech_census -- the classification/aggregation logic itself
lives there so the CLI script (scripts/data/build_tech_census.py) and this
API-facing tool can never drift apart. See that module's docstring for the
gate/exclusion/subset design.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from loguru import logger

from ..base import BaseTool, DataSourceRef, ToolMetadata, ToolResult

# CensusAward field names this tool expects as DataFrame columns. Unlike
# some other tools in this package, no defensive multi-name column lookup is
# needed: this tool and its callers (scripts/data/*.py) are the only
# producers of the input DataFrame, so one fixed convention is enforced
# rather than guessed at.
_REQUIRED_COLUMNS = (
    "title",
    "abstract",
    "company",
    "agency",
    "phase",
    "award_year",
    "award_amount",
)


class ComputeTechCensusTool(BaseTool):
    """Classify SBIR/STTR awards into technology subsets and aggregate by fiscal year."""

    name = "compute_tech_census"
    version = "1.0.0"

    def execute(
        self,
        metadata: ToolMetadata,
        *,
        awards_df: pd.DataFrame | None = None,
        area_id: str = "drone_manufacturing",
        **kwargs: Any,
    ) -> ToolResult:
        """Run the census for one configured technology area.

        Args:
            metadata: Pre-initialized metadata to populate
            awards_df: SBIR awards with columns title/abstract/company/agency/
                phase/award_year/award_amount (see sbir_etl.utils.tech_census.
                CensusAward). All phases -- not Phase-II-filtered.
            area_id: config/tech_census/<area_id>.yaml to classify against

        Returns:
            ToolResult with a per-award results DataFrame and a summary dict
            (grand total, fy totals, subset totals, by-fy-subset breakdown,
            exclusion/adjacent category counts).
        """
        from sbir_etl.utils.tech_census import CompiledCensus, load_census_config, run_census

        metadata.parameters_used["area_id"] = area_id

        if awards_df is None or awards_df.empty:
            metadata.warnings.append("No awards data provided")
            return ToolResult(data=self._empty_result(area_id), metadata=metadata)

        missing = [c for c in _REQUIRED_COLUMNS if c not in awards_df.columns]
        if missing:
            metadata.warnings.append(f"awards_df missing required columns: {missing}")
            return ToolResult(data=self._empty_result(area_id), metadata=metadata)

        try:
            cfg = load_census_config(area_id)
        except (FileNotFoundError, ValueError) as exc:
            metadata.warnings.append(f"Could not load tech-census config: {exc}")
            return ToolResult(data=self._empty_result(area_id), metadata=metadata)

        compiled = CompiledCensus(cfg)
        awards = awards_df[list(_REQUIRED_COLUMNS)].to_dict(orient="records")

        logger.info(f"Running tech census for {compiled.display_name} over {len(awards):,} awards")
        result = run_census(awards, compiled)

        results_df = pd.DataFrame(result["classified_awards"])

        summary = {
            "area_id": result["area_id"],
            "display_name": result["display_name"],
            "grand_total": result["grand_total"],
            "fy_totals": {str(k): v for k, v in result["fy_totals"].items()},
            "subset_totals": result["subset_totals"],
            "by_fy_subset": {
                f"{fy}|{subset}": v for (fy, subset), v in result["by_fy_subset"].items()
            },
            "exclusion_counts": result["exclusion_counts"],
            "adjacent_counts": result["adjacent_counts"],
        }

        metadata.record_count = len(results_df)
        metadata.data_sources.append(
            DataSourceRef(
                name="SBIR.gov Awards",
                url="https://data.www.sbir.gov/mod_awarddatapublic/award_data.csv",
                record_count=len(awards_df),
                access_method="bulk_csv",
            )
        )

        return ToolResult(data={"results": results_df, "summary": summary}, metadata=metadata)

    @staticmethod
    def _empty_result(area_id: str) -> dict[str, Any]:
        return {
            "results": pd.DataFrame(),
            "summary": {
                "area_id": area_id,
                "grand_total": {"n": 0, "usd": 0.0},
                "fy_totals": {},
                "subset_totals": {},
                "by_fy_subset": {},
                "exclusion_counts": {},
                "adjacent_counts": {},
            },
        }
