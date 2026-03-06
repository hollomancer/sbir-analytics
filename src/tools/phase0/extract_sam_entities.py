"""
Extract SAM.gov entity registration data.

Wraps the existing SAMGovExtractor to pull entity registration from SAM.gov
public extract: UEI, DUNS, NAICS, size standard, address, status.

UEI is the primary key for entity resolution. Without it, cross-source
matching degrades to fuzzy name matching.

Data source: SAM.gov public entity extract (sam.gov)
Access method: Parquet file (bulk download) or S3
Refresh cadence: Daily
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger

from ..base import BaseTool, DataSourceRef, ToolMetadata, ToolResult


class ExtractSAMEntitiesTool(BaseTool):
    """Pull SAM.gov entity registrations: UEI, DUNS, NAICS, size, address, status.

    This tool provides the authoritative UEI source for entity resolution.
    Every company in the SBIR ecosystem should be linkable through SAM.gov
    registration data.
    """

    name = "extract_sam_entities"
    version = "1.0.0"

    def execute(
        self,
        metadata: ToolMetadata,
        parquet_path: str | Path | None = None,
        use_s3_first: bool | None = None,
        filter_active: bool = False,
        filter_naics: list[str] | None = None,
        filter_states: list[str] | None = None,
    ) -> ToolResult:
        """Extract SAM.gov entities with optional filtering.

        Args:
            metadata: Pre-initialized metadata to populate
            parquet_path: Override path to SAM.gov parquet file
            use_s3_first: Whether to try S3 before local. None = use config
            filter_active: If True, return only active registrations
            filter_naics: Filter to entities with these NAICS codes (prefix match)
            filter_states: Filter to entities in these states

        Returns:
            ToolResult with DataFrame of SAM.gov entity records
        """
        from src.extractors.sam_gov import SAMGovExtractor

        extractor = SAMGovExtractor()

        # Load the parquet data
        df = extractor.load_parquet(
            parquet_path=Path(parquet_path) if parquet_path else None,
            use_s3_first=use_s3_first,
        )

        initial_count = len(df)

        # Apply filters
        if filter_active and "registration_status" in df.columns:
            df = df[df["registration_status"].str.upper() == "ACTIVE"]
            logger.info(f"Active filter: {initial_count} → {len(df)} entities")

        if filter_naics and "naics_code" in df.columns:
            mask = pd.Series(False, index=df.index)
            for prefix in filter_naics:
                mask |= df["naics_code"].astype(str).str.startswith(prefix)
            df = df[mask]
            logger.info(f"NAICS filter ({filter_naics}): → {len(df)} entities")

        if filter_states and "physical_address_state" in df.columns:
            states_upper = [s.upper() for s in filter_states]
            df = df[df["physical_address_state"].str.upper().isin(states_upper)]
            logger.info(f"State filter ({filter_states}): → {len(df)} entities")

        # Populate metadata
        metadata.data_sources.append(
            DataSourceRef(
                name="SAM.gov Entity Data",
                url="https://sam.gov",
                version=datetime.utcnow().strftime("%Y-%m-%d"),
                record_count=len(df),
                access_method="parquet_bulk",
            )
        )
        metadata.record_count = len(df)

        if initial_count > 0 and len(df) == 0:
            metadata.warnings.append("All records filtered out — check filter parameters")

        return ToolResult(data=df, metadata=metadata)
