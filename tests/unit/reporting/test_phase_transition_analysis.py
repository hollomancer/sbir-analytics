"""Contract tests for the explicitly exploratory phase-transition report."""

import json

import duckdb
import pytest

from sbir_etl.reporting.phase_transition_analysis import (
    generate_phase_transition_report,
    main,
)


def _write_parquet(path, query: str) -> None:
    escaped = str(path).replace("'", "''")
    with duckdb.connect(":memory:") as connection:
        connection.execute(f"COPY ({query}) TO '{escaped}' (FORMAT PARQUET)")


def test_report_is_materialized_with_non_citable_marker(tmp_path) -> None:
    phase_ii = tmp_path / "phase_ii.parquet"
    phase_iii = tmp_path / "phase_iii.parquet"
    pairs = tmp_path / "pairs.parquet"
    survival = tmp_path / "survival.parquet"
    output = tmp_path / "report"

    _write_parquet(phase_ii, "SELECT 1 AS award_id")
    _write_parquet(phase_iii, "SELECT 1 AS contract_id")
    _write_parquet(
        pairs,
        "SELECT 90 AS latency_days, 'ARMY' AS phase_ii_agency UNION ALL SELECT 180, 'ARMY'",
    )
    _write_parquet(
        survival,
        "SELECT 'ARMY' AS phase_ii_agency, true AS event_observed, "
        "DATE '2024-06-30' AS phase_ii_end_date, 90 AS time_days "
        "UNION ALL SELECT 'ARMY', false, DATE '2024-12-31', 120",
    )

    generate_phase_transition_report(phase_ii, phase_iii, pairs, survival, output)

    report = json.loads((output / "phase_transition_report.json").read_text())
    assert report["_epistemic"] == {
        "tier": "exploratory",
        "citable": False,
        "notice": "Exploratory analysis; do not cite as an evidence-tier result.",
    }
    # Latency is counted over observed events in `survival`, one row per Phase II
    # award — not over the two `pairs` rows, which share a single award.
    assert report["latency_distribution"]["n"] == 1
    assert report["cohort_transition_rate"][0]["transition_rate"] == 0.5


def test_cli_fails_clearly_when_materializations_are_missing(tmp_path) -> None:
    with pytest.raises(SystemExit, match="Missing upstream parquet files"):
        main(["--phase-ii", str(tmp_path / "missing.parquet")])


def test_latency_and_rate_share_the_award_grain(tmp_path) -> None:
    """One award matching several Phase III contracts must count once.

    `pairs` carries a row per matched contract, so reading latency from it while
    reading the transition rate from `survival` reported two different
    denominators under one transition vocabulary.
    """

    phase_ii = tmp_path / "phase_ii.parquet"
    phase_iii = tmp_path / "phase_iii.parquet"
    pairs = tmp_path / "pairs.parquet"
    survival = tmp_path / "survival.parquet"
    output = tmp_path / "report"

    _write_parquet(phase_ii, "SELECT 1 AS award_id")
    _write_parquet(phase_iii, "SELECT 1 AS contract_id")
    # One award, three Phase III contracts.
    _write_parquet(
        pairs,
        "SELECT 30 AS latency_days, 'NAVY' AS phase_ii_agency "
        "UNION ALL SELECT 60, 'NAVY' UNION ALL SELECT 900, 'NAVY'",
    )
    _write_parquet(
        survival,
        "SELECT 'NAVY' AS phase_ii_agency, true AS event_observed, "
        "DATE '2024-06-30' AS phase_ii_end_date, 30 AS time_days "
        "UNION ALL SELECT 'NAVY', false, DATE '2024-06-30', 365",
    )

    generate_phase_transition_report(phase_ii, phase_iii, pairs, survival, output)
    report = json.loads((output / "phase_transition_report.json").read_text())

    latency = report["latency_distribution"]
    agency = report["agency_breakdown"][0]

    assert latency["n"] == 1
    assert latency["percentiles_days"]["p50"] == 30
    # The agency row's denominator and its median must describe the same awards.
    assert agency["phase_ii_total"] == 2
    assert agency["matched"] == 1
    assert agency["match_rate"] == 0.5
    assert agency["median_latency_days"] == 30
