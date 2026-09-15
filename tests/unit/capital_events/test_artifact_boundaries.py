"""Invariants that consumers of the M&A artifacts rely on.

Each test states the assumption in terms of what a consumer can observe, not
in terms of what the producer intends. Three consumers key off row presence and
never read `confidence`, so "the tier is low" is not an assumption any of them
can act on.
"""

from __future__ import annotations

import json
from pathlib import Path


from sbir_etl.capital_events.sources.ma_events import build_ma_events

COHORT = [{"company_name": "ACME INC"}]


def _row(name: str, confidence: str, **extra: object) -> dict:
    row = {
        "company_name": name,
        "event_date": "2023-06-15",
        "acquirer": "GLOBEX CORP",
        "confidence": confidence,
        "signals": {"efts_subsidiary": True},
        "signal_count": 1,
    }
    row.update(extra)
    return row


def test_every_emitted_row_names_a_counterparty_or_says_why_not(tmp_path: Path) -> None:
    """A consumer reading `counterparty` cannot tell null-because-unknown from
    null-because-the-firm-was-the-buyer.

    407 events once reached this artifact at high confidence with a null
    acquirer, because a Form D business-combination flag graded high on its own
    and Form D names no counterparty.
    """
    src = tmp_path / "ma.jsonl"
    src.write_text(json.dumps(_row("ACME INC", "high", acquirer=None)) + "\n")

    events = list(build_ma_events(COHORT, src))
    for event in events:
        assert event["counterparty"], (
            "an emitted M&A event must name a counterparty; a row that cannot "
            "name one belongs in data/sbir_ma_non_exit.jsonl"
        )


def test_signal_count_matches_the_signals_it_reports(tmp_path: Path) -> None:
    """A row's `signal_count` must equal the signals it actually carries.

    Legacy rows on disk carry a count inflated by a removed source: the
    deleted press stage incremented `signal_count` once per press hit, and
    all 18 of its hits were false positives, so 18 rows carry a count one
    above their own `signals`. PR #709 recomputes the count from `signals`
    rather than trusting the stored value, which is what this asserts.
    """
    src = tmp_path / "ma.jsonl"
    row = _row("ACME INC", "high")
    row["signal_count"] = 99
    src.write_text(json.dumps(row) + "\n")

    events = list(build_ma_events(COHORT, src))
    meta = json.loads(events[0]["metadata"])
    assert meta["signal_count"] == 1


def test_absent_source_file_yields_nothing_rather_than_raising(tmp_path: Path) -> None:
    """Pin the current behavior: a missing input yields `[]`, not an error.

    This is the hazard, not the safeguard. `build_ma_events` returns silently
    when its input is absent, so a rebuild that lost the artifact is
    indistinguishable from a rebuild that genuinely found zero M&A events --
    which is how deleting the only producer of
    `enriched_sbir_ma_events.jsonl` would drop every MA_EVENT without an
    error. The assertion records that behavior so a future change to raise
    instead is a deliberate, visible decision.
    """
    events = list(build_ma_events(COHORT, tmp_path / "absent.jsonl"))
    assert events == []
