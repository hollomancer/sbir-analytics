# sbir-etl/src/enrichers/usaspending_enricher.py
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

import pandas as pd

try:
    from rapidfuzz import fuzz, process
except ImportError:
    # Fallback to simple string matching if rapidfuzz not available
    fuzz = None
    process = None


def normalize_recipient_name(name: str | None) -> str:
    """
    Normalize recipient/company name for matching:
    - Lowercase
    - Remove punctuation
    - Normalize common suffixes
    - Collapse whitespace
    """
    if not name:
        return ""
    s = str(name).strip().lower()
    # Replace punctuation with spaces
    import re

    s = re.sub(r"[^\w\s]", " ", s)
    # Normalize common business suffixes
    s = re.sub(
        r"\b(incorporated|incorporation|inc|corp|corporation|llc|ltd|limited|co|company)\b", "", s
    )
    s = re.sub(r"\s+", " ", s).strip()
    return s


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

    # Match each SBIR award
    for idx, row in sbir.iterrows():
        # Try UEI exact match
        uei = str(row.get(sbir_uei_col, "")).strip().upper()
        if uei and uei in recipient_by_uei:
            sbir.at[idx, "_usaspending_recipient_idx"] = recipient_by_uei[uei]
            sbir.at[idx, "_usaspending_match_score"] = 100
            sbir.at[idx, "_usaspending_match_method"] = "uei-exact"
            continue

        # Try DUNS exact match
        duns = "".join(ch for ch in str(row.get(sbir_duns_col, "")) if ch.isdigit())
        if duns and duns in recipient_by_duns:
            sbir.at[idx, "_usaspending_recipient_idx"] = recipient_by_duns[duns]
            sbir.at[idx, "_usaspending_match_score"] = 100
            sbir.at[idx, "_usaspending_match_method"] = "duns-exact"
            continue

        # Fuzzy name matching
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
                    sbir.at[idx, "_usaspending_match_candidates"] = json.dumps(candidates)

                if candidates:
                    best = candidates[0]
                    if best["score"] >= high_threshold:
                        sbir.at[idx, "_usaspending_recipient_idx"] = best["idx"]
                        sbir.at[idx, "_usaspending_match_score"] = best["score"]
                        sbir.at[idx, "_usaspending_match_method"] = "name-fuzzy-auto"
                    elif best["score"] >= low_threshold:
                        sbir.at[idx, "_usaspending_match_score"] = best["score"]
                        sbir.at[idx, "_usaspending_match_method"] = "name-fuzzy-candidate"
                    else:
                        sbir.at[idx, "_usaspending_match_score"] = best["score"]
                        sbir.at[idx, "_usaspending_match_method"] = "name-fuzzy-low"

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
