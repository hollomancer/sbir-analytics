"""Versioned canonical company merge for pre-load deduplication.

Epistemic tier: primitives. Each policy freezes one complete merge behavior —
key preference, thresholds, candidate ordering, and tie handling. An
output-changing adjustment requires a new named policy version, never an
edit in place.

``PRELOAD_V1`` reproduces, byte-identically, the mapping historically
produced by ``sbir_etl.utils.company_canonicalizer`` via the exploratory
fuzzy self-enrichment path (golden corpus:
``tests/fixtures/identity/canonical_merge_corpus.csv``). Its quirks are part
of the frozen contract:

- Unique companies are keyed ``UEI:`` > ``DUNS:`` > ``NAME:<normalized>``
  from raw identifier values; the first row seen for a key supplies the
  company record.
- UEI equality (upper-cased) matches first, then DUNS digit equality
  *overwrites* any UEI match; in both maps the last record sharing the
  identifier wins.
- Remaining records fuzzy self-match on ``MATCHING_V1``-normalized names
  within a two-character prefix block, scored by the shared token-set
  contract. A record's own name always scores 100, so only candidates that
  tie it at 100 (identical or token-subset names) can win, and the earliest
  such candidate does. Sub-100 scores therefore never merge regardless of
  the 90 auto-merge / 75 review thresholds, which are retained as the frozen
  gate values.
- The mapping is not transitively closed: a canonical value may itself be an
  original key that maps elsewhere.
"""

from enum import StrEnum
from typing import Any, cast

import pandas as pd

from .company_names import (
    CompanyNameProfile,
    normalize_company_name,
    rapidfuzz_token_set_100,
)


EPISTEMIC_TIER = "primitives"

# Frozen PRELOAD_V1 parameters (see module docstring for their effect).
_PRELOAD_V1_HIGH_THRESHOLD = 90
_PRELOAD_V1_LOW_THRESHOLD = 75
_PRELOAD_V1_BLOCK_PREFIX_LENGTH = 2
_PRELOAD_V1_FALLBACK_CANDIDATE_CAP = 500


class CanonicalMergePolicy(StrEnum):
    """Named, versioned canonical company merge behaviors."""

    PRELOAD_V1 = "preload-v1"


def _normalize_name(value: object) -> str:
    """Blank-safe ``MATCHING_V1`` normalization (missing values become '')."""

    return normalize_company_name(value, profile=CompanyNameProfile.MATCHING_V1)


def _matching_text(value: object) -> str:
    """Historical award-side text coercion: ``str()`` without null masking."""

    return str(value)


def _company_text(value: object) -> str:
    """Historical company-side text coercion: nulls become empty strings."""

    return "" if _is_missing(value) else str(value)


def _is_missing(value: object) -> bool:
    """Scalar ``pd.isna`` (the frozen null test: '' and whitespace are values)."""

    try:
        # value is an arbitrary DataFrame cell; cast satisfies the scalar
        # isna overload without changing the runtime call.
        return bool(pd.isna(cast(Any, value)))
    except (TypeError, ValueError):  # pragma: no cover - non-scalar cell
        return False


def _own_key(uei: object, duns: object, name: object) -> str:
    """Canonical identifier preference: UEI > DUNS > normalized name."""

    if not _is_missing(uei) and uei:
        return f"UEI:{uei}"
    if not _is_missing(duns) and duns:
        return f"DUNS:{duns}"
    return f"NAME:{_normalize_name(name)}"


def _unique_companies(awards: pd.DataFrame) -> list[dict[str, object]]:
    """Extract first-seen unique company records keyed UEI > DUNS > name."""

    records: list[dict[str, object]] = []
    seen: set[str] = set()
    for _, award in awards.iterrows():
        name = award.get("company_name") or award.get("company", "")
        uei = award.get("company_uei") or award.get("uei")
        duns = award.get("company_duns") or award.get("duns")
        if _is_missing(uei):
            uei = None
        if _is_missing(duns):
            duns = None
        key = _own_key(uei, duns, name)
        if key in seen:
            continue
        seen.add(key)
        records.append(
            {"company": name, "UEI": uei or "", "Duns": duns or "", "_original_key": key}
        )
    return records


