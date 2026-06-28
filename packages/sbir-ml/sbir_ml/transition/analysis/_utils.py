"""Shared utilities for transition analysis modules."""

from __future__ import annotations

import pandas as pd


def _first_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """Return the first column name from candidates that exists in df."""
    for c in candidates:
        if c in df.columns:
            return c
    lower_map = {c.lower(): c for c in df.columns}
    for c in candidates:
        if c.lower() in lower_map:
            return lower_map[c.lower()]
    return None


def _company_id_series(df: pd.DataFrame) -> pd.Series:
    """Build a canonical company ID with priority: UEI > DUNS > name.

    Prefixes each value ("uei:", "duns:", "name:", "row:") to avoid collisions
    between identifier systems. Falls back to row index when no valid identifier
    is found.
    """
    uei_col = _first_col(df, ["UEI", "uei", "company_uei"])
    duns_col = _first_col(df, ["Duns", "duns", "company_duns"])
    name_col = _first_col(
        df, ["Company", "company", "company_name", "vendor_name", "Vendor", "Name"]
    )

    result = pd.Series([""] * len(df), index=df.index, dtype="object")

    _invalid = {"None", "nan", "NaN", "none"}

    if uei_col:
        uei = df[uei_col].fillna("").astype(str).str.strip()
        valid = (uei != "") & (~uei.isin(_invalid))
        result = result.mask(valid, "uei:" + uei)
    if duns_col:
        duns = df[duns_col].fillna("").astype(str).str.strip()
        valid = (duns != "") & (~duns.isin(_invalid))
        result = result.mask((~result.astype(bool)) & valid, "duns:" + duns)
    if name_col:
        names = df[name_col].fillna("").astype(str).str.strip().str.lower()
        valid = (names != "") & (~names.isin(_invalid))
        result = result.mask((~result.astype(bool)) & valid, "name:" + names)

    result = result.where(result.astype(bool), "row:" + df.index.astype(str))
    return result
