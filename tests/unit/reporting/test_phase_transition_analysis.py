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
        "DATE '2024-06-30' AS phase_ii_end_date "
        "UNION ALL SELECT 'ARMY', false, DATE '2024-12-31'",
    )

    generate_phase_transition_report(phase_ii, phase_iii, pairs, survival, output)

    report = json.loads((output / "phase_transition_report.json").read_text())
    assert report["_epistemic"] == {
        "tier": "exploratory",
        "citable": False,
        "notice": "Exploratory analysis; do not cite as an evidence-tier result.",
    }
    assert report["latency_distribution"]["n"] == 2
    assert report["cohort_transition_rate"][0]["transition_rate"] == 0.5


def test_cli_fails_clearly_when_materializations_are_missing(tmp_path) -> None:
    with pytest.raises(SystemExit, match="Missing upstream parquet files"):
        main(["--phase-ii", str(tmp_path / "missing.parquet")])
