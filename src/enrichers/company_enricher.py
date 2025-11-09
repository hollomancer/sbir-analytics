# sbir-etl/src/enrichers/company_enricher.py
"""
Company enricher using fuzzy matching (rapidfuzz) with identifier-first strategy.

Strategy summary:
1. Attempt deterministic joins:
   - UEI exact match (preferred)
   - DUNS exact match (digits-only)
2. If no deterministic match, generate a small candidate set via blocking
   (by normalized name prefix and optionally by state/zip) and apply fuzzy
   scoring using rapidfuzz's token_set_ratio.
3. Use configurable high/low thresholds to auto-accept or flag matches for review.
4. Return a copy of the awards DataFrame with enrichment columns and
   match metadata (_matched_company_idx, _match_score, _match_method,
   _match_candidates).

Notes:
- rapidfuzz must be installed in the runtime environment for best quality
  fuzzy matching: `pip install rapidfuzz`.
- The module is intentionally dependency-light besides pandas + rapidfuzz.
- Keep audit fields (score and method) so downstream logic can decide how to
  treat lower-confidence matches.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence

import pandas as pd

from ..exceptions import ValidationError
from ..utils.text_normalization import normalize_company_name


try:
    from rapidfuzz import fuzz, process
except Exception as e:  # pragma: no cover - defensive runtime behavior
    raise ImportError(
        "rapidfuzz is required for the company enricher. Install via `pip install rapidfuzz`."
    ) from e


def _coerce_int(value: object) -> int | None:
    """Best-effort conversion to int without propagating errors."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# -------------------------
# Normalization / blocking
# -------------------------
# Note: normalize_company_name() is now imported from utils.text_normalization


def build_block_key(name_norm: str, prefix_len: int = 2) -> str:
    """
    Simple blocking key: the first `prefix_len` characters of the normalized name.
    Returns empty string for empty names.
    """
    if not name_norm:
        return ""
    return name_norm[:prefix_len]


# -------------------------
# Candidate indexing
# -------------------------


def _build_company_indexes(
    companies_df: pd.DataFrame,
    company_name_col: str = "company",
    uei_col: str = "UEI",
    duns_col: str = "Duns",
    state_col: str | None = None,
    zip_col: str | None = None,
    prefix_len: int = 2,
) -> dict[str, dict]:
    """
    Precompute indexes used by the enricher:
      - comp_by_uei: mapping UEI -> company index
      - comp_by_duns: mapping digits-only DUNS -> company index
      - blocks: mapping block_key -> list of company indices
      - norm_name: normalized name series stored on index

    Returns a dictionary containing these structures.
    """
    df = companies_df.copy()
    # Ensure unique index for companies (use the original index)
    df = df.reset_index().set_index("index")

    # Normalized name and block key
    norm_series = df[company_name_col].fillna("").astype(str).map(normalize_company_name)
    block_series = norm_series.map(lambda n: build_block_key(n, prefix_len))

    # UEI exact mapping (uppercased)
    comp_by_uei: dict[str, int] = {}
    if uei_col in df.columns:
        for idx, v in df[uei_col].dropna().items():
            key = str(v).strip().upper()
            if key:
                comp_by_uei[key] = idx

    # DUNS exact mapping (digits-only)
    comp_by_duns: dict[str, int] = {}
    if duns_col in df.columns:
        for idx, v in df[duns_col].dropna().items():
            digits = "".join(ch for ch in str(v) if ch.isdigit())
            if digits:
                comp_by_duns[digits] = idx

    # Blocks dict: block_key -> list of indices
    blocks: dict[str, list[int]] = {}
    for idx, blk in block_series.items():
        blocks.setdefault(blk, []).append(idx)

    indexes = {
        "df": df,
        "norm_name": norm_series,
        "block": block_series,
        "comp_by_uei": comp_by_uei,
        "comp_by_duns": comp_by_duns,
        "blocks": blocks,
    }
    return indexes


# -------------------------
# Enrichment core function
# -------------------------


