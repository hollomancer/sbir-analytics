"""Build NIH RePORTER refresh requests from the SBIR.gov award frame.

Epistemic tier: pipelines. Exact ``project_num`` / ``core_project_num`` + FY
on known NIH/HHS awards. Windows become RePORTER criteria, not a local
award-date filter. Company name is never a join key.
"""

from __future__ import annotations

from pathlib import Path
from collections.abc import Mapping
from typing import Any

import pandas as pd

from sbir_etl.enrichers.nih_reporter.keys import (
    NIHSearchWindow,
    NIHWindowKind,
    canonicalize_nih_query_key,
    parse_refresh_window,
)
from sbir_etl.extractors.sbir_public_awards import load_sbir_awards_csv
from sbir_etl.utils.cloud_storage import find_latest_sbir_awards


EPISTEMIC_TIER = "pipelines"

NIH_REPORTER_AGENCIES = frozenset({"HHS", "NIH"})
NIH_IC_LABELS = frozenset(
    {
        "NCI",
        "NIAID",
        "NHLBI",
        "NIGMS",
        "NINDS",
        "NIMH",
        "NIDA",
        "NIA",
        "NICHD",
        "NIDDK",
        "NEI",
        "NHGRI",
        "NIEHS",
        "NIAMS",
        "NIDCR",
        "NIDCD",
        "NIAAA",
        "NIBIB",
        "NIMHD",
        "NCCIH",
        "NINR",
        "NLM",
        "FIC",
        "NCATS",
        "CIT",
        "OD",
        "NCRR",
        "NCCAM",
        "CSR",
        "CC",
    }
)
PROJECT_KEY_COLUMNS = ("contract_number", "agency_tracking_number")


def sbir_awards_path() -> Path | None:
    """Canonical SBIR.gov award CSV, or ``None`` when no vintage exists."""

    found = find_latest_sbir_awards()
    return Path(found) if found else None


def load_sbir_award_frame(path: Path | None = None) -> pd.DataFrame:
    """Load the SBIR.gov award frame used to build RePORTER lookups.

    Raises:
        FileNotFoundError: If the SBIR.gov CSV is missing. Callers must not
            treat a missing frame as an empty refresh.
    """

    src = path if path is not None else sbir_awards_path()
    if src is None or not Path(src).is_file():
        raise FileNotFoundError(
            "SBIR.gov award CSV is unavailable; NIH RePORTER refresh needs "
            "data/raw/sbir/award_data.csv (or a history/ vintage). "
            "Download the public awards file before running "
            "refresh-enrichment --source nih_reporter."
        )
    return load_sbir_awards_csv(Path(src))


def is_nih_reporter_agency(agency: Any, branch: Any = None) -> bool:
    """True when agency or branch is NIH, HHS, or a known NIH institute label."""

    for raw in (agency, branch):
        token = _token(raw)
        if not token:
            continue
        if token in NIH_REPORTER_AGENCIES or token in NIH_IC_LABELS or token.startswith("NIH"):
            return True
    return False


def four_digit_award_year(value: Any) -> int | None:
    """Return a four-digit award year, or ``None`` when the cell is unusable."""

    if value is None or value is pd.NA:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    try:
        year = int(value)
    except (TypeError, ValueError):
        text = str(value).strip()
        if len(text) >= 4 and text[:4].isdigit():
            year = int(text[:4])
        else:
            return None
    if 1900 <= year <= 2100:
        return year
    return None


def project_keys_for_row(row: pd.Series | Mapping[str, Any]) -> list[str]:
    """Canonical project keys from contract and agency tracking number."""

    keys: list[str] = []
    for column in PROJECT_KEY_COLUMNS:
        key = canonicalize_nih_query_key(_cell(row, column))
        if key and key not in keys:
            keys.append(key)
    return keys


def build_nih_reporter_requests(
    awards: pd.DataFrame,
    window: str | NIHSearchWindow | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Map an SBIR.gov frame to runner requests.

    Returns:
        ``(requests, skipped)`` where ``skipped`` is the number of NIH/HHS
        rows dropped for a missing project key or four-digit award year.
        A ``fy:`` window restricts ``award_year`` so we do not look up years
        the API would reject; a date window is attached as criteria only.
    """

    parsed = window if isinstance(window, NIHSearchWindow) else parse_refresh_window(window)
    skipped = 0
    requests: list[dict[str, Any]] = []
    if awards.empty:
        return requests, skipped

    for _, row in awards.iterrows():
        if not is_nih_reporter_agency(row.get("agency"), row.get("branch")):
            continue
        keys = project_keys_for_row(row)
        year = four_digit_award_year(row.get("award_year"))
        if not keys or year is None:
            skipped += 1
            continue
        if parsed.kind is NIHWindowKind.FISCAL_YEARS and year not in parsed.fiscal_years:
            continue
        award_id = row.get("award_id")
        if award_id is None or (isinstance(award_id, float) and pd.isna(award_id)):
            skipped += 1
            continue
        request: dict[str, Any] = {
            "award_id": str(award_id),
            "project_num": keys[0],
            "project_nums": keys,
            "award_year": year,
        }
        if parsed.kind is NIHWindowKind.PROJECT_START_DATE:
            request["window"] = f"{parsed.from_date}:{parsed.to_date}"
        requests.append(request)
    return requests, skipped


def _token(value: Any) -> str:
    if value is None or value is pd.NA:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip().upper()


def _cell(row: pd.Series | Mapping[str, Any], column: str) -> Any:
    if hasattr(row, "index") and column not in row.index:
        return None
    try:
        return row[column]
    except (KeyError, TypeError, IndexError):
        return row.get(column) if hasattr(row, "get") else None
