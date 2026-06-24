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
    # Pathway flag defaults to False when there are no events.
    assert bool(boring["has_strict_phase_ii_to_ma_pathway"]) is False


def test_summary_strict_pathway_for_p2_fd_ma_sequence(cohort):
    """Firm with Phase II → Form D → M&A in order gets pathway columns set."""
    events = _events_df(
        [
            _event("ACME INC", "2018-06-15", "sbir_award", "sbir_phase_i", 150000.0),
            _event("ACME INC", "2020-09-01", "sbir_award", "sbir_phase_ii", 1_000_000.0),
            _event("ACME INC", "2022-03-10", "form_d_filing", "equity", 5_000_000.0),
            _event("ACME INC", "2024-02-01", "ma_event", "high"),
        ]
    )
    summary = summarize_per_firm(events, cohort)
    acme = summary[summary.company_name == "ACME INC"].iloc[0]
    assert acme["first_phase_ii_date"] == "2020-09-01"
    assert acme["first_form_d_date"] == "2022-03-10"
    assert acme["first_ma_event_date"] == "2024-02-01"
    # 2020-09-01 → 2022-03-10 = 555 days
    assert acme["days_phase_ii_to_form_d"] == 555
    # 2022-03-10 → 2024-02-01 = 693 days
    assert acme["days_form_d_to_ma"] == 693
    # 2020-09-01 → 2024-02-01 = 1248 days
    assert acme["days_phase_ii_to_ma"] == 1248
    assert bool(acme["has_strict_phase_ii_to_ma_pathway"]) is True


def test_summary_strict_pathway_requires_p2_before_fd_before_ma(cohort):
    """Out-of-order events do not satisfy the strict pathway."""
    events = _events_df(
        [
            # Form D before Phase II — invalid sequence.
            _event("ACME INC", "2018-06-15", "form_d_filing", "equity", 1_000_000.0),
            _event("ACME INC", "2020-09-01", "sbir_award", "sbir_phase_ii", 1_000_000.0),
            _event("ACME INC", "2024-02-01", "ma_event", "high"),
        ]
    )
    summary = summarize_per_firm(events, cohort)
    acme = summary[summary.company_name == "ACME INC"].iloc[0]
    assert bool(acme["has_strict_phase_ii_to_ma_pathway"]) is False


def test_summary_strict_pathway_false_when_only_phase_i(cohort):
    """A Phase I award is not Phase II — pathway only triggers on Phase II."""
    events = _events_df(
        [
            _event("ACME INC", "2018-06-15", "sbir_award", "sbir_phase_i", 150000.0),
            _event("ACME INC", "2020-03-10", "form_d_filing", "equity", 5_000_000.0),
            _event("ACME INC", "2024-02-01", "ma_event", "high"),
        ]
    )
    summary = summarize_per_firm(events, cohort)
    acme = summary[summary.company_name == "ACME INC"].iloc[0]
    assert bool(acme["has_strict_phase_ii_to_ma_pathway"]) is False
    assert pd.isna(acme["first_phase_ii_date"])
    assert pd.isna(acme["days_phase_ii_to_ma"])


def test_summary_pathway_day_deltas_are_nan_when_out_of_order(cohort):
    """Negative or zero pathway-leg deltas are masked to NaN to avoid misleading
    downstream consumers (the columns describe the strict pathway, not arbitrary
    gaps). Flag is False; full-span gap is NaN. ~1,227 cohort firms in production
    data have Form D before Phase II — typical: incorporated and raised seed
    capital before pursuing SBIR.
    """
    events = _events_df(
        [
            # Form D before Phase II — negative P2 → FD gap.
            _event("ACME INC", "2018-06-15", "form_d_filing", "equity", 1_000_000.0),
            _event("ACME INC", "2020-09-01", "sbir_award", "sbir_phase_ii", 1_000_000.0),
            _event("ACME INC", "2024-02-01", "ma_event", "high"),
        ]
    )
    summary = summarize_per_firm(events, cohort)
    acme = summary[summary.company_name == "ACME INC"].iloc[0]
    # All three first-* dates still populated (they're factual, not pathway-conditional).
    assert acme["first_phase_ii_date"] == "2020-09-01"
    assert acme["first_form_d_date"] == "2018-06-15"
    assert acme["first_ma_event_date"] == "2024-02-01"
    # But the day-deltas are NaN for any leg that isn't strictly positive.
    assert pd.isna(acme["days_phase_ii_to_form_d"])  # FD → P2 is negative
    # FD → MA is still strictly positive (and unrelated to P2 ordering), so populated.
    assert acme["days_form_d_to_ma"] == 2057  # 2018-06-15 → 2024-02-01
    # P2 → MA is strictly positive in absolute terms.
    assert acme["days_phase_ii_to_ma"] == 1248
    # But the strict-pathway flag requires BOTH legs (P2 → FD AND FD → MA) to be > 0.
    assert bool(acme["has_strict_phase_ii_to_ma_pathway"]) is False


def test_summary_pathway_ignores_empty_event_dates(cohort):
    """Empty-string event dates must not win groupby().min() and propagate into
    `first_*` columns. Current source builders all skip events with unresolvable
    dates, but we defend against future regressions.
    """
    events = _events_df(
        [
            # An empty-date Phase II row would naively sort before "2020-09-01"
            # and become first_phase_ii_date if not filtered.
            _event("ACME INC", "", "sbir_award", "sbir_phase_ii", 0.0),
            _event("ACME INC", "2020-09-01", "sbir_award", "sbir_phase_ii", 1_000_000.0),
            _event("ACME INC", "2022-03-10", "form_d_filing", "equity", 5_000_000.0),
            _event("ACME INC", "2024-02-01", "ma_event", "high"),
        ]
    )
    summary = summarize_per_firm(events, cohort)
    acme = summary[summary.company_name == "ACME INC"].iloc[0]
    # The empty-date row is dropped; first valid Phase II date wins.
    assert acme["first_phase_ii_date"] == "2020-09-01"
    # Pathway still resolves correctly with the valid date.
    assert bool(acme["has_strict_phase_ii_to_ma_pathway"]) is True
    assert acme["days_phase_ii_to_form_d"] == 555
    assert acme["days_phase_ii_to_ma"] == 1248
