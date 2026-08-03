"""Fixed-seed, cross-firm placebo mechanics for the Phase III census."""

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from ..phase_iii_census.criteria import build_census_tables


PLACEBO_SEED = 20260801
ASSIGNMENT_AUDIT_COLUMNS = (
    "recipient_award_id",
    "recipient_firm_uei",
    "donor_award_id",
    "donor_firm_uei",
    "original_prior_end",
    "permuted_prior_end",
    "date_value_changed",
    "seed",
    "mapping_sha256",
)
_REQUIRED_COLUMNS = frozenset(
    {
        "prior_award_id",
        "prior_recipient_uei",
        "prior_period_of_performance_end",
    }
)
_NULL_TEXT = frozenset({"", "<NA>", "NAN", "NAT", "NONE", "NULL", r"\N"})


class PlaceboInputError(ValueError):
    """Raised when a pair frame cannot support the frozen placebo."""


@dataclass(frozen=True)
class PlaceboAssignment:
    """The award-level donor audit and its exact fan-back to the pair frame."""

    audit: pd.DataFrame
    permuted_pairs: pd.DataFrame
    mapping_sha256: str


@dataclass(frozen=True)
class PlaceboCensusTables:
    """The assignment and the two unchanged census tables for one placebo frame."""

    assignment: PlaceboAssignment
    dropoff: pd.DataFrame
    sensitivity: pd.DataFrame


def _text(value: Any) -> str:
    if value is None or value is pd.NA or value is pd.NaT:
        return ""
    try:
        if bool(pd.isna(value)):
            return ""
    except (TypeError, ValueError):
        pass
    normalized = str(value).strip().upper()
    return "" if normalized in _NULL_TEXT else normalized


def _require_columns(frame: pd.DataFrame) -> None:
    missing = sorted(_REQUIRED_COLUMNS - set(frame.columns))
    if missing:
        raise PlaceboInputError(f"placebo pair frame is missing required columns: {missing}")


def _parse_prior_end_dates(values: pd.Series) -> pd.Series:
    present = values.map(_text).ne("")
    parsed = pd.to_datetime(values, errors="coerce", utc=True, format="mixed")
    parsed = parsed.dt.tz_localize(None).dt.normalize()
    if (present & parsed.isna()).any():
        raise PlaceboInputError(
            "prior_period_of_performance_end contains an unparsable nonblank value"
        )
    return parsed


def _date_multiset(values: pd.Series) -> Counter[int | None]:
    return Counter(None if pd.isna(value) else int(pd.Timestamp(value).value) for value in values)


def _unique_prior_awards(pairs: pd.DataFrame) -> pd.DataFrame:
    award_keys = pairs["prior_award_id"].map(_text)
    firm_keys = pairs["prior_recipient_uei"].map(_text)
    if award_keys.eq("").any():
        raise PlaceboInputError("Every placebo pair row must have a prior_award_id")
    if firm_keys.eq("").any():
        raise PlaceboInputError("Every placebo pair row must have a prior_recipient_uei")

    awards = pd.DataFrame(
        {
            "recipient_award_id": award_keys,
            "recipient_firm_uei": firm_keys,
            "original_prior_end": _parse_prior_end_dates(pairs["prior_period_of_performance_end"]),
        },
        index=pairs.index,
    )
    firm_variants = awards.groupby("recipient_award_id", sort=False)["recipient_firm_uei"].nunique(
        dropna=False
    )
    if firm_variants.gt(1).any():
        raise PlaceboInputError("Each prior_award_id must map to exactly one firm")
    date_variants = awards.groupby("recipient_award_id", sort=False)["original_prior_end"].nunique(
        dropna=False
    )
    if date_variants.gt(1).any():
        raise PlaceboInputError(
            "Each prior_award_id must map to exactly one prior_period_of_performance_end"
        )
    return (
        awards.drop_duplicates("recipient_award_id", keep="first")
        .sort_values(["recipient_firm_uei", "recipient_award_id"], kind="stable")
        .reset_index(drop=True)
    )


def _null_safe_changed(original: pd.Series, permuted: pd.Series) -> pd.Series:
    both_null = original.isna() & permuted.isna()
    one_null = original.isna() ^ permuted.isna()
    return (one_null | (~both_null & original.ne(permuted))).astype(bool)


def _date_json(value: Any) -> str | None:
    return None if pd.isna(value) else pd.Timestamp(value).date().isoformat()


