"""DuckDB aggregation: the OT-consortium magnitude report.

Turns a list of :class:`TierAssignment` into a :class:`MagnitudeReport` —
counts and obligated dollars per tier, overall and broken down by CMF, agency,
and fiscal year. The unverifiable share (T2+T3+T4) is computed as a first-class
headline and is never folded into the verified (T1) total.
"""

from __future__ import annotations

from typing import Any

import duckdb
import pandas as pd

from .models import (
    UNVERIFIABLE_TIERS,
    CoveredSalesClaim,
    MagnitudeReport,
    TierAssignment,
    TierBucket,
    VerificationTier,
)


def assignments_to_frame(assignments: list[TierAssignment]) -> pd.DataFrame:
    """Flatten assignments into a DataFrame for SQL aggregation."""
    rows = [
        {
            "award_id": a.award_id,
            "tier": str(a.tier),
            "cmf_name": a.cmf_name,
            "agency": a.agency,
            "fiscal_year": a.fiscal_year,
            "obligation_amount": float(a.obligation_amount or 0.0),
            "is_verifiable": a.is_verifiable,
        }
        for a in assignments
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "award_id",
            "tier",
            "cmf_name",
            "agency",
            "fiscal_year",
            "obligation_amount",
            "is_verifiable",
        ],
    )


def _coerce_for_duckdb(df: pd.DataFrame) -> pd.DataFrame:
    """Project to the aggregated columns and give them explicit nullable dtypes.

    Projecting first means callers may pass the full per-record assignment frame
    (with extra all-null columns that would otherwise break DuckDB type
    inference) — only the columns the report needs are registered.
    """
    out = pd.DataFrame(index=df.index)
    for col in ("award_id", "tier", "cmf_name", "agency"):
        out[col] = (
            df[col].astype("string")
            if col in df.columns
            else pd.Series(pd.NA, index=df.index, dtype="string")
        )
    out["fiscal_year"] = (
        pd.to_numeric(df["fiscal_year"], errors="coerce").astype("Int64")
        if "fiscal_year" in df.columns
        else pd.Series(pd.NA, index=df.index, dtype="Int64")
    )
    out["obligation_amount"] = (
        pd.to_numeric(df["obligation_amount"], errors="coerce").fillna(0.0)
        if "obligation_amount" in df.columns
        else 0.0
    )
    return out


def _breakdown(con: duckdb.DuckDBPyConnection, dimension: str) -> dict[str, Any]:
    """Count + obligated $ per tier for one grouping dimension."""
    query = f"""
        SELECT COALESCE(CAST({dimension} AS VARCHAR), 'unknown') AS key,
               tier,
               COUNT(*) AS n,
               SUM(obligation_amount) AS dollars
        FROM assignments
        GROUP BY key, tier
        ORDER BY key, tier
    """  # nosec B608 - dimension is a fixed internal column name, not user input
    result: dict[str, Any] = {}
    for key, tier, n, dollars in con.execute(query).fetchall():
        result.setdefault(key, {})[tier] = {"count": int(n), "obligated_usd": float(dollars or 0.0)}
    return result


def build_magnitude_report(
    assignments: list[TierAssignment],
    *,
    mode: str,
    non_attributable: list[CoveredSalesClaim] | None = None,
) -> MagnitudeReport:
    """Build the magnitude report from tier assignments.

    Args:
        assignments: Per-award tier assignments to aggregate.
        mode: ``"baseline"`` or ``"audit"``.
        non_attributable: Audit-mode aggregated claims that could not be tied to a
            specific award; counted in a separate bucket, never tiered.

    Returns:
        A populated :class:`MagnitudeReport`.
    """
    na_count = len(non_attributable) if non_attributable else 0
    na_usd = (
        float(sum(c.claimed_obligation_usd or 0.0 for c in non_attributable))
        if non_attributable
        else 0.0
    )
    return aggregate_assignment_frame(
        assignments_to_frame(assignments),
        mode=mode,
        non_attributable_count=na_count,
        non_attributable_usd=na_usd,
    )


def aggregate_assignment_frame(
    df: pd.DataFrame,
    *,
    mode: str,
    non_attributable_count: int = 0,
    non_attributable_usd: float = 0.0,
) -> MagnitudeReport:
    """Aggregate a prepared assignment DataFrame into a :class:`MagnitudeReport`.

    The DataFrame must carry the columns produced by :func:`assignments_to_frame`
    (``tier``, ``cmf_name``, ``agency``, ``fiscal_year``, ``obligation_amount``).
    This is the shared core used by both the in-memory and parquet-backed paths.
    """
    report = MagnitudeReport(mode=mode)

    if df is not None and not df.empty:
        df = _coerce_for_duckdb(df)
        con = duckdb.connect(":memory:")
        con.register("assignments", df)

        per_tier = con.execute("""
            SELECT tier, COUNT(*) AS n, SUM(obligation_amount) AS dollars
            FROM assignments GROUP BY tier ORDER BY tier
            """).fetchall()
        buckets = {
            tier: TierBucket(
                tier=VerificationTier(tier), count=int(n), obligated_usd=float(dollars or 0.0)
            )
            for tier, n, dollars in per_tier
        }
        # Ensure every tier appears, even with zero, for a stable report shape.
        report.by_tier = [
            buckets.get(str(t), TierBucket(tier=t, count=0, obligated_usd=0.0))
            for t in VerificationTier
        ]

        report.total_count = int(df.shape[0])
        report.total_obligated_usd = float(df["obligation_amount"].sum())

        unverifiable_keys = {str(t) for t in UNVERIFIABLE_TIERS}
        for bucket in report.by_tier:
            if str(bucket.tier) in unverifiable_keys:
                report.unverifiable_count += bucket.count
                report.unverifiable_obligated_usd += bucket.obligated_usd
            else:
                report.verified_count += bucket.count
                report.verified_obligated_usd += bucket.obligated_usd

        report.breakdowns = {
            "by_cmf": _breakdown(con, "cmf_name"),
            "by_agency": _breakdown(con, "agency"),
            "by_fiscal_year": _breakdown(con, "fiscal_year"),
        }
        con.close()

    report.non_attributable_count = non_attributable_count
    report.non_attributable_obligated_usd = non_attributable_usd
    return report
