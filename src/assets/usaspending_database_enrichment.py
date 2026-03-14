"""Dagster assets for USAspending database dump enrichment.

This module processes USAspending PostgreSQL database dumps stored in S3
to extract and enrich SBIR award data with transaction-level details.
"""

import pandas as pd
from dagster import AssetExecutionContext, MetadataValue, Output, asset
from loguru import logger

from ..config.loader import get_config
from ..exceptions import ExtractionError
from ..extractors.usaspending import DuckDBUSAspendingExtractor
from ..models.sbir_identification import ALL_SBIR_ALNS, EXCLUSIVE_SBIR_ALNS, SBIR_RESEARCH_CODES
from ..utils.cloud_storage import find_latest_usaspending_dump, get_s3_bucket_from_env


def _table_has_column(
    extractor: DuckDBUSAspendingExtractor,
    table_name: str,
    column_name: str,
) -> bool:
    """Check whether *table_name* has a column called *column_name*."""
    try:
        info = extractor.get_table_info(table_name)
        columns = info.get("columns", [])
        return any(
            col.get("column_name", "").lower() == column_name.lower() for col in columns
        )
    except Exception:
        return False


@asset(
    description="SBIR-relevant transactions from USAspending database dump",
    group_name="usaspending_database",
    compute_kind="duckdb",
)
def sbir_relevant_usaspending_transactions(
    context: AssetExecutionContext,
) -> Output[pd.DataFrame]:
    """
    Extract SBIR-relevant transactions from USAspending database dump.

    This asset:
    1. Loads the USAspending database dump from S3 (or local fallback)
    2. Filters transactions for SBIR-relevant agencies and programs
    3. Extracts transaction details for SBIR companies
    4. Returns enriched transaction data for Neo4j loading

    Filtering criteria:
    - Federal agencies with SBIR programs (DOD, NASA, NSF, NIH, DOE, etc.)
    - NAICS codes common for SBIR companies
    - Contract types typical for SBIR awards

    Returns:
        DataFrame with SBIR-relevant USAspending transactions
    """
    config = get_config()

    # PRIMARY: Get dump file path from S3 (required)
    s3_bucket = get_s3_bucket_from_env()

    if not s3_bucket:
        raise ExtractionError(
            "S3 bucket not configured. Set S3_BUCKET or SBIR_ANALYTICS_S3_BUCKET env var.",
            component="assets.usaspending_database_enrichment",
            operation="resolve_dump_path",
            details={"env_checked": ["S3_BUCKET", "SBIR_ANALYTICS_S3_BUCKET"]},
        )

    # Find the latest dump file in S3
    # Format: raw/usaspending/database/YYYY-MM-DD/usaspending-db_YYYYMMDD.zip
    # Prefer test database for faster processing, fallback to full
    dump_path = find_latest_usaspending_dump(
        bucket=s3_bucket, database_type="test"
    ) or find_latest_usaspending_dump(bucket=s3_bucket, database_type="full")

    if not dump_path:
        # FALLBACK: Try API if S3 dump not available
        context.log.warning("No S3 dump found. Attempting API fallback (limited functionality)...")
        # Note: API fallback would need custom implementation for transaction queries
        # For now, fail with clear error
        raise ExtractionError(
            "USAspending database dump not found in S3. "
            "S3 dump is required for transaction-level queries. "
            "API fallback is not available for this operation.",
            component="assets.usaspending_database_enrichment",
            operation="resolve_dump_path",
            details={
                "s3_bucket": s3_bucket,
                "s3_prefix": "raw/usaspending/database/",
                "database_types_checked": ["test", "full"],
            },
        )

    context.log.info(f"Using latest S3 dump (PRIMARY): {dump_path}")

    context.log.info(
        "Extracting SBIR-relevant transactions from USAspending dump",
        extra={"dump_path": str(dump_path)},
    )

    # Initialize DuckDB extractor
    extractor = DuckDBUSAspendingExtractor(db_path=config.duckdb.database_path)

    # Import transaction_normalized table
    table_name = "transaction_normalized"
    success = extractor.import_postgres_dump(dump_path, table_name)
    if not success:
        raise ExtractionError(
            "Failed to import USAspending dump",
            component="assets.usaspending_database_enrichment",
            operation="import_dump",
            details={"dump_path": str(dump_path), "table_name": table_name},
        )

    physical_table = extractor.resolve_physical_table_name(table_name)
    context.log.info(f"Resolved physical table: {physical_table}")

    # Check if the FPDS 'research' column exists in this table.
    # The 'research' field (Element 10Q) is the authoritative SBIR/STTR
    # indicator: SR1-SR3 for SBIR, ST1-ST3 for STTR.
    has_research_col = _table_has_column(extractor, physical_table, "research")

    if has_research_col:
        context.log.info(
            "FPDS 'research' column detected — using authoritative SBIR/STTR filter "
            f"(codes: {', '.join(sorted(SBIR_RESEARCH_CODES))})"
        )
    else:
        context.log.warning(
            "FPDS 'research' column not found in table — falling back to "
            "agency + NAICS + dollar-cap heuristic filter"
        )

    # Build the WHERE clause based on available columns
    research_codes_sql = ",".join(f"'{c}'" for c in sorted(SBIR_RESEARCH_CODES))

    if has_research_col:
        # PRIMARY: Use the authoritative FPDS research field
        where_clause = f"""
        WHERE research IN ({research_codes_sql})
          AND federal_action_obligation > 0
        """
        select_extra = ",\n        research"
    else:
        # FALLBACK: Heuristic filter (agency + NAICS + dollar cap)
        sbir_agencies = [
            "Department of Defense", "DOD",
            "Department of Energy", "DOE",
            "National Aeronautics and Space Administration", "NASA",
            "National Science Foundation", "NSF",
            "Department of Health and Human Services", "HHS",
            "NIH", "National Institutes of Health",
            "Department of Agriculture", "USDA",
            "Department of Commerce", "DOC", "NOAA",
            "Department of Homeland Security", "DHS",
            "Department of Transportation", "DOT",
            "Environmental Protection Agency", "EPA",
            "Department of Education", "ED",
        ]
        agencies_sql = ",".join(f"'{a}'" for a in sbir_agencies)

        where_clause = f"""
        WHERE
            (
                awarding_agency_name IN ({agencies_sql})
                OR funding_agency_name IN ({agencies_sql})
            )
            AND (
                naics_code LIKE '5417%'
                OR naics_code LIKE '3254%'
                OR naics_code LIKE '3341%'
                OR naics_code LIKE '3364%'
                OR naics_code LIKE '5112%'
            )
            AND federal_action_obligation <= 2500000
            AND federal_action_obligation > 0
        """
        select_extra = ""

    query = f"""
    SELECT
        transaction_id,
        action_date,
        fiscal_year,
        award_id_fain as award_id,
        recipient_name,
        recipient_uei,
        recipient_duns,
        awarding_agency_name,
        awarding_sub_agency_name,
        funding_agency_name,
        federal_action_obligation,
        total_obligated_amount,
        award_description,
        naics_code,
        naics_description,
        type_of_contract_pricing,
        type_description as transaction_type,
        business_categories,
        place_of_performance_city,
        place_of_performance_state,
        place_of_performance_zip,
        awarding_office_name{select_extra}
    FROM {physical_table}
    {where_clause}
    LIMIT 1000000
    """

    try:
        context.log.info("Executing SBIR filter query...")
        df = extractor.connect().execute(query).fetchdf()
        context.log.info(f"Extracted {len(df)} SBIR-relevant transactions")
    except Exception as e:
        logger.error(f"Query failed: {e}")
        raise ExtractionError(
            "Failed to query USAspending transactions",
            component="assets.usaspending_database_enrichment",
            operation="query_transactions",
            details={"error": str(e)},
        )

    # Data quality checks
    if df.empty:
        context.log.warning("No SBIR-relevant transactions found in dump")
        return Output(value=df, metadata={"row_count": 0})  # type: ignore[arg-type]

    # Compute metadata
    total_obligation = (
        df["federal_action_obligation"].sum() if "federal_action_obligation" in df.columns else 0
    )
    unique_recipients = df["recipient_uei"].nunique() if "recipient_uei" in df.columns else 0
    unique_agencies = (
        df["awarding_agency_name"].nunique() if "awarding_agency_name" in df.columns else 0
    )

    metadata = {
        "row_count": len(df),
        "unique_recipients": unique_recipients,
        "unique_agencies": unique_agencies,
        "total_obligation": f"${total_obligation:,.2f}",
        "sbir_filter_method": "fpds_research_field" if has_research_col else "heuristic",
        "date_range": f"{df['action_date'].min()} to {df['action_date'].max()}"
        if "action_date" in df.columns
        else "N/A",
        "preview": MetadataValue.md(df.head(10).to_markdown()),
    }

    context.log.info(
        "SBIR transaction extraction complete",
        extra={
            "transactions": len(df),
            "recipients": unique_recipients,
            "agencies": unique_agencies,
        },
    )

    return Output(value=df, metadata=metadata)  # type: ignore[arg-type]


