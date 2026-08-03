"""Fixed-seed, cross-firm placebo mechanics for the Phase III census."""

from collections import Counter
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from ..phase_iii_census.criteria import build_dropoff_ladder, build_sensitivity_grid


PLACEBO_SEED = 20260801
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
            "_prior_key": award_keys,
            "_firm_key": firm_keys,
            "_prior_end": _parse_prior_end_dates(pairs["prior_period_of_performance_end"]),
        },
        index=pairs.index,
    )
    firm_variants = awards.groupby("_prior_key", sort=False)["_firm_key"].nunique(dropna=False)
    if firm_variants.gt(1).any():
        raise PlaceboInputError("Each prior_award_id must map to exactly one firm")
    date_variants = awards.groupby("_prior_key", sort=False)["_prior_end"].nunique(dropna=False)
    if date_variants.gt(1).any():
        raise PlaceboInputError(
            "Each prior_award_id must map to exactly one prior_period_of_performance_end"
        )
    return (
        awards.drop_duplicates("_prior_key", keep="first")
        .sort_values(["_firm_key", "_prior_key"], kind="stable")
        .reset_index(drop=True)
    )


def _cross_firm_date_map(unique_awards: pd.DataFrame) -> dict[str, Any]:
    firm_counts = unique_awards["_firm_key"].value_counts()
    award_count = len(unique_awards)
    largest_firm_count = int(firm_counts.max())
    if len(firm_counts) < 2 or largest_firm_count * 2 > award_count:
        raise PlaceboInputError(
            "A cross-firm placebo permutation is impossible because one firm owns more than "
            "half of the unique prior awards (or only one firm is present)"
        )

    rng = np.random.default_rng(PLACEBO_SEED)
    firms = np.array(sorted(firm_counts.index), dtype=object)
    ordered_firms = firms[rng.permutation(len(firms))]
    ordered_groups: list[pd.DataFrame] = []
    for firm in ordered_firms:
        group = unique_awards.loc[unique_awards["_firm_key"].eq(firm)].sort_values(
            "_prior_key",
            kind="stable",
        )
        order = rng.permutation(len(group))
        ordered_groups.append(group.iloc[order])
    receivers = pd.concat(ordered_groups, ignore_index=True)
    donor_dates = (
        receivers["_prior_end"]
        .iloc[np.roll(np.arange(award_count), -largest_firm_count)]
        .reset_index(drop=True)
    )
    donor_firms = (
        receivers["_firm_key"]
        .iloc[np.roll(np.arange(award_count), -largest_firm_count)]
        .reset_index(drop=True)
    )
    if donor_firms.eq(receivers["_firm_key"].reset_index(drop=True)).any():
        raise PlaceboInputError("Cross-firm placebo construction produced a within-firm donor")
    return dict(zip(receivers["_prior_key"], donor_dates, strict=True))


def permute_prior_end_dates_across_firms(pairs: pd.DataFrame) -> pd.DataFrame:
    """Permute unique-award completion dates using donors from other firms only."""

    _require_columns(pairs)
    if pairs.empty:
        return pairs.copy()

    unique_awards = _unique_prior_awards(pairs)
    date_by_award = _cross_firm_date_map(unique_awards)
    award_keys = pairs["prior_award_id"].map(_text)
    output = pairs.copy()
    output["prior_period_of_performance_end"] = pd.to_datetime(award_keys.map(date_by_award))

    if len(output) != len(pairs) or not output.index.equals(pairs.index):
        raise PlaceboInputError("Placebo permutation changed pair row count or order")
    for column in pairs.columns:
        if column == "prior_period_of_performance_end":
            continue
        if not output[column].equals(pairs[column]):
            raise PlaceboInputError(
                f"Placebo permutation changed prohibited non-date column: {column}"
            )

    output_awards = _unique_prior_awards(output)
    if _date_multiset(output_awards["_prior_end"]) != _date_multiset(unique_awards["_prior_end"]):
        raise PlaceboInputError(
            "Placebo permutation did not preserve the unique-award date distribution"
        )
    return output


def build_placebo_census_tables(
    pairs: pd.DataFrame,
    data_cut_date: date,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run the one permuted pair frame through both unchanged census helpers."""

    placebo_pairs = permute_prior_end_dates_across_firms(pairs)
    return (
        build_dropoff_ladder(placebo_pairs, data_cut_date),
        build_sensitivity_grid(placebo_pairs, data_cut_date),
    )
