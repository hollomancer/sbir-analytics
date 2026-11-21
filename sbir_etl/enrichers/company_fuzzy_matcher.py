"""Company fuzzy matcher using rapidfuzz with an identifier-first strategy.

Previously named ``company_enricher.py`` — renamed because "enricher"
is the generic term for every module in this package. This one does
pure local fuzzy matching of SBIR awards against a company master
list; it does not call any external APIs. For federal API lookups
(USAspending, SAM.gov, FPDS) see ``company_enrichment.py``.

Strategy summary:
1. Attempt deterministic joins:
   - UEI exact match (preferred)
   - DUNS exact match (digits-only)
2. Phonetic matching (if enabled):
   - Match phonetically similar names (e.g., "Smith" vs "Smyth")
3. If no deterministic match, generate a small candidate set via blocking
   (by normalized name prefix and optionally by state/zip) and apply fuzzy
   scoring using rapidfuzz's token_set_ratio or Jaro-Winkler.
4. Use configurable high/low thresholds to auto-accept or flag matches for review.
5. Return a copy of the awards DataFrame with enrichment columns and
   match metadata (_matched_company_idx, _match_score, _match_method,
   _match_candidates).

Enhanced features (configurable):
- Phonetic matching: Catches sound-alike misspellings
- Jaro-Winkler: Better for names with distinctive prefixes
- Enhanced abbreviations: Normalizes "Technologies" -> "tech", etc.

Notes:
- rapidfuzz must be installed in the runtime environment for best quality
  fuzzy matching: `pip install rapidfuzz`.
- The module is intentionally dependency-light besides pandas + rapidfuzz.
- Keep audit fields (score and method) so downstream logic can decide how to
  treat lower-confidence matches.

Epistemic tier: exploratory. Threshold-based fuzzy match acceptance is
contestable identity inference, not deterministic data movement, so its match
decisions are non-citable.
"""

from __future__ import annotations

import json
import re
from collections.abc import Hashable, Sequence
from numbers import Integral
from typing import Any, TypedDict, cast

import pandas as pd

from ..exceptions import ValidationError
from ..utils.text_normalization import normalize_name
from sbir_etl.identity import rapidfuzz_jaro_winkler_100, rapidfuzz_token_set_100
from sbir_etl.utils.identifiers import normalize_duns, normalize_uei


EPISTEMIC_TIER = "exploratory"


def _set_award_match(
    awards: pd.DataFrame,
    row_idx: Hashable,
    *,
    method: str,
    score: float | int,
    company_idx: int | None = None,
) -> None:
    """Update match-result columns on ``awards`` for a single iterrows key.

    Centralizes the ``awards.at[...]`` assignments so the pandas-stubs
    ``_AtIndexerFrame`` index-typing friction is suppressed in one place.
    """
    at = cast(Any, awards.at)
    if company_idx is not None:
        at[row_idx, "_matched_company_idx"] = company_idx
    at[row_idx, "_match_score"] = score
    at[row_idx, "_match_method"] = method


def _set_award_candidates(awards: pd.DataFrame, row_idx: Hashable, candidates_json: str) -> None:
    """Store candidate audit JSON without changing the match decision."""
    cast(Any, awards.at)[row_idx, "_match_candidates"] = candidates_json


try:
    from rapidfuzz import process
except ImportError as e:  # pragma: no cover - dependency contract
    raise ImportError(
        "rapidfuzz is required for the company enricher. Install via `pip install rapidfuzz`."
    ) from e

from .matching import get_phonetic_code

from sbir_etl.utils.coercion import _to_int as _coerce_int  # noqa: E402


