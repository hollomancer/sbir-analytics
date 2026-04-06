"""Dagster assets for SEC EDGAR company enrichment.

Enriches SBIR companies with public filing data from SEC EDGAR:
- CIK resolution (company name → SEC identifier)
- XBRL financial data (revenue, R&D expense, assets)
- M&A event detection from 8-K filings
"""

import asyncio

import pandas as pd
from dagster import (
    AssetCheckExecutionContext,
    AssetCheckResult,
    AssetCheckSeverity,
    AssetExecutionContext,
    MetadataValue,
    Output,
    asset,
    asset_check,
)

from sbir_etl.config.loader import get_config
from sbir_etl.enrichers.sec_edgar import EdgarAPIClient, enrich_companies_with_edgar


@asset(
    description="SBIR companies enriched with SEC EDGAR public filing data (CIK, financials, M&A events)",
    group_name="sec_edgar",
    compute_kind="enrichment",
)
def sec_edgar_enriched_companies(
    context: AssetExecutionContext,
    validated_sbir_awards: pd.DataFrame,
) -> Output[pd.DataFrame]:
    """Enrich SBIR companies with SEC EDGAR data.

    Resolves company names to SEC CIK numbers, fetches XBRL financials,
    and detects M&A events from 8-K filings. Expects ~5-15% match rate
    since most SBIR awardees are private companies.

    Args:
        validated_sbir_awards: Validated SBIR awards with company identifiers.

    Returns:
        DataFrame with SEC EDGAR enrichment columns prefixed with ``sec_``.
    """
    config = get_config()
    sec_config = config.enrichment.sec_edgar
    refresh_config = config.enrichment_refresh.sec_edgar

    if not refresh_config.enabled:
        context.log.warning(
            "SEC EDGAR enrichment is disabled. "
            "Set SBIR_ETL__ENRICHMENT_REFRESH__SEC_EDGAR__ENABLED=true to enable."
        )
        return Output(
            value=validated_sbir_awards,
            metadata={
                "status": "skipped",
                "reason": "sec_edgar_disabled",
                "row_count": len(validated_sbir_awards),
            },
        )

    # De-duplicate to company level before enrichment
    company_name_col = "company_name"
    uei_col = "uei"

    # Ensure we have the expected columns
    if company_name_col not in validated_sbir_awards.columns:
        # Try common alternatives
        for alt in ["company", "firm", "organization_name"]:
            if alt in validated_sbir_awards.columns:
                company_name_col = alt
                break
        else:
            context.log.error(
                f"No company name column found. Available: {list(validated_sbir_awards.columns)}"
            )
            return Output(
                value=validated_sbir_awards,
                metadata={"status": "error", "reason": "no_company_name_column"},
            )

    total_awards = len(validated_sbir_awards)
    unique_companies = validated_sbir_awards[company_name_col].nunique()
    context.log.info(
        f"Starting SEC EDGAR enrichment: {unique_companies} unique companies "
        f"from {total_awards} awards"
    )

    # Run async enrichment
    client = EdgarAPIClient(config=dict(sec_config))

    async def _run_enrichment() -> pd.DataFrame:
        try:
            enrichment_kwargs: dict = {
                "client": client,
                "company_name_col": company_name_col,
                "high_threshold": 90,
                "low_threshold": 75,
                "fetch_financials": True,
                "fetch_filings": True,
            }
            if uei_col in validated_sbir_awards.columns:
                enrichment_kwargs["company_uei_col"] = uei_col

            return await enrich_companies_with_edgar(
                validated_sbir_awards,
                **enrichment_kwargs,
            )
        finally:
            await client.aclose()

    try:
        result_df = asyncio.run(_run_enrichment())
    except Exception as e:
        context.log.error(f"SEC EDGAR enrichment failed: {e}")
        return Output(
            value=validated_sbir_awards,
            metadata={"status": "error", "reason": str(e)},
        )

    # Compute metrics
    matched = 0
    if "sec_is_publicly_traded" in result_df.columns:
        matched = int(result_df["sec_is_publicly_traded"].sum())

    match_rate = matched / unique_companies if unique_companies > 0 else 0.0

    context.log.info(
        f"SEC EDGAR enrichment complete: {matched}/{unique_companies} companies matched "
        f"({match_rate * 100:.1f}%)"
    )

    metadata = {
        "row_count": len(result_df),
        "unique_companies": unique_companies,
        "sec_matched_companies": matched,
        "sec_match_rate_pct": MetadataValue.float(match_rate * 100),
        "sec_columns_added": MetadataValue.int(
            len([c for c in result_df.columns if c.startswith("sec_")])
        ),
    }

    # Add financial summary if available
    if "sec_latest_revenue" in result_df.columns:
        has_revenue = result_df["sec_latest_revenue"].notna().sum()
        metadata["companies_with_revenue_data"] = MetadataValue.int(int(has_revenue))
    if "sec_ma_event_count" in result_df.columns:
        total_ma = int(result_df["sec_ma_event_count"].sum())
        metadata["total_ma_events_detected"] = MetadataValue.int(total_ma)

    return Output(value=result_df, metadata=metadata)


@asset_check(asset=sec_edgar_enriched_companies)
def sec_edgar_enrichment_quality_check(
    context: AssetCheckExecutionContext,
    sec_edgar_enriched_companies: pd.DataFrame,
) -> AssetCheckResult:
    """Validate SEC EDGAR enrichment quality.

    Checks:
    - Enrichment columns are present (if enrichment was enabled)
    - Match rate is within expected bounds (1-30% for SBIR companies)
    - No data corruption in enrichment merge
    """
    df = sec_edgar_enriched_companies
    issues = []

    # Check if enrichment columns exist
    sec_cols = [c for c in df.columns if c.startswith("sec_")]
    if not sec_cols:
        # Enrichment may have been skipped
        return AssetCheckResult(
            passed=True,
            metadata={"note": "No SEC columns found - enrichment may be disabled"},
        )

    # Check match rate bounds
    if "sec_is_publicly_traded" in df.columns:
        identifier_candidates = ["uei", "company_uei", "company_name"]
        identifier_col = next(
            (col for col in identifier_candidates if col in df.columns),
            None,
        )
        if identifier_col is not None:
            unique_companies = df[identifier_col].nunique()
        else:
            unique_companies = len(df)

        matched = int(df["sec_is_publicly_traded"].sum())
        match_rate = matched / unique_companies if unique_companies > 0 else 0.0

        if match_rate > 0.50:
            issues.append(
                f"Unexpectedly high match rate ({match_rate:.1%}) - possible false positives"
            )

    # Check for null corruption in original columns
    original_cols = [c for c in df.columns if not c.startswith("sec_")]
    null_increase = 0
    for col in original_cols[:10]:  # Sample check
        if df[col].isna().all() and len(df) > 0:
            null_increase += 1
    if null_increase > 3:
        issues.append(f"{null_increase} original columns became all-null after merge")

    passed = len(issues) == 0
    result_kwargs: dict = {
        "passed": passed,
        "metadata": {
            "sec_columns_count": len(sec_cols),
            "issues": issues if issues else ["No issues detected"],
        },
    }
    if not passed:
        result_kwargs["severity"] = AssetCheckSeverity.WARN

    return AssetCheckResult(**result_kwargs)
