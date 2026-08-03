"""Pure firm-level outcomes for the Phase III matched negative control."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date
from typing import Any, NamedTuple

import pandas as pd

from sbir_etl.utils.identifiers import normalize_uei

from ..phase_iii_census.criteria import CORE_CLAUSES, CensusInputError, apply_core_clauses


MAPPING_COLUMNS = ("exact_uei", "firm_id")
FIRM_COUNT_COLUMNS = (
    "firm_id",
    "step_order",
    "clause_id",
    "clause",
    "surviving_pairs",
    "distinct_transactions",
    "distinct_contracts",
)
FREQUENCY_COLUMNS = (
    "step_order",
    "clause_id",
    "clause",
    "contracts_surviving",
    "firms",
    "firm_proportion",
)


class FirmOutcomeTables(NamedTuple):
    """Unlabeled tables returned by the shared evaluator."""

    firm_counts: pd.DataFrame
    frequency_distribution: pd.DataFrame


class FirmOutcomeComparison(NamedTuple):
    """Labeled tables and the final-clause arm comparison."""

    firm_counts: pd.DataFrame
    frequency_distribution: pd.DataFrame
    final_comparison: pd.DataFrame


def _text(value: Any) -> str:
    if value is None or value is pd.NA or value is pd.NaT:
        return ""
    try:
        if bool(pd.isna(value)):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return "" if text.upper() in {"", "<NA>", "NAN", "NAT", "NONE", "NULL", r"\N"} else text


def _values(value: Any) -> tuple[Any, ...]:
    if isinstance(value, tuple | list | set | frozenset):
        return tuple(value)
    tolist = getattr(value, "tolist", None)
    converted = tolist() if callable(tolist) else None
    if isinstance(converted, list):
        return tuple(converted)
    return () if not _text(value) else (value,)


def _require_columns(frame: pd.DataFrame, required: Iterable[str], *, label: str) -> None:
    if missing := sorted(set(required) - set(frame.columns)):
        raise CensusInputError(f"{label} is missing required columns: {missing}")


def _normalize_uei_or_raise(value: Any, *, label: str) -> str:
    normalized = normalize_uei(value)
    if normalized is None:
        raise CensusInputError(f"{label} contains a blank or invalid exact UEI")
    return normalized


def _normalize_firm_id(value: Any, *, label: str) -> str:
    firm_id = _text(value)
    if not firm_id:
        raise CensusInputError(f"{label} contains a blank firm_id")
    return firm_id


def _matched_ids(
    values: Iterable[Any], *, label: str, require_unique: bool = False
) -> tuple[str, ...]:
    normalized = tuple(_normalize_firm_id(value, label=label) for value in values)
    if require_unique and len(normalized) != len(set(normalized)):
        raise CensusInputError(f"{label} contains duplicate firm IDs")
    return tuple(dict.fromkeys(normalized))


def build_uei_firm_mapping(
    covariates: pd.DataFrame, matched_firm_ids: Iterable[Any]
) -> pd.DataFrame:
    """Expand selected firm envelopes into a unique exact-UEI-to-firm mapping."""

    _require_columns(covariates, {"firm_id", "firm_ueis"}, label="firm covariates")
    selected = _matched_ids(matched_firm_ids, label="matched firm risk set")
    selected_set = set(selected)

    normalized_rows: dict[str, tuple[str, ...]] = {}
    owned_ueis: dict[str, str] = {}
    for row in covariates.loc[:, ["firm_id", "firm_ueis"]].itertuples(index=False):
        firm_id = _normalize_firm_id(row.firm_id, label="firm covariates")
        if firm_id not in selected_set:
            continue
        if firm_id in normalized_rows:
            raise CensusInputError(f"firm covariates contain duplicate firm_id: {firm_id}")
        ueis = tuple(
            sorted(
                {
                    _normalize_uei_or_raise(value, label=f"firm {firm_id}")
                    for value in _values(row.firm_ueis)
                }
            )
        )
        if not ueis:
            raise CensusInputError(f"firm {firm_id} has no exact UEIs")
        for uei in ueis:
            previous = owned_ueis.setdefault(uei, firm_id)
            if previous != firm_id:
                raise CensusInputError(
                    f"exact UEI {uei} belongs to multiple firm envelopes: {previous}, {firm_id}"
                )
        normalized_rows[firm_id] = ueis

    missing = sorted(set(selected) - set(normalized_rows))
    if missing:
        raise CensusInputError(f"matched firm risk set is absent from covariates: {missing}")
    records = [
        {"exact_uei": uei, "firm_id": firm_id}
        for firm_id in selected
        for uei in normalized_rows[firm_id]
    ]
    return pd.DataFrame.from_records(records, columns=MAPPING_COLUMNS)


def build_control_pseudo_priors(
    phase_ii: pd.DataFrame,
    matches: pd.DataFrame,
    control_covariates: pd.DataFrame,
) -> pd.DataFrame:
    """Copy each matched treated firm's complete Phase II rows to each control exact UEI."""

    _require_columns(phase_ii, {"recipient_uei"}, label="Phase II rows")
    _require_columns(
        matches,
        {"treated_firm_id", "control_firm_id"},
        label="matched controls",
    )
    if matches[["treated_firm_id", "control_firm_id"]].duplicated().any():
        raise CensusInputError("matched controls contain duplicate treated-control pairs")
    control_ids = _matched_ids(matches["control_firm_id"], label="matched control IDs")
    mapping = build_uei_firm_mapping(control_covariates, control_ids)

    normalized_phase_ii = phase_ii["recipient_uei"].map(normalize_uei)
    if normalized_phase_ii.isna().any():
        raise CensusInputError("Phase II rows contain a blank or invalid recipient_uei")

    records: list[dict[str, Any]] = []
    for match in matches.loc[:, ["treated_firm_id", "control_firm_id"]].itertuples(index=False):
        treated_uei = _normalize_uei_or_raise(
            match.treated_firm_id, label="matched treated firm IDs"
        )
        source_rows = phase_ii.loc[normalized_phase_ii.eq(treated_uei)]
        if source_rows.empty:
            raise CensusInputError(f"matched treated firm {treated_uei} has no Phase II rows")
        control_id = _normalize_firm_id(match.control_firm_id, label="matched control IDs")
        control_ueis = mapping.loc[mapping["firm_id"].eq(control_id), "exact_uei"]
        for control_uei in control_ueis:
            for source in source_rows.to_dict(orient="records"):
                copied = {str(key): value for key, value in source.items()}
                copied["recipient_uei"] = control_uei
                records.append(copied)
    return pd.DataFrame.from_records(records, columns=phase_ii.columns)


