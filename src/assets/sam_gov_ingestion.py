"""Dagster assets for SAM.gov data ingestion pipeline.

Data Source Priority:
1. PRIMARY: Parquet file (S3 or local)
2. FALLBACK: SAM.gov API (if parquet unavailable)
3. FAIL: If both sources fail
"""

from pathlib import Path

import pandas as pd
from dagster import AssetExecutionContext, MetadataValue, Output, asset

from ..config.loader import get_config
from ..exceptions import ExtractionError
from ..extractors.sam_gov import SAMGovExtractor
from ..utils.cloud_storage import find_latest_sam_gov_parquet, resolve_data_path


def _import_sam_gov_entities(
    context: AssetExecutionContext,
) -> Output[pd.DataFrame]:
    """
    Helper to import SAM.gov entities with parquet-first, API-fallback strategy.

    Priority:
    1. Try S3 parquet file (primary)
    2. Try local parquet file (fallback)
    3. Fall back to API if parquet fails
    4. Fail if all sources fail
    """
    config = get_config()
    sam_config = config.extraction.sam_gov

    # PRIMARY: Try S3 parquet file first
    parquet_path = None
    s3_bucket = config.s3.get("bucket") if hasattr(config, "s3") else None

    if s3_bucket and sam_config.use_s3_first:
        context.log.info("Attempting to load SAM.gov data from S3 (PRIMARY)")
        s3_parquet_url = find_latest_sam_gov_parquet(bucket=s3_bucket)

        if s3_parquet_url:
            try:
                # Resolve S3 path (downloads to temp if needed)
                parquet_path = resolve_data_path(s3_parquet_url)
                context.log.info(f"Using S3 parquet: {s3_parquet_url} -> {parquet_path}")
            except Exception as e:
                context.log.warning(f"S3 parquet resolution failed: {e}")
                parquet_path = None

    # FALLBACK: Try local parquet file
    if not parquet_path:
        try:
            local_path = Path(sam_config.parquet_path)
            if local_path.exists():
                parquet_path = local_path
                context.log.info(f"Using local parquet: {parquet_path}")
            else:
                context.log.warning(f"Local parquet not found: {local_path}")
                parquet_path = None
        except Exception as e:
            context.log.warning(f"Local parquet path check failed: {e}")
            parquet_path = None

    # Try to load from parquet if available
    parquet_success = False
    df = None

    if parquet_path:
        context.log.info(
            "Starting SAM.gov entity extraction from parquet",
            extra={
                "parquet_path": str(parquet_path),
                "source": "S3_parquet" if s3_bucket else "local_parquet",
            },
        )

        try:
            extractor = SAMGovExtractor()
            df = extractor.load_parquet(parquet_path, use_s3_first=False)
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
                    "s3_attempted": s3_bucket is not None,
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
                "s3_bucket": s3_bucket,
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

    # Create metadata
    metadata = {
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
    1. PRIMARY: S3 parquet file (if configured and use_s3_first=True)
    2. FALLBACK: Local parquet file (from config.extraction.sam_gov.parquet_path)
    3. FAIL: If parquet unavailable (API fallback not implemented for bulk data)

    Returns:
        pandas DataFrame with SAM.gov entity records
    """
    return _import_sam_gov_entities(context)