@asset(
    description="USAspending recipients enriched with SBIR company matches",
    group_name="usaspending_database",
    compute_kind="duckdb",
    deps=["enriched_sbir_awards"],
)
def sbir_company_usaspending_recipients(
    context: AssetExecutionContext,
    enriched_sbir_awards: pd.DataFrame,
) -> Output[pd.DataFrame]:
    """
    Extract USAspending recipient records for SBIR companies.

    This asset:
    1. Loads the recipient_lookup table from the dump
    2. Matches recipients to SBIR companies using UEI/DUNS
    3. Returns recipient details for Neo4j enrichment

    Args:
        enriched_sbir_awards: SBIR awards with company identifiers

    Returns:
        DataFrame with USAspending recipient details for SBIR companies
    """
    config = get_config()

    # PRIMARY: Get dump file path from S3 (required)
    s3_bucket = get_s3_bucket_from_env()

    if not s3_bucket:
        raise ExtractionError(
            "S3 bucket not configured. Set S3_BUCKET or SBIR_ANALYTICS_S3_BUCKET env var.",
            component="assets.usaspending_database_enrichment",
            operation="resolve_dump_path",
        )

    # Find the latest dump file in S3
    dump_path = find_latest_usaspending_dump(
        bucket=s3_bucket, database_type="test"
    ) or find_latest_usaspending_dump(bucket=s3_bucket, database_type="full")

    if not dump_path:
        raise ExtractionError(
            "USAspending database dump not found in S3. "
            "S3 dump is required for recipient lookup queries.",
            component="assets.usaspending_database_enrichment",
            operation="resolve_dump_path",
            details={"s3_bucket": s3_bucket},
        )

    context.log.info(f"Using latest S3 dump (PRIMARY): {dump_path}")

    context.log.info("Extracting recipients for SBIR companies")

    # Initialize DuckDB extractor
    extractor = DuckDBUSAspendingExtractor(db_path=config.duckdb.database_path)

    # Import recipient_lookup table (or similar)
    table_name = "recipient_lookup"
    success = extractor.import_postgres_dump(dump_path, table_name)
    if not success:
        raise ExtractionError(
            "Failed to import recipient table",
            component="assets.usaspending_database_enrichment",
            operation="import_recipients",
        )

    physical_table = extractor.resolve_physical_table_name(table_name)

    # Get unique UEIs and DUNS from SBIR awards
    uei_values = []
    duns_values = []

    for col in ["UEI", "uei", "company_uei", "recipient_uei"]:
        if col in enriched_sbir_awards.columns:
            uei_values.extend(enriched_sbir_awards[col].dropna().unique().tolist())

    for col in ["Duns", "duns", "company_duns", "recipient_duns"]:
        if col in enriched_sbir_awards.columns:
            duns_values.extend(enriched_sbir_awards[col].dropna().unique().tolist())

    uei_values = list(set(uei_values))[:10000]  # Limit for performance
    duns_values = list(set(duns_values))[:10000]

    context.log.info(f"Matching {len(uei_values)} UEIs and {len(duns_values)} DUNS")

    # Query recipients matching SBIR companies
    if uei_values:
        uei_list = ",".join(f"'{v}'" for v in uei_values)
        query = f"""
        SELECT DISTINCT
            recipient_hash,
            recipient_name,
            recipient_uei,
            recipient_duns,
            parent_recipient_hash,
            parent_recipient_name,
            parent_uei,
            parent_duns,
            business_types_codes,
            business_types_description
        FROM {physical_table}
        WHERE recipient_uei IN ({uei_list})
           OR recipient_duns IN ({",".join(f"'{v}'" for v in duns_values) if duns_values else "''"})
        LIMIT 100000
        """

        try:
            df = extractor.connect().execute(query).fetchdf()
            context.log.info(f"Found {len(df)} recipient records for SBIR companies")
        except Exception as e:
            logger.error(f"Recipient query failed: {e}")
            df = pd.DataFrame()
    else:
        context.log.warning("No UEI/DUNS values found in SBIR awards")
        df = pd.DataFrame()

    metadata = {
        "row_count": len(df),
        "sbir_uei_count": len(uei_values),
        "sbir_duns_count": len(duns_values),
        "match_rate": f"{len(df) / max(len(uei_values), 1) * 100:.1f}%",
    }

    return Output(value=df, metadata=metadata)  # type: ignore[arg-type]


