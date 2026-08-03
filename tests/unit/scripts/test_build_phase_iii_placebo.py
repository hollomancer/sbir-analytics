"""Focused tests for the frozen Phase III placebo materializer."""

import importlib.util
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from sbir_analytics.assets.phase_iii_census.criteria import CensusInputError
from sbir_analytics.assets.phase_iii_negative_controls.placebo import (
    PlaceboAssignment,
    PlaceboCensusTables,
)
from sbir_analytics.assets.phase_iii_negative_controls import placebo as placebo_module


SCRIPT = Path(__file__).parents[3] / "scripts/data/build_phase_iii_placebo.py"
SPEC = importlib.util.spec_from_file_location("build_phase_iii_placebo", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _dropoff(value: int, dollars: float) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "step_order": 0,
                "clause_id": "all_exact_uei_pairs",
                "clause": "All exact-UEI pairs",
                "surviving_pairs": value,
                "distinct_firms": value,
                "distinct_contracts": value,
                "total_obligated_dollars": dollars,
            }
        ]
    )


def _sensitivity(value: int, dollars: float) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "cell_id": "none__same_agency",
                "time_window": "none",
                "agency_match": "same_agency",
                "surviving_pairs": value,
                "distinct_firms": value,
                "distinct_contracts": value,
                "total_obligated_dollars": dollars,
            }
        ]
    )


def test_compare_tables_uses_frozen_direction_and_explicit_zero_denominator() -> None:
    comparison = MODULE._compare_tables(
        _dropoff(3, -10.0),
        _dropoff(0, 5.0),
        keys=("step_order", "clause_id"),
        labels=("clause",),
    )

    assert comparison.loc[0, "surviving_pairs_actual"] == 3
    assert comparison.loc[0, "surviving_pairs_placebo"] == 0
    assert comparison.loc[0, "surviving_pairs_actual_minus_placebo"] == 3
    assert pd.isna(comparison.loc[0, "surviving_pairs_actual_to_placebo_ratio"])
    assert (
        comparison.loc[0, "surviving_pairs_actual_to_placebo_ratio_status"]
        == "undefined_zero_placebo_denominator"
    )
    assert comparison.loc[0, "total_obligated_dollars_actual_minus_placebo"] == -15.0
    assert comparison.loc[0, "total_obligated_dollars_actual_to_placebo_ratio"] == -2.0
    assert comparison.loc[0, "total_obligated_dollars_actual_to_placebo_ratio_status"] == "defined"

    both_zero = MODULE._compare_tables(
        _dropoff(0, 0.0),
        _dropoff(0, 0.0),
        keys=("step_order", "clause_id"),
        labels=("clause",),
    )
    assert pd.isna(both_zero.loc[0, "surviving_pairs_actual_to_placebo_ratio"])
    assert (
        both_zero.loc[0, "surviving_pairs_actual_to_placebo_ratio_status"]
        == "undefined_zero_placebo_denominator"
    )


def test_compare_tables_rejects_nonmatching_rows_and_labels() -> None:
    mismatched_key = _dropoff(1, 1.0).assign(clause_id="different")
    with pytest.raises(CensusInputError, match="same stages or cells"):
        MODULE._compare_tables(
            _dropoff(1, 1.0),
            mismatched_key,
            keys=("step_order", "clause_id"),
            labels=("clause",),
        )

    mismatched_label = _dropoff(1, 1.0).assign(clause="Different label")
    with pytest.raises(CensusInputError, match="disagrees on clause"):
        MODULE._compare_tables(
            _dropoff(1, 1.0),
            mismatched_label,
            keys=("step_order", "clause_id"),
            labels=("clause",),
        )

    duplicated = pd.concat([_dropoff(1, 1.0), _dropoff(1, 1.0)], ignore_index=True)
    with pytest.raises(CensusInputError, match="keys must be unique"):
        MODULE._compare_tables(
            duplicated,
            duplicated,
            keys=("step_order", "clause_id"),
            labels=("clause",),
        )


def test_build_output_frames_calls_actual_and_placebo_paths_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pairs = pd.DataFrame({"pair": [1]})
    actual_dropoff = _dropoff(4, 20.0)
    actual_sensitivity = _sensitivity(2, 10.0)
    placebo_dropoff = _dropoff(2, 5.0)
    placebo_sensitivity = _sensitivity(1, 2.5)
    audit = pd.DataFrame({"recipient_award_id": ["A"]})
    assignment = PlaceboAssignment(audit, pairs.copy(), "a" * 64)
    census_calls: list[tuple[pd.DataFrame, date]] = []
    placebo_calls: list[tuple[pd.DataFrame, date]] = []

    def fake_census(frame: pd.DataFrame, cut: date):
        census_calls.append((frame, cut))
        return actual_dropoff, actual_sensitivity

    def fake_placebo(frame: pd.DataFrame, cut: date):
        placebo_calls.append((frame, cut))
        return PlaceboCensusTables(assignment, placebo_dropoff, placebo_sensitivity)

    monkeypatch.setattr(MODULE, "build_census_tables", fake_census)
    monkeypatch.setattr(MODULE, "build_placebo_study_tables", fake_placebo)

    frames, mapping_sha256 = MODULE._build_output_frames(pairs, date(2026, 2, 6))

    assert len(census_calls) == 1
    assert len(placebo_calls) == 1
    assert census_calls[0][0] is pairs
    assert placebo_calls[0][0] is pairs
    assert mapping_sha256 == "a" * 64
    assert frames["assignment_audit"] is audit
    assert frames["dropoff_comparison"].loc[0, "surviving_pairs_actual_minus_placebo"] == 2
    assert frames["sensitivity_comparison"].loc[0, "distinct_firms_actual_to_placebo_ratio"] == 2.0


