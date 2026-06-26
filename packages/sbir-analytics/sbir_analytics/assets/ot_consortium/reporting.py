"""OT consortium tiering and magnitude reporting helpers.

Aggregate-only external rows (for example consortium-level public totals with no
recipient firm) should not disappear just because they cannot be assigned a T1-T4
firm evidence tier.  The helpers in this module keep those rows as an explicit
"non_attributable_external" bucket in the final magnitude report.
"""

from pathlib import Path
from typing import Any

import pandas as pd

try:
    from dagster import MetadataValue, Output, asset
except Exception:  # pragma: no cover - import-safe unit-test shim
    def asset(*args: Any, **kwargs: Any):
        def _wrap(fn):
            return fn

        return _wrap

    class Output:  # type: ignore[no-redef]
        def __init__(self, value: Any, metadata: dict[str, Any] | None = None) -> None:
            self.value = value
            self.metadata = metadata or {}

    class MetadataValue:  # type: ignore[no-redef]
        @staticmethod
        def json(value: Any) -> Any:
            return value


_USD_COLUMNS = (
    "transition_amount_usd",
    "amount_usd",
    "obligation_usd",
    "federal_action_obligation",
    "total_value_usd",
    "usd",
)
_COUNT_COLUMNS = ("transition_count", "count", "row_count")
_FIRM_COLUMNS = (
    "company_id",
    "firm_id",
    "recipient_uei",
    "uei",
    "recipient_name",
    "company_name",
)
_NON_ATTRIBUTABLE_FLAGS = (
    "non_attributable",
    "is_non_attributable",
    "aggregate_only",
    "is_aggregate_only",
)


def _truthy(value: Any) -> bool:
    if value is None or pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {
            "1",
            "true",
            "t",
            "yes",
            "y",
            "aggregate_only",
            "non_attributable",
        }
    return bool(value)


def _first_present(columns: pd.Index, candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def _numeric_sum(frame: pd.DataFrame, columns: tuple[str, ...]) -> float:
    column = _first_present(frame.columns, columns)
    if column is None or frame.empty:
        return 0.0
    return float(pd.to_numeric(frame[column], errors="coerce").fillna(0).sum())


def non_attributable_external_mask(frame: pd.DataFrame) -> pd.Series:
    """Return rows representing external evidence that cannot be firm-tiered.

    Rows are treated as non-attributable when an explicit aggregate/non-attributable
    flag is set, or when an external-source row has no firm identifiers or names.
    """
    if frame.empty:
        return pd.Series([], index=frame.index, dtype=bool)

    mask = pd.Series(False, index=frame.index)
    for column in _NON_ATTRIBUTABLE_FLAGS:
        if column in frame.columns:
            mask = mask | frame[column].map(_truthy)

    if "attribution_status" in frame.columns:
        status = frame["attribution_status"].fillna("").astype(str).str.lower()
        mask = mask | status.isin({"aggregate_only", "non_attributable", "non-attributable"})

    source_col = _first_present(frame.columns, ("source", "evidence_source", "input_source"))
    if source_col is not None:
        source = frame[source_col].fillna("").astype(str).str.lower()
        external = source.str.contains("external|manual|consortium", regex=True)
        firm_cols = [col for col in _FIRM_COLUMNS if col in frame.columns]
        if firm_cols:
            has_firm = frame[firm_cols].fillna("").astype(str).apply(
                lambda row: any(value.strip() for value in row), axis=1
            )
            mask = mask | (external & ~has_firm)

    return mask


def non_attributable_external_totals(frame: pd.DataFrame) -> dict[str, float | int]:
    """Summarize external rows that cannot be assigned to a recipient firm."""
    subset = frame.loc[non_attributable_external_mask(frame)]
    count_value = _numeric_sum(subset, _COUNT_COLUMNS)
    return {
        "non_attributable_external_count": (
            int(count_value) if count_value else int(len(subset))
        ),
        "non_attributable_external_usd": _numeric_sum(subset, _USD_COLUMNS),
    }


def aggregate_assignment_frame(
    assignment_frame: pd.DataFrame,
    *,
    non_attributable_external_count: int = 0,
    non_attributable_external_usd: float = 0.0,
) -> pd.DataFrame:
    """Aggregate tiered OT transition evidence for the magnitude report.

    The returned rows distinguish verified T1 firm-attributed transitions,
    unresolved/unverifiable T2-T4 evidence, and non-attributable external evidence
    that cannot be tiered.
    """
    frame = assignment_frame.copy()
    if not frame.empty:
        embedded = non_attributable_external_totals(frame)
        non_attributable_external_count += int(embedded["non_attributable_external_count"])
        non_attributable_external_usd += float(embedded["non_attributable_external_usd"])
        frame = frame.loc[~non_attributable_external_mask(frame)].copy()

    tier_col = _first_present(frame.columns, ("tier", "assignment_tier", "evidence_tier"))
    usd_col = _first_present(frame.columns, _USD_COLUMNS)
    count_col = _first_present(frame.columns, _COUNT_COLUMNS)

    def summarize(label: str, tier_values: set[str], description: str) -> dict[str, Any]:
        if tier_col is None or frame.empty:
            subset = frame.iloc[0:0]
        else:
            normalized = (
                frame[tier_col]
                .fillna("")
                .astype(str)
                .str.upper()
                .str.replace(" ", "", regex=False)
            )
            subset = frame.loc[normalized.isin(tier_values)]
        if count_col:
            numeric_count = pd.to_numeric(subset[count_col], errors="coerce")
            count = int(numeric_count.sum()) if numeric_count.notna().any() else len(subset)
        else:
            count = len(subset)
        usd = (
            float(pd.to_numeric(subset[usd_col], errors="coerce").fillna(0).sum())
            if usd_col
            else 0.0
        )
        return {
            "assignment_bucket": label,
            "transition_count": count,
            "transition_usd": usd,
            "description": description,
        }

    rows = [
        summarize(
            "t1_verified_firm_attributed",
            {"T1", "1", "TIER1"},
            "T1 verified firm-attributed OT Phase III transitions",
        ),
        summarize(
            "t2_t4_unresolved_unverifiable",
            {"T2", "T3", "T4", "2", "3", "4", "TIER2", "TIER3", "TIER4"},
            "T2-T4 unresolved or unverifiable OT transition evidence",
        ),
        {
            "assignment_bucket": "non_attributable_external",
            "transition_count": int(non_attributable_external_count),
            "transition_usd": float(non_attributable_external_usd),
            "description": "Non-attributable external transition evidence that cannot be tiered",
        },
    ]
    return pd.DataFrame(rows)


@asset(
    name="ot_consortium_magnitude_report",
    group_name="reporting",
    compute_kind="pandas",
    description="Aggregate OT consortium tier assignments into reportable magnitude buckets.",
)
def ot_consortium_magnitude_report(
    context, ot_consortium_tier_assignments: pd.DataFrame
) -> Output[pd.DataFrame]:
    totals = non_attributable_external_totals(ot_consortium_tier_assignments)
    report = aggregate_assignment_frame(ot_consortium_tier_assignments)
    out_path = Path("data/processed/ot_consortium_magnitude_report.parquet")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report.to_parquet(out_path, index=False)
    metadata = {
        "path": str(out_path),
        "rows": len(report),
        "non_attributable_external": MetadataValue.json(totals),
    }
    context.log.info("Built OT consortium magnitude report", extra=metadata)
    return Output(report, metadata=metadata)
