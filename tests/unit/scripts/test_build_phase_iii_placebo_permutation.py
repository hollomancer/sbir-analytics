"""Focused tests for the R16 permutation-separation runner."""

import importlib.util
import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from sbir_analytics.assets.phase_iii_census.criteria import CensusInputError
from sbir_analytics.assets.phase_iii_negative_controls import permutation as perm
from sbir_analytics.assets.phase_iii_negative_controls.placebo import PLACEBO_SEED
from tests.unit.phase_iii_negative_controls.test_permutation import _pair

SCRIPT = Path(__file__).parents[3] / "scripts/data/build_phase_iii_placebo_permutation.py"
SPEC = importlib.util.spec_from_file_location("build_phase_iii_placebo_permutation", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

DATA_CUT = date(2026, 2, 6)


def _pairs() -> pd.DataFrame:
    return pd.DataFrame(
        [
            _pair(1, 1, "2018-01-31", firm="FIRM-A"),
            _pair(2, 3, None, firm="FIRM-A"),
            _pair(3, 4, "2020-03-31", firm="FIRM-B"),
            _pair(4, 5, "2025-12-31", firm="FIRM-B"),
            _pair(5, 6, "2022-05-31", firm="FIRM-C"),
            _pair(6, 7, "2023-06-30", firm="FIRM-D"),
        ]
    )


def _wire(monkeypatch: pytest.MonkeyPatch, pairs: pd.DataFrame, *, draws: int) -> None:
    """Bypass real inputs and the R15 recorded values; shrink the design to ``draws``."""

    monkeypatch.setattr(MODULE, "verify_frozen_spec", lambda: {"revision": "phase-0-r16"})
    monkeypatch.setattr(MODULE, "_load_pairs", lambda: (pairs, {"pair_rows": len(pairs)}, DATA_CUT))
    monkeypatch.setattr(MODULE.perm, "R16_DRAWS", draws)
    seen = perm.run_permutation_draws(pairs, DATA_CUT, [PLACEBO_SEED])
    monkeypatch.setattr(
        MODULE,
        "R15_RECORDED",
        {
            "assignment_mapping_sha256": seen.mapping_digests.iloc[0]["mapping_sha256"],
            "placebo_final": seen.placebo_final.iloc[0].to_dict(),
            "actual_final": seen.actual_final.iloc[0].to_dict(),
        },
    )


def test_run_is_blocked_without_owner_approval(tmp_path: Path) -> None:
    with pytest.raises(CensusInputError, match="remains blocked"):
        MODULE.run(tmp_path)
    assert not list(tmp_path.iterdir())


def test_run_refuses_a_draw_count_other_than_the_preregistered_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(MODULE, "verify_frozen_spec", lambda: pytest.fail("freeze read too early"))
    with pytest.raises(CensusInputError, match="preregistered design fixes"):
        MODULE.run(tmp_path, owner_approved=True, draws=perm.R16_DRAWS - 1)


def test_run_fails_before_input_reads_when_freeze_is_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def invalid_freeze():
        raise CensusInputError("frozen spec mismatch")

    monkeypatch.setattr(MODULE, "verify_frozen_spec", invalid_freeze)
    monkeypatch.setattr(
        MODULE, "_load_pairs", lambda: pytest.fail("inputs read before freeze check")
    )
    with pytest.raises(CensusInputError, match="frozen spec mismatch"):
        MODULE.run(tmp_path, owner_approved=True)
    assert not list(tmp_path.iterdir())


def test_precondition_failure_stops_before_any_confirmatory_draw(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pairs = _pairs()
    _wire(monkeypatch, pairs, draws=3)
    wrong = dict(MODULE.R15_RECORDED)
    wrong["placebo_final"] = {**wrong["placebo_final"], "surviving_pairs": 10**9}
    monkeypatch.setattr(MODULE, "R15_RECORDED", wrong)

    with pytest.raises(CensusInputError, match="equivalence precondition failed"):
        MODULE.run(tmp_path, owner_approved=True, draws=3)
    assert not (tmp_path / "draw_store").exists()
    assert not (tmp_path / MODULE.PRECONDITION_NAME).exists()


def test_partial_batch_writes_store_but_no_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pairs = _pairs()
    _wire(monkeypatch, pairs, draws=4)

    status = MODULE.run(tmp_path, owner_approved=True, draws=4, batch_size=2)

    assert status["complete"] is False
    assert status["result"] is None
    assert status["draws_complete"] == 2
    assert (tmp_path / "draw_store" / "draws_final.parquet").exists()
    assert not (tmp_path / MODULE.MANIFEST_NAME).exists()
    assert not (tmp_path / MODULE.OUTPUT_NAMES["exceedance"]).exists()
    assert json.loads((tmp_path / MODULE.PRECONDITION_NAME).read_text())["matched_recorded_r15"]


def test_resumed_run_completes_over_the_fixed_seed_list_and_writes_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pairs = _pairs()
    _wire(monkeypatch, pairs, draws=4)
    MODULE.run(tmp_path, owner_approved=True, draws=4, batch_size=3)

    status = MODULE.run(tmp_path, owner_approved=True, draws=4)

    assert status["complete"] is True
    assert status["draws_complete"] == 4
    result = status["result"]
    assert result["denominator"] == 4
    assert 0 <= result["numerator"] <= 4
    assert result["interval_low"] <= result["numerator"] / 4 <= result["interval_high"]
    assert result["interval_method"] == "wilson_95"
    assert isinstance(result["threshold_met"], bool)
    final = pd.read_parquet(tmp_path / MODULE.OUTPUT_NAMES["placebo_final"])
    assert final["seed"].tolist() == perm.preregistered_seeds(4)
    assert PLACEBO_SEED not in set(final["seed"])
    manifest = json.loads((tmp_path / MODULE.MANIFEST_NAME).read_text())
    assert manifest["design_revision"] == "phase-0-r16"
    assert set(manifest["artifacts"]) == set(MODULE.OUTPUT_NAMES)


def test_store_with_foreign_seed_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pairs = _pairs()
    _wire(monkeypatch, pairs, draws=2)
    MODULE.run(tmp_path, owner_approved=True, draws=2, batch_size=1)
    store = tmp_path / "draw_store" / "draws_final.parquet"
    frame = pd.read_parquet(store)
    frame.loc[0, "seed"] = 1
    frame.to_parquet(store, index=False)

    with pytest.raises(CensusInputError, match="outside the preregistered list"):
        MODULE.run(tmp_path, owner_approved=True, draws=2)


def test_recorded_r15_constants_are_the_published_final_stage_values() -> None:
    """Guard the transcription of placebo-results-2026-08-03.md."""

    recorded = MODULE.R15_RECORDED
    assert recorded["assignment_mapping_sha256"].startswith("c1c97a9c7f1c8110")
    assert recorded["placebo_final"]["surviving_pairs"] == 546_242
    assert recorded["placebo_final"]["distinct_firms"] == 1_985
    assert recorded["placebo_final"]["distinct_contracts"] == 21_357
    assert recorded["actual_final"]["surviving_pairs"] == 727_292
    assert recorded["actual_final"]["distinct_firms"] == 2_369
    assert recorded["actual_final"]["distinct_contracts"] == 28_665