def _validated_mapping(
    uei_to_firm: pd.DataFrame, firm_risk_set: Sequence[Any]
) -> tuple[pd.DataFrame, tuple[str, ...]]:
    _require_columns(uei_to_firm, MAPPING_COLUMNS, label="UEI-to-firm mapping")
    risk_set = _matched_ids(firm_risk_set, label="firm risk set", require_unique=True)
    records: list[dict[str, str]] = []
    for row in uei_to_firm.loc[:, list(MAPPING_COLUMNS)].itertuples(index=False):
        records.append(
            {
                "exact_uei": _normalize_uei_or_raise(row.exact_uei, label="UEI-to-firm mapping"),
                "firm_id": _normalize_firm_id(row.firm_id, label="UEI-to-firm mapping"),
            }
        )
    mapping = pd.DataFrame.from_records(records, columns=MAPPING_COLUMNS)
    if mapping["exact_uei"].duplicated().any():
        raise CensusInputError("UEI-to-firm mapping must contain each exact UEI exactly once")
    if set(mapping["firm_id"]) != set(risk_set):
        raise CensusInputError("UEI-to-firm mapping firm IDs must equal the complete firm risk set")
    return mapping, risk_set


def _normalized_distinct(series: pd.Series) -> pd.Series:
    normalized = series.astype("string").str.strip().str.upper()
    return normalized.mask(normalized.isin(["", "NAN", "NONE", "NULL", "<NA>", r"\N"]))


def evaluate_firm_outcomes(
    pair_frame: pd.DataFrame,
    uei_to_firm: pd.DataFrame,
    firm_risk_set: Sequence[Any],
    data_cut_date: date,
) -> FirmOutcomeTables:
    """Evaluate the inherited universe and frozen cumulative clauses for every firm."""

    mapping, risk_set = _validated_mapping(uei_to_firm, firm_risk_set)
    stages = apply_core_clauses(pair_frame, data_cut_date)
    pair_ueis = pair_frame["prior_recipient_uei"].map(normalize_uei)
    if pair_ueis.isna().any():
        raise CensusInputError("paired prior_recipient_uei values must be valid exact UEIs")
    missing_ueis = sorted(set(pair_ueis) - set(mapping["exact_uei"]))
    if missing_ueis:
        raise CensusInputError(
            f"paired UEIs are absent from the UEI-to-firm mapping: {missing_ueis}"
        )
    firm_by_uei = mapping.set_index("exact_uei")["firm_id"]

    count_rows: list[dict[str, Any]] = []
    distribution_rows: list[dict[str, Any]] = []
    denominator = len(risk_set)
    for step_order, (clause_id, clause, survivors) in enumerate(stages):
        stage = survivors.assign(
            _exact_uei=survivors["prior_recipient_uei"].map(normalize_uei),
            _transaction=_normalized_distinct(survivors["target_transaction_id"]),
            _contract=_normalized_distinct(survivors["target_contract_key"]),
        )
        stage["_firm_id"] = stage["_exact_uei"].map(firm_by_uei)
        grouped = stage.groupby("_firm_id", sort=False, dropna=False)
        pairs = grouped.size()
        transactions = grouped["_transaction"].nunique(dropna=True)
        contracts = grouped["_contract"].nunique(dropna=True)
        stage_contract_counts: list[int] = []
        for firm_id in risk_set:
            contract_count = int(contracts.get(firm_id, 0))
            stage_contract_counts.append(contract_count)
            count_rows.append(
                {
                    "firm_id": firm_id,
                    "step_order": step_order,
                    "clause_id": clause_id,
                    "clause": clause,
                    "surviving_pairs": int(pairs.get(firm_id, 0)),
                    "distinct_transactions": int(transactions.get(firm_id, 0)),
                    "distinct_contracts": contract_count,
                }
            )
        frequencies = pd.Series(stage_contract_counts, dtype="int64").value_counts().sort_index()
        for contracts_surviving, firms in frequencies.items():
            contracts_value: Any = contracts_surviving
            distribution_rows.append(
                {
                    "step_order": step_order,
                    "clause_id": clause_id,
                    "clause": clause,
                    "contracts_surviving": int(contracts_value),
                    "firms": int(firms),
                    "firm_proportion": float(firms / denominator) if denominator else 0.0,
                }
            )
    return FirmOutcomeTables(
        pd.DataFrame.from_records(count_rows, columns=FIRM_COUNT_COLUMNS),
        pd.DataFrame.from_records(distribution_rows, columns=FREQUENCY_COLUMNS),
    )