class CompanyIndexes(TypedDict):
    """Typed indexes used by the matching stages."""

    df: pd.DataFrame
    norm_name: pd.Series
    block: pd.Series
    comp_by_uei: dict[str, int]
    comp_by_duns: dict[str, int]
    blocks: dict[str, list[int]]
    phonetic_by_code: dict[str, list[int]]


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
    enhanced_config: dict[str, Any] | None = None,
) -> CompanyIndexes:
    """
    Precompute indexes used by the enricher:
      - comp_by_uei: mapping UEI -> company index
      - comp_by_duns: mapping digits-only DUNS -> company index
      - blocks: mapping block_key -> list of company indices
      - norm_name: normalized name series stored on index
      - phonetic_codes: phonetic codes if phonetic matching enabled

    Args:
        enhanced_config: Enhanced matching configuration dict with keys:
            - enable_enhanced_abbreviations: bool
            - custom_abbreviations: dict
            - enable_phonetic_matching: bool
            - phonetic_algorithm: str

    Returns a dictionary containing these structures.
    """
    df = companies_df.copy()
    # Reset to a clean integer RangeIndex so downstream idx types are always int
    df = df.reset_index(drop=True)

    # Check for enhanced abbreviations config
    apply_abbrev = False
    custom_abbrev = None
    if enhanced_config:
        apply_abbrev = enhanced_config.get("enable_enhanced_abbreviations", False)
        custom_abbrev = enhanced_config.get("custom_abbreviations")

    # Normalized name and block key
    norm_series = (
        df[company_name_col]
        .fillna("")
        .astype(str)
        .map(
            lambda n: normalize_name(
                n,
                remove_suffixes=False,
                apply_abbreviations=apply_abbrev,
                abbreviations=custom_abbrev,
            )
        )
    )
    block_series = norm_series.map(lambda n: build_block_key(n, prefix_len))

    # UEI exact mapping (valid, non-placeholder UEIs only)
    comp_by_uei: dict[str, int] = {}
    if uei_col in df.columns:
        for idx, v in df[uei_col].dropna().items():
            key = _exact_uei_key(v)
            if key:
                comp_by_uei[key] = cast(int, idx)

    # DUNS exact mapping (valid, non-placeholder DUNS only)
    comp_by_duns: dict[str, int] = {}
    if duns_col in df.columns:
        for idx, v in df[duns_col].dropna().items():
            key = _exact_duns_key(v)
            if key:
                comp_by_duns[key] = cast(int, idx)

    # Blocks dict: block_key -> list of indices
    blocks: dict[str, list[int]] = {}
    for idx, blk in block_series.items():
        blocks.setdefault(blk, []).append(cast(int, idx))

    # Phonetic codes (if enabled)
    phonetic_by_code: dict[str, list[int]] = {}
    if enhanced_config and enhanced_config.get("enable_phonetic_matching", False):
        algo = enhanced_config.get("phonetic_algorithm", "metaphone")
        for idx, name in df[company_name_col].items():
            code = get_phonetic_code(str(name), algorithm=algo)
            if code:
                phonetic_by_code.setdefault(code, []).append(cast(int, idx))

    indexes: CompanyIndexes = {
        "df": df,
        "norm_name": norm_series,
        "block": block_series,
        "comp_by_uei": comp_by_uei,
        "comp_by_duns": comp_by_duns,
        "blocks": blocks,
        "phonetic_by_code": phonetic_by_code,
    }
    return indexes


# -------------------------
# Enrichment core function
# -------------------------


def _resolve_name_column(
    frame: pd.DataFrame,
    requested: str,
    *,
    fallbacks: Sequence[str],
    parameter_name: str,
    frame_name: str,
) -> str:
    """Resolve a requested name column or raise the public validation error."""
    if requested in frame.columns:
        return requested
    for candidate in fallbacks:
        if candidate in frame.columns:
            return candidate
    raise ValidationError(
        f"{parameter_name} '{requested}' not in {frame_name}",
        component="enricher.company",
        operation="enrich_companies",
        details={parameter_name: requested, "available_columns": list(frame.columns)},
    )


