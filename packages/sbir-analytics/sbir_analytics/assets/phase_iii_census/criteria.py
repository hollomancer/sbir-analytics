"""Pure criteria and audit-table builders for the label-free Phase III census.

This module deliberately has no dependency on the Phase III scoring implementation.
Every inclusion decision is one of the clauses frozen in
``specs/phase-iii-census/design.md``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

import pandas as pd


class CensusInputError(ValueError):
    """Raised when source data cannot support the frozen census contract."""


class SensitivityReviewRequired(RuntimeError):
    """Raised when the pre-authorized sensitivity checkpoint is triggered."""

    def __init__(self, grid: pd.DataFrame, reasons: list[str]) -> None:
        self.grid = grid.copy()
        self.reasons = tuple(reasons)
        table = grid.to_dict(orient="records")
        super().__init__(f"Sensitivity grid requires review: {reasons}; full_grid={table}")


@dataclass(frozen=True)
class Clause:
    """One frozen cumulative census clause."""

    clause_id: str
    label: str
    predicate: Callable[[pd.DataFrame, date], pd.Series]


REQUIRED_PAIR_COLUMNS = frozenset(
    {
        "prior_award_id",
        "prior_recipient_uei",
        "prior_agency",
        "prior_sub_agency",
        "prior_naics_code",
        "prior_psc_code",
        "prior_period_of_performance_end",
        "target_id",
        "target_recipient_uei",
        "target_agency",
        "target_sub_agency",
        "target_naics_code",
        "target_psc_code",
        "target_action_date",
        "target_competition_type",
        "target_obligated_amount",
        "target_research",
        "target_sbir_phase",
        "target_transaction_id",
        "target_contract_key",
        "agency_match_level",
    }
)

REQUIRED_PRIOR_SOURCE_COLUMNS = frozenset(
    {
        "award_id",
        "recipient_uei",
        "agency",
        "sub_agency",
        "naics_code",
        "psc_code",
        "period_of_performance_end",
    }
)

# USAspending's authoritative FPDS coding field must exist even when every value is
# genuinely null. ``sbir_phase`` is optional supplemental evidence and is checked by
# the pair criteria when genuinely supplied, but is never required or synthesized.
REQUIRED_TARGET_SOURCE_COLUMNS = frozenset({"research"})
TARGET_NAICS_SOURCE_COLUMNS = frozenset({"naics_code", "naics"})
TARGET_PSC_SOURCE_COLUMNS = frozenset({"psc_code", "product_or_service_code"})
REQUIRED_TARGET_SOURCE_ALIASES: dict[str, frozenset[str]] = {
    "contract identifier": frozenset({"contract_id", "piid", "generated_unique_award_id"}),
    "recipient UEI": frozenset({"vendor_uei", "recipient_uei", "uei"}),
    "top-tier agency": frozenset(
        {
            "awarding_toptier_agency_name",
            "awarding_agency_name",
            "agency",
            "awarding_agency",
        }
    ),
    "sub-tier agency": frozenset(
        {"awarding_subtier_agency_name", "awarding_sub_tier_agency_name", "sub_agency"}
    ),
    "action date": frozenset({"action_date", "award_date"}),
    "competition type": frozenset({"extent_competed", "competition_type", "type_of_set_aside"}),
    "obligated amount": frozenset(
        {"federal_action_obligation", "obligated_amount", "obligation_amount"}
    ),
    "stable transaction identifier": frozenset({"transaction_unique_id"}),
    "generated award identifier": frozenset({"generated_unique_award_id", "unique_award_key"}),
}

PHASE_I_II_RESEARCH_CODES = frozenset({"SR1", "SR2", "ST1", "ST2"})
PHASE_III_RESEARCH_CODES = frozenset({"SR3", "ST3"})
PHASE_I_II_LABELS = frozenset({"PHASE I", "I", "1", "PHASE 1", "PHASE II", "II", "2", "PHASE 2"})
PHASE_III_LABELS = frozenset({"PHASE III", "III", "3", "PHASE 3"})

METRIC_COLUMNS = [
    "surviving_pairs",
    "distinct_firms",
    "distinct_contracts",
    "total_obligated_dollars",
]

_TARGET_TRANSACTION_INVARIANTS = [
    "target_id",
    "target_recipient_uei",
    "target_agency",
    "target_sub_agency",
    "target_naics_code",
    "target_psc_code",
    "target_action_date",
    "target_competition_type",
    "target_obligated_amount",
    "target_research",
    "target_sbir_phase",
    "target_contract_key",
]


def _normalize_text(series: pd.Series) -> pd.Series:
    normalized = series.astype("string").str.strip().str.upper()
    return normalized.mask(normalized.isin(["", "NAN", "NONE", "NULL", "<NA>", r"\N"]))


def _normalized_key(series: pd.Series) -> pd.Series:
    return _normalize_text(series)


def _coerce_dates(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce", utc=True).dt.tz_localize(None).dt.normalize()


def _cut_timestamp(data_cut_date: date) -> pd.Timestamp:
    if not isinstance(data_cut_date, date):
        raise CensusInputError("census_data_cut_date must be an explicit date")
    return pd.Timestamp(data_cut_date)


def validate_source_columns(prior_awards: pd.DataFrame, contracts: pd.DataFrame) -> None:
    """Fail when source-column absence would masquerade as negative evidence."""

    missing_prior = sorted(REQUIRED_PRIOR_SOURCE_COLUMNS - set(prior_awards.columns))
    if missing_prior:
        raise CensusInputError(f"Phase II source is missing required columns: {missing_prior}")

    missing_target = sorted(REQUIRED_TARGET_SOURCE_COLUMNS - set(contracts.columns))
    if missing_target:
        raise CensusInputError(
            "Contract source is missing required coding columns; absence cannot be treated "
            f"as an uncoded value: {missing_target}"
        )

    if not TARGET_NAICS_SOURCE_COLUMNS.intersection(contracts.columns):
        raise CensusInputError(
            "Contract source has no NAICS column (expected one of "
            f"{sorted(TARGET_NAICS_SOURCE_COLUMNS)})"
        )
    if not TARGET_PSC_SOURCE_COLUMNS.intersection(contracts.columns):
        raise CensusInputError(
            "Contract source has no PSC column (expected one of "
            f"{sorted(TARGET_PSC_SOURCE_COLUMNS)})"
        )

    missing_alias_groups = {
        label: sorted(aliases)
        for label, aliases in REQUIRED_TARGET_SOURCE_ALIASES.items()
        if not aliases.intersection(contracts.columns)
    }
    if missing_alias_groups:
        raise CensusInputError(
            "Contract source is missing required target field groups; absent source "
            f"fields cannot produce a publishable zero: {missing_alias_groups}"
        )


def validate_pair_frame(pairs: pd.DataFrame) -> None:
    """Validate keys and transaction fan-out invariants before any counting."""

    missing = sorted(REQUIRED_PAIR_COLUMNS - set(pairs.columns))
    if missing:
        raise CensusInputError(f"Pair frame is missing required columns: {missing}")
    if pairs.empty:
        return

    transaction_key = _normalized_key(pairs["target_transaction_id"])
    contract_key = _normalized_key(pairs["target_contract_key"])
    prior_key = _normalized_key(pairs["prior_award_id"])
    prior_uei = _normalized_key(pairs["prior_recipient_uei"])
    target_uei = _normalized_key(pairs["target_recipient_uei"])

    if transaction_key.isna().any():
        raise CensusInputError("Every paired target row must have a stable transaction identifier")
    if contract_key.isna().any():
        raise CensusInputError(
            "Every paired target row must have a generated award key; PIID is not a substitute"
        )
    if prior_key.isna().any():
        raise CensusInputError("Every paired prior row must have a stable award identifier")
    if prior_uei.isna().any() or target_uei.isna().any() or prior_uei.ne(target_uei).any():
        raise CensusInputError("Every census pair must satisfy the normalized exact-UEI gate")

    prior_has_taxonomy = (
        _normalize_text(pairs["prior_naics_code"]).notna()
        | _normalize_text(pairs["prior_psc_code"]).notna()
    )
    target_has_taxonomy = (
        _normalize_text(pairs["target_naics_code"]).notna()
        | _normalize_text(pairs["target_psc_code"]).notna()
    )
    if not prior_has_taxonomy.any() or not target_has_taxonomy.any():
        raise CensusInputError(
            "The exact-UEI pair universe has no usable prior or target NAICS/PSC values; "
            "publishing an all-zero lineage result would confuse missing provenance with "
            "taxonomy disagreement"
        )

    obligations = pd.to_numeric(pairs["target_obligated_amount"], errors="coerce")
    if obligations.isna().any():
        raise CensusInputError(
            "Every paired target transaction must have a numeric signed obligated amount"
        )

    pair_keys = pd.DataFrame({"prior": prior_key, "transaction": transaction_key})
    if pair_keys.duplicated().any():
        raise CensusInputError(
            "Duplicate prior-award × target-transaction rows violate the pair-table grain"
        )

    check = pairs.assign(_transaction_key=transaction_key)
    for column in _TARGET_TRANSACTION_INVARIANTS:
        comparable = _normalize_text(check[column])
        variants = comparable.groupby(check["_transaction_key"], dropna=False).nunique(dropna=False)
        if variants.gt(1).any():
            raise CensusInputError(
                f"Target transaction identifier maps to conflicting {column} values"
            )


def criterion_prior_end_observable(pairs: pd.DataFrame, data_cut_date: date) -> pd.Series:
    prior_end = _coerce_dates(pairs["prior_period_of_performance_end"])
    return prior_end.notna() & prior_end.le(_cut_timestamp(data_cut_date))


def criterion_target_post_completion(pairs: pd.DataFrame, data_cut_date: date) -> pd.Series:
    prior_end = _coerce_dates(pairs["prior_period_of_performance_end"])
    target_date = _coerce_dates(pairs["target_action_date"])
    cut = _cut_timestamp(data_cut_date)
    return target_date.notna() & prior_end.lt(target_date) & target_date.le(cut)


def criterion_not_phase_i_or_ii_coded(pairs: pd.DataFrame, _data_cut_date: date) -> pd.Series:
    research = _normalize_text(pairs["target_research"])
    phase = _normalize_text(pairs["target_sbir_phase"])
    return ~research.isin(PHASE_I_II_RESEARCH_CODES) & ~phase.isin(PHASE_I_II_LABELS)


def criterion_not_phase_iii_coded(pairs: pd.DataFrame, _data_cut_date: date) -> pd.Series:
    research = _normalize_text(pairs["target_research"])
    phase = _normalize_text(pairs["target_sbir_phase"])
    return ~research.isin(PHASE_III_RESEARCH_CODES) & ~phase.isin(PHASE_III_LABELS)


def criterion_exact_taxonomy_lineage(pairs: pd.DataFrame, _data_cut_date: date) -> pd.Series:
    prior_naics = _normalize_text(pairs["prior_naics_code"])
    target_naics = _normalize_text(pairs["target_naics_code"])
    prior_psc = _normalize_text(pairs["prior_psc_code"])
    target_psc = _normalize_text(pairs["target_psc_code"])
    naics_match = prior_naics.notna() & target_naics.notna() & prior_naics.eq(target_naics)
    psc_match = prior_psc.notna() & target_psc.notna() & prior_psc.eq(target_psc)
    return naics_match | psc_match


CORE_CLAUSES: tuple[Clause, ...] = (
    Clause(
        "prior_end_observable",
        "Prior Phase II end date is observable at the data cut",
        criterion_prior_end_observable,
    ),
    Clause(
        "target_post_completion",
        "Target action is strictly after the Phase II end and at the data cut",
        criterion_target_post_completion,
    ),
    Clause(
        "not_phase_i_or_ii_coded",
        "Target is not affirmatively coded SBIR/STTR Phase I or II",
        criterion_not_phase_i_or_ii_coded,
    ),
    Clause(
        "not_phase_iii_coded",
        "Target is not already coded SBIR/STTR Phase III",
        criterion_not_phase_iii_coded,
    ),
    Clause(
        "exact_naics_or_psc_lineage",
        "Prior and target share an exact full NAICS or PSC code",
        criterion_exact_taxonomy_lineage,
    ),
)


def ordered_clause_metadata() -> list[dict[str, str]]:
    return [{"clause_id": clause.clause_id, "label": clause.label} for clause in CORE_CLAUSES]


def _summarize(pairs: pd.DataFrame) -> dict[str, int | float]:
    if pairs.empty:
        return {
            "surviving_pairs": 0,
            "distinct_firms": 0,
            "distinct_contracts": 0,
            "total_obligated_dollars": 0.0,
        }

    firms = _normalized_key(pairs["prior_recipient_uei"])
    contracts = _normalized_key(pairs["target_contract_key"])
    transactions = _normalized_key(pairs["target_transaction_id"])
    unique_transactions = pairs.assign(_transaction_key=transactions).drop_duplicates(
        subset=["_transaction_key"], keep="first"
    )
    obligations = pd.to_numeric(unique_transactions["target_obligated_amount"], errors="raise")
    total = obligations.sum()

    return {
        "surviving_pairs": int(len(pairs)),
        "distinct_firms": int(firms.nunique(dropna=True)),
        "distinct_contracts": int(contracts.nunique(dropna=True)),
        "total_obligated_dollars": float(total),
    }


def apply_core_clauses(
    pairs: pd.DataFrame, data_cut_date: date
) -> list[tuple[str, str, pd.DataFrame]]:
    """Return the inherited universe plus each frozen cumulative survivor frame."""

    validate_pair_frame(pairs)
    _cut_timestamp(data_cut_date)

    current = pairs.copy()
    stages = [
        (
            "all_exact_uei_pairs",
            "All inherited normalized exact-UEI pairs",
            current.reset_index(drop=True),
        )
    ]
    for clause in CORE_CLAUSES:
        mask = clause.predicate(current, data_cut_date).fillna(False).astype(bool)
        current = current.loc[mask].copy()
        stages.append((clause.clause_id, clause.label, current.reset_index(drop=True)))
    return stages


def build_dropoff_ladder(pairs: pd.DataFrame, data_cut_date: date) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for order, (clause_id, label, survivors) in enumerate(apply_core_clauses(pairs, data_cut_date)):
        rows.append(
            {
                "step_order": order,
                "clause_id": clause_id,
                "clause": label,
                **_summarize(survivors),
            }
        )
    return pd.DataFrame(rows)


def _same_department(pairs: pd.DataFrame) -> pd.Series:
    prior = _normalize_text(pairs["prior_agency"])
    target = _normalize_text(pairs["target_agency"])
    return prior.notna() & target.notna() & prior.eq(target)


def _same_agency_component(pairs: pd.DataFrame) -> pd.Series:
    prior = _normalize_text(pairs["prior_sub_agency"])
    target = _normalize_text(pairs["target_sub_agency"])
    return _same_department(pairs) & prior.notna() & target.notna() & prior.eq(target)


def _within_calendar_years(pairs: pd.DataFrame, years: int) -> pd.Series:
    prior_end = _coerce_dates(pairs["prior_period_of_performance_end"])
    target_date = _coerce_dates(pairs["target_action_date"])
    anniversary = prior_end.map(
        lambda value: value + pd.DateOffset(years=years) if pd.notna(value) else pd.NaT
    )
    return target_date.le(anniversary)


def build_sensitivity_grid(pairs: pd.DataFrame, data_cut_date: date) -> pd.DataFrame:
    """Build all six frozen time-window × agency-continuity cells."""

    full = apply_core_clauses(pairs, data_cut_date)[-1][2]
    rows: list[dict[str, object]] = []
    windows: tuple[tuple[str, int | None], ...] = (("none", None), ("5y", 5), ("10y", 10))
    agencies: tuple[tuple[str, Callable[[pd.DataFrame], pd.Series]], ...] = (
        ("same_agency", _same_agency_component),
        ("same_department", _same_department),
    )

    for window_label, years in windows:
        window_mask = (
            pd.Series(True, index=full.index, dtype=bool)
            if years is None
            else _within_calendar_years(full, years)
        )
        for agency_label, agency_predicate in agencies:
            mask = window_mask & agency_predicate(full)
            survivors = full.loc[mask.fillna(False)].copy()
            rows.append(
                {
                    "cell_id": f"{window_label}__{agency_label}",
                    "time_window": window_label,
                    "agency_match": agency_label,
                    **_summarize(survivors),
                }
            )

    return pd.DataFrame(rows)


def sensitivity_review_reasons(grid: pd.DataFrame) -> list[str]:
    """Return pre-authorized greater-than-threefold checkpoint reasons."""

    reasons: list[str] = []
    for metric in ("distinct_firms", "distinct_contracts"):
        values = pd.to_numeric(grid[metric], errors="coerce").dropna()
        if values.empty:
            continue
        smallest = values.min()
        largest = values.max()
        if (smallest == 0 and largest > 0) or (smallest > 0 and largest > smallest * 3):
            reasons.append(f"{metric} spans more than 3x across cells")

    dollars = pd.to_numeric(grid["total_obligated_dollars"], errors="coerce").dropna()
    if not dollars.empty and dollars.gt(0).all() and dollars.max() > dollars.min() * 3:
        reasons.append("total_obligated_dollars spans more than 3x across positive cells")
    return reasons


def enforce_sensitivity_checkpoint(grid: pd.DataFrame) -> None:
    reasons = sensitivity_review_reasons(grid)
    if reasons:
        raise SensitivityReviewRequired(grid, reasons)


__all__ = [
    "CORE_CLAUSES",
    "CensusInputError",
    "METRIC_COLUMNS",
    "SensitivityReviewRequired",
    "apply_core_clauses",
    "build_dropoff_ladder",
    "build_sensitivity_grid",
    "criterion_exact_taxonomy_lineage",
    "criterion_not_phase_i_or_ii_coded",
    "criterion_not_phase_iii_coded",
    "criterion_prior_end_observable",
    "criterion_target_post_completion",
    "enforce_sensitivity_checkpoint",
    "ordered_clause_metadata",
    "sensitivity_review_reasons",
    "validate_pair_frame",
    "validate_source_columns",
]
