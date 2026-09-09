"""Tests for M&A capital-event builder."""

import json


from sbir_etl.capital_events.sources.ma_events import build_ma_events


def _ma_row(name, date, confidence, acquirer=None, signals=None, press=None):
    return {
        "company_name": name,
        "event_date": date,
        "confidence": confidence,
        "acquirer": acquirer,
        "signals": signals or {},
        "signal_count": 1,
        "form_d_detail": None,
        "efts_detail": None,
        "sbir_context": {"agency": "DoD"},
    }


def test_emits_high_and_medium_drops_low(cohort, tmp_path):
    src = tmp_path / "ma.jsonl"
    src.write_text(
        "\n".join(
            json.dumps(r)
            for r in [
                _ma_row("ACME INC", "2023-06-15", "high", acquirer="GiantCo"),
                _ma_row("OUT-OF-STATE CORP", "2022-11-01", "medium"),
                _ma_row("ACME INC", "2024-02-01", "low"),
            ]
        )
        + "\n"
    )

    events = list(build_ma_events(cohort, src))
    assert len(events) == 2
    by_firm = {e["company_name"]: e for e in events}
    acme = by_firm["ACME INC"]
    assert acme["event_date"] == "2023-06-15"
    assert acme["event_type"] == "ma_event"
    assert acme["event_subtype"] == "high"
    assert acme["counterparty"] == "GiantCo"
    assert acme["amount_usd"] is None
    assert acme["source_id"] == "ACME INC__2023-06-15"


def test_skips_non_cohort_firms(cohort, tmp_path):
    src = tmp_path / "ma.jsonl"
    src.write_text(json.dumps(_ma_row("UNRELATED INC", "2023-01-01", "high")) + "\n")
    assert list(build_ma_events(cohort, src)) == []


def test_returns_empty_when_file_missing(cohort, tmp_path):
    assert list(build_ma_events(cohort, tmp_path / "nope.jsonl")) == []


def test_metadata_carries_signals(cohort, tmp_path):
    """The signals dict reaches capital-event metadata intact."""
    src = tmp_path / "ma.jsonl"
    src.write_text(
        json.dumps(
            _ma_row(
                "ACME INC",
                "2023-06-15",
                "high",
                signals={"form_d_business_combination": True},
            )
        )
        + "\n"
    )
    events = list(build_ma_events(cohort, src))
    meta = json.loads(events[0]["metadata"])
    assert meta["signals"]["form_d_business_combination"] is True


def test_signal_count_is_recomputed_not_forwarded(cohort, tmp_path):
    """Legacy rows carry a press-inflated count; recompute from signals.

    The removed press stage added one to signal_count per press hit, and all
    18 of its hits were false positives, so the stored count overstates the
    evidence on those rows.
    """
    src = tmp_path / "ma.jsonl"
    row = _ma_row("ACME INC", "2023-06-15", "high", signals={"efts_subsidiary": True})
    row["signal_count"] = 99
    src.write_text(json.dumps(row) + "\n")

    events = list(build_ma_events(cohort, src))
    assert json.loads(events[0]["metadata"])["signal_count"] == 1
