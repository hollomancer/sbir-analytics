"""Dagster assets for SAM.gov data ingestion pipeline.

Data Source Priority:
1. PRIMARY: Parquet file (S3 or local)
2. FALLBACK: SAM.gov API (if parquet unavailable)
3. FAIL: If both sources fail
"""

from pathlib import Path
from typing import Any

import pandas as pd
from dagster import AssetExecutionContext, MetadataValue, Output, asset

from sbir_etl.config.loader import get_config
from sbir_etl.exceptions import ExtractionError
from sbir_etl.extractors.sam_gov import SAMGovExtractor
from sbir_etl.utils.cloud_storage import find_latest_sam_gov_parquet

from ._ingestion_utils import _resolve_tiered_path, stamp_provenance


def _import_sam_gov_entities(
    context: AssetExecutionContext,
) -> Output[pd.DataFrame]:
    """
    Helper to import SAM.gov entities with parquet-first, API-fallback strategy.

    Priority:
    1. Try the configured local parquet file
    2. Try discovery under the data root
    3. Fall back to API if parquet fails
    4. Fail if all sources fail
    """
    config = get_config()
    sam_config = config.extraction.sam_gov
    parquet_path, discovered_parquet = _resolve_tiered_path(
        context,
        discover=find_latest_sam_gov_parquet,
        local_path_getter=lambda: Path(sam_config.parquet_path),
        label="SAM.gov parquet",
    )

    # Try to load from parquet if available
    parquet_success = False
    df = None

    if parquet_path:
        context.log.info(
            "Starting SAM.gov entity extraction from parquet",
            extra={
                "parquet_path": str(parquet_path),
                "source": "discovered_parquet" if discovered_parquet else "local_parquet",
            },
        )

        try:
            extractor = SAMGovExtractor()
            df = extractor.load_parquet(
                parquet_path,
                columns=SAMGovExtractor.ENRICHMENT_COLUMNS,
            )
            parquet_success = True
            context.log.info("Successfully loaded SAM.gov entities from parquet")
        except Exception as e:
            context.log.warning(f"Parquet load failed: {e}")
            parquet_success = False

    # FALLBACK: If parquet failed, try API
    if not parquet_success:
        context.log.warning("Parquet file unavailable, falling back to SAM.gov API (FALLBACK)")
        try:
            # Note: API fallback would need to fetch all entities, which is not practical
            # SAMGovAPIClient is available but not used for bulk data fallback
            # For now, we'll raise an error to indicate bulk data is required
            context.log.error(
                "API fallback not yet implemented for bulk entity data. Parquet file is required."
            )
            raise ExtractionError(
                "SAM.gov data unavailable: Parquet file failed and API fallback not implemented for bulk data",
                component="assets.sam_gov_ingestion",
                operation="import_entities",
                details={
                    "discovery_attempted": discovered_parquet is not None,
                    "parquet_path_attempted": str(parquet_path) if parquet_path else None,
                    "local_path_attempted": sam_config.parquet_path,
                },
            )
        except ImportError:
            context.log.error("SAM.gov API client not available")
            raise ExtractionError(
                "SAM.gov data unavailable: Parquet file failed and API client not available",
                component="assets.sam_gov_ingestion",
                operation="import_entities",
                details={"parquet_path": str(parquet_path) if parquet_path else None},
            )

    # FAIL: If parquet failed and no API fallback available
    if not parquet_success or df is None:
        raise ExtractionError(
            "Failed to import SAM.gov entities: Parquet file unavailable and no fallback",
            component="assets.sam_gov_ingestion",
            operation="import_parquet",
            details={
                "parquet_path": str(parquet_path) if parquet_path else None,
                "local_path": sam_config.parquet_path,
                "discovered_parquet": discovered_parquet,
            },
        )

    context.log.info(
        "SAM.gov entity extraction complete",
        extra={
            "row_count": len(df),
            "column_count": len(df.columns),
            "source": "parquet",
        },
    )

    # Stamp data source provenance on every record
    stamp_provenance(df, "sam.gov", str(discovered_parquet or parquet_path))

    # Create metadata
    metadata: dict[str, Any] = {
        "row_count": len(df),
        "num_columns": len(df.columns),
        "columns": MetadataValue.json(list(df.columns[:20])),  # First 20 columns
        "preview": MetadataValue.md(df.head(10).to_markdown()),
        "key_columns": MetadataValue.json(
            [
                "unique_entity_id",
                "cage_code",
                "legal_business_name",
                "primary_naics",
            ]
        ),
    }

    return Output(value=df, metadata=metadata)


@asset(
    description="SAM.gov entity records loaded from parquet file",
    group_name="extraction",
    compute_kind="parquet",
)
def raw_sam_gov_entities(context: AssetExecutionContext) -> Output[pd.DataFrame]:
    """
    Load SAM.gov entity records from parquet file.

    Data Source Priority:
    1. PRIMARY: local parquet file, then discovery under the data root
    2. FALLBACK: Local parquet file (from config.extraction.sam_gov.parquet_path)
    3. FAIL: If parquet unavailable (API fallback not implemented for bulk data)

    Returns:
        pandas DataFrame with SAM.gov entity records
    """
    return _import_sam_gov_entities(context)