def _mapping_digest(audit: pd.DataFrame) -> str:
    records = [
        {
            "recipient_award_id": row.recipient_award_id,
            "recipient_firm_uei": row.recipient_firm_uei,
            "donor_award_id": row.donor_award_id,
            "donor_firm_uei": row.donor_firm_uei,
            "original_prior_end": _date_json(row.original_prior_end),
            "permuted_prior_end": _date_json(row.permuted_prior_end),
            "date_value_changed": bool(row.date_value_changed),
            "seed": int(str(row.seed)),
        }
        for row in audit.sort_values("recipient_award_id", kind="stable").itertuples(index=False)
    ]
    serialized = json.dumps(records, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(serialized).hexdigest()


def _cross_firm_assignment(unique_awards: pd.DataFrame) -> pd.DataFrame:
    """Build the frozen randomized cyclic assignment (not a uniform derangement)."""

    firm_counts = unique_awards["recipient_firm_uei"].value_counts()
    award_count = len(unique_awards)
    if firm_counts.empty:
        raise PlaceboInputError("The placebo requires at least two firms")
    largest_firm_count = int(firm_counts.max())
    if len(firm_counts) < 2 or largest_firm_count * 2 > award_count:
        raise PlaceboInputError(
            "A cross-firm placebo permutation is impossible because one firm owns more than "
            "half of the unique prior awards (or fewer than two firms are present)"
        )

    rng = np.random.default_rng(PLACEBO_SEED)
    firms = np.array(sorted(firm_counts.index), dtype=object)
    ordered_firms = firms[rng.permutation(len(firms))]
    ordered_groups: list[pd.DataFrame] = []
    for firm in ordered_firms:
        group = unique_awards.loc[unique_awards["recipient_firm_uei"].eq(firm)].sort_values(
            "recipient_award_id", kind="stable"
        )
        ordered_groups.append(group.iloc[rng.permutation(len(group))])

    receivers = pd.concat(ordered_groups, ignore_index=True)
    donor_positions = np.roll(np.arange(award_count), -largest_firm_count)
    donors = receivers.iloc[donor_positions].reset_index(drop=True)
    audit = receivers.reset_index(drop=True).copy()
    audit["donor_award_id"] = donors["recipient_award_id"]
    audit["donor_firm_uei"] = donors["recipient_firm_uei"]
    audit["permuted_prior_end"] = donors["original_prior_end"]
    if audit["donor_firm_uei"].eq(audit["recipient_firm_uei"]).any():
        raise PlaceboInputError("Cross-firm placebo construction produced a within-firm donor")
    audit["date_value_changed"] = _null_safe_changed(
        audit["original_prior_end"], audit["permuted_prior_end"]
    )
    audit["seed"] = PLACEBO_SEED
    audit = audit[
        [column for column in ASSIGNMENT_AUDIT_COLUMNS if column != "mapping_sha256"]
    ].sort_values("recipient_award_id", kind="stable", ignore_index=True)
    mapping_sha256 = _mapping_digest(audit)
    audit["mapping_sha256"] = mapping_sha256
    return audit[list(ASSIGNMENT_AUDIT_COLUMNS)]


def build_placebo_assignment(pairs: pd.DataFrame) -> PlaceboAssignment:
    """Assign each unique award a fixed-seed date donor from another firm."""

    _require_columns(pairs)
    unique_awards = _unique_prior_awards(pairs)
    audit = _cross_firm_assignment(unique_awards)
    date_by_award = audit.set_index("recipient_award_id")["permuted_prior_end"]
    award_keys = pairs["prior_award_id"].map(_text)
    output = pairs.copy()
    output["prior_period_of_performance_end"] = pd.to_datetime(
        award_keys.map(date_by_award), errors="coerce"
    )

    if len(output) != len(pairs) or not output.index.equals(pairs.index):
        raise PlaceboInputError("Placebo permutation changed pair row count or order")
    for column in pairs.columns:
        if column == "prior_period_of_performance_end":
            continue
        if not output[column].equals(pairs[column]):
            raise PlaceboInputError(
                f"Placebo permutation changed prohibited non-date column: {column}"
            )
    before_fanout = award_keys.value_counts(sort=False).sort_index()
    after_fanout = output["prior_award_id"].map(_text).value_counts(sort=False).sort_index()
    if not after_fanout.equals(before_fanout):
        raise PlaceboInputError("Placebo permutation changed award-to-pair fanout")

    output_awards = _unique_prior_awards(output)
    if _date_multiset(output_awards["original_prior_end"]) != _date_multiset(
        unique_awards["original_prior_end"]
    ):
        raise PlaceboInputError(
            "Placebo permutation did not preserve the null-inclusive unique-award date multiset"
        )
    mapping_sha256 = str(audit["mapping_sha256"].iloc[0])
    return PlaceboAssignment(
        audit=audit,
        permuted_pairs=output,
        mapping_sha256=mapping_sha256,
    )


def permute_prior_end_dates_across_firms(pairs: pd.DataFrame) -> pd.DataFrame:
    """Return the pair frame with the frozen cross-firm award-date assignment."""

    return build_placebo_assignment(pairs).permuted_pairs


def build_placebo_study_tables(
    pairs: pd.DataFrame,
    data_cut_date: date,
) -> PlaceboCensusTables:
    """Build the assignment and run its frame through one memory-safe census pass."""

    assignment = build_placebo_assignment(pairs)
    dropoff, sensitivity = build_census_tables(assignment.permuted_pairs, data_cut_date)
    return PlaceboCensusTables(
        assignment=assignment,
        dropoff=dropoff,
        sensitivity=sensitivity,
    )


def build_placebo_census_tables(
    pairs: pd.DataFrame,
    data_cut_date: date,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return both placebo tables from exactly one shared census-table call."""

    tables = build_placebo_study_tables(pairs, data_cut_date)
    return tables.dropoff, tables.sensitivity