def test_output_builder_uses_shared_census_path_once_per_arm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pairs = pd.DataFrame({"pair": [1]})
    permuted = pd.DataFrame({"pair": [2]})
    audit = pd.DataFrame({"recipient_award_id": ["A"]})
    assignment = PlaceboAssignment(audit, permuted, "b" * 64)
    calls: list[pd.DataFrame] = []

    def fake_assignment(frame: pd.DataFrame) -> PlaceboAssignment:
        assert frame is pairs
        return assignment

    def fake_census(frame: pd.DataFrame, _cut: date):
        calls.append(frame)
        value = 4 if frame is pairs else 2
        return _dropoff(value, float(value)), _sensitivity(value, float(value))

    monkeypatch.setattr(placebo_module, "build_placebo_assignment", fake_assignment)
    monkeypatch.setattr(placebo_module, "build_census_tables", fake_census)
    monkeypatch.setattr(MODULE, "build_census_tables", fake_census)

    MODULE._build_output_frames(pairs, date(2026, 2, 6))

    assert calls == [pairs, permuted]


def test_verify_phase_i_tables_requires_exact_persisted_tables(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dropoff_path = tmp_path / "dropoff.parquet"
    sensitivity_path = tmp_path / "sensitivity.parquet"
    dropoff = _dropoff(1, 1.0)
    sensitivity = _sensitivity(1, 1.0)
    dropoff.to_parquet(dropoff_path, index=False)
    sensitivity.to_parquet(sensitivity_path, index=False)
    monkeypatch.setattr(MODULE, "DROP_OFF_OUTPUT_PATH", dropoff_path)
    monkeypatch.setattr(MODULE, "SENSITIVITY_OUTPUT_PATH", sensitivity_path)

    records = MODULE._verify_phase_i_tables(dropoff, sensitivity)

    assert records["dropoff"]["rows"] == 1
    assert len(records["sensitivity"]["sha256"]) == 64
    with pytest.raises(CensusInputError, match="does not equal"):
        MODULE._verify_phase_i_tables(_dropoff(2, 1.0), sensitivity)


def test_run_fails_before_input_reads_or_writes_when_freeze_is_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def invalid_freeze():
        raise CensusInputError("frozen spec mismatch")

    monkeypatch.setattr(MODULE, "verify_frozen_spec", invalid_freeze)
    monkeypatch.setattr(
        MODULE.pd,
        "read_parquet",
        lambda *_args, **_kwargs: pytest.fail("input read happened before freeze verification"),
    )
    monkeypatch.setattr(
        MODULE,
        "_write_parquet_atomic",
        lambda *_args, **_kwargs: pytest.fail("artifact write happened after provenance failure"),
    )

    with pytest.raises(CensusInputError, match="frozen spec mismatch"):
        MODULE.run(tmp_path)
    assert not list(tmp_path.iterdir())


def test_run_stops_before_census_or_writes_when_phase_i_provenance_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    phase_ii_path = tmp_path / "phase_ii.parquet"
    monkeypatch.setenv(MODULE.PHASE_II_OUTPUT_ENV, str(phase_ii_path))
    monkeypatch.setattr(MODULE, "verify_frozen_spec", lambda: {"revision": "phase-0-r15"})
    monkeypatch.setattr(MODULE.pd, "read_parquet", lambda _path: pd.DataFrame({"prior": [1]}))
    monkeypatch.setattr(
        MODULE,
        "_load_contracts",
        lambda: (pd.DataFrame({"contract": [1]}), tmp_path / "contracts.parquet"),
    )
    monkeypatch.setattr(
        MODULE,
        "_verify_phase_ii_provenance",
        lambda *_args: (_ for _ in ()).throw(CensusInputError("provenance mismatch")),
    )
    monkeypatch.setattr(
        MODULE,
        "_build_output_frames",
        lambda *_args: pytest.fail("census ran after provenance failure"),
    )
    monkeypatch.setattr(
        MODULE,
        "_write_parquet_atomic",
        lambda *_args, **_kwargs: pytest.fail("artifact write happened after provenance failure"),
    )

    with pytest.raises(CensusInputError, match="provenance mismatch"):
        MODULE.run(tmp_path / "outputs")
    assert not (tmp_path / "outputs").exists()
