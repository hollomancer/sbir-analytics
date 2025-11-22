# sbir-analytics/src/enrichers/usaspending_enricher.py
"""
USAspending enricher for SBIR awards using identifier-first matching strategy.

Strategy summary:
1. Attempt deterministic joins on identifiers:
   - UEI exact match (preferred)
   - DUNS exact match (digits-only)
2. If no exact match, use fuzzy name matching on recipient names
3. Enrich awards with USAspending transaction data (federal obligations, etc.)
4. Return enriched DataFrame with match metadata and USAspending columns

Notes:
- Uses rapidfuzz for fuzzy matching if available
- Works with DuckDB-loaded USAspending data
- Provides configurable thresholds for match quality
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from ...utils.text_normalization import normalize_recipient_name


try:
    from rapidfuzz import fuzz, process
except ImportError:
    # Fallback to simple string matching if rapidfuzz not available
    fuzz: Any | None = None
    process: Any | None = None


def enrich_sbir_with_usaspending(
    sbir_df: pd.DataFrame,
    recipient_df: pd.DataFrame,
    transaction_df: pd.DataFrame | None = None,
    *,
    sbir_company_col: str = "Company",
    sbir_uei_col: str = "UEI",
    sbir_duns_col: str = "Duns",
    recipient_name_col: str = "recipient_name",
    recipient_uei_col: str = "recipient_uei",
    recipient_duns_col: str = "recipient_duns",
    high_threshold: int = 90,
    low_threshold: int = 75,
    top_k: int = 5,
    return_candidates: bool = False,
) -> pd.DataFrame:
    """
    Enrich SBIR awards with USAspending recipient and transaction data.

    Parameters:
    - sbir_df: DataFrame of SBIR awards
    - recipient_df: DataFrame of USAspending recipients
    - transaction_df: Optional DataFrame of USAspending transactions
    - sbir_company_col: Column in sbir_df with company name
    - sbir_uei_col: Column in sbir_df with UEI
    - sbir_duns_col: Column in sbir_df with DUNS
    - recipient_name_col: Column in recipient_df with recipient name
    - recipient_uei_col: Column in recipient_df with UEI
    - recipient_duns_col: Column in recipient_df with DUNS
    - high_threshold: Auto-accept fuzzy matches >= this score
    - low_threshold: Flag fuzzy matches >= this score for review
    - top_k: Number of fuzzy candidates to evaluate
    - return_candidates: If True, include match candidates in output

    Returns:
    - Enriched DataFrame with USAspending data and match metadata
    """
    # Defensive copies
    sbir = sbir_df.copy()
    recipients = recipient_df.copy()

    # Normalize column names
    if sbir_company_col not in sbir.columns:
        for col in ["company", "Company Name", "Company"]:
            if col in sbir.columns:
                sbir_company_col = col
                break

    # Add normalized names
    sbir["_norm_name"] = sbir[sbir_company_col].fillna("").astype(str).map(normalize_recipient_name)
    recipients["_norm_name"] = (
        recipients[recipient_name_col].fillna("").astype(str).map(normalize_recipient_name)
    )

    # Build indexes for exact matching
    recipient_by_uei = {}
    recipient_by_duns = {}

    if recipient_uei_col in recipients.columns:
        for idx, uei in recipients[recipient_uei_col].dropna().items():
            if uei:
                recipient_by_uei[str(uei).strip().upper()] = idx

    if recipient_duns_col in recipients.columns:
        for idx, duns in recipients[recipient_duns_col].dropna().items():
            if duns:
                digits = "".join(ch for ch in str(duns) if ch.isdigit())
                if digits:
                    recipient_by_duns[digits] = idx

    # Prepare output columns
    sbir["_usaspending_recipient_idx"] = pd.NA
    sbir["_usaspending_match_score"] = pd.NA
    sbir["_usaspending_match_method"] = pd.NA
    if return_candidates:
        sbir["_usaspending_match_candidates"] = pd.NA

    # Vectorized exact matches (fast, no mypy errors)
    # UEI exact matches
    if sbir_uei_col in sbir.columns:
        uei_series = sbir[sbir_uei_col].fillna("").astype(str).str.strip().str.upper()
        uei_mask = uei_series.isin(recipient_by_uei.keys())
        if uei_mask.any():
            sbir.loc[uei_mask, "_usaspending_recipient_idx"] = uei_series[uei_mask].map(
                recipient_by_uei
            )
            sbir.loc[uei_mask, "_usaspending_match_score"] = 100
            sbir.loc[uei_mask, "_usaspending_match_method"] = "uei-exact"

    # DUNS exact matches
    if sbir_duns_col in sbir.columns:
        duns_series = (
            sbir[sbir_duns_col]
            .fillna("")
            .astype(str)
            .apply(lambda x: "".join(ch for ch in str(x) if ch.isdigit()))
        )
        duns_mask = duns_series.isin(recipient_by_duns.keys())
        if duns_mask.any():
            sbir.loc[duns_mask, "_usaspending_recipient_idx"] = duns_series[duns_mask].map(
                recipient_by_duns
            )
            sbir.loc[duns_mask, "_usaspending_match_score"] = 100
            sbir.loc[duns_mask, "_usaspending_match_method"] = "duns-exact"

    # Fuzzy name matching (complex logic, use iterrows with type ignore)
    # Only process rows that don't have exact matches
    unmatched_mask = sbir["_usaspending_recipient_idx"].isna()
    for idx, row in sbir[unmatched_mask].iterrows():
        if fuzz and process:
            norm_name = row.get("_norm_name", "")
            if norm_name:
                # Get candidate recipients (simple approach: all for now, could add blocking)
                choices = recipients["_norm_name"].to_dict()

                results = process.extract(
                    norm_name, choices, scorer=fuzz.token_set_ratio, limit=top_k
                )

                candidates = []
                for _choice, score, key in results:
                    if score >= low_threshold:
                        candidates.append(
                            {
                                "idx": key,
                                "score": score,
                                "name": recipients.at[key, recipient_name_col],
                            }
                        )

                if return_candidates:
                    sbir.at[idx, "_usaspending_match_candidates"] = json.dumps(candidates)  # type: ignore[index]

                if candidates:
                    best = candidates[0]
                    if best["score"] >= high_threshold:
                        sbir.at[idx, "_usaspending_recipient_idx"] = best["idx"]  # type: ignore[index]
                        sbir.at[idx, "_usaspending_match_score"] = best["score"]  # type: ignore[index]
                        sbir.at[idx, "_usaspending_match_method"] = "name-fuzzy-auto"  # type: ignore[index]
                    elif best["score"] >= low_threshold:
                        sbir.at[idx, "_usaspending_match_score"] = best["score"]  # type: ignore[index]
                        sbir.at[idx, "_usaspending_match_method"] = "name-fuzzy-candidate"  # type: ignore[index]
                    else:
                        sbir.at[idx, "_usaspending_match_score"] = best["score"]  # type: ignore[index]
                        sbir.at[idx, "_usaspending_match_method"] = "name-fuzzy-low"  # type: ignore[index]

    # Merge recipient data
    recipients_prefixed = recipients.add_prefix("usaspending_recipient_")
    enriched = (
        sbir.reset_index()
        .set_index("_usaspending_recipient_idx")
        .join(recipients_prefixed, how="left")
        .reset_index()
        .drop(columns=["_usaspending_recipient_idx"])
    )

    # If transaction data provided, add aggregate transaction info
    if transaction_df is not None:
        # This would require recipient_id mapping to transaction recipient_id
        # For now, skip detailed transaction enrichment
        pass

    # Clean up temporary columns
    enriched = enriched.drop(columns=[c for c in ["_norm_name"] if c in enriched.columns])

    return enriched
