#!/usr/bin/env python3
"""Find same-firm SBIR/STTR awards that appear to fund the same work.

The raw SBIR.gov export is the record system of truth for this analysis.  In
particular, this script does not use ``validated_sbir_awards`` because bare
agency tracking numbers are reused in the source data.

Two outputs are intentionally produced:

* one row per unordered candidate pair, with the text and identity evidence;
* one row per implicated source award, preserving every raw source column.

The result is an audit queue, not a finding of improper duplicate funding.
Exact or near-identical work can be a legitimate Phase progression, a
continuation, or complementary work for different operational users.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from rapidfuzz import fuzz, process

from sbir_etl.utils.text_normalization import normalize_name


SOURCE_URL = "https://data.www.sbir.gov/mod_awarddatapublic/award_data.csv"

REQUIRED_COLUMNS = {
    "Company",
    "Award Title",
    "Agency",
    "Agency Tracking Number",
    "Contract",
    "Phase",
    "Program",
    "Proposal Award Date",
    "Solicitation Number",
    "Topic Code",
    "Award Year",
    "Award Amount",
    "UEI",
    "Duns",
    "State",
    "Abstract",
    "PI Name",
}

PAIR_SOURCE_COLUMNS = [
    "Company",
    "UEI",
    "Duns",
    "State",
    "Agency",
    "Branch",
    "Program",
    "Phase",
    "Agency Tracking Number",
    "Contract",
    "Proposal Award Date",
    "Contract End Date",
    "Solicitation Number",
    "Topic Code",
    "Award Year",
    "Award Amount",
    "Award Title",
    "Abstract",
    "PI Name",
]

PLACEHOLDER_TEXT = {
    "",
    "n a",
    "na",
    "none",
    "not applicable",
    "not available",
    "null",
    "unknown",
}

PLACEHOLDER_CODES = {
    "",
    "NA",
    "NONE",
    "NOTAPPLICABLE",
    "NOTAVAILABLE",
    "NULL",
    "UNKNOWN",
}

TOKEN_RE = re.compile(r"[a-z0-9]+")
VALID_UEI_RE = re.compile(r"[A-Z0-9]{12}")
VALID_DUNS_RE = re.compile(r"[0-9]{9}")

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "of",
    "on",
    "or",
    "our",
    "that",
    "the",
    "these",
    "this",
    "those",
    "to",
    "we",
    "with",
}

TIER_RANK = {"review": 1, "strong": 2, "exact": 3}


@dataclass(frozen=True)
class MatchConfig:
    """Auditable thresholds for lexical same-work candidate detection."""

    min_title_chars: int = 20
    min_abstract_chars: int = 80
    min_exact_abstract_chars: int = 300
    near_title_min: int = 85
    near_title_strong: int = 92
    near_abstract_min: int = 75
    near_abstract_strong: int = 85
    exact_title_strong_abstract: int = 80
    max_phase_progression_days: int = 5 * 366
    workers: int = 1


def normalize_text(value: Any) -> str:
    """Normalize free text for exact/fuzzy comparison."""

    if value is None or pd.isna(value):
        return ""
    return " ".join(TOKEN_RE.findall(str(value).lower()))


def normalize_code(value: Any) -> str:
    """Normalize an identifier-like value without treating blank as a value."""

    if value is None or pd.isna(value):
        return ""
    return re.sub(r"[^A-Z0-9]", "", str(value).strip().upper())


def normalize_topic_code(value: Any) -> str:
    """Normalize common branch-prefixed variants of the same source topic code."""

    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        # Some source releases serialized numeric codes with binary-float tails
        # (for example, 8.3 versus 8.300000000000001).
        text = format(float(text), ".12g")
    code = normalize_code(text)
    if code in PLACEHOLDER_CODES:
        return ""
    for long_prefix, short_prefix in (
        ("AIRFORCE", "AF"),
        ("USAF", "AF"),
        ("ARMY", "A"),
        ("NAVY", "N"),
    ):
        if code.startswith(long_prefix):
            return f"{short_prefix}{code[len(long_prefix) :]}"
    return code


def valid_uei(value: Any) -> str:
    normalized = normalize_code(value)
    return normalized if VALID_UEI_RE.fullmatch(normalized) else ""


def valid_duns(value: Any) -> str:
    normalized = normalize_code(value)
    return normalized if VALID_DUNS_RE.fullmatch(normalized) else ""


def is_meaningful(text: str, minimum_chars: int) -> bool:
    return len(text) >= minimum_chars and text not in PLACEHOLDER_TEXT


def tokenize_content(text: str) -> set[str]:
    return {token for token in text.split() if len(token) > 2 and token not in STOPWORDS}


def jaccard(left: Iterable[str], right: Iterable[str]) -> float:
    left_set = set(left)
    right_set = set(right)
    union = left_set | right_set
    if not union:
        return 0.0
    return len(left_set & right_set) / len(union)


def _name_state_key(company: Any, state: Any, source_record_number: int) -> str:
    name = normalize_name(str(company or ""), remove_suffixes=False)
    state_code = normalize_code(state)
    if not name:
        return f"ROW:{source_record_number}"
    return f"NAMESTATE:{name}|{state_code or 'UNKNOWN'}"


def assign_firm_keys(awards: pd.DataFrame) -> pd.DataFrame:
    """Assign conservative, ID-first firm keys without transitive ID merging.

    UEI is authoritative.  A DUNS-only row is bridged to a UEI only when that
    DUNS maps to exactly one UEI in the source.  A no-ID row is attached to an
    identifier-backed firm only when its exact normalized name+state maps to
    exactly one such firm.  Ambiguous fallbacks remain separate.
    """

    result = awards.copy()
    result["_valid_uei"] = result["UEI"].map(valid_uei)
    result["_valid_duns"] = result["Duns"].map(valid_duns)
    result["_name_state_key"] = [
        _name_state_key(company, state, int(record_number))
        for company, state, record_number in zip(
            result["Company"],
            result["State"],
            result["_source_record_number"],
            strict=True,
        )
    ]

    duns_to_ueis: dict[str, set[str]] = defaultdict(set)
    for uei, duns in zip(result["_valid_uei"], result["_valid_duns"], strict=True):
        if uei and duns:
            duns_to_ueis[duns].add(uei)

    provisional_keys: list[str] = []
    provisional_methods: list[str] = []
    for uei, duns in zip(result["_valid_uei"], result["_valid_duns"], strict=True):
        if uei:
            provisional_keys.append(f"UEI:{uei}")
            provisional_methods.append("uei")
            continue
        mapped_ueis = duns_to_ueis.get(duns, set()) if duns else set()
        if duns and len(mapped_ueis) == 1:
            provisional_keys.append(f"UEI:{next(iter(mapped_ueis))}")
            provisional_methods.append("duns_to_uei")
        elif duns and len(mapped_ueis) == 0:
            provisional_keys.append(f"DUNS:{duns}")
            provisional_methods.append("duns")
        else:
            provisional_keys.append("")
            provisional_methods.append("ambiguous_duns" if duns else "no_valid_id")

    result["_provisional_firm_key"] = provisional_keys
    result["_provisional_firm_method"] = provisional_methods

    name_state_to_firms: dict[str, set[str]] = defaultdict(set)
    for name_state, firm_key in zip(
        result["_name_state_key"], result["_provisional_firm_key"], strict=True
    ):
        if firm_key:
            name_state_to_firms[name_state].add(firm_key)

    firm_keys: list[str] = []
    firm_methods: list[str] = []
    for name_state, firm_key, method in zip(
        result["_name_state_key"],
        result["_provisional_firm_key"],
        result["_provisional_firm_method"],
        strict=True,
    ):
        if firm_key:
            firm_keys.append(firm_key)
            firm_methods.append(method)
            continue
        attached_firms = name_state_to_firms.get(name_state, set())
        if len(attached_firms) == 1:
            firm_keys.append(next(iter(attached_firms)))
            firm_methods.append("name_state_to_id")
        else:
            firm_keys.append(name_state)
            firm_methods.append(
                "name_state_ambiguous_duns" if method == "ambiguous_duns" else "name_state"
            )

    result["_firm_key"] = firm_keys
    result["_firm_key_method"] = firm_methods
    result["_ambiguous_duns"] = result["_valid_duns"].map(
        lambda duns: bool(duns and len(duns_to_ueis.get(duns, set())) > 1)
    )
    return result


def prepare_awards(awards: pd.DataFrame) -> pd.DataFrame:
    """Validate and add comparison-only fields while preserving source rows."""

    missing = sorted(REQUIRED_COLUMNS - set(awards.columns))
    if missing:
        raise ValueError(f"award CSV is missing required columns: {', '.join(missing)}")

    result = awards.fillna("").astype(str).reset_index(drop=True)
    result["_source_record_number"] = np.arange(1, len(result) + 1)
    result["_title_norm"] = result["Award Title"].map(normalize_text)
    result["_abstract_norm"] = result["Abstract"].map(normalize_text)
    result["_agency_norm"] = result["Agency"].map(normalize_text)
    result["_pi_norm"] = result["PI Name"].map(normalize_text)

    topic_codes = result["Topic Code"].map(normalize_topic_code)
    solicitations = result["Solicitation Number"].map(normalize_code)
    result["_topic_code_norm"] = topic_codes
    result["_source_topic_key"] = [
        f"{agency}|{solicitation or 'UNKNOWN_SOLICITATION'}|{topic}" if topic else ""
        for agency, solicitation, topic in zip(
            result["_agency_norm"], solicitations, topic_codes, strict=True
        )
    ]
    return assign_firm_keys(result)


def _pair_scope(left: pd.Series, right: pd.Series) -> tuple[bool, bool]:
    cross_agency = bool(
        left["_agency_norm"]
        and right["_agency_norm"]
        and left["_agency_norm"] != right["_agency_norm"]
    )
    different_topic = bool(
        not cross_agency
        and left["_topic_code_norm"]
        and right["_topic_code_norm"]
        and left["_topic_code_norm"] != right["_topic_code_norm"]
    )
    return cross_agency, different_topic


def _identity_basis(left: pd.Series, right: pd.Series) -> tuple[str, str]:
    if left["_valid_uei"] and left["_valid_uei"] == right["_valid_uei"]:
        return "uei_exact", "high"
    if (
        left["_valid_duns"]
        and left["_valid_duns"] == right["_valid_duns"]
        and not left["_ambiguous_duns"]
        and not right["_ambiguous_duns"]
    ):
        return "duns_exact", "high"
    if left["_name_state_key"] == right["_name_state_key"]:
        return "name_state_exact", "medium"
    return "id_bridge", "high"


def _classify_match(
    *,
    exact_title: bool,
    exact_abstract: bool,
    exact_abstract_chars: int,
    title_similarity: int,
    abstract_similarity: int,
    abstract_comparable: bool,
    config: MatchConfig,
) -> tuple[str, str] | None:
    bases: list[str] = []
    if exact_abstract:
        bases.append("exact_abstract")
    if exact_title:
        bases.append("exact_title")

    if exact_title and exact_abstract:
        return "exact", "+".join(bases)
    if exact_abstract:
        tier = (
            "strong"
            if exact_abstract_chars >= config.min_exact_abstract_chars
            and title_similarity >= config.near_title_min
            else "review"
        )
        return tier, "+".join(bases)
    if exact_title:
        tier = (
            "strong"
            if abstract_comparable and abstract_similarity >= config.exact_title_strong_abstract
            else "review"
        )
        return tier, "+".join(bases)
    if (
        abstract_comparable
        and title_similarity >= config.near_title_strong
        and abstract_similarity >= config.near_abstract_strong
    ):
        return "strong", "near_title+near_abstract"
    if (
        abstract_comparable
        and title_similarity >= config.near_title_min
        and abstract_similarity >= config.near_abstract_min
    ):
        return "review", "near_title+near_abstract"
    return None


def _normalized_phase(value: Any) -> str:
    text = normalize_text(value)
    if "iii" in text or text.endswith("3"):
        return "III"
    if "ii" in text or text.endswith("2"):
        return "II"
    if "i" in text or text.endswith("1"):
        return "I"
    return text.upper()


def _date_gap_days(left: Any, right: Any) -> int | None:
    left_date = pd.to_datetime(left, errors="coerce")
    right_date = pd.to_datetime(right, errors="coerce")
    if pd.isna(left_date) or pd.isna(right_date):
        return None
    return abs((right_date - left_date).days)


def _performance_periods_overlap(left: pd.Series, right: pd.Series) -> bool | None:
    dates = [
        pd.to_datetime(left["Proposal Award Date"], errors="coerce"),
        pd.to_datetime(left["Contract End Date"], errors="coerce"),
        pd.to_datetime(right["Proposal Award Date"], errors="coerce"),
        pd.to_datetime(right["Contract End Date"], errors="coerce"),
    ]
    if any(pd.isna(value) for value in dates):
        return None
    left_start, left_end, right_start, right_end = dates
    if left_end < left_start or right_end < right_start:
        return None
    return bool(max(left_start, right_start) <= min(left_end, right_end))


def _normalized_reference(value: Any) -> str:
    code = normalize_code(value)
    return "" if code in PLACEHOLDER_CODES else code


def _same_nonblank_reference(left: Any, right: Any) -> bool:
    left_code = _normalized_reference(left)
    right_code = _normalized_reference(right)
    return bool(left_code and right_code and left_code == right_code)


def _phase_progression_evidence(
    left: pd.Series,
    right: pd.Series,
    *,
    cross_agency: bool,
    title_similarity: int,
    config: MatchConfig,
) -> tuple[bool, bool, str, str]:
    """Return sequential-pair flag, likely flag, status, and supporting basis."""

    phase_a = _normalized_phase(left["Phase"])
    phase_b = _normalized_phase(right["Phase"])
    phase_order = {"I": 1, "II": 2, "III": 3}
    sequential_phase_pair = bool(
        phase_a in phase_order
        and phase_b in phase_order
        and abs(phase_order[phase_a] - phase_order[phase_b]) == 1
    )
    if not sequential_phase_pair:
        return False, False, "not_sequential_phase_pair", ""

    same_tracking = _same_nonblank_reference(
        left["Agency Tracking Number"], right["Agency Tracking Number"]
    )
    same_contract = _same_nonblank_reference(left["Contract"], right["Contract"])
    exact_source_reference = same_tracking or same_contract
    similar_title = title_similarity >= config.near_title_min
    if not (exact_source_reference or similar_title):
        return True, False, "phase_sequence_no_project_link", ""

    left_date = pd.to_datetime(left["Proposal Award Date"], errors="coerce")
    right_date = pd.to_datetime(right["Proposal Award Date"], errors="coerce")
    if pd.isna(left_date) or pd.isna(right_date):
        if exact_source_reference:
            references = []
            if same_tracking:
                references.append("same_tracking_number")
            if same_contract:
                references.append("same_contract")
            references.append("date_missing")
            return True, True, "likely_progression", "+".join(references)
        return True, False, "phase_sequence_unknown", ""

    if phase_order[phase_a] < phase_order[phase_b]:
        earlier_date, later_date = left_date, right_date
    else:
        earlier_date, later_date = right_date, left_date
    signed_gap_days = int((later_date - earlier_date).days)
    if signed_gap_days < 0:
        return True, False, "phase_sequence_reverse_dates", ""
    if signed_gap_days > config.max_phase_progression_days:
        return True, False, "phase_sequence_long_gap", ""

    bases = ["cross_agency" if cross_agency else "same_agency", "chronological_within_5y"]
    if same_tracking:
        bases.append("same_tracking_number")
    if same_contract:
        bases.append("same_contract")
    if similar_title:
        bases.append("similar_title")
    return True, True, "likely_progression", "+".join(bases)


def _source_pair_fields(left: pd.Series, right: pd.Series) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for suffix, row in (("a", left), ("b", right)):
        fields[f"source_record_number_{suffix}"] = int(row["_source_record_number"])
        fields[f"firm_key_method_{suffix}"] = row["_firm_key_method"]
        fields[f"source_topic_key_{suffix}"] = row["_source_topic_key"]
        for column in PAIR_SOURCE_COLUMNS:
            if column in row.index:
                key = re.sub(r"[^a-z0-9]+", "_", column.lower()).strip("_")
                fields[f"{key}_{suffix}"] = row[column]
    return fields


def find_same_work_pairs(
    prepared_awards: pd.DataFrame,
    *,
    config: MatchConfig | None = None,
    minimum_tier: str = "review",
) -> pd.DataFrame:
    """Return all candidate pairs meeting the configured audit rule."""

    config = config or MatchConfig()
    if minimum_tier not in TIER_RANK:
        raise ValueError(f"unknown minimum tier: {minimum_tier}")

    pairs: list[dict[str, Any]] = []
    minimum_rank = TIER_RANK[minimum_tier]
    agency_values = prepared_awards["_agency_norm"].to_numpy()
    topic_values = prepared_awards["_topic_code_norm"].to_numpy()
    title_values = prepared_awards["_title_norm"].to_numpy()
    abstract_values = prepared_awards["_abstract_norm"].to_numpy()

    for firm_key, group_indexes in prepared_awards.groupby("_firm_key", sort=False).indices.items():
        indexes = [int(index) for index in group_indexes]
        if len(indexes) < 2:
            continue
        if len({agency_values[index] for index in indexes}) < 2:
            known_topics = {topic_values[index] for index in indexes if topic_values[index]}
            if len(known_topics) < 2:
                continue

        candidate_title_scores: dict[tuple[int, int], int] = {}

        exact_titles: dict[str, list[int]] = defaultdict(list)
        exact_abstracts: dict[str, list[int]] = defaultdict(list)
        valid_title_indexes: list[int] = []
        valid_titles: list[str] = []

        for index in indexes:
            title = title_values[index]
            abstract = abstract_values[index]
            if is_meaningful(title, config.min_title_chars):
                exact_titles[title].append(index)
                valid_title_indexes.append(index)
                valid_titles.append(title)
            if is_meaningful(abstract, config.min_abstract_chars):
                exact_abstracts[abstract].append(index)

        for same_title_indexes in exact_titles.values():
            for left_index, right_index in combinations(same_title_indexes, 2):
                candidate_title_scores[(left_index, right_index)] = 100

        for same_abstract_indexes in exact_abstracts.values():
            for left_index, right_index in combinations(same_abstract_indexes, 2):
                pair = (left_index, right_index)
                candidate_title_scores.setdefault(pair, 0)

        if len(valid_titles) >= 2:
            title_matrix = process.cdist(
                valid_titles,
                valid_titles,
                scorer=fuzz.ratio,
                score_cutoff=config.near_title_min,
                dtype=np.uint8,
                workers=config.workers,
            )
            left_positions, right_positions = np.where(
                np.triu(title_matrix, k=1) >= config.near_title_min
            )
            for left_position, right_position in zip(left_positions, right_positions, strict=True):
                left_index = valid_title_indexes[int(left_position)]
                right_index = valid_title_indexes[int(right_position)]
                candidate_title_scores[(left_index, right_index)] = int(
                    title_matrix[left_position, right_position]
                )

        token_cache: dict[int, set[str]] = {}
        for (left_index, right_index), title_similarity in sorted(candidate_title_scores.items()):
            cross_agency = bool(
                agency_values[left_index]
                and agency_values[right_index]
                and agency_values[left_index] != agency_values[right_index]
            )
            different_topic = bool(
                not cross_agency
                and topic_values[left_index]
                and topic_values[right_index]
                and topic_values[left_index] != topic_values[right_index]
            )
            if not (cross_agency or different_topic):
                continue

            left = prepared_awards.loc[left_index]
            right = prepared_awards.loc[right_index]
            left_title = title_values[left_index]
            right_title = title_values[right_index]
            left_abstract = abstract_values[left_index]
            right_abstract = abstract_values[right_index]
            exact_title = bool(
                left_title == right_title and is_meaningful(left_title, config.min_title_chars)
            )
            exact_abstract = bool(
                left_abstract == right_abstract
                and is_meaningful(left_abstract, config.min_abstract_chars)
            )
            exact_abstract_chars = len(left_abstract) if exact_abstract else 0
            if (
                title_similarity == 0
                and is_meaningful(left_title, config.min_title_chars)
                and is_meaningful(right_title, config.min_title_chars)
            ):
                title_similarity = int(round(fuzz.ratio(left_title, right_title)))

            abstract_comparable = bool(
                is_meaningful(left_abstract, config.min_abstract_chars)
                and is_meaningful(right_abstract, config.min_abstract_chars)
            )
            abstract_similarity = (
                int(round(fuzz.ratio(left_abstract, right_abstract))) if abstract_comparable else 0
            )
            classification = _classify_match(
                exact_title=exact_title,
                exact_abstract=exact_abstract,
                exact_abstract_chars=exact_abstract_chars,
                title_similarity=title_similarity,
                abstract_similarity=abstract_similarity,
                abstract_comparable=abstract_comparable,
                config=config,
            )
            if classification is None:
                continue
            tier, match_basis = classification
            if TIER_RANK[tier] < minimum_rank:
                continue

            for index, row in ((left_index, left), (right_index, right)):
                if index not in token_cache:
                    token_cache[index] = tokenize_content(
                        f"{row['_title_norm']} {row['_abstract_norm']}"
                    )

            identity_basis, identity_confidence = _identity_basis(left, right)
            sequential_phase_pair, likely_phase_progression, phase_status, phase_basis = (
                _phase_progression_evidence(
                    left,
                    right,
                    cross_agency=cross_agency,
                    title_similarity=title_similarity,
                    config=config,
                )
            )
            relationship_context = (
                "likely_phase_progression"
                if likely_phase_progression
                else "cross_agency_overlap"
                if cross_agency
                else "same_agency_different_topic"
            )
            phase_a = _normalized_phase(left["Phase"])
            phase_b = _normalized_phase(right["Phase"])
            same_phase = bool(phase_a and phase_b and phase_a == phase_b)
            same_award_year = _same_nonblank_reference(left["Award Year"], right["Award Year"])
            performance_periods_overlap = _performance_periods_overlap(left, right)
            contemporaneous_same_phase = bool(
                same_phase and (performance_periods_overlap is True or same_award_year)
            )
            corroborated_lexical = tier in {"exact", "strong"}
            priority_review = bool(
                not likely_phase_progression
                and (corroborated_lexical or contemporaneous_same_phase)
            )
            priority_reasons = []
            if corroborated_lexical:
                priority_reasons.append("corroborated_lexical")
            if contemporaneous_same_phase:
                priority_reasons.append("contemporaneous_same_phase")
            pair: dict[str, Any] = {
                "firm_key": firm_key,
                "firm_match_basis": identity_basis,
                "firm_match_confidence": identity_confidence,
                "match_tier": tier,
                "match_basis": match_basis,
                "scope": "cross_agency" if cross_agency else "different_topic",
                "cross_agency": cross_agency,
                "different_topic": different_topic,
                "title_similarity_pct": title_similarity,
                "abstract_similarity_pct": abstract_similarity,
                "abstract_comparable": abstract_comparable,
                "exact_title": exact_title,
                "exact_abstract": exact_abstract,
                "exact_abstract_chars": exact_abstract_chars,
                "work_token_jaccard": round(
                    jaccard(token_cache[left_index], token_cache[right_index]), 6
                ),
                "same_pi": bool(
                    left["_pi_norm"] and right["_pi_norm"] and left["_pi_norm"] == right["_pi_norm"]
                ),
                "same_program": _same_nonblank_reference(left["Program"], right["Program"]),
                "same_tracking_number": _same_nonblank_reference(
                    left["Agency Tracking Number"], right["Agency Tracking Number"]
                ),
                "same_contract": _same_nonblank_reference(left["Contract"], right["Contract"]),
                "sequential_phase_pair": sequential_phase_pair,
                "likely_phase_progression": likely_phase_progression,
                "phase_progression_status": phase_status,
                "phase_progression_basis": phase_basis,
                "relationship_context": relationship_context,
                "award_date_gap_days": _date_gap_days(
                    left["Proposal Award Date"], right["Proposal Award Date"]
                ),
                "same_award_year": same_award_year,
                "same_phase": same_phase,
                "performance_periods_overlap": performance_periods_overlap,
                "contemporaneous_same_phase": contemporaneous_same_phase,
                "priority_review": priority_review,
                "priority_reason": "+".join(priority_reasons) if priority_review else "",
                "_left_index": left_index,
                "_right_index": right_index,
            }
            pair.update(_source_pair_fields(left, right))
            pairs.append(pair)

    return pd.DataFrame(pairs)


def _row_fingerprint(row: pd.Series, source_columns: list[str]) -> str:
    payload = json.dumps(
        {
            "source_record_number": int(row["_source_record_number"]),
            "values": [str(row[column]) for column in source_columns],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def add_ids_and_clusters(
    prepared_awards: pd.DataFrame,
    pairs: pd.DataFrame,
    source_columns: list[str],
) -> tuple[pd.DataFrame, dict[int, str]]:
    """Add stable record/pair IDs and connected-component work clusters."""

    if pairs.empty:
        result = pairs.copy()
        for column in ["pair_id", "work_cluster_id", "record_id_a", "record_id_b"]:
            result[column] = pd.Series(dtype=str)
        return result, {}

    implicated_indexes = sorted(
        set(pairs["_left_index"].astype(int)) | set(pairs["_right_index"].astype(int))
    )
    fingerprints = {
        index: _row_fingerprint(prepared_awards.loc[index], source_columns)
        for index in implicated_indexes
    }

    parent = {index: index for index in implicated_indexes}

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left_index: int, right_index: int) -> None:
        left_root = find(left_index)
        right_root = find(right_index)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    for left_index, right_index in zip(
        pairs["_left_index"].astype(int), pairs["_right_index"].astype(int), strict=True
    ):
        union(left_index, right_index)

    component_members: dict[int, list[int]] = defaultdict(list)
    for index in implicated_indexes:
        component_members[find(index)].append(index)

    cluster_by_index: dict[int, str] = {}
    for members in component_members.values():
        cluster_payload = "|".join(sorted(fingerprints[index] for index in members))
        cluster_id = f"work-{hashlib.sha256(cluster_payload.encode()).hexdigest()[:16]}"
        for index in members:
            cluster_by_index[index] = cluster_id

    result = pairs.copy()
    result["record_id_a"] = result["_left_index"].map(
        lambda index: f"award-{fingerprints[int(index)][:16]}"
    )
    result["record_id_b"] = result["_right_index"].map(
        lambda index: f"award-{fingerprints[int(index)][:16]}"
    )
    result["work_cluster_id"] = result["_left_index"].map(
        lambda index: cluster_by_index[int(index)]
    )
    result["pair_id"] = [
        f"pair-{hashlib.sha256('|'.join(sorted((left, right))).encode()).hexdigest()[:16]}"
        for left, right in zip(result["record_id_a"], result["record_id_b"], strict=True)
    ]
    return result, cluster_by_index


def build_record_output(
    prepared_awards: pd.DataFrame,
    pairs: pd.DataFrame,
    cluster_by_index: dict[int, str],
    source_columns: list[str],
) -> pd.DataFrame:
    """Return every implicated raw award with cluster and partner metadata."""

    if pairs.empty:
        return pd.DataFrame(columns=["record_id", "work_cluster_id", *source_columns])

    partner_indexes: dict[int, set[int]] = defaultdict(set)
    tiers_by_index: dict[int, set[str]] = defaultdict(set)
    scopes_by_index: dict[int, set[str]] = defaultdict(set)
    bases_by_index: dict[int, set[str]] = defaultdict(set)
    record_ids: dict[int, str] = {}

    for _, row in pairs.iterrows():
        left_index = int(row["_left_index"])
        right_index = int(row["_right_index"])
        partner_indexes[left_index].add(right_index)
        partner_indexes[right_index].add(left_index)
        tiers_by_index[left_index].add(row["match_tier"])
        tiers_by_index[right_index].add(row["match_tier"])
        scopes_by_index[left_index].add(row["scope"])
        scopes_by_index[right_index].add(row["scope"])
        bases_by_index[left_index].add(row["match_basis"])
        bases_by_index[right_index].add(row["match_basis"])
        record_ids[left_index] = row["record_id_a"]
        record_ids[right_index] = row["record_id_b"]

    cluster_members: dict[str, list[int]] = defaultdict(list)
    for index, cluster_id in cluster_by_index.items():
        cluster_members[cluster_id].append(index)

    output_rows: list[dict[str, Any]] = []
    for index in sorted(partner_indexes):
        row = prepared_awards.loc[index]
        cluster_id = cluster_by_index[index]
        cluster_indexes = sorted(cluster_members[cluster_id])
        known_topics = sorted(
            {
                prepared_awards.at[candidate_index, "_source_topic_key"]
                for candidate_index in cluster_indexes
                if prepared_awards.at[candidate_index, "_source_topic_key"]
            }
        )
        agencies = sorted(
            {
                prepared_awards.at[candidate_index, "Agency"]
                for candidate_index in cluster_indexes
                if prepared_awards.at[candidate_index, "Agency"]
            }
        )
        highest_tier = max(tiers_by_index[index], key=TIER_RANK.__getitem__)
        output: dict[str, Any] = {
            "record_id": record_ids[index],
            "work_cluster_id": cluster_id,
            "source_record_number": int(row["_source_record_number"]),
            "firm_key": row["_firm_key"],
            "firm_key_method": row["_firm_key_method"],
            "highest_match_tier": highest_tier,
            "partner_count": len(partner_indexes[index]),
            "partner_source_record_numbers": ";".join(
                str(int(prepared_awards.at[partner, "_source_record_number"]))
                for partner in sorted(partner_indexes[index])
            ),
            "match_scopes": ";".join(sorted(scopes_by_index[index])),
            "match_bases": ";".join(sorted(bases_by_index[index])),
            "cluster_record_count": len(cluster_indexes),
            "cluster_agencies": ";".join(agencies),
            "cluster_source_topics": ";".join(known_topics),
        }
        output.update({column: row[column] for column in source_columns})
        output_rows.append(output)
    return pd.DataFrame(output_rows)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def summarize(
    *,
    awards_path: Path,
    prepared_awards: pd.DataFrame,
    pairs: pd.DataFrame,
    records: pd.DataFrame,
    config: MatchConfig,
    minimum_tier: str,
) -> dict[str, Any]:
    source_stats = awards_path.stat()

    def counts(column: str) -> dict[str, int]:
        if pairs.empty:
            return {}
        return {str(key): int(value) for key, value in pairs[column].value_counts().items()}

    if pairs.empty:
        corroborated_lexical = pd.Series(dtype=bool)
        non_progression = pd.Series(dtype=bool)
        lexical_priority = pd.Series(dtype=bool)
        priority_review = pd.Series(dtype=bool)
        priority_record_ids: set[str] = set()
    else:
        corroborated_lexical = pairs["match_tier"].isin({"exact", "strong"})
        non_progression = ~pairs["likely_phase_progression"]
        lexical_priority = corroborated_lexical & non_progression
        priority_review = pairs["priority_review"]
        priority_record_ids = set(pairs.loc[priority_review, "record_id_a"]) | set(
            pairs.loc[priority_review, "record_id_b"]
        )

    return {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "source": {
            "path": str(awards_path.resolve()),
            "url": SOURCE_URL,
            "bytes": source_stats.st_size,
            "local_file_modified_at_utc": datetime.fromtimestamp(
                source_stats.st_mtime, tz=UTC
            ).isoformat(),
            "sha256": _sha256_file(awards_path),
        },
        "method": {
            "firm_identity": (
                "valid UEI; else unambiguous valid DUNS; else normalized company+state"
            ),
            "topic_identity": "different known source Topic Code values within the same agency",
            "minimum_tier": minimum_tier,
            "thresholds": asdict(config),
            "interpretation": "candidate audit queue; not proof of improper duplicate funding",
        },
        "counts": {
            "source_records": int(len(prepared_awards)),
            "firm_keys": int(prepared_awards["_firm_key"].nunique()),
            "candidate_pairs": int(len(pairs)),
            "implicated_records": int(len(records)),
            "work_clusters": int(pairs["work_cluster_id"].nunique()) if not pairs.empty else 0,
            "implicated_firms": int(pairs["firm_key"].nunique()) if not pairs.empty else 0,
            "cross_agency_pairs": int(pairs["cross_agency"].sum()) if not pairs.empty else 0,
            "different_topic_pairs": int(pairs["different_topic"].sum()) if not pairs.empty else 0,
            "sequential_phase_pairs": int(pairs["sequential_phase_pair"].sum())
            if not pairs.empty
            else 0,
            "likely_phase_progressions": int(pairs["likely_phase_progression"].sum())
            if not pairs.empty
            else 0,
            "non_progression_pairs": int(non_progression.sum()),
            "exact_or_strong_pairs": int(corroborated_lexical.sum()),
            "contemporaneous_same_phase_pairs": int(pairs["contemporaneous_same_phase"].sum())
            if not pairs.empty
            else 0,
            "priority_exact_or_strong_non_progression_pairs": int(lexical_priority.sum()),
            "priority_review_pairs": int(priority_review.sum()),
            "priority_review_implicated_records": len(priority_record_ids),
            "pairs_by_tier": counts("match_tier"),
            "pairs_by_basis": counts("match_basis"),
            "pairs_by_scope": counts("scope"),
            "pairs_by_firm_basis": counts("firm_match_basis"),
            "source_rows_by_firm_key_method": {
                str(key): int(value)
                for key, value in prepared_awards["_firm_key_method"].value_counts().items()
            },
        },
        "limitations": [
            "The lexical screen favors precision and can miss semantic paraphrases with dissimilar titles.",
            "Blank topic codes are unknown and are never treated as different topics.",
            "Name+state firm matches are weaker than UEI/DUNS matches and remain labeled.",
            "Similar text may describe a legitimate phase progression, continuation, or complementary work.",
            "Different source Topic Code values are metadata differences, not proof of different technical subjects.",
        ],
    }


def render_markdown(summary: dict[str, Any]) -> str:
    counts = summary["counts"]
    tiers = counts["pairs_by_tier"]
    return "\n".join(
        [
            "# Same-firm, same-work SBIR/STTR award candidates",
            "",
            (
                f"Analyzed **{counts['source_records']:,}** raw SBIR.gov award records and "
                f"identified **{counts['candidate_pairs']:,}** candidate pairs covering "
                f"**{counts['implicated_records']:,}** source records in "
                f"**{counts['work_clusters']:,}** work clusters."
            ),
            "",
            "## Pair counts",
            "",
            f"- Exact-title-and-abstract pairs: {tiers.get('exact', 0):,}",
            f"- Strong lexical pairs: {tiers.get('strong', 0):,}",
            f"- Review pairs: {tiers.get('review', 0):,}",
            f"- Cross-agency pairs: {counts['cross_agency_pairs']:,}",
            f"- Different-known-topic pairs: {counts['different_topic_pairs']:,}",
            f"- Sequential phase pairs: {counts['sequential_phase_pairs']:,}",
            f"- Likely phase progressions with linkage evidence: {counts['likely_phase_progressions']:,}",
            f"- Contemporaneous same-phase pairs: {counts['contemporaneous_same_phase_pairs']:,}",
            (
                "- Priority review pairs outside likely phase progressions: "
                f"{counts['priority_review_pairs']:,}"
            ),
            "",
            "## Interpretation",
            "",
            "These rows are an audit queue, not evidence of improper duplicate funding. ",
            "Review operational environment, end user, technical readiness level, and phase history.",
            "",
            "## Files",
            "",
            "- `same_work_award_pairs.csv`: one row per unordered candidate pair.",
            "- `same_work_award_priority_pairs.csv`: the priority-review subset.",
            "- `same_work_award_records.csv`: every implicated raw source record.",
            "- `same_work_award_summary.json`: thresholds, provenance, counts, and limitations.",
            "",
            "## Firm and topic rules",
            "",
            f"- Firm: {summary['method']['firm_identity']}.",
            f"- Topic: {summary['method']['topic_identity']}.",
            "- A blank topic is unknown, never a different topic.",
            "- Different source codes do not necessarily mean different technical subjects.",
            "- Source rows are preserved; tracking number and contract are reference fields, not keys.",
            "",
            "## Limitations",
            "",
            *[f"- {limitation}" for limitation in summary["limitations"]],
            "",
        ]
    )


def run(
    awards_path: Path,
    output_dir: Path,
    *,
    config: MatchConfig | None = None,
    minimum_tier: str = "review",
) -> dict[str, Any]:
    config = config or MatchConfig()
    awards = pd.read_csv(awards_path, dtype=str, keep_default_na=False)
    source_columns = list(awards.columns)
    prepared = prepare_awards(awards)
    pairs = find_same_work_pairs(prepared, config=config, minimum_tier=minimum_tier)
    pairs, cluster_by_index = add_ids_and_clusters(prepared, pairs, source_columns)
    records = build_record_output(prepared, pairs, cluster_by_index, source_columns)

    internal_columns = ["_left_index", "_right_index"]
    pair_columns = [
        "pair_id",
        "work_cluster_id",
        "record_id_a",
        "record_id_b",
        *[
            column
            for column in pairs.columns
            if column
            not in {
                "pair_id",
                "work_cluster_id",
                "record_id_a",
                "record_id_b",
                *internal_columns,
            }
        ],
    ]
    pairs_for_output = pairs.reindex(columns=pair_columns)
    if not pairs_for_output.empty:
        pairs_for_output = (
            pairs_for_output.assign(
                _priority_sort=pairs_for_output["priority_review"].astype(int),
                _tier_sort=pairs_for_output["match_tier"].map(TIER_RANK),
            )
            .sort_values(
                ["_priority_sort", "_tier_sort", "title_similarity_pct", "pair_id"],
                ascending=[False, False, False, True],
                kind="stable",
            )
            .drop(columns=["_priority_sort", "_tier_sort"])
        )
        priority_pairs_for_output = pairs_for_output.loc[pairs_for_output["priority_review"]]
    else:
        priority_pairs_for_output = pairs_for_output.copy()
    summary = summarize(
        awards_path=awards_path,
        prepared_awards=prepared,
        pairs=pairs,
        records=records,
        config=config,
        minimum_tier=minimum_tier,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    pairs_for_output.to_csv(output_dir / "same_work_award_pairs.csv", index=False)
    priority_pairs_for_output.to_csv(output_dir / "same_work_award_priority_pairs.csv", index=False)
    records.to_csv(output_dir / "same_work_award_records.csv", index=False)
    (output_dir / "same_work_award_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "README.md").write_text(render_markdown(summary), encoding="utf-8")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--awards",
        type=Path,
        default=Path("data/raw/sbir/award_data.csv"),
        help="Raw SBIR.gov award_data.csv path.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports/same-work-awards"),
        help="Destination directory for pair, record, and summary outputs.",
    )
    parser.add_argument(
        "--minimum-tier",
        choices=tuple(TIER_RANK),
        default="review",
        help="Lowest tier to emit. 'review' emits exact, strong, and review rows.",
    )
    parser.add_argument("--near-title-min", type=int, default=85)
    parser.add_argument("--min-exact-abstract-chars", type=int, default=300)
    parser.add_argument("--near-title-strong", type=int, default=92)
    parser.add_argument("--near-abstract-min", type=int, default=75)
    parser.add_argument("--near-abstract-strong", type=int, default=85)
    parser.add_argument("--workers", type=int, default=1)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = MatchConfig(
        min_exact_abstract_chars=args.min_exact_abstract_chars,
        near_title_min=args.near_title_min,
        near_title_strong=args.near_title_strong,
        near_abstract_min=args.near_abstract_min,
        near_abstract_strong=args.near_abstract_strong,
        workers=args.workers,
    )
    summary = run(
        args.awards,
        args.output_dir,
        config=config,
        minimum_tier=args.minimum_tier,
    )
    counts = summary["counts"]
    print(
        f"Wrote {counts['candidate_pairs']:,} pairs and "
        f"{counts['implicated_records']:,} source records to {args.output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
