"""SAM.gov data extractor for parquet files.

This module provides functionality to extract SAM.gov entity data from parquet files.
Reads parquet files from local disk, with discovery under the data root.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger

from ..config.loader import get_config
from ..utils.cloud_storage import find_latest_sam_gov_parquet, resolve_data_path


class SAMGovExtractor:
    """Extractor for SAM.gov entity data from parquet files."""

    def __init__(self, config=None):
        """Initialize the extractor.

        Args:
            config: Optional PipelineConfig. If None, loads from get_config().
        """
        self.config = config or get_config()
        self.sam_config = self.config.extraction.sam_gov

    # Columns used downstream by enrichment (UEI/DUNS index + merge columns).
    # Loading only these instead of all columns cuts memory 50-80%.
    ENRICHMENT_COLUMNS: list[str] = [
        "unique_entity_id",
        "legal_business_name",
        "dba_name",
        "physical_address_line_1",
        "physical_address_line_2",
        "physical_address_city",
        "physical_address_state",
        "physical_address_zip_postal_code",
        "cage_code",
        "primary_naics",
        "naics_code_string",
        "duns_number",
    ]

    def load_parquet(
        self,
        parquet_path: Path | str | None = None,
        *,
        columns: list[str] | None = None,
    ) -> pd.DataFrame:
        """
        Load SAM.gov entity records from parquet file.

        Args:
            parquet_path: Path to parquet file. If None, uses config.
            columns: Specific columns to load (reduces memory). If None, loads all columns.
                     Use SAMGovExtractor.ENRICHMENT_COLUMNS for standard enrichment.

        Returns:
            pandas DataFrame with SAM.gov entity records

        Raises:
            FileNotFoundError: If parquet file not found
        """
        if parquet_path is None:
            parquet_path = self.sam_config.parquet_path

        # Fall back to discovery under the data root when the configured path
        # is absent, so a dated parquet still resolves.
        resolved_path: Path | None = None
        try:
            discovered = find_latest_sam_gov_parquet()
            resolved_path = resolve_data_path(
                parquet_path or "",
                local_fallback=Path(discovered) if discovered else None,
            )
        except FileNotFoundError:
            resolved_path = Path(parquet_path) if parquet_path else None

        if not resolved_path or not resolved_path.exists():
            raise FileNotFoundError(
                f"SAM.gov parquet file not found: {resolved_path or parquet_path}"
            )

        logger.info(f"Loading SAM.gov parquet from: {resolved_path}")
        read_kwargs: dict[str, Any] = {}
        if columns:
            # Only request columns that exist in the file (parquet metadata check)
            try:
                import pyarrow.parquet as pq

                schema = pq.read_schema(resolved_path)
                available = set(schema.names)
                read_kwargs["columns"] = [c for c in columns if c in available]
                skipped = set(columns) - available
                if skipped:
                    logger.debug(f"Requested columns not in parquet: {skipped}")
            except Exception:
                # Fall back to letting pandas handle missing columns
                read_kwargs["columns"] = columns

        df = pd.read_parquet(resolved_path, **read_kwargs)

        logger.info(f"Loaded {len(df):,} SAM.gov entity records with {len(df.columns)} columns")

        return df

    def get_entity_by_uei(self, df: pd.DataFrame, uei: str) -> pd.Series | None:
        """
        Get entity record by UEI (Unique Entity Identifier).

        Args:
            df: DataFrame with SAM.gov entities
            uei: Unique Entity Identifier

        Returns:
            Series with entity data, or None if not found
        """
        matches = df[df["unique_entity_id"] == uei]
        return matches.iloc[0] if len(matches) > 0 else None

    def get_entity_by_cage(self, df: pd.DataFrame, cage: str) -> pd.Series | None:
        """
        Get entity record by CAGE code.

        Args:
            df: DataFrame with SAM.gov entities
            cage: CAGE code

        Returns:
            Series with entity data, or None if not found
        """
        matches = df[df["cage_code"] == cage]
        return matches.iloc[0] if len(matches) > 0 else None

    def get_entities_by_duns(self, df: pd.DataFrame, duns: str) -> pd.DataFrame:
        """
        Get entity records by DUNS number.

        Note: DUNS may not be a direct column in SAM.gov data (UEI replaced DUNS).
        This method searches for DUNS in various identifier fields.

        Args:
            df: DataFrame with SAM.gov entities
            duns: DUNS number

        Returns:
            DataFrame with matching entities
        """
        # SAM.gov uses UEI now, but some records may have legacy DUNS references
        # Search in tax_identifier_number or other fields if available
        # For now, return empty if DUNS column doesn't exist
        if "duns" in df.columns:
            return df[df["duns"] == duns]
        # If no DUNS column, return empty DataFrame
        return pd.DataFrame()
