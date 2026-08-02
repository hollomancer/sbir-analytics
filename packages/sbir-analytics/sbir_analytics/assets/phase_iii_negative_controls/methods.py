"""Approved pure mechanics for Phase III controls and the fixed placebo.

This module does not choose a control population, match firms, materialize an
artifact, or change the frozen census criteria. Its inputs are already-canonical
frames supplied by a future, separately approved orchestration layer.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from sbir_etl.utils.identifiers import normalize_duns, normalize_uei
from sbir_etl.utils.text_normalization import normalize_company_name

from ..phase_iii_census.criteria import build_dropoff_ladder, build_sensitivity_grid


PLACEBO_SEED = 20260801
CONTROL_STATUS_LABEL = "no observed exact-identifier SBIR/STTR match"

EXACT_UEI_EXCLUSION_REASON = "observed_exact_uei_sbir_sttr_match"
EXACT_DUNS_EXCLUSION_REASON = "observed_exact_duns_sbir_sttr_match"

_CANDIDATE_IDENTIFIER_COLUMNS = frozenset({"entity_id", "uei", "duns"})
_HISTORY_IDENTIFIER_COLUMNS = frozenset({"uei", "duns"})
_ELIGIBILITY_AUDIT_COLUMNS = frozenset(
    {
        "passes_exact_identifier_screen",
        "control_status_label",
    }
)
_NULL_TEXT = frozenset({"", "<NA>", "NAN", "NAT", "NONE", "NULL", r"\N"})


class NegativeControlInputError(ValueError):
    """Raised when an input cannot support the approved audit or placebo."""


def _require_columns(frame: pd.DataFrame, required: frozenset[str], *, label: str) -> None:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise NegativeControlInputError(f"{label} is missing required columns: {missing}")


def _normalized_record_key(value: Any) -> str:
    if value is None or value is pd.NA or value is pd.NaT:
        return ""
    try:
        if bool(pd.isna(value)):
            return ""
    except (TypeError, ValueError):
        pass
    normalized = str(value).strip().upper()
    return "" if normalized in _NULL_TEXT else normalized


def _normalized_company_name(value: Any) -> str | None:
    if _normalized_record_key(value) == "":
        return None
    normalized = normalize_company_name(str(value))
    return normalized or None


def _validated_entity_keys(candidate_entities: pd.DataFrame) -> pd.Series:
    keys = candidate_entities["entity_id"].map(_normalized_record_key)
    if keys.eq("").any():
        raise NegativeControlInputError("Every candidate entity must have a nonblank entity_id")
    if keys.duplicated().any():
        raise NegativeControlInputError(
            "Candidate entity_id values must be unique after case/whitespace normalization"
        )
    return keys


def _validate_history(
    candidate_entities: pd.DataFrame,
    complete_award_history: pd.DataFrame,
) -> None:
    _require_columns(
        complete_award_history,
        _HISTORY_IDENTIFIER_COLUMNS,
        label="complete SBIR/STTR award history",
    )
    if not candidate_entities.empty and complete_award_history.empty:
        raise NegativeControlInputError(
            "A nonempty candidate frame cannot be screened against empty SBIR/STTR history"
        )


def audit_exact_identifier_eligibility(
    candidate_entities: pd.DataFrame,
    complete_award_history: pd.DataFrame,
) -> pd.DataFrame:
    """Audit exact UEI/DUNS exclusions against supplied complete award history.

    Passing this screen means only that no exact usable identifier was observed in
    the supplied history. It does not certify that an entity never received an
    SBIR/STTR award.
    """

    _require_columns(
        candidate_entities,
        _CANDIDATE_IDENTIFIER_COLUMNS,
        label="candidate entity frame",
    )
    _validate_history(candidate_entities, complete_award_history)
    _validated_entity_keys(candidate_entities)

    history_ueis = {
        normalized
        for normalized in complete_award_history["uei"].map(normalize_uei)
        if isinstance(normalized, str)
    }
    history_duns = {
        normalized
        for normalized in complete_award_history["duns"].map(normalize_duns)
        if isinstance(normalized, str)
    }

    output = candidate_entities.copy()
    normalized_uei = output["uei"].map(normalize_uei)
    normalized_duns = output["duns"].map(normalize_duns)
    exact_uei_match = normalized_uei.isin(history_ueis)
    exact_duns_match = normalized_duns.isin(history_duns)
    passes = ~(exact_uei_match | exact_duns_match)

    reasons = [
        ";".join(
            reason
            for matched, reason in (
                (uei_match, EXACT_UEI_EXCLUSION_REASON),
                (duns_match, EXACT_DUNS_EXCLUSION_REASON),
            )
            if matched
        )
        for uei_match, duns_match in zip(exact_uei_match, exact_duns_match, strict=True)
    ]

    output["normalized_uei"] = pd.Series(normalized_uei, index=output.index, dtype="string")
    output["normalized_duns"] = pd.Series(normalized_duns, index=output.index, dtype="string")
    output["exact_uei_sbir_sttr_match"] = exact_uei_match.astype(bool)
    output["exact_duns_sbir_sttr_match"] = exact_duns_match.astype(bool)
    output["exclusion_reason"] = pd.Series(reasons, index=output.index, dtype="string").mask(
        lambda series: series.eq("")
    )
    output["passes_exact_identifier_screen"] = passes.astype(bool)
    output["control_status_label"] = pd.Series(
        [CONTROL_STATUS_LABEL if passed else pd.NA for passed in passes],
        index=output.index,
        dtype="string",
    )
    return output


def flag_identifier_free_name_stress_set(
    eligibility_audit: pd.DataFrame,
    complete_award_history: pd.DataFrame,
) -> pd.DataFrame:
    """Flag exact normalized names found on identifier-free award rows.

    The flag is for worst-case stress reporting only. It is not an eligibility
    rule, contamination estimate, upper bound, fuzzy match, or alias screen.
    """

    _require_columns(
        eligibility_audit,
        frozenset({"entity_name", *_ELIGIBILITY_AUDIT_COLUMNS}),
        label="eligibility audit",
    )
    _validate_history(eligibility_audit, complete_award_history)
    _require_columns(
        complete_award_history,
        frozenset({"company_name"}),
        label="complete SBIR/STTR award history",
    )

    history_uei = complete_award_history["uei"].map(normalize_uei)
    history_duns = complete_award_history["duns"].map(normalize_duns)
    history_names = complete_award_history["company_name"].map(_normalized_company_name)
    identifier_free = history_uei.isna() & history_duns.isna()
    reference_names = {
        normalized
        for normalized in history_names.loc[identifier_free]
        if isinstance(normalized, str)
    }

    output = eligibility_audit.copy()
    normalized_entity_name = output["entity_name"].map(_normalized_company_name)
    output["normalized_entity_name"] = pd.Series(
        normalized_entity_name,
        index=output.index,
        dtype="string",
    )
    output["identifier_free_award_exact_name_match"] = (
        normalized_entity_name.notna() & normalized_entity_name.isin(reference_names)
    ).astype(bool)
    return output


def _parse_prior_end_dates(values: pd.Series) -> pd.Series:
    present = values.map(_normalized_record_key).ne("")
    parsed = pd.to_datetime(values, errors="coerce", utc=True, format="mixed")
    parsed = parsed.dt.tz_localize(None).dt.normalize()
    if (present & parsed.isna()).any():
        raise NegativeControlInputError(
            "prior_period_of_performance_end contains an unparsable nonblank value"
        )
    return parsed


def _date_multiset(values: pd.Series) -> Counter[int | None]:
    return Counter(None if pd.isna(value) else int(pd.Timestamp(value).value) for value in values)


def permute_prior_end_dates(pairs: pd.DataFrame) -> pd.DataFrame:
    """Apply the one fixed placebo permutation at unique prior-award grain."""

    required = frozenset({"prior_award_id", "prior_period_of_performance_end"})
    _require_columns(pairs, required, label="placebo pair frame")
    if pairs.empty:
        return pairs.copy()

    prior_keys = pairs["prior_award_id"].map(_normalized_record_key)
    if prior_keys.eq("").any():
        raise NegativeControlInputError("Every placebo pair row must have a prior_award_id")

    prior_dates = _parse_prior_end_dates(pairs["prior_period_of_performance_end"])
    award_rows = pd.DataFrame(
        {"_prior_key": prior_keys, "_prior_end": prior_dates},
        index=pairs.index,
    )
    date_variants = award_rows.groupby("_prior_key", sort=False)["_prior_end"].nunique(dropna=False)
    if date_variants.gt(1).any():
        raise NegativeControlInputError(
            "Each prior_award_id must map to exactly one prior_period_of_performance_end"
        )

    unique_awards = (
        award_rows.drop_duplicates("_prior_key", keep="first")
        .sort_values("_prior_key", kind="stable")
        .reset_index(drop=True)
    )
    donor_order = np.random.default_rng(PLACEBO_SEED).permutation(len(unique_awards))
    shuffled_dates = unique_awards["_prior_end"].iloc[donor_order].reset_index(drop=True)
    date_by_award = dict(zip(unique_awards["_prior_key"], shuffled_dates, strict=True))

    output = pairs.copy()
    output_dates = prior_keys.map(date_by_award)
    output["prior_period_of_performance_end"] = pd.to_datetime(output_dates)

    if len(output) != len(pairs) or not output.index.equals(pairs.index):
        raise NegativeControlInputError("Placebo permutation changed pair row count or order")
    for column in pairs.columns:
        if column == "prior_period_of_performance_end":
            continue
        if not output[column].equals(pairs[column]):
            raise NegativeControlInputError(
                f"Placebo permutation changed prohibited non-date column: {column}"
            )

    output_award_dates = pd.DataFrame(
        {"_prior_key": prior_keys, "_prior_end": output["prior_period_of_performance_end"]}
    )
    output_variants = output_award_dates.groupby("_prior_key", sort=False)["_prior_end"].nunique(
        dropna=False
    )
    if output_variants.gt(1).any():
        raise NegativeControlInputError(
            "Placebo date was not propagated consistently across prior-award fan-out"
        )
    output_unique_dates = output_award_dates.drop_duplicates("_prior_key", keep="first")[
        "_prior_end"
    ]
    if _date_multiset(output_unique_dates) != _date_multiset(unique_awards["_prior_end"]):
        raise NegativeControlInputError(
            "Placebo permutation did not preserve the award-grain date distribution"
        )
    return output


def build_placebo_census_tables(
    pairs: pd.DataFrame,
    data_cut_date: date,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run one permuted frame through both unchanged frozen census helpers."""

    placebo_pairs = permute_prior_end_dates(pairs)
    return (
        build_dropoff_ladder(placebo_pairs, data_cut_date),
        build_sensitivity_grid(placebo_pairs, data_cut_date),
    )