def _duns_digits(value: object) -> str:
    return "".join(ch for ch in str(value) if ch.isdigit())


def _match_records(records: list[dict[str, object]]) -> list[int | None]:
    """Self-match records exactly as the frozen PRELOAD_V1 procedure does.

    Returns, per record, the index of the record it auto-merges into (which
    may be itself), or None when no candidate reaches the auto-merge gate.
    """

    company_norms = [_normalize_name(_company_text(record["company"])) for record in records]
    award_norms = [_normalize_name(_matching_text(record["company"])) for record in records]

    by_uei: dict[str, int] = {}
    by_duns: dict[str, int] = {}
    blocks: dict[str, list[int]] = {}
    for index, record in enumerate(records):
        uei_key = str(record["UEI"]).strip().upper()
        if uei_key:
            by_uei[uei_key] = index
        digits = _duns_digits(record["Duns"])
        if digits:
            by_duns[digits] = index
        blocks.setdefault(company_norms[index][:_PRELOAD_V1_BLOCK_PREFIX_LENGTH], []).append(index)

    matches: list[int | None] = [None] * len(records)
    for index, record in enumerate(records):
        # Identifier equality first: UEI, then DUNS digits — DUNS overwrites.
        uei_key = str(record["UEI"]).strip().upper() if record["UEI"] else ""
        if uei_key and uei_key in by_uei:
            matches[index] = by_uei[uei_key]
        digits = _duns_digits(record["Duns"]) if record["Duns"] else ""
        if digits and digits in by_duns:
            matches[index] = by_duns[digits]
        if matches[index] is not None:
            continue

        target = award_norms[index]
        if not target:
            continue
        block = target[:_PRELOAD_V1_BLOCK_PREFIX_LENGTH]
        candidates = blocks.get(block, [])
        if not candidates:
            first_token = target.split(" ", 1)[0]
            fallback: list[int] = []
            if first_token:
                for candidate, norm in enumerate(company_norms):
                    if norm.startswith(first_token):
                        fallback.append(candidate)
                        if len(fallback) >= _PRELOAD_V1_FALLBACK_CANDIDATE_CAP:
                            break
            candidates = fallback or list(range(len(records)))

        best_index: int | None = None
        best_score = 0.0
        for candidate in candidates:
            score = rapidfuzz_token_set_100(target, company_norms[candidate])
            if best_index is None or score > best_score:
                best_index = candidate
                best_score = score
        if best_index is not None and int(best_score) >= _PRELOAD_V1_HIGH_THRESHOLD:
            matches[index] = best_index

    return matches


def build_canonical_company_map(
    awards: pd.DataFrame, *, policy: CanonicalMergePolicy
) -> dict[str, str]:
    """Map original company keys to canonical keys under a named policy.

    Args:
        awards: Award rows carrying ``company_name``/``company`` names and
            optional ``company_uei``/``uei`` and ``company_duns``/``duns``
            identifier columns.
        policy: The frozen merge behavior to apply.

    Returns:
        Mapping from each unique original ``UEI:``/``DUNS:``/``NAME:`` key to
        its canonical key.
    """

    if policy is not CanonicalMergePolicy.PRELOAD_V1:
        raise ValueError(f"unsupported canonical merge policy: {policy}")

    records = _unique_companies(awards)
    if not records:
        return {}
    matches = _match_records(records)

    canonical_map: dict[str, str] = {}
    for record, match in zip(records, matches, strict=True):
        source = records[match] if match is not None else record
        canonical_map[str(record["_original_key"])] = _own_key(
            source["UEI"], source["Duns"], source["company"]
        )
    return canonical_map


__all__ = [
    "EPISTEMIC_TIER",
    "CanonicalMergePolicy",
    "build_canonical_company_map",
]
