"""Focused regression tests for the exploratory headcount readout."""

import importlib.util
import sys
from pathlib import Path
from typing import get_type_hints

import pandas as pd


SCRIPT = Path(__file__).parents[3] / "scripts/data/build_headcount_at_award_readout.py"
SPEC = importlib.util.spec_from_file_location("build_headcount_at_award_readout", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_default_materialization_is_isolated_from_phase_iii_evidence() -> None:
    normalized = MODULE.MATERIALIZED_SBIR_PATH.as_posix()

    assert "headcount_at_award" in normalized
    assert "phase_iii_census" not in normalized


def test_existing_materialization_is_verified_and_reused(tmp_path: Path, monkeypatch) -> None:
    materialized = tmp_path / "awards.parquet"
    materialized.write_text("existing", encoding="utf-8")
    expected = pd.DataFrame({"number_employees": [10]})
    calls: list[str] = []

    monkeypatch.setattr(MODULE.pd, "read_parquet", lambda path: expected)
    monkeypatch.setattr(
        MODULE,
        "verify_sbir_gov_materialization",
        lambda path, frame: calls.append(str(path)) or {"generated_at": "2026-08-23"},
    )
    monkeypatch.setattr(
        MODULE,
        "materialize_sbir_gov_history",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not rewrite")),
    )

    frame, manifest = MODULE._materialize_source(tmp_path / "raw.csv", materialized)

    assert frame is expected
    assert manifest["generated_at"] == "2026-08-23"
    assert calls == [str(materialized)]


def test_headcount_parser_flags_extraction_and_rejects_ranges() -> None:
    assert MODULE._parse_headcount_with_method("1,000") == (1000, "numeric")
    assert MODULE._parse_headcount_with_method("approx. 500") == (500, "embedded_numeric")
    assert MODULE._parse_headcount_with_method("10-50") == (
        None,
        "ambiguous_multiple_numbers",
    )
    assert MODULE._parse_headcount_with_method("5 to 10") == (
        None,
        "ambiguous_multiple_numbers",
    )
    assert MODULE._parse_headcount_with_method("NaN") == (None, "missing")
    assert MODULE._parse_headcount_with_method("inf") == (None, "nonfinite")


def test_phase_sort_accepts_materialized_phase_labels() -> None:
    assert MODULE._phase_sort_key("Phase I") < MODULE._phase_sort_key("Phase II")
    assert MODULE._phase_sort_key("Phase IB") < MODULE._phase_sort_key("Phase II")
    assert MODULE._phase_sort_key("III") == (5, "III")


def test_awards_are_sorted_once_by_firm_and_chronology() -> None:
    frame = pd.DataFrame(
        {
            "firm_key": ["B", "A", "A"],
            "award_sort_date": pd.to_datetime(["2020-01-01", "2021-01-01", "2021-01-01"]),
            "award_year": [2020, 2021, 2021],
            "phase_sort_key": [1, 3, 1],
            "award_record_key": ["b", "a2", "a1"],
        }
    )

    ordered = MODULE._sort_awards(frame)

    assert ordered["award_record_key"].tolist() == ["a1", "a2", "b"]


def test_crossed_threshold_requires_an_upward_crossing() -> None:
    assert MODULE._crossed_threshold_upward(pd.Series([90, 420, 300]), 350)
    assert not MODULE._crossed_threshold_upward(pd.Series([420, 300, 90]), 350)
    assert not MODULE._crossed_threshold_upward(pd.Series([420, 500]), 350)


def test_crosscheck_status_is_derived_from_local_files(tmp_path: Path) -> None:
    absent = MODULE._build_crosscheck_summary(tmp_path)
    assert absent["crosscheck_status"].eq("source_not_found").all()
    assert absent["agree_count"].isna().all()

    candidate = tmp_path / "sam_employee_counts.csv"
    candidate.write_text("uei,employee_count\nABC,10\n", encoding="utf-8")
    detected = MODULE._build_crosscheck_summary(tmp_path)
    assert detected["crosscheck_status"].eq("source_detected_join_not_implemented").all()
    assert detected["materialized_source_available"].all()
    assert str(candidate) in detected["note"].iloc[0]


def test_correlation_annotations_resolve() -> None:
    assert get_type_hints(MODULE._safe_corr)["return"] == float | None
    assert get_type_hints(MODULE._year_fixed_effect_corr)["return"] == float | None
