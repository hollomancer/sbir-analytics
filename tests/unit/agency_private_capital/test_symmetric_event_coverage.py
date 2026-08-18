"""Tests for symmetric date-aware event and coverage evaluation."""

from __future__ import annotations

from datetime import date

import pytest

from sbir_analytics.assets.agency_private_capital.symmetric_event_coverage import (
    EVENT_TYPE,
    OutcomeContractError,
    aggregate_event_presence,
    evaluate_event_presence,
)


pytestmark = pytest.mark.fast

SOURCE = "sec_dera_form_d_quarterly_bulk"
SNAPSHOT_ID = "snapshot:test"


def _risk(arm: str, cik: str, index_date: str) -> dict[str, object]:
    return {"arm": arm, "firm_key": f"form_d_cik:{cik}", "index_date": index_date}


def _coverage(
    cik: str,
    *,
    start: str = "2009-01-01",
    end: str = "2024-12-31",
    snapshot_date: str = "2024-12-31",
    complete: bool = True,
) -> dict[str, object]:
    return {
        "coverage_end_date": end,
        "coverage_start_date": start,
        "firm_key": f"form_d_cik:{cik}",
        "metric": EVENT_TYPE,
        "source": SOURCE,
        "source_complete": complete,
        "source_snapshot_date": snapshot_date,
        "source_snapshot_id": SNAPSHOT_ID,
    }


def _event(
    cik: str,
    event_date: str,
    accession: str,
    *,
    amendment: bool = False,
    previous_accession: str | None = None,
) -> dict[str, object]:
    return {
        "accession_number": accession,
        "date_basis": "filing_date",
        "event_date": event_date,
        "event_id": f"form_d_accession:{accession}",
        "event_type": EVENT_TYPE,
        "evidence_kind": "proxy",
        "filing_date": event_date,
        "firm_key": f"form_d_cik:{cik}",
        "is_amendment": amendment,
        "previous_accession_number": previous_accession,
        "source": SOURCE,
        "source_quarter": "2024Q4",
        "source_snapshot_id": SNAPSHOT_ID,
    }


def test_inclusive_boundaries_use_the_same_evaluator_for_both_arms() -> None:
    risks = [
        _risk("treated", "1", "2019-12-31"),
        _risk("control", "2", "2019-12-31"),
    ]
    events = [
        _event("1", "2019-12-30", "OUTSIDE-BEFORE"),
        _event("1", "2019-12-31", "AT-INDEX"),
        _event("2", "2024-12-31", "AT-HORIZON"),
    ]

    rows = evaluate_event_presence(risks, events, [_coverage("1"), _coverage("2")])

    assert [row["value"] for row in rows] == [1, 1]
    assert [row["event_count"] for row in rows] == [1, 1]
    assert rows[0]["evidence"][0]["accession_number"] == "AT-INDEX"
    assert rows[1]["evidence"][0]["accession_number"] == "AT-HORIZON"


def test_multiple_filings_and_amendment_count_once_but_preserve_evidence() -> None:
    events = [
        _event("1", "2020-01-01", "D-1"),
        _event("1", "2021-01-01", "D-A-1", amendment=True, previous_accession="D-1"),
    ]

    row = evaluate_event_presence(
        [_risk("treated", "1", "2019-01-01")],
        events,
        [_coverage("1")],
    )[0]

    assert row["available"] is True
    assert row["value"] == 1
    assert row["event_count"] == 2
    assert [evidence["accession_number"] for evidence in row["evidence"]] == ["D-1", "D-A-1"]
    assert row["evidence"][1]["is_amendment"] is True
    assert row["evidence"][1]["previous_accession_number"] == "D-1"


def test_covered_no_event_is_observed_zero_and_remains_in_denominator() -> None:
    evaluated = evaluate_event_presence(
        [_risk("treated", "1", "2019-12-31"), _risk("control", "2", "2019-12-31")],
        [_event("1", "2020-01-01", "EVENT-1")],
        [_coverage("1"), _coverage("2")],
    )

    assert evaluated[1]["available"] is True
    assert evaluated[1]["value"] == 0
    aggregates = aggregate_event_presence(evaluated)
    by_arm = {row["arm"]: row for row in aggregates}
    assert by_arm["treated"]["numerator"] == 1
    assert by_arm["treated"]["denominator"] == 1
    assert by_arm["control"]["numerator"] == 0
    assert by_arm["control"]["denominator"] == 1


def test_snapshot_boundary_right_censors_insufficient_follow_up() -> None:
    evaluated = evaluate_event_presence(
        [
            _risk("treated", "1", "2019-12-31"),
            _risk("control", "2", "2020-01-01"),
        ],
        [_event("2", "2020-06-01", "EARLY-BUT-CENSORED")],
        [_coverage("1"), _coverage("2")],
    )

    assert evaluated[0]["available"] is True
    assert evaluated[0]["horizon_end_date"] == "2024-12-31"
    assert evaluated[1]["available"] is False
    assert evaluated[1]["horizon_end_date"] == "2025-01-01"
    assert evaluated[1]["unavailability_reason"] == "right_censored"
    assert evaluated[1]["event_count"] == 0
    aggregates = aggregate_event_presence(evaluated)
    assert {row["arm"]: row["denominator"] for row in aggregates} == {
        "treated": 1,
        "control": 0,
    }


