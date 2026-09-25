"""NIH RePORTER query-key and refresh-window helpers.

Epistemic tier: pipelines. Canonicalization is exact-key formatting, not
company-name identity. Window strings become RePORTER criteria; they are
never applied as a post-fetch filter.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any

import pandas as pd


EPISTEMIC_TIER = "pipelines"

_NULL_TEXT = frozenset({"<NA>", "NAN", "NONE", "NULL", r"\N"})
_FY_WINDOW_PREFIX = "fy:"


class NIHWindowKind(StrEnum):
    """How a refresh window maps onto RePORTER search criteria."""

    ALL = "all"
    PROJECT_START_DATE = "project_start_date"
    FISCAL_YEARS = "fiscal_years"


@dataclass(frozen=True)
class NIHSearchWindow:
    """Parsed ``--window`` value ready to attach to a RePORTER criteria object."""

    kind: NIHWindowKind
    from_date: str | None = None
    to_date: str | None = None
    fiscal_years: tuple[int, ...] = ()

    def apply_to_criteria(self, criteria: dict[str, Any]) -> None:
        """Mutate ``criteria`` with this window. ``ALL`` adds nothing."""

        if self.kind is NIHWindowKind.ALL:
            return
        if self.kind is NIHWindowKind.PROJECT_START_DATE:
            criteria["project_start_date"] = {
                "from_date": self.from_date,
                "to_date": self.to_date,
            }
            return
        criteria["fiscal_years"] = list(self.fiscal_years)


def canonicalize_nih_query_key(value: Any) -> str | None:
    """Format an SBIR source key for an exact NIH project-number query.

    Behavior is the Phase III identity-recovery contract: strip surrounding
    spaces and commas, uppercase, drop interior whitespace, and reject null
    tokens. Structural punctuation such as ``-`` is preserved.
    """

    if value is None or value is pd.NA:
        return None
    text = str(value).strip(" ,").upper()
    if not text or text in _NULL_TEXT:
        return None
    return "".join(text.split()) or None


def parse_refresh_window(window: str | None) -> NIHSearchWindow:
    """Parse a CLI window into RePORTER criteria.

    Accepted forms:

    - ``None`` / blank — full activity-code snapshot, no date or FY filter
    - ``YYYY-MM-DD:YYYY-MM-DD`` — inclusive ``project_start_date`` range
    - ``fy:YYYY-YYYY`` — inclusive fiscal-year range

    Raises:
        ValueError: If the window is malformed or inverted.
    """

    if window is None:
        return NIHSearchWindow(kind=NIHWindowKind.ALL)
    text = window.strip()
    if not text:
        return NIHSearchWindow(kind=NIHWindowKind.ALL)

    lowered = text.lower()
    if lowered.startswith(_FY_WINDOW_PREFIX):
        return _parse_fiscal_year_window(text[len(_FY_WINDOW_PREFIX) :])
    return _parse_project_start_window(text)


def _parse_fiscal_year_window(spec: str) -> NIHSearchWindow:
    parts = spec.split("-")
    if len(parts) != 2 or not all(part.isdigit() and len(part) == 4 for part in parts):
        raise ValueError(f"invalid NIH fiscal-year window {spec!r}; expected fy:YYYY-YYYY")
    start_year = int(parts[0])
    end_year = int(parts[1])
    if end_year < start_year:
        raise ValueError(f"inverted NIH fiscal-year window fy:{start_year}-{end_year}")
    years = tuple(range(start_year, end_year + 1))
    return NIHSearchWindow(kind=NIHWindowKind.FISCAL_YEARS, fiscal_years=years)


def _parse_project_start_window(spec: str) -> NIHSearchWindow:
    parts = spec.split(":")
    if len(parts) != 2:
        raise ValueError(f"invalid NIH date window {spec!r}; expected YYYY-MM-DD:YYYY-MM-DD")
    try:
        start = date.fromisoformat(parts[0])
        end = date.fromisoformat(parts[1])
    except ValueError as error:
        raise ValueError(
            f"invalid NIH date window {spec!r}; expected YYYY-MM-DD:YYYY-MM-DD"
        ) from error
    if end < start:
        raise ValueError(f"inverted NIH date window {spec}")
    return NIHSearchWindow(
        kind=NIHWindowKind.PROJECT_START_DATE,
        from_date=start.isoformat(),
        to_date=end.isoformat(),
    )