def compare_firm_outcomes(
    sbir_outcomes: FirmOutcomeTables,
    control_outcomes: FirmOutcomeTables,
) -> FirmOutcomeComparison:
    """Label two shared-evaluator results and compare their final contract-count PMFs."""

    final_clause = CORE_CLAUSES[-1].clause_id
    labeled_counts = []
    labeled_distributions = []
    clearing: dict[str, tuple[int, int, float]] = {}
    final_pmfs: dict[str, pd.Series] = {}
    for label, outcomes in (("sbir", sbir_outcomes), ("control", control_outcomes)):
        counts = outcomes.firm_counts.copy()
        distribution = outcomes.frequency_distribution.copy()
        _require_columns(counts, FIRM_COUNT_COLUMNS, label=f"{label} firm counts")
        _require_columns(distribution, FREQUENCY_COLUMNS, label=f"{label} distribution")
        counts.insert(0, "arm", label)
        distribution.insert(0, "arm", label)
        labeled_counts.append(counts)
        labeled_distributions.append(distribution)

        final_counts = counts.loc[counts["clause_id"].eq(final_clause)]
        if final_counts["firm_id"].duplicated().any() or final_counts.empty:
            raise CensusInputError(f"{label} outcomes must contain one final row per firm")
        numerator = int(final_counts["distinct_contracts"].gt(0).sum())
        denominator = int(len(final_counts))
        proportion = numerator / denominator
        clearing[label] = (numerator, denominator, float(proportion))

        final_distribution = distribution.loc[distribution["clause_id"].eq(final_clause)]
        if final_distribution["contracts_surviving"].duplicated().any():
            raise CensusInputError(f"{label} final distribution contains duplicate counts")
        final_pmfs[label] = final_distribution.set_index("contracts_surviving")[
            "firm_proportion"
        ].astype(float)

    support = final_pmfs["sbir"].index.union(final_pmfs["control"].index)
    sbir_pmf = final_pmfs["sbir"].reindex(support, fill_value=0.0)
    control_pmf = final_pmfs["control"].reindex(support, fill_value=0.0)
    overlap = float(pd.concat([sbir_pmf, control_pmf], axis=1).min(axis=1).sum())
    sbir_numerator, sbir_denominator, sbir_proportion = clearing["sbir"]
    control_numerator, control_denominator, control_proportion = clearing["control"]
    risk_ratio = None if control_proportion == 0 else sbir_proportion / control_proportion
    comparison = pd.DataFrame.from_records(
        [
            {
                "final_clause_id": final_clause,
                "overlap_coefficient": overlap,
                "sbir_clearing_numerator": sbir_numerator,
                "sbir_clearing_denominator": sbir_denominator,
                "sbir_clearing_proportion": sbir_proportion,
                "control_clearing_numerator": control_numerator,
                "control_clearing_denominator": control_denominator,
                "control_clearing_proportion": control_proportion,
                "sbir_control_risk_ratio": risk_ratio,
            }
        ]
    )
    return FirmOutcomeComparison(
        pd.concat(labeled_counts, ignore_index=True),
        pd.concat(labeled_distributions, ignore_index=True),
        comparison,
    )


__all__ = [
    "FIRM_COUNT_COLUMNS",
    "FREQUENCY_COLUMNS",
    "MAPPING_COLUMNS",
    "FirmOutcomeComparison",
    "FirmOutcomeTables",
    "build_control_pseudo_priors",
    "build_uei_firm_mapping",
    "compare_firm_outcomes",
    "evaluate_firm_outcomes",
]
