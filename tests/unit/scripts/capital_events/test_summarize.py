"""Tests for per-firm summary aggregator."""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts" / "data"))

from capital_events.summarize import summarize_per_firm  # noqa: E402


def _events_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(
        rows,
        columns=[
            "company_name",
            "event_date",
            "event_type",
            "event_subtype",
            "amount_usd",
            "counterparty",
            "source_id",
            "metadata",
        ],
    )


def _event(
    company, date, etype, subtype=None, amount=None, counterparty=None, source_id="X", metadata="{}"
):
    return {
        "company_name": company,
        "event_date": date,
        "event_type": etype,
        "event_subtype": subtype,
        "amount_usd": amount,
        "counterparty": counterparty,
        "source_id": source_id,
        "metadata": metadata,
    }


def test_summary_includes_one_row_per_cohort_firm(cohort):
    events = _events_df([])
    summary = summarize_per_firm(events, cohort)
    assert len(summary) == 3
    assert set(summary["company_name"]) == {"ACME INC", "BORING LLC", "OUT-OF-STATE CORP"}


def test_summary_counts_and_sums_sbir_events(cohort):
    events = _events_df(
        [
            _event("ACME INC", "2018-06-15", "sbir_award", "sbir_phase_i", 150000.0),
            _event("ACME INC", "2020-09-01", "sbir_award", "sbir_phase_ii", 1000000.0),
            _event("BORING LLC", "2020-04-01", "sbir_award", "sbir_phase_i", 250000.0),
        ]
    )
    summary = summarize_per_firm(events, cohort)
    acme = summary[summary.company_name == "ACME INC"].iloc[0]
    assert acme["sbir_award_count"] == 2
    assert acme["total_sbir_amount"] == 1_150_000.0


def test_summary_form_d_aggregations(cohort):
    events = _events_df(
        [
            _event("ACME INC", "2023-01-15", "form_d_filing", "equity", 5_000_000.0),
            _event("ACME INC", "2023-08-22", "form_d_filing", "debt", 10_000_000.0),
        ]
    )
    summary = summarize_per_firm(events, cohort)
    acme = summary[summary.company_name == "ACME INC"].iloc[0]
    assert acme["form_d_filing_count"] == 2
    assert acme["total_form_d_raised"] == 15_000_000.0


def test_summary_ma_flags_and_dates(cohort):
    events = _events_df(
        [
            _event("ACME INC", "2024-02-01", "ma_event", "medium"),
            _event("ACME INC", "2024-03-01", "ma_event", "high"),
        ]
    )
    summary = summarize_per_firm(events, cohort)
    acme = summary[summary.company_name == "ACME INC"].iloc[0]
    assert bool(acme["has_ma_event"]) is True
    assert acme["first_ma_event_date"] == "2024-02-01"
    assert acme["ma_confidence_max_tier"] == "high"


def test_summary_first_and_last_event_dates(cohort):
    events = _events_df(
        [
            _event("ACME INC", "2018-06-15", "sbir_award", "sbir_phase_i", 150000.0),
            _event("ACME INC", "2024-02-01", "ma_event", "high"),
            _event("ACME INC", "2023-08-22", "form_d_filing", "equity", 10_000_000.0),
        ]
    )
    summary = summarize_per_firm(events, cohort)
    acme = summary[summary.company_name == "ACME INC"].iloc[0]
    assert acme["first_event_date"] == "2018-06-15"
    assert acme["last_event_date"] == "2024-02-01"
    assert acme["event_type_count"] == 3


def test_summary_zero_event_firm_has_zero_counts(cohort):
    """A cohort firm with no events should still appear with zeros."""
    events = _events_df([])
    summary = summarize_per_firm(events, cohort)
    boring = summary[summary.company_name == "BORING LLC"].iloc[0]
    assert boring["sbir_award_count"] == 0
    assert boring["form_d_filing_count"] == 0
    assert bool(boring["has_ma_event"]) is False
    assert pd.isna(boring["first_event_date"])
