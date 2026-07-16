"""Stable contract-award identity and transaction-grain helpers."""

from collections.abc import Sequence

import pandas as pd


UNIQUE_AWARD_KEY_COLUMNS: tuple[str, ...] = (
    "contract_award_unique_key",
    "generated_unique_award_id",
    "unique_award_key",
)
PIID_COLUMNS: tuple[str, ...] = ("piid", "PIID", "award_id")
AWARDING_AGENCY_COLUMNS: tuple[str, ...] = (
    "agencyID",
    "agency_id",
    "awarding_agency_code",
)
PARENT_IDV_COLUMNS: tuple[str, ...] = (
    "referencedIDVID",
    "referenced_idv_piid",
    "parent_contract_id",
    "parent_award_id",
)
DEFAULT_TRANSACTION_DATE_COLUMNS: tuple[str, ...] = (
    "action_date",
    "award_date",
    "signedDate",
    "effectiveDate",
)


class AwardIdentityError(ValueError):
    """Raised when a frame cannot produce an award-grade identity safely."""


def normalize_award_key_value(value: object) -> str:
    """Normalize source identifiers without turning nulls into string keys."""

    if value is None or value is pd.NA:
        return ""
    normalized = str(value).strip().upper()
    return "" if normalized in {"", "NAN", "NAT", "NONE", "<NA>"} else normalized


def _normalized_series(df: pd.DataFrame, column: str) -> pd.Series:
    return df[column].map(normalize_award_key_value)


def _coalesce_required_component(
    df: pd.DataFrame,
    candidates: Sequence[str],
    *,
    component: str,
) -> pd.Series:
    present = [column for column in candidates if column in df.columns]
    if not present:
        raise AwardIdentityError(
            f"contracts frame has no {component} column (need one of {tuple(candidates)})"
        )

    normalized = pd.DataFrame(
        {column: _normalized_series(df, column) for column in present},
        index=df.index,
    )
    conflicts = normalized.apply(
        lambda row: len({value for value in row if value}) > 1,
        axis=1,
    )
    if conflicts.any():
        rows = list(df.index[conflicts][:5])
        raise AwardIdentityError(f"conflicting {component} aliases at rows {rows}")

    values = normalized.replace("", pd.NA).bfill(axis=1).iloc[:, 0].fillna("")
    missing = values.eq("")
    if missing.any():
        rows = list(df.index[missing][:5])
        raise AwardIdentityError(f"missing {component} at rows {rows}")
    return values.astype(str)


def award_key_series(df: pd.DataFrame) -> pd.Series:
    """Return an award-grade key for every row, failing on partial identities.

    A complete precomputed USAspending award key is preferred. Otherwise the
    required compound is awarding agency + parent IDV + PIID. ``contract_id``
    is deliberately excluded because this repository commonly uses it for a
    bare PIID. Repeated keys are valid for transaction/modification rows.
    """

    if df.empty:
        return pd.Series(index=df.index, dtype="object", name="_award_key")

    for column in UNIQUE_AWARD_KEY_COLUMNS:
        if column not in df.columns:
            continue
        values = _normalized_series(df, column)
        nonempty = values.ne("")
        if nonempty.all():
            return values.rename("_award_key")
        if nonempty.any():
            rows = list(df.index[~nonempty][:5])
            raise AwardIdentityError(
                f"precomputed award key {column!r} is partial; missing at rows {rows}"
            )

    piid = _coalesce_required_component(df, PIID_COLUMNS, component="PIID")
    agency = _coalesce_required_component(
        df,
        AWARDING_AGENCY_COLUMNS,
        component="awarding agency",
    )
    parent_idv = _coalesce_required_component(
        df,
        PARENT_IDV_COLUMNS,
        component="parent IDV",
    )
    return agency.str.cat(parent_idv, sep="|").str.cat(piid, sep="|").rename("_award_key")


def collapse_transactions_to_award_grain(
    df: pd.DataFrame,
    *,
    award_keys: pd.Series | None = None,
    date_columns: Sequence[str] = DEFAULT_TRANSACTION_DATE_COLUMNS,
) -> pd.DataFrame:
    """Keep one representative transaction per award, preferring the latest.

    This is a row-selection policy, not a financial aggregation: amount fields
    remain values from the selected transaction. Callers must aggregate amounts
    separately when they need award totals.
    """

    if df.empty:
        result = df.copy()
        result["_award_key"] = pd.Series(index=result.index, dtype="object")
        return result

    keys = award_key_series(df) if award_keys is None else award_keys.reindex(df.index)
    normalized_keys = keys.map(normalize_award_key_value)
    missing = normalized_keys.eq("")
    if missing.any():
        rows = list(df.index[missing][:5])
        raise AwardIdentityError(f"missing award key before grain collapse at rows {rows}")

    result = df.copy().assign(_award_key=normalized_keys)
    date_column = next((column for column in date_columns if column in result.columns), None)
    if date_column is not None:
        result = result.assign(
            _award_sort_date=pd.to_datetime(result[date_column], errors="coerce", utc=True)
        ).sort_values("_award_sort_date", kind="mergesort", na_position="first")
        result = result.drop(columns="_award_sort_date")
    return result.drop_duplicates("_award_key", keep="last").reset_index(drop=True)


__all__ = [
    "AWARDING_AGENCY_COLUMNS",
    "AwardIdentityError",
    "PARENT_IDV_COLUMNS",
    "PIID_COLUMNS",
    "UNIQUE_AWARD_KEY_COLUMNS",
    "award_key_series",
    "collapse_transactions_to_award_grain",
    "normalize_award_key_value",
]