def _canonicalize_frames(
    awards_df: pd.DataFrame,
    companies_df: pd.DataFrame,
    *,
    award_company_col: str,
    company_name_col: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Copy inputs and add the canonical company and URL columns."""
    awards = awards_df.copy()
    companies = companies_df.copy()

    if "company" not in awards.columns:
        awards["company"] = awards[award_company_col].astype(str)
    if "company" not in companies.columns:
        companies["company"] = companies[company_name_col].astype(str)

    if "company_url" not in awards.columns:
        for candidate in ("Company Website", "Company URL", "company_website", "company url"):
            if candidate in awards.columns:
                awards["company_url"] = awards[candidate].replace("", pd.NA)
                break
        else:
            awards["company_url"] = pd.NA

    if "company_url" not in companies.columns:
        for candidate in ("Company URL", "Company Website", "company_website", "company url"):
            if candidate in companies.columns:
                companies["company_url"] = companies[candidate].replace("", pd.NA)
                break
        else:
            companies["company_url"] = pd.NA

    return awards, companies


def _normalize_company_series(series: pd.Series, enhanced_config: dict[str, Any]) -> pd.Series:
    """Normalize a company-name series with the configured abbreviation policy."""
    apply_abbreviations = enhanced_config.get("enable_enhanced_abbreviations", False)
    abbreviations = enhanced_config.get("custom_abbreviations")
    return series.astype(str).map(
        lambda name: normalize_name(
            name,
            remove_suffixes=False,
            apply_abbreviations=apply_abbreviations,
            abbreviations=abbreviations,
        )
    )


def _prepare_match_columns(
    awards: pd.DataFrame,
    companies: pd.DataFrame,
    *,
    award_company_col: str,
    prefix_len: int,
    return_candidates: bool,
    enhanced_config: dict[str, Any],
) -> None:
    """Add normalized inputs and empty audit columns in place."""
    if "_norm_name" not in companies.columns:
        companies["_norm_name"] = _normalize_company_series(companies["company"], enhanced_config)
    awards["_norm_name"] = _normalize_company_series(awards[award_company_col], enhanced_config)
    awards["_block"] = awards["_norm_name"].map(lambda name: build_block_key(name, prefix_len))
    awards["_matched_company_idx"] = pd.NA
    awards["_match_score"] = pd.NA
    awards["_match_method"] = pd.NA
    if return_candidates:
        awards["_match_candidates"] = pd.NA


def _is_placeholder(key: str) -> bool:
    """A key of one repeated character (000000000, 999999999) is a placeholder."""
    return len(set(key)) == 1


def _exact_uei_key(value: object) -> str | None:
    """Valid 12-character UEI usable as an exact-match key, else None."""
    key = normalize_uei(value)
    return None if key is None or _is_placeholder(key) else key


_DUNS_AS_DECIMAL_TEXT = re.compile(r"^\s*(\d{1,9})\.0+\s*$")


def _exact_duns_key(value: object) -> str | None:
    """Valid 9-digit DUNS usable as an exact-match key, else None.

    A DUNS read as a number (pandas without ``dtype=str``) loses its leading
    zeros and may carry ".0", so whole numbers are formatted back to 9 digits.
    A string such as "12345678.0" is that number written as text and gets the
    same treatment. A plain 8-digit string stays invalid: text sources keep
    leading zeros, so a short string is a truncated DUNS, not a number.
    """
    if isinstance(value, Integral) and not isinstance(value, bool):
        value = f"{int(value):09d}"
    elif isinstance(value, float) and value.is_integer():
        value = f"{int(value):09d}"
    elif isinstance(value, str) and (whole := _DUNS_AS_DECIMAL_TEXT.match(value)):
        value = f"{int(whole.group(1)):09d}"
    key = normalize_duns(value)
    return None if key is None or _is_placeholder(key) else key


def _apply_exact_identifier_matches(
    awards: pd.DataFrame,
    *,
    uei_col: str,
    duns_col: str,
    comp_by_uei: dict[str, int],
    comp_by_duns: dict[str, int],
) -> None:
    """Apply vectorized UEI and DUNS matches in place."""
    if uei_col in awards.columns:
        uei_series = awards[uei_col].map(_exact_uei_key)
        uei_mask = uei_series.notna() & uei_series.isin(comp_by_uei)
        if uei_mask.any():
            awards.loc[uei_mask, "_matched_company_idx"] = uei_series[uei_mask].map(comp_by_uei)
            awards.loc[uei_mask, "_match_score"] = 100
            awards.loc[uei_mask, "_match_method"] = "uei-exact"

    if duns_col in awards.columns:
        duns_series = awards[duns_col].map(_exact_duns_key)
        duns_mask = duns_series.notna() & duns_series.isin(comp_by_duns)
        if duns_mask.any():
            awards.loc[duns_mask, "_matched_company_idx"] = duns_series[duns_mask].map(comp_by_duns)
            awards.loc[duns_mask, "_match_score"] = 100
            awards.loc[duns_mask, "_match_method"] = "duns-exact"


def _candidate_choices(
    award_row: pd.Series,
    *,
    comp_blocks: dict[str, list[int]],
    comp_norm: pd.Series,
    global_choices: dict[int, str],
) -> dict[int, str]:
    """Return the blocked candidate mapping for one unmatched award."""
    block = award_row.get("_block") or ""
    candidate_indices: Sequence[int] = comp_blocks.get(block, [])
    if not candidate_indices:
        award_norm = award_row.get("_norm_name") or ""
        first_token = award_norm.split(" ", 1)[0] if award_norm else ""
        small_candidates: list[int] = []
        if first_token:
            for company_idx, normalized_name in global_choices.items():
                if normalized_name.startswith(first_token):
                    small_candidates.append(company_idx)
                    if len(small_candidates) >= 500:
                        break
        candidate_indices = small_candidates or list(global_choices)
    return {
        int(company_idx): comp_norm.at[company_idx]
        for company_idx in candidate_indices
        if company_idx in comp_norm.index
    }


def _active_scorer(scorer: Any, enhanced_config: dict[str, Any]) -> Any:
    """Return the configured RapidFuzz-compatible scorer."""
    if not (
        enhanced_config.get("enable_jaro_winkler", False)
        and enhanced_config.get("jaro_winkler_use_as_primary", False)
    ):
        return scorer

    prefix_weight = enhanced_config.get("jaro_winkler_prefix_weight", 0.1)

    def jaro_winkler_scorer(s1: str, s2: str, **kwargs: Any) -> float:
        return rapidfuzz_jaro_winkler_100(
            s1,
            s2,
            prefix_weight=prefix_weight,
            **kwargs,
        )

    return jaro_winkler_scorer


def _simplify_extract_results(
    results: Sequence[tuple[Any, ...]], choices: dict[int, str]
) -> list[tuple[int, int]]:
    """Normalize RapidFuzz's mapping and sequence result tuple shapes."""
    simplified: list[tuple[int, int]] = []
    reverse_map = {value: key for key, value in choices.items()}
    for result in results:
        try:
            candidate_value = result[0]
            score = int(result[1])
            if len(result) >= 3:
                key = result[2]
                candidate_idx = _coerce_int(key) if key in choices else None
                if candidate_idx is None and candidate_value in reverse_map:
                    candidate_idx = int(reverse_map[candidate_value])
                if candidate_idx is None:
                    candidate_idx = _coerce_int(key) or _coerce_int(candidate_value)
            elif candidate_value in reverse_map:
                candidate_idx = int(reverse_map[candidate_value])
            else:
                candidate_idx = _coerce_int(candidate_value)
            if candidate_idx is not None:
                simplified.append((candidate_idx, score))
        except (IndexError, TypeError, ValueError):
            continue
    return simplified


def _apply_phonetic_match(
    awards: pd.DataFrame,
    row_idx: Hashable,
    award_row: pd.Series,
    *,
    award_company_col: str,
    phonetic_by_code: dict[str, list[int]],
    enhanced_config: dict[str, Any],
) -> bool:
    """Apply the configured phonetic match and report whether it matched."""
    if not enhanced_config.get("enable_phonetic_matching", False) or not phonetic_by_code:
        return False
    award_name = str(award_row.get(award_company_col) or "")
    algorithm = enhanced_config.get("phonetic_algorithm", "metaphone")
    award_phonetic = get_phonetic_code(award_name, algorithm=algorithm)
    candidates = phonetic_by_code.get(award_phonetic, []) if award_phonetic else []
    if not candidates:
        return False
    score = min(95 + enhanced_config.get("phonetic_boost", 5), 100)
    _set_award_match(
        awards,
        row_idx,
        method="phonetic-match",
        score=score,
        company_idx=candidates[0],
    )
    return True


def _apply_fuzzy_matches(
    awards: pd.DataFrame,
    *,
    award_company_col: str,
    comp_norm: pd.Series,
    comp_blocks: dict[str, list[int]],
    phonetic_by_code: dict[str, list[int]],
    scorer: Any,
    top_k: int,
    high_threshold: int,
    low_threshold: int,
    return_candidates: bool,
    enhanced_config: dict[str, Any],
) -> None:
    """Apply phonetic and fuzzy matching to awards without identifier matches."""
    global_choices: dict[int, str] = comp_norm.to_dict()
    unmatched = awards[awards["_matched_company_idx"].isna()]
    for row_idx, award_row in unmatched.iterrows():
        if _apply_phonetic_match(
            awards,
            row_idx,
            award_row,
            award_company_col=award_company_col,
            phonetic_by_code=phonetic_by_code,
            enhanced_config=enhanced_config,
        ):
            continue

        norm_target = award_row.get("_norm_name") or ""
        if not norm_target:
            continue
        choices = _candidate_choices(
            award_row,
            comp_blocks=comp_blocks,
            comp_norm=comp_norm,
            global_choices=global_choices,
        )
        results = process.extract(
            norm_target,
            choices,
            scorer=_active_scorer(scorer, enhanced_config),
            processor=None,
            limit=top_k,
        )
        simplified = _simplify_extract_results(results, choices)
        if return_candidates:
            candidates_json = json.dumps(
                [
                    {"idx": company_idx, "score": score, "name": choices[company_idx]}
                    for company_idx, score in simplified
                ],
                ensure_ascii=False,
            )
            _set_award_candidates(awards, row_idx, candidates_json)
        if not simplified:
            continue
        best_idx, best_score = simplified[0]
        if best_score >= high_threshold:
            _set_award_match(
                awards,
                row_idx,
                method="fuzzy-auto",
                score=best_score,
                company_idx=best_idx,
            )
        elif best_score >= low_threshold:
            _set_award_match(awards, row_idx, method="fuzzy-candidate", score=best_score)
        else:
            _set_award_match(awards, row_idx, method="fuzzy-low", score=best_score)


def _merge_company_columns(awards: pd.DataFrame, companies: pd.DataFrame) -> pd.DataFrame:
    """Join accepted company rows and remove award-side matching helpers."""
    enriched = (
        awards.reset_index()
        .set_index("_matched_company_idx")
        .join(companies.add_prefix("company_"), how="left")
        .reset_index()
    )
    return enriched.drop(
        columns=[column for column in ("_norm_name", "_block") if column in enriched]
    )


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
    scorer=rapidfuzz_token_set_100,
    return_candidates: bool = False,
    enhanced_config: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Match awards to companies by identifier, then phonetic or fuzzy name.

    The returned copy includes prefixed company fields and match audit columns.
    See the module docstring for the matching order and confidence semantics.
    """
    enhanced_config = enhanced_config or {}
    award_company_col = _resolve_name_column(
        awards_df,
        award_company_col,
        fallbacks=("Company", "company", "Company Name"),
        parameter_name="award_company_col",
        frame_name="awards_df",
    )
    company_name_col = _resolve_name_column(
        companies_df,
        company_name_col,
        fallbacks=("Company Name", "company", "Company"),
        parameter_name="company_name_col",
        frame_name="companies_df",
    )
    awards, companies = _canonicalize_frames(
        awards_df,
        companies_df,
        award_company_col=award_company_col,
        company_name_col=company_name_col,
    )
    _prepare_match_columns(
        awards,
        companies,
        award_company_col=award_company_col,
        prefix_len=prefix_len,
        return_candidates=return_candidates,
        enhanced_config=enhanced_config,
    )
    indexes = _build_company_indexes(
        companies,
        company_name_col=company_name_col,
        uei_col=uei_col,
        duns_col=duns_col,
        state_col=state_col,
        zip_col=zip_col,
        prefix_len=prefix_len,
        enhanced_config=enhanced_config,
    )
    _apply_exact_identifier_matches(
        awards,
        uei_col=uei_col,
        duns_col=duns_col,
        comp_by_uei=indexes["comp_by_uei"],
        comp_by_duns=indexes["comp_by_duns"],
    )
    _apply_fuzzy_matches(
        awards,
        award_company_col=award_company_col,
        comp_norm=indexes["norm_name"],
        comp_blocks=indexes["blocks"],
        phonetic_by_code=indexes["phonetic_by_code"],
        scorer=scorer,
        top_k=top_k,
        high_threshold=high_threshold,
        low_threshold=low_threshold,
        return_candidates=return_candidates,
        enhanced_config=enhanced_config,
    )
    return _merge_company_columns(awards, indexes["df"])


# -------------------------
# End of module
# -------------------------
