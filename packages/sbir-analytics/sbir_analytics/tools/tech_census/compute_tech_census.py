"""ToolResult adapter for the shared config-driven technology census."""

from __future__ import annotations

import math
from typing import Any, cast

import pandas as pd
from loguru import logger

from ..base import BaseTool, DataSourceRef, ToolMetadata, ToolResult

_REQUIRED_COLUMNS = (
    "title",
    "abstract",
    "company",
    "agency",
    "phase",
    "award_year",
    "award_amount",
)
_OPTIONAL_AWARD_COLUMNS = (
    "program",
    "agency_tracking_number",
    "contract",
    "source_row",
)


def _is_missing(value: Any) -> bool:
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _as_text(value: Any) -> str:
    return "" if _is_missing(value) else str(value)


def _as_year(value: Any) -> int | None:
    if _is_missing(value):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return int(numeric) if math.isfinite(numeric) and numeric.is_integer() else None


def _as_amount(value: Any) -> float:
    if _is_missing(value):
        return 0.0
    try:
        numeric = float(str(value).replace("$", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0
    return numeric if math.isfinite(numeric) else 0.0


class ComputeTechCensusTool(BaseTool):
    """Classify awards into a versioned technology profile and aggregate them."""

    name = "compute_tech_census"
    version = "2.0.0"

    def execute(
        self,
        metadata: ToolMetadata,
        *,
        awards_df: pd.DataFrame | None = None,
        area_id: str = "drone_manufacturing",
        programs: list[str] | tuple[str, ...] | None = None,
        fiscal_years: list[int] | tuple[int, ...] | None = None,
        source_path: str | None = None,
        source_sha256: str | None = None,
        source_timestamp: str | None = None,
        data_vintage: str | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Run one profile, optionally narrowing its program and fiscal-year scope."""

        from sbir_etl.utils.tech_census import (
            CensusAward,
            CompiledCensus,
            load_census_config,
            run_census,
        )

        selected_fys = (
            sorted({int(year) for year in fiscal_years}) if fiscal_years is not None else []
        )
        metadata.parameters_used.update(
            {
                "area_id": area_id,
                "programs": list(programs) if programs is not None else None,
                "fiscal_years": selected_fys or None,
                "data_vintage": data_vintage,
            }
        )

        if awards_df is None or awards_df.empty:
            metadata.warnings.append("No awards data provided")
            return ToolResult(data=self._empty_result(area_id), metadata=metadata)

        try:
            compiled = CompiledCensus(load_census_config(area_id))
        except (FileNotFoundError, ValueError) as exc:
            metadata.warnings.append(f"Could not load tech-census config: {exc}")
            return ToolResult(data=self._empty_result(area_id), metadata=metadata)

        effective_programs = tuple(programs) if programs is not None else compiled.programs
        required_columns = list(_REQUIRED_COLUMNS)
        if effective_programs:
            required_columns.append("program")
        missing = [column for column in required_columns if column not in awards_df.columns]
        if missing:
            metadata.warnings.append(f"awards_df missing required columns: {missing}")
            return ToolResult(data=self._empty_result(area_id), metadata=metadata)
        if effective_programs and not (
            awards_df["program"].fillna("").astype(str).str.strip().ne("").any()
        ):
            metadata.warnings.append("awards_df has no usable program values for filtering")
            return ToolResult(data=self._empty_result(area_id), metadata=metadata)

        input_row_count = len(awards_df)
        reporting_df = awards_df
        if selected_fys:
            numeric_years = pd.to_numeric(reporting_df["award_year"], errors="coerce")
            reporting_df = reporting_df[numeric_years.isin(selected_fys)]

        columns = list(_REQUIRED_COLUMNS) + [
            column for column in _OPTIONAL_AWARD_COLUMNS if column in reporting_df.columns
        ]
        raw_awards = reporting_df[columns].to_dict(orient="records")
        awards: list[CensusAward] = []
        for raw in raw_awards:
            normalized = cast(
                CensusAward,
                {
                    "title": _as_text(raw.get("title")),
                    "abstract": _as_text(raw.get("abstract")),
                    "company": _as_text(raw.get("company")),
                    "agency": _as_text(raw.get("agency")),
                    "program": _as_text(raw.get("program")),
                    "phase": _as_text(raw.get("phase")),
                    "award_year": _as_year(raw.get("award_year")),
                    "award_amount": _as_amount(raw.get("award_amount")),
                    "agency_tracking_number": _as_text(raw.get("agency_tracking_number")),
                    "contract": _as_text(raw.get("contract")),
                },
            )
            source_row = _as_year(raw.get("source_row"))
            if source_row is not None:
                normalized["source_row"] = source_row
            awards.append(normalized)
        logger.info(f"Running tech census for {compiled.display_name} over {len(awards):,} awards")
        result = run_census(awards, compiled, programs=programs)
        results_df = pd.DataFrame(result["classified_awards"])

        summary = {
            "area_id": result["area_id"],
            "display_name": result["display_name"],
            "config_version": result["config_version"],
            "override_version": result["override_version"],
            "programs": result["programs"],
            "grand_total": result["grand_total"],
            "fy_totals": {str(key): value for key, value in result["fy_totals"].items()},
            "subset_totals": result["subset_totals"],
            "scope_totals": result["scope_totals"],
            "by_fy_subset": {
                f"{fy}|{subset}": value for (fy, subset), value in result["by_fy_subset"].items()
            },
            "exclusion_counts": result["exclusion_counts"],
            "adjacent_counts": result["adjacent_counts"],
            "program_exclusion_counts": result["program_exclusion_counts"],
            "rejection_counts": result["rejection_counts"],
            "reporting_window": {
                "fiscal_years": selected_fys or None,
                "programs": result["programs"],
            },
            "provenance": {
                "source_path": source_path,
                "sha256": source_sha256,
                "source_timestamp": source_timestamp,
                "data_vintage": data_vintage,
                "source_row_count": input_row_count,
                "reporting_row_count": len(reporting_df),
            },
        }

        metadata.record_count = len(results_df)
        metadata.data_sources.append(
            DataSourceRef(
                name="SBIR.gov Awards",
                url="https://data.www.sbir.gov/mod_awarddatapublic/award_data.csv",
                version=data_vintage or source_timestamp or source_sha256,
                record_count=input_row_count,
                access_method="bulk_csv",
            )
        )
        grand_total = result["grand_total"]
        return ToolResult(
            data={
                "award_count": int(grand_total["n"]),
                "award_dollars": float(grand_total["usd"]),
                "results": results_df,
                "summary": summary,
            },
            metadata=metadata,
        )

    @staticmethod
    def _empty_result(area_id: str) -> dict[str, Any]:
        return {
            "award_count": 0,
            "award_dollars": 0.0,
            "results": pd.DataFrame(),
            "summary": {
                "area_id": area_id,
                "grand_total": {"n": 0, "usd": 0.0},
                "fy_totals": {},
                "subset_totals": {},
                "scope_totals": {},
                "by_fy_subset": {},
                "exclusion_counts": {},
                "adjacent_counts": {},
                "program_exclusion_counts": {},
                "rejection_counts": {},
                "reporting_window": {"fiscal_years": None, "programs": []},
                "provenance": {},
            },
        }