def enrich_awards_with_companies(
    awards_df: pd.DataFrame,
    companies_df: pd.DataFrame,
    *,
    award_company_col: str = "company",
    company_name_col: str = "company",
    uei_col: str = "UEI",
    duns_col: str = "Duns",
    state_col: str | None = None,
    zip_col: str | None = None,
    prefix_len: int = 2,
    high_threshold: int = 90,
    low_threshold: int = 75,
    top_k: int = 3,
    scorer=fuzz.token_set_ratio,
    return_candidates: bool = False,
) -> pd.DataFrame:
    """
    Enrich awards DataFrame with company-level attributes using rapidfuzz fuzzy matching.

    Parameters:
    - awards_df: DataFrame of award rows (must include award_company_col)
    - companies_df: DataFrame of company rows (must include company_name_col)
    - award_company_col: column in awards_df containing company name to match
    - company_name_col: column in companies_df with company names
    - uei_col / duns_col: optional identifier columns for exact matching
    - prefix_len: length of normalized prefix used for blocking
    - high_threshold: accept match when score >= this
    - low_threshold: mark candidate for review when score >= low_threshold
    - top_k: number of fuzzy candidates to evaluate and optionally return
    - scorer: rapidfuzz scoring function (defaults to token_set_ratio)
    - return_candidates: if True, attach a JSON of top candidates in `_match_candidates`

    Returns:
    - enriched DataFrame (copy) with:
      - merged company columns prefixed with `company_` where matches were accepted
      - match metadata columns in the awards DataFrame:
        `_matched_company_idx`, `_match_score`, `_match_method`, optionally `_match_candidates`
    """
    # Fallback detection for common header name synonyms.
    # If the caller provided a column name that is not present, attempt to locate
    # a reasonable alternative in the provided DataFrames.
    if award_company_col not in awards_df.columns:
        for cand in ("Company", "company", "Company Name"):
            if cand in awards_df.columns:
                award_company_col = cand
                break

    if company_name_col not in companies_df.columns:
        for cand in ("Company Name", "company", "Company"):
            if cand in companies_df.columns:
                company_name_col = cand
                break

    # If either column is still missing after attempted fallbacks, raise a clear error.
    if award_company_col not in awards_df.columns:
        raise ValidationError(
            f"award_company_col '{award_company_col}' not in awards_df",
            component="enricher.company",
            operation="enrich_companies",
            details={
                "award_company_col": award_company_col,
                "available_columns": list(awards_df.columns),
            },
        )
    if company_name_col not in companies_df.columns:
        raise ValidationError(
            f"company_name_col '{company_name_col}' not in companies_df",
            component="enricher.company",
            operation="enrich_companies",
            details={
                "company_name_col": company_name_col,
                "available_columns": list(companies_df.columns),
            },
        )

    # Defensive copies
    awards = awards_df.copy()
    companies = companies_df.copy()

    # Create canonical company/name and company_url columns to smooth differences
    # between various CSV header names ("Company" vs "Company Name",
    # "Company Website" vs "Company URL").
    # Award-side canonical company column
    if "company" not in awards.columns:
        if award_company_col in awards.columns:
            awards["company"] = awards[award_company_col].astype(str)
        else:
            awards["company"] = ""

    # Company-side canonical company column
    if "company" not in companies.columns:
        if company_name_col in companies.columns:
            companies["company"] = companies[company_name_col].astype(str)
        else:
            # fallback to first available column
            companies["company"] = (
                companies.iloc[:, 0].astype(str) if len(companies.columns) > 0 else ""
            )

    # Canonical company URL column detection + normalization
    if "company_url" not in awards.columns:
        for cand in ("Company Website", "Company URL", "company_website", "company url"):
            if cand in awards.columns:
                awards["company_url"] = awards[cand].replace("", pd.NA)
                break
        else:
            awards["company_url"] = pd.NA

    if "company_url" not in companies.columns:
        for cand in ("Company URL", "Company Website", "company_website", "company url"):
            if cand in companies.columns:
                companies["company_url"] = companies[cand].replace("", pd.NA)
                break
        else:
            companies["company_url"] = pd.NA

    # Add normalized name helpers (used for blocking / matching later)
    if "_norm_name" not in companies.columns:
        companies["_norm_name"] = companies["company"].astype(str).map(normalize_company_name)
    if "_norm_name" not in awards.columns:
        awards["_norm_name"] = awards["company"].astype(str).map(normalize_company_name)

    # Build indexes
    idx = _build_company_indexes(
        companies,
        company_name_col=company_name_col,
        uei_col=uei_col,
        duns_col=duns_col,
        state_col=state_col,
        zip_col=zip_col,
        prefix_len=prefix_len,
    )
    comp_df = idx["df"]
    comp_norm = idx["norm_name"]
    comp_blocks = idx["blocks"]
    comp_by_uei = idx["comp_by_uei"]
    comp_by_duns = idx["comp_by_duns"]

    # Prepare award normalization
    awards["_norm_name"] = awards[award_company_col].astype(str).map(normalize_company_name)
    awards["_block"] = awards["_norm_name"].map(lambda n: build_block_key(n, prefix_len))

    # Prepare output columns
    awards["_matched_company_idx"] = pd.NA
    awards["_match_score"] = pd.NA
    awards["_match_method"] = pd.NA
    if return_candidates:
        awards["_match_candidates"] = pd.NA

    # Precompute global choices mapping (index -> normalized name) for fallback
    global_choices: dict[int, str] = comp_norm.to_dict()

    # For each award row, try exact matches first, then fuzzy candidates
    for ai, arow in awards.iterrows():
        # Exact UEI match
        award_uei = str(arow.get(uei_col) or "").strip().upper()
        if award_uei:
            comp_idx = comp_by_uei.get(award_uei)
            if comp_idx is not None:
                awards.at[ai, "_matched_company_idx"] = comp_idx
                awards.at[ai, "_match_score"] = 100
                awards.at[ai, "_match_method"] = "uei-exact"
                continue

        # Exact DUNS match
        award_duns = "".join(ch for ch in str(arow.get(duns_col) or "") if ch.isdigit())
        if award_duns:
            comp_idx = comp_by_duns.get(award_duns)
            if comp_idx is not None:
                awards.at[ai, "_matched_company_idx"] = comp_idx
                awards.at[ai, "_match_score"] = 100
                awards.at[ai, "_match_method"] = "duns-exact"
                continue

        # Candidate generation via blocking
        blk = arow.get("_block") or ""
        candidate_idxs: Sequence[int] = comp_blocks.get(blk, [])
        # If block produced no candidates, optionally fall back to a short global sample:
        if not candidate_idxs:
            # Fallback: use entire set but that can be expensive; we use a small heuristic:
            # choose companies whose normalized name shares first token with award
            award_norm = arow.get("_norm_name") or ""
            first_token = award_norm.split(" ", 1)[0] if award_norm else ""
            small_candidates = []
            if first_token:
                for idx_c, nm in global_choices.items():
                    if nm.startswith(first_token):
                        small_candidates.append(idx_c)
                        if len(small_candidates) >= 500:
                            break
            candidate_idxs = small_candidates or list(global_choices.keys())

        # Build mapping for rapidfuzz choices: idx -> normalized name
        choices = {int(ci): comp_norm.at[ci] for ci in candidate_idxs if ci in comp_norm.index}

        # Use rapidfuzz.process.extract to get top_k candidate scores
        norm_target = arow.get("_norm_name") or ""
        if not norm_target:
            continue  # nothing to match
        # process.extract expects a mapping candidate -> string; returns tuples (candidate, score, _)
        results: list[tuple] = process.extract(
            norm_target,
            choices,
            scorer=scorer,
            processor=None,
            limit=top_k,
        )

        # Convert results to simple list: (idx, score).
        # rapidfuzz.process.extract can return tuples in a couple of shapes depending
        # on the `choices` argument: often (choice_value, score, key) where `key`
        # is the original key from the choices mapping, but sometimes (choice_value, score).
        # Our `choices` is a mapping idx -> normalized_name, so we handle both forms and
        # perform a reverse lookup when necessary.
        simple_results: list[tuple[int, int]] = []
        if results:
            # build reverse lookup from normalized name -> index for fallback
            reverse_map = {v: k for k, v in choices.items()}
            for r in results:
                try:
                    # Typical tuple: (choice_value, score, key)
                    if len(r) >= 3:
                        candidate_value = r[0]
                        score = int(r[1])
                        key = r[2]
                        candidate_idx = None
                        if key in choices:
                            candidate_idx = _coerce_int(key)
                        elif candidate_value in reverse_map:
                            candidate_idx = int(reverse_map[candidate_value])
                        if candidate_idx is None:
                            candidate_idx = _coerce_int(key) or _coerce_int(candidate_value)
                        if candidate_idx is None:
                            continue
                        simple_results.append((candidate_idx, score))
                    else:
                        # Fallback tuple shape: (choice_value, score)
                        candidate_value = r[0]
                        score = int(r[1])
                        if candidate_value in reverse_map:
                            candidate_idx = int(reverse_map[candidate_value])
                        else:
                            candidate_idx = _coerce_int(candidate_value)
                        if candidate_idx is None:
                            continue
                        simple_results.append((candidate_idx, score))
                except (TypeError, ValueError):
                    # Defensive: skip malformed result entries
                    continue

        # Store candidates if requested
        if return_candidates:
            awards.at[ai, "_match_candidates"] = json.dumps(
                [{"idx": r[0], "score": r[1], "name": choices[r[0]]} for r in simple_results],
                ensure_ascii=False,
            )

        # Choose best
        if not simple_results:
            continue
        best_idx, best_score = simple_results[0]

        if best_score >= high_threshold:
            awards.at[ai, "_matched_company_idx"] = best_idx
            awards.at[ai, "_match_score"] = best_score
            awards.at[ai, "_match_method"] = "fuzzy-auto"
        elif best_score >= low_threshold:
            awards.at[ai, "_match_score"] = best_score
            awards.at[ai, "_match_method"] = "fuzzy-candidate"
        else:
            awards.at[ai, "_match_score"] = best_score
            awards.at[ai, "_match_method"] = "fuzzy-low"

    # Merge matched company columns into awards (flattened) using company_ prefix
    # comp_df has index equal to original companies index (via reset_index in _build_company_indexes)
    comp_prefixed = comp_df.add_prefix("company_")
    # Ensure the _matched_company_idx column exists prior to the join. In some
    # code paths (e.g. when early continues occur) it may not have been created,
    # which would cause a KeyError during set_index(). Create it defensively.
    if "_matched_company_idx" not in awards.columns:
        awards["_matched_company_idx"] = pd.NA
    # The comp_df index is original company indices: we'll join on that.
    enriched = (
        awards.reset_index()
        .set_index("_matched_company_idx")
        .join(comp_prefixed, how="left")
        .reset_index()
    )

    # Clean up temporary normalization/block columns
    enriched = enriched.drop(columns=[c for c in ["_norm_name", "_block"] if c in enriched.columns])

    return enriched


# -------------------------
# End of module
# -------------------------
