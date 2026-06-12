"""Unit tests for the agency cohort builder (ALN / agency filter + vintage)."""

from __future__ import annotations

import pandas as pd
import pytest

from sbir_analytics.assets.agency_private_capital.cohort import (
    AGENCY_ALN_MAP,
    NSF_ALNS,
    AgencyCohortBuilder,
    NSFCohortBuilder,
    _is_agency_row,
    vintage_bucket,
)


pytestmark = pytest.mark.fast


def test_nsf_alns_match_identification_module() -> None:
    assert NSF_ALNS == frozenset({"47.041", "47.084"})


def test_agency_aln_map_contains_nsf() -> None:
    assert "NSF" in AGENCY_ALN_MAP
    assert AGENCY_ALN_MAP["NSF"] == frozenset({"47.041", "47.084"})


def test_vintage_bucket_5yr_default() -> None:
    assert vintage_bucket(2015) == "2015-2019"
    assert vintage_bucket(2019) == "2015-2019"
    assert vintage_bucket(2020) == "2020-2024"
    assert vintage_bucket(2003) == "2000-2004"


# ---------------------------------------------------------------------------
# _is_agency_row — NSF variants (fixes the old exact-match bug)
# ---------------------------------------------------------------------------


def test_is_agency_row_accepts_nsf_abbreviation() -> None:
    row = pd.Series({"agency": "NSF", "award_year": 2017})
    assert _is_agency_row(row, agency_code="NSF") is True


def test_is_agency_row_accepts_nsf_full_name() -> None:
    row = pd.Series({"agency": "National Science Foundation", "award_year": 2017})
    assert _is_agency_row(row, agency_code="NSF") is True


def test_is_agency_row_accepts_nsf_parenthetical() -> None:
    row = pd.Series({"agency": "National Science Foundation (NSF)", "award_year": 2017})
    assert _is_agency_row(row, agency_code="NSF") is True


def test_is_agency_row_rejects_non_nsf_agency() -> None:
    row = pd.Series({"agency": "Department of Defense", "award_year": 2017})
    assert _is_agency_row(row, agency_code="NSF") is False


# ---------------------------------------------------------------------------
# _is_agency_row — NIH (locks in the abstraction for non-NSF agencies)
# ---------------------------------------------------------------------------


def test_is_agency_row_accepts_nih_full_name() -> None:
    """A row with agency 'National Institutes of Health (NIH)' matches agency_code='NIH'."""
    row = pd.Series({"agency": "National Institutes of Health (NIH)", "award_year": 2018})
    assert _is_agency_row(row, agency_code="NIH") is True


def test_is_agency_row_rejects_nih_for_nsf_code() -> None:
    row = pd.Series({"agency": "National Institutes of Health (NIH)", "award_year": 2018})
    assert _is_agency_row(row, agency_code="NSF") is False


# ---------------------------------------------------------------------------
# AgencyCohortBuilder
# ---------------------------------------------------------------------------


def test_filter_keeps_only_nsf_rows_by_agency_name() -> None:
    df = pd.DataFrame(
        [
            {
                "agency": "National Science Foundation",
                "phase": "Phase I",
                "award_year": 2017,
                "uei": "AAA",
            },
            {"agency": "NSF", "phase": "Phase II", "award_year": 2018, "uei": "BBB"},
            {
                "agency": "Department of Defense",
                "phase": "Phase I",
                "award_year": 2017,
                "uei": "CCC",
            },
            {
                "agency": "Department of Health and Human Services",
                "phase": "Phase II",
                "award_year": 2018,
                "uei": "DDD",
            },
        ]
    )
    cohort = AgencyCohortBuilder(agency_code="NSF").build(df)
    assert sorted(cohort["uei"].tolist()) == ["AAA", "BBB"]
    assert set(cohort["phase_label"].tolist()) == {"I", "II"}
    assert set(cohort["vintage_bucket"].tolist()) == {"2015-2019"}


def test_filter_keeps_rows_by_explicit_aln() -> None:
    df = pd.DataFrame(
        [
            {
                "agency": "Other Agency",
                "cfda_number": "47.041",
                "phase": "Phase I",
                "award_year": 2016,
                "uei": "AAA",
            },
            {
                "agency": "Other Agency",
                "cfda_number": "47.084",
                "phase": "Phase II",
                "award_year": 2016,
                "uei": "BBB",
            },
            {
                "agency": "Other Agency",
                "cfda_number": "12.910",
                "phase": "Phase I",
                "award_year": 2016,
                "uei": "CCC",
            },
        ]
    )
    cohort = AgencyCohortBuilder(agency_code="NSF").build(df)
    assert sorted(cohort["uei"].tolist()) == ["AAA", "BBB"]


def test_filter_handles_empty_input() -> None:
    df = pd.DataFrame(columns=["agency", "phase", "award_year"])
    cohort = AgencyCohortBuilder(agency_code="NSF").build(df)
    assert cohort.empty
    assert "vintage_bucket" in cohort.columns
    assert "phase_label" in cohort.columns


def test_award_date_fallback_for_year() -> None:
    df = pd.DataFrame(
        [
            {"agency": "NSF", "phase": "Phase I", "award_date": "2018-04-15", "uei": "AAA"},
        ]
    )
    cohort = AgencyCohortBuilder(agency_code="NSF").build(df)
    assert cohort.iloc[0]["vintage_bucket"] == "2015-2019"


def test_stratum_counts_returns_per_stratum_n() -> None:
    df = pd.DataFrame(
        [
            {"agency": "NSF", "phase": "Phase I", "award_year": 2017, "uei": "A"},
            {"agency": "NSF", "phase": "Phase I", "award_year": 2017, "uei": "B"},
            {"agency": "NSF", "phase": "Phase II", "award_year": 2017, "uei": "A"},
        ]
    )
    cohort = AgencyCohortBuilder(agency_code="NSF").build(df)
    counts = AgencyCohortBuilder.stratum_counts(cohort)
    assert set(counts.columns) == {"vintage_bucket", "phase_label", "n"}
    rows = {(r["vintage_bucket"], r["phase_label"]): r["n"] for _, r in counts.iterrows()}
    assert rows[("2015-2019", "I")] == 2
    assert rows[("2015-2019", "II")] == 1


def test_nsf_cohort_builder_backward_compat() -> None:
    """NSFCohortBuilder() still works as a back-compat alias."""
    df = pd.DataFrame(
        [
            {"agency": "NSF", "phase": "Phase I", "award_year": 2017, "uei": "A"},
        ]
    )
    cohort = NSFCohortBuilder().build(df)
    assert len(cohort) == 1
    assert cohort.iloc[0]["phase_label"] == "I"
