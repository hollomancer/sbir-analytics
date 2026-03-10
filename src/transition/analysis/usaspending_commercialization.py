"""Build a commercialization DataFrame from USAspending transaction data.

Aggregates federal obligation amounts per company from USAspending
contract/transaction Parquet files, producing the ``commercialization_df``
schema that :class:`BenchmarkEligibilityEvaluator` accepts.

USAspending obligation amounts are a proxy for the "sales and investment"
metric in the SBIR/STTR commercialization benchmark.  They capture the
federal side but do **not** include private capital or commercial revenue.

Typical usage::

    from src.transition.analysis.usaspending_commercialization import (
        build_commercialization_from_usaspending,
    )

    comm_df = build_commercialization_from_usaspending(
        transaction_path="data/usaspending/contracts.parquet",
        evaluation_fy=2026,
    )
    summary = evaluator.evaluate(awards_df, commercialization_df=comm_df)
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def build_commercialization_from_usaspending(
    transaction_path: str | Path,
    evaluation_fy: int = 2026,
    *,
    lookback_years: int = 10,
    exclude_recent_years: int = 2,
) -> pd.DataFrame:
    """Aggregate USAspending transactions into per-company commercialization data.

    Parameters
    ----------
    transaction_path :
        Path to a Parquet file produced by :class:`ContractExtractor`.
        Expected columns: ``vendor_uei``, ``vendor_duns``, ``vendor_name``,
        ``obligation_amount``, ``start_date``.
    evaluation_fy :
        The fiscal year being evaluated (e.g. 2026).
    lookback_years :
        Number of years in the commercialization window (default 10).
    exclude_recent_years :
        Number of most-recent FYs to exclude (default 2).

    Returns
    -------
    pd.DataFrame
        Columns: ``company_id``, ``total_sales_and_investment``, ``patent_count``.
        ``company_id`` values use the ``uei:``, ``duns:``, or ``name:`` prefix
        scheme expected by :func:`BenchmarkEligibilityEvaluator`.
    """
    transaction_path = Path(transaction_path)
    df = pd.read_parquet(transaction_path)

    # --- Resolve fiscal year from start_date ---------------------------------
    if "start_date" in df.columns:
        df["start_date"] = pd.to_datetime(df["start_date"], errors="coerce")
        # Federal fiscal year: Oct (month 10) of year Y → FY Y+1
        df["_fy"] = df["start_date"].dt.year + (df["start_date"].dt.month >= 10).astype(int)
    elif "action_date" in df.columns:
        df["action_date"] = pd.to_datetime(df["action_date"], errors="coerce")
        df["_fy"] = df["action_date"].dt.year + (df["action_date"].dt.month >= 10).astype(int)
    else:
        raise ValueError(
            "Transaction data must contain 'start_date' or 'action_date' column"
        )

    # --- Filter to commercialization window ----------------------------------
    end_fy = evaluation_fy - exclude_recent_years
    start_fy = end_fy - lookback_years + 1
    df = df[(df["_fy"] >= start_fy) & (df["_fy"] <= end_fy)]

    if df.empty:
        return pd.DataFrame(
            columns=["company_id", "total_sales_and_investment", "patent_count"]
        )

    # --- Build canonical company_id (matches evaluator logic) ----------------
    df["_company_id"] = _resolve_company_id(df)

    # Drop rows with no company ID
    df = df[df["_company_id"] != ""]

    # --- Aggregate obligations per company -----------------------------------
    amount_col = _first_present(df, ["obligation_amount", "federal_action_obligation"])
    if amount_col is None:
        raise ValueError(
            "Transaction data must contain 'obligation_amount' or "
            "'federal_action_obligation' column"
        )

    df[amount_col] = pd.to_numeric(df[amount_col], errors="coerce").fillna(0.0)

    agg = df.groupby("_company_id", as_index=False).agg(
        total_sales_and_investment=(amount_col, "sum"),
    )
    agg = agg.rename(columns={"_company_id": "company_id"})

    # Patent data is not available from USAspending; set to 0
    agg["patent_count"] = 0

    return agg


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_company_id(df: pd.DataFrame) -> pd.Series:
    """Mirror the evaluator's company ID resolution: UEI > DUNS > name."""
    result = pd.Series("", index=df.index, dtype="object")

    uei_col = _first_present(df, ["vendor_uei", "uei", "UEI", "recipient_uei"])
    duns_col = _first_present(df, ["vendor_duns", "duns", "Duns", "recipient_duns"])
    name_col = _first_present(df, ["vendor_name", "recipient_name", "Company", "company_name"])

    if uei_col is not None:
        uei = df[uei_col].astype(str).str.strip()
        valid = (uei != "") & (~uei.isin(["None", "nan", "NaN"]))
        result = result.mask(valid, "uei:" + uei)
    if duns_col is not None:
        duns = df[duns_col].astype(str).str.strip()
        valid = (duns != "") & (~duns.isin(["None", "nan", "NaN"]))
        result = result.mask((result == "") & valid, "duns:" + duns)
    if name_col is not None:
        names = df[name_col].astype(str).str.strip().str.lower()
        valid = (names != "") & (~names.isin(["none", "nan"]))
        result = result.mask((result == "") & valid, "name:" + names)

    return result


def _first_present(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """Return the first column name from *candidates* that exists in *df*."""
    for col in candidates:
        if col in df.columns:
            return col
    return None
