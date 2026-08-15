"""Build USAspending refresh requests from a stale-award frame.

Epistemic tier: pipelines. One canonical mapping from enriched-award columns to
runner request dicts, shared by the Dagster asset and the operator CLI so both
paths supply the identifiers ``enrich_award`` looks up (UEI / DUNS / CAGE / PIID).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from sbir_etl.exceptions import ValidationError


EPISTEMIC_TIER = "pipelines"

AWARD_ID_COLUMNS = ["award_id", "Award_ID", "id", "ID"]
UEI_COLUMNS = ["UEI", "uei", "company_uei", "recipient_uei"]
DUNS_COLUMNS = ["Duns", "duns", "company_duns", "recipient_duns"]
CAGE_COLUMNS = ["CAGE", "cage", "company_cage", "recipient_cage"]
PIID_COLUMNS = ["Contract", "contract", "contract_number", "piid"]
AWARD_DATE_COLUMNS = ["award_date", "Award_Date", "Award Date", "proposal_award_date", "Award Year"]

IDENTIFIER_FIELDS = ("uei", "duns", "cage", "piid")


def first_present_column(frame: pd.DataFrame, candidates: list[str]) -> str | None:
    """Return the first candidate column present on ``frame``."""

    for col in candidates:
        if col in frame.columns:
            return col
    return None


def enriched_awards_path() -> Path:
    """Canonical location of the enriched award parquet."""

    from sbir_etl.utils.cloud_storage import get_data_root

    return get_data_root() / "processed" / "enriched" / "sbir_awards.parquet"


def load_enriched_awards(path: Path | None = None) -> pd.DataFrame | None:
    """Load the enriched award parquet, or ``None`` when it is unavailable."""

    src = path or enriched_awards_path()
    if not src.is_file():
        return None
    try:
        return pd.read_parquet(src)
    except Exception:
        return None


def _identifier(row: pd.Series, column: str | None) -> str | None:
    """Read one identifier cell, mapping missing values to ``None``.

    ``pd.notna`` matters here: a NaN cell stringifies to ``"nan"``, which is
    truthy and would be sent to the API as a real identifier.
    """

    if not column:
        return None
    value = row.get(column)
    if not pd.notna(value):
        return None
    text = str(value).strip()
    return text or None


def stale_awards_to_requests(stale_awards: pd.DataFrame) -> list[dict[str, Any]]:
    """Map a stale-award frame to runner request dicts."""

    if stale_awards.empty:
        return []
    award_id_col = first_present_column(stale_awards, AWARD_ID_COLUMNS)
    if not award_id_col:
        raise ValidationError(
            "Could not find award ID column",
            component="enrichers.usaspending.requests",
            operation="stale_awards_to_requests",
            details={
                "expected_columns": AWARD_ID_COLUMNS,
                "available_columns": list(stale_awards.columns),
            },
        )
    uei_col = first_present_column(stale_awards, UEI_COLUMNS)
    duns_col = first_present_column(stale_awards, DUNS_COLUMNS)
    cage_col = first_present_column(stale_awards, CAGE_COLUMNS)
    contract_col = first_present_column(stale_awards, PIID_COLUMNS)
    requests: list[dict[str, Any]] = []
    for _, row in stale_awards.iterrows():
        requests.append(
            {
                "award_id": str(row[award_id_col]),
                "uei": _identifier(row, uei_col),
                "duns": _identifier(row, duns_col),
                "cage": _identifier(row, cage_col),
                "piid": _identifier(row, contract_col),
            }
        )
    return requests


def has_identifier(request: dict[str, Any]) -> bool:
    """True when a request carries at least one identifier ``enrich_award`` can use."""

    return any(request.get(field) for field in IDENTIFIER_FIELDS)


def filter_by_window(frame: pd.DataFrame, window: str) -> pd.DataFrame:
    """Restrict ``frame`` to rows whose award date falls inside ``start:end``.

    Raises ``ValidationError`` when the frame carries no recognizable award-date
    column, rather than silently widening the refresh to the full stale set.
    """

    start_text, _, end_text = window.partition(":")
    if not start_text or not end_text:
        raise ValidationError(
            "window must be formatted as START:END (ISO dates)",
            component="enrichers.usaspending.requests",
            operation="filter_by_window",
            details={"window": window},
        )
    date_col = first_present_column(frame, AWARD_DATE_COLUMNS)
    if not date_col:
        raise ValidationError(
            "no award-date column available to apply --window",
            component="enrichers.usaspending.requests",
            operation="filter_by_window",
            details={
                "expected_columns": AWARD_DATE_COLUMNS,
                "available_columns": list(frame.columns),
            },
        )
    dates = pd.to_datetime(frame[date_col], errors="coerce", format="mixed")
    start = pd.to_datetime(start_text)
    end = pd.to_datetime(end_text)
    return frame.loc[dates.between(start, end)].copy()
