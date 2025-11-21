"""SAM.gov data extractor for parquet files.

This module provides functionality to extract SAM.gov entity data from parquet files.
Supports both local and S3-stored parquet files with automatic path resolution.
"""

from pathlib import Path

import pandas as pd
from loguru import logger

from ..config.loader import get_config
from ..utils.cloud_storage import resolve_data_path


class SAMGovExtractor:
    """Extractor for SAM.gov entity data from parquet files."""

    def __init__(self):
        """Initialize the extractor."""
        self.config = get_config()
        self.sam_config = self.config.extraction.sam_gov

    def load_parquet(
        self,
        parquet_path: Path | str | None = None,
        *,
        use_s3_first: bool | None = None,
    ) -> pd.DataFrame:
        """
        Load SAM.gov entity records from parquet file.

        Args:
            parquet_path: Path to parquet file (local or S3 URL). If None, uses config.
            use_s3_first: Whether to try S3 first. If None, uses config setting.

        Returns:
            pandas DataFrame with SAM.gov entity records

        Raises:
            FileNotFoundError: If parquet file not found
        """
        if parquet_path is None:
            parquet_path = self.sam_config.parquet_path

        if use_s3_first is None:
            use_s3_first = self.sam_config.use_s3_first

        # Build S3 path if configured
        s3_url = None
        if use_s3_first:
            s3_bucket = self.config.s3.get("bucket") if hasattr(self.config, "s3") else None
            if s3_bucket:
                # Try to find latest in S3
                from ..utils.cloud_storage import find_latest_sam_gov_parquet

                s3_url = find_latest_sam_gov_parquet(bucket=s3_bucket)
                if s3_url:
                    logger.info(f"Found SAM.gov parquet in S3: {s3_url}")

        # Resolve path (handles S3 download if needed)
        resolved_path: Path | None = None
        if s3_url:
            try:
                resolved_path = resolve_data_path(
                    s3_url,
                    local_fallback=Path(parquet_path) if parquet_path else None,
                )
                logger.info(f"Using S3 file: {s3_url} -> {resolved_path}")
            except Exception as e:
                logger.warning(f"S3 resolution failed: {e}, falling back to local")
                resolved_path = Path(parquet_path) if parquet_path else None
        else:
            resolved_path = Path(parquet_path) if parquet_path else None

        if not resolved_path or not resolved_path.exists():
            raise FileNotFoundError(
                f"SAM.gov parquet file not found: {resolved_path or parquet_path}"
            )

        logger.info(f"Loading SAM.gov parquet from: {resolved_path}")
        df = pd.read_parquet(resolved_path)

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
