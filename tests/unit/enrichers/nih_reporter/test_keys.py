"""Tests for NIH RePORTER key canonicalization and window parsing."""

from __future__ import annotations

import pandas as pd
import pytest

from sbir_etl.enrichers.nih_reporter.keys import (
    NIHWindowKind,
    canonicalize_nih_query_key,
    parse_refresh_window,
)


pytestmark = pytest.mark.fast


def test_canonicalize_preserves_structural_punctuation() -> None:
    assert canonicalize_nih_query_key(" 5 F32 DK132864-03, ") == "5F32DK132864-03"


def test_canonicalize_rejects_null_tokens() -> None:
    assert canonicalize_nih_query_key(None) is None
    assert canonicalize_nih_query_key(pd.NA) is None
    assert canonicalize_nih_query_key("nan") is None
    assert canonicalize_nih_query_key("  ") is None


def test_blank_window_is_full_snapshot() -> None:
    parsed = parse_refresh_window(None)
    assert parsed.kind is NIHWindowKind.ALL
    criteria: dict[str, object] = {"activity_codes": ["R43"]}
    parsed.apply_to_criteria(criteria)
    assert criteria == {"activity_codes": ["R43"]}


def test_iso_date_window_becomes_project_start_date() -> None:
    parsed = parse_refresh_window("2020-01-01:2024-12-31")
    assert parsed.kind is NIHWindowKind.PROJECT_START_DATE
    criteria: dict[str, object] = {}
    parsed.apply_to_criteria(criteria)
    assert criteria == {"project_start_date": {"from_date": "2020-01-01", "to_date": "2024-12-31"}}


def test_fiscal_year_window_is_inclusive() -> None:
    parsed = parse_refresh_window("fy:2022-2024")
    assert parsed.fiscal_years == (2022, 2023, 2024)
    criteria: dict[str, object] = {}
    parsed.apply_to_criteria(criteria)
    assert criteria == {"fiscal_years": [2022, 2023, 2024]}


@pytest.mark.parametrize(
    "window",
    [
        "2020-01-01",
        "fy:2024",
        "fy:2024-20",
        "not-a-window",
        "2024-12-31:2020-01-01",
        "fy:2024-2022",
    ],
)
def test_malformed_or_inverted_windows_fail_closed(window: str) -> None:
    with pytest.raises(ValueError):
        parse_refresh_window(window)
