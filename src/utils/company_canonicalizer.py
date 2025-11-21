"""Company canonicalization utilities for pre-loading deduplication."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import pandas as pd

from ..enrichers.company_enricher import enrich_awards_with_companies
from ..utils.text_normalization import normalize_company_name


def canonicalize_companies_from_awards(
    awards_df: pd.DataFrame,
    *,
    high_threshold: int = 90,
    low_threshold: int = 75,
    enhanced_config: dict[str, Any] | None = None,
) -> dict[str, str]:
    """
    Pre-deduplicate companies using fuzzy matching to create canonical company IDs.

    Strategy:
    1. Extract unique companies from awards
    2. Use company_enricher to match companies against themselves (self-enrichment)
    3. Create canonical mapping: original_key -> canonical_key
    4. Prefer UEI > DUNS > normalized_name for canonical ID

    Args:
        awards_df: DataFrame of awards with company information
        high_threshold: Auto-merge matches >= this score (default 90)
        low_threshold: Flag for review matches >= this score (default 75)
        enhanced_config: Enhanced matching configuration

    Returns:
        Mapping from original company_id -> canonical company_id
    """
    # Extract unique companies from awards
    companies_data = []
    seen_keys = set()

    for _, award in awards_df.iterrows():
        company_name = award.get("company_name") or award.get("company", "")
        uei = award.get("company_uei") or award.get("uei")
        duns = award.get("company_duns") or award.get("duns")

        # Create unique key for deduplication
        if uei:
            key = f"UEI:{uei}"
        elif duns:
            key = f"DUNS:{duns}"
        else:
            normalized = normalize_company_name(company_name)
            key = f"NAME:{normalized}"

        if key not in seen_keys:
            seen_keys.add(key)
            companies_data.append(
                {
                    "company": company_name,
                    "UEI": uei or "",
                    "Duns": duns or "",
                    "_original_key": key,
                }
            )

    if not companies_data:
        return {}

    companies_df = pd.DataFrame(companies_data)

    # Self-enrichment: match companies against themselves
    enriched = enrich_awards_with_companies(
        companies_df,
        companies_df,
        award_company_col="company",
        company_name_col="company",
        uei_col="UEI",
        duns_col="Duns",
        high_threshold=high_threshold,
        low_threshold=low_threshold,
        return_candidates=False,
        enhanced_config=enhanced_config,
    )

    # Build canonical mapping
    canonical_map = {}
    canonical_groups = defaultdict(list)

    for _idx, row in enriched.iterrows():
        original_key = row["_original_key"]
        matched_idx = row.get("_matched_company_idx")
        match_score = row.get("_match_score", 0)

        # Determine canonical ID (prefer UEI > DUNS > NAME)
        if row["UEI"]:
            canonical_id = f"UEI:{row['UEI']}"
        elif row["Duns"]:
            canonical_id = f"DUNS:{row['Duns']}"
        else:
            normalized = normalize_company_name(row["company"])
            canonical_id = f"NAME:{normalized}"

        # If matched to another company with high confidence, use that canonical ID
        if matched_idx is not None and match_score >= high_threshold:
            matched_row = companies_df.iloc[matched_idx]
            # Use matched company's canonical ID (prefer UEI > DUNS > NAME)
            if matched_row["UEI"]:
                canonical_id = f"UEI:{matched_row['UEI']}"
            elif matched_row["Duns"]:
                canonical_id = f"DUNS:{matched_row['Duns']}"
            else:
                matched_normalized = normalize_company_name(matched_row["company"])
                canonical_id = f"NAME:{matched_normalized}"

        canonical_map[original_key] = canonical_id
        canonical_groups[canonical_id].append(original_key)

    return canonical_map