@asset(
    description="SBIR/STTR grants identified via Assistance Listing Numbers in FABS data",
    group_name="usaspending_database",
    compute_kind="duckdb",
)
def sbir_grant_transactions(
    context: AssetExecutionContext,
) -> Output[pd.DataFrame]:
    """Extract SBIR/STTR grant awards from USAspending FABS data.

    Uses Assistance Listing Numbers (ALN, formerly CFDA) to identify SBIR/STTR
    financial assistance awards.  Two tiers of confidence:

    - **Exclusive ALNs** (e.g. 12.910 DoD SBIR): award is definitively SBIR/STTR.
    - **Shared ALNs** (e.g. 93.855 NIH NIAID): award *may* be SBIR/STTR;
      requires cross-reference with SBIR.gov or description parsing to confirm.

    Returns:
        DataFrame with SBIR/STTR grant transactions and identification metadata.
    """
    config = get_config()

    s3_bucket = get_s3_bucket_from_env()
    if not s3_bucket:
        raise ExtractionError(
            "S3 bucket not configured.",
            component="assets.usaspending_database_enrichment",
            operation="sbir_grants",
        )

    dump_path = find_latest_usaspending_dump(
        bucket=s3_bucket, database_type="test"
    ) or find_latest_usaspending_dump(bucket=s3_bucket, database_type="full")

    if not dump_path:
        raise ExtractionError(
            "USAspending database dump not found in S3.",
            component="assets.usaspending_database_enrichment",
            operation="sbir_grants",
            details={"s3_bucket": s3_bucket},
        )

    context.log.info(f"Extracting SBIR grants from dump: {dump_path}")

    extractor = DuckDBUSAspendingExtractor(db_path=config.duckdb.database_path)

    # FABS data lives in transaction_fabs or transaction_normalized
    # Try transaction_fabs first (has cfda_number), fall back to transaction_normalized
    table_candidate = "transaction_normalized"
    for candidate in ["transaction_fabs", "transaction_normalized"]:
        success = extractor.import_postgres_dump(dump_path, candidate)
        if success:
            table_candidate = candidate
            break
    else:
        raise ExtractionError(
            "Failed to import FABS transaction table from dump.",
            component="assets.usaspending_database_enrichment",
            operation="sbir_grants",
        )

    physical_table = extractor.resolve_physical_table_name(table_candidate)

    # Check for the cfda_number column
    has_cfda = _table_has_column(extractor, physical_table, "cfda_number")
    if not has_cfda:
        context.log.warning(
            "cfda_number column not found — cannot filter SBIR grants by ALN. "
            "Returning empty DataFrame."
        )
        return Output(
            value=pd.DataFrame(),
            metadata={"row_count": 0, "reason": "no_cfda_column"},  # type: ignore[arg-type]
        )

    # Build SQL with all known SBIR/STTR ALNs
    all_alns_sql = ",".join(f"'{a}'" for a in sorted(ALL_SBIR_ALNS))
    exclusive_alns_sql = ",".join(f"'{a}'" for a in sorted(EXCLUSIVE_SBIR_ALNS))

    query = f"""
    SELECT
        *,
        CASE
            WHEN cfda_number IN ({exclusive_alns_sql}) THEN 'exclusive'
            ELSE 'shared'
        END AS sbir_aln_confidence
    FROM {physical_table}
    WHERE cfda_number IN ({all_alns_sql})
      AND federal_action_obligation > 0
    LIMIT 500000
    """

    try:
        context.log.info(
            f"Querying FABS data for {len(ALL_SBIR_ALNS)} SBIR/STTR ALNs "
            f"({len(EXCLUSIVE_SBIR_ALNS)} exclusive)"
        )
        df = extractor.connect().execute(query).fetchdf()
        context.log.info(f"Found {len(df)} potential SBIR grant transactions")
    except Exception as e:
        logger.error(f"SBIR grant query failed: {e}")
        raise ExtractionError(
            "Failed to query SBIR grant transactions",
            component="assets.usaspending_database_enrichment",
            operation="sbir_grants",
            details={"error": str(e)},
        )

    if df.empty:
        return Output(value=df, metadata={"row_count": 0})  # type: ignore[arg-type]

    exclusive_count = int(
        (df["sbir_aln_confidence"] == "exclusive").sum()
        if "sbir_aln_confidence" in df.columns
        else 0
    )
    shared_count = len(df) - exclusive_count

    metadata = {
        "row_count": len(df),
        "exclusive_aln_matches": exclusive_count,
        "shared_aln_matches": shared_count,
        "alns_matched": sorted(df["cfda_number"].unique().tolist())
        if "cfda_number" in df.columns
        else [],
        "preview": MetadataValue.md(df.head(10).to_markdown()),
    }

    context.log.info(
        "SBIR grant extraction complete",
        extra={
            "total": len(df),
            "exclusive": exclusive_count,
            "shared": shared_count,
        },
    )

    return Output(value=df, metadata=metadata)  # type: ignore[arg-type]
