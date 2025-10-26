"""Dagster assets for SBIR-USAspending enrichment pipeline."""

import pandas as pd
from dagster import (
    AssetExecutionContext,
    AssetIn,
    MetadataValue,
    Output,
    asset,
)

from ..config.loader import get_config
from ..enrichers.usaspending_enricher import enrich_sbir_with_usaspending


@asset(
    description="SBIR awards enriched with USAspending recipient data",
    group_name="enrichment",
    compute_kind="pandas",
)
def enriched_sbir_awards(
    context: AssetExecutionContext,
    validated_sbir_awards: pd.DataFrame,
    usaspending_recipient_lookup: pd.DataFrame,
) -> Output[pd.DataFrame]:
    """
    Enrich validated SBIR awards with USAspending recipient data.

    Args:
        validated_sbir_awards: Validated SBIR awards DataFrame
        usaspending_recipient_lookup: USAspending recipient lookup data

    Returns:
        Enriched SBIR awards with USAspending data and match metadata
    """
    config = get_config()

    context.log.info(
        "Starting SBIR-USAspending enrichment",
        extra={
            "sbir_records": len(validated_sbir_awards),
            "usaspending_recipients": len(usaspending_recipient_lookup),
        },
    )

    # Perform enrichment
    enriched_df = enrich_sbir_with_usaspending(
        sbir_df=validated_sbir_awards,
        recipient_df=usaspending_recipient_lookup,
        sbir_company_col="Company",
        sbir_uei_col="UEI",
        sbir_duns_col="Duns",
        recipient_name_col="usaspending_recipient_recipient_name",
        recipient_uei_col="usaspending_recipient_recipient_uei",
        recipient_duns_col="usaspending_recipient_recipient_duns",
        high_threshold=90,
        low_threshold=75,
        return_candidates=True,
    )

    # Calculate enrichment statistics
    total_awards = len(enriched_df)
    matched_awards = enriched_df["_usaspending_match_method"].notna().sum()
    exact_matches = enriched_df["_usaspending_match_method"].str.contains("exact", na=False).sum()
    fuzzy_matches = enriched_df["_usaspending_match_method"].str.contains("fuzzy", na=False).sum()

    match_rate = matched_awards / total_awards if total_awards > 0 else 0

    context.log.info(
        "Enrichment complete",
        extra={
            "total_awards": total_awards,
            "matched_awards": matched_awards,
            "exact_matches": exact_matches,
            "fuzzy_matches": fuzzy_matches,
            "match_rate": f"{match_rate:.1%}",
        },
    )

    # Create metadata
    metadata = {
        "num_records": len(enriched_df),
        "match_rate": f"{match_rate:.1%}",
        "matched_awards": matched_awards,
        "exact_matches": exact_matches,
        "fuzzy_matches": fuzzy_matches,
        "enrichment_columns": [
            col for col in enriched_df.columns if col.startswith("usaspending_")
        ],
        "preview": MetadataValue.md(enriched_df.head(10).to_markdown()),
    }

    return Output(value=enriched_df, metadata=metadata)


@asset(
    description="SBIR-USAspending enrichment quality report",
    group_name="enrichment",
    compute_kind="pandas",
)
def sbir_usaspending_enrichment_report(
    context: AssetExecutionContext, enriched_sbir_awards: pd.DataFrame
) -> Output[dict]:
    """
    Generate quality report for SBIR-USAspending enrichment.

    Args:
        enriched_sbir_awards: Enriched SBIR awards DataFrame

    Returns:
        Enrichment quality report
    """
    # Analyze match quality
    match_methods = enriched_sbir_awards["_usaspending_match_method"].value_counts(dropna=False)

    # Score distribution for fuzzy matches
    fuzzy_scores = enriched_sbir_awards[
        enriched_sbir_awards["_usaspending_match_method"].str.contains("fuzzy", na=False)
    ]["_usaspending_match_score"]

    score_bins = pd.cut(fuzzy_scores, bins=[0, 75, 85, 90, 95, 100], right=False)
    score_distribution = score_bins.value_counts().sort_index()

    # Unmatched awards analysis
    unmatched = enriched_sbir_awards[enriched_sbir_awards["_usaspending_match_method"].isna()]
    unmatched_with_identifiers = unmatched[(unmatched["UEI"].notna()) | (unmatched["Duns"].notna())]

    report = {
        "total_awards": len(enriched_sbir_awards),
        "matched_awards": match_methods.sum() - match_methods.get("NaN", 0),
        "match_rate": (match_methods.sum() - match_methods.get("NaN", 0))
        / len(enriched_sbir_awards),
        "match_methods": match_methods.to_dict(),
        "fuzzy_score_distribution": score_distribution.to_dict(),
        "unmatched_with_identifiers": len(unmatched_with_identifiers),
        "unmatched_total": len(unmatched),
    }

    context.log.info(
        "Enrichment report generated",
        extra={
            "match_rate": f"{report['match_rate']:.1%}",
            "matched_awards": report["matched_awards"],
            "unmatched_with_identifiers": report["unmatched_with_identifiers"],
        },
    )

    # Create metadata
    metadata = {
        "match_rate": f"{report['match_rate']:.1%}",
        "matched_awards": report["matched_awards"],
        "unmatched_awards": report["unmatched_total"],
        "match_methods": MetadataValue.json(report["match_methods"]),
        "fuzzy_score_distribution": MetadataValue.json(report["fuzzy_score_distribution"]),
    }

    return Output(value=report, metadata=metadata)
