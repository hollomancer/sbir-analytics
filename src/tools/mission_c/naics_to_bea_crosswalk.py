"""
NAICS → BEA sector crosswalk tool.

Wraps the existing NAICSToBEAMapper with the standard tool interface.
Maps NAICS codes on SBIR awards to BEA Summary sectors for economic
multiplier application in Track A fiscal estimation.

Judgment point: ~15-20% of NAICS codes don't cleanly map. The LLM reads
award abstract and CET classification to choose best sector fit.

Data source: BEA published crosswalk tables (bea.gov)
Access method: Bulk download (Excel/CSV)
Refresh cadence: Annual
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from loguru import logger

from ..base import BaseTool, DataSourceRef, ToolMetadata, ToolResult


class NAICSToBEACrosswalkTool(BaseTool):
    """Map NAICS codes to BEA sectors for economic modeling.

    Wraps the existing NAICSToBEAMapper transformer with provenance
    tracking and ambiguity logging for the tool interface.
    """

    name = "naics_to_bea_crosswalk"
    version = "1.0.0"

    def execute(
        self,
        metadata: ToolMetadata,
        awards_df: pd.DataFrame | None = None,
        naics_column: str = "naics_code",
        mapping_path: str | None = None,
        bea_excel_path: str | None = None,
    ) -> ToolResult:
        """Map NAICS codes on awards to BEA sectors.

        Args:
            metadata: Pre-initialized metadata to populate
            awards_df: DataFrame with a NAICS code column
            naics_column: Name of the column containing NAICS codes
            mapping_path: Override path to naics_to_bea.csv
            bea_excel_path: Override path to BEA concordance Excel

        Returns:
            ToolResult with awards DataFrame augmented with bea_sector column
        """
        from src.transformers.naics_to_bea import NAICSToBEAMapper

        if awards_df is None or awards_df.empty:
            metadata.warnings.append("No awards data provided for crosswalk")
            return ToolResult(data=pd.DataFrame(), metadata=metadata)

        metadata.upstream_tools.extend(["extract_awards", "classify_cet"])

        mapper_kwargs: dict[str, Any] = {}
        if mapping_path:
            mapper_kwargs["mapping_path"] = mapping_path
        if bea_excel_path:
            mapper_kwargs["bea_excel_path"] = bea_excel_path

        mapper = NAICSToBEAMapper(**mapper_kwargs)

        df = awards_df.copy()

        # Map each NAICS code
        mapped_count = 0
        unmapped_count = 0
        ambiguous_count = 0
        bea_sectors = []

        for _, row in df.iterrows():
            naics = str(row.get(naics_column, "")).strip()
            if not naics or naics == "nan":
                bea_sectors.append(None)
                unmapped_count += 1
                continue

            result = mapper.map_code(naics)
            if result is None:
                bea_sectors.append(None)
                unmapped_count += 1
            elif isinstance(result, list):
                # Ambiguous: multiple BEA codes match
                bea_sectors.append(result[0] if result else None)
                ambiguous_count += 1
                mapped_count += 1
            else:
                bea_sectors.append(result)
                mapped_count += 1

        df["bea_sector"] = bea_sectors

        # Populate metadata
        total = len(df)
        metadata.record_count = total
        metadata.data_sources.append(
            DataSourceRef(
                name="BEA Industry Concordance",
                url="https://bea.gov",
                version="2024",
                record_count=total,
                access_method="crosswalk_csv",
            )
        )

        if unmapped_count > 0:
            pct = round(100 * unmapped_count / total, 1)
            metadata.warnings.append(
                f"{unmapped_count} ({pct}%) NAICS codes could not be mapped to BEA sectors"
            )
        if ambiguous_count > 0:
            pct = round(100 * ambiguous_count / total, 1)
            metadata.warnings.append(
                f"{ambiguous_count} ({pct}%) NAICS codes mapped ambiguously — "
                f"first BEA match selected; LLM tiebreaker recommended"
            )

        result_data = {
            "awards": df,
            "mapping_stats": {
                "total": total,
                "mapped": mapped_count,
                "unmapped": unmapped_count,
                "ambiguous": ambiguous_count,
                "mapping_rate": round(mapped_count / total, 4) if total > 0 else 0.0,
            },
        }

        return ToolResult(data=result_data, metadata=metadata)