def test_calendar_year_horizon_maps_leap_day_to_february_end() -> None:
    coverage = _coverage("1", end="2025-02-28", snapshot_date="2025-02-28")
    row = evaluate_event_presence(
        [_risk("treated", "1", "2020-02-29")],
        [
            _event("1", "2025-02-28", "LEAP-BOUNDARY"),
            _event("1", "2025-03-01", "AFTER-BOUNDARY"),
        ],
        [coverage],
        snapshot_date=date(2025, 2, 28),
    )[0]

    assert row["horizon_end_date"] == "2025-02-28"
    assert row["value"] == 1
    assert row["event_count"] == 1


def test_invalid_identity_missing_coverage_and_outside_interval_are_unavailable() -> None:
    risks = [
        {"arm": "treated", "firm_key": None, "company_name": "Acme", "index_date": "2019-01-01"},
        _risk("treated", "2", "2019-01-01"),
        _risk("control", "3", "2008-12-31"),
    ]
    rows = evaluate_event_presence(risks, [], [_coverage("3")])

    assert [row["unavailability_reason"] for row in rows] == [
        "invalid_firm_key",
        "missing_coverage",
        "outside_coverage",
    ]
    assert all(row["available"] is False and row["value"] is None for row in rows)
    aggregates = aggregate_event_presence(rows)
    assert all(row["denominator"] == 0 for row in aggregates)


def test_swapping_arm_labels_does_not_change_firm_results_or_rates() -> None:
    events = [
        _event("1", "2020-01-01", "EVENT-1"),
        _event("2", "2020-01-01", "EVENT-2"),
    ]
    coverage = [_coverage("1"), _coverage("2")]
    original = evaluate_event_presence(
        [_risk("treated", "1", "2019-01-01"), _risk("control", "2", "2019-01-01")],
        events,
        coverage,
    )
    swapped = evaluate_event_presence(
        [_risk("control", "1", "2019-01-01"), _risk("treated", "2", "2019-01-01")],
        events,
        coverage,
    )

    original_by_firm = {
        row["firm_key"]: (row["available"], row["value"], row["event_count"]) for row in original
    }
    swapped_by_firm = {
        row["firm_key"]: (row["available"], row["value"], row["event_count"]) for row in swapped
    }
    assert original_by_firm == swapped_by_firm
    assert {row["arm"]: row["rate"] for row in aggregate_event_presence(original)} == {
        "treated": 1.0,
        "control": 1.0,
    }
    assert {row["arm"]: row["rate"] for row in aggregate_event_presence(swapped)} == {
        "treated": 1.0,
        "control": 1.0,
    }


def test_source_completeness_is_global_and_empty_source_is_distinct() -> None:
    risks = [_risk("treated", "1", "2019-01-01"), _risk("control", "2", "2019-01-01")]
    incomplete = evaluate_event_presence(
        risks,
        [],
        [_coverage("1"), _coverage("2", complete=False)],
    )
    missing = evaluate_event_presence(risks, [], [])

    assert {row["unavailability_reason"] for row in incomplete} == {"incomplete_source"}
    assert {row["unavailability_reason"] for row in missing} == {"missing_source"}


def test_incomplete_event_evidence_makes_that_firm_unavailable() -> None:
    event = _event("1", "2020-01-01", "EVENT-1")
    event["evidence_kind"] = "asserted_event"

    row = evaluate_event_presence([_risk("treated", "1", "2019-01-01")], [event], [_coverage("1")])[
        0
    ]

    assert row["available"] is False
    assert row["unavailability_reason"] == "incomplete_source"


def test_invalid_arm_and_cross_arm_identity_overlap_are_rejected() -> None:
    with pytest.raises(OutcomeContractError, match="arm must be"):
        evaluate_event_presence([_risk("case", "1", "2019-01-01")], [], [_coverage("1")])

    with pytest.raises(OutcomeContractError, match="both arms"):
        evaluate_event_presence(
            [_risk("treated", "1", "2019-01-01"), _risk("control", "1", "2019-01-01")],
            [],
            [_coverage("1")],
        )


def test_contract_uses_only_the_exact_proxy_metric_and_exact_cik_namespace() -> None:
    assert EVENT_TYPE == "form_d_business_combination_filing_proxy"
    row = evaluate_event_presence(
        [{"arm": "treated", "firm_key": "name:acme", "index_date": "2019-01-01"}],
        [],
        [_coverage("1")],
    )[0]
    assert row["available"] is False
    assert row["unavailability_reason"] == "invalid_firm_key"
