"""Focused tests for the R16 permutation-separation runner."""

import hashlib
import importlib.util
import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from sbir_analytics.assets.phase_iii_census.assets import FROZEN_SPEC_REVISION
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


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _refuse_draws(*_args: object, **_kwargs: object) -> None:
    pytest.fail(
        "a confirmatory draw was taken after a provenance guard should have stopped the run"
    )


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

    monkeypatch.setattr(MODULE, "verify_frozen_spec", lambda: {"revision": FROZEN_SPEC_REVISION})
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
    assert manifest["design_revision"] == FROZEN_SPEC_REVISION
    assert set(manifest["artifacts"]) == set(MODULE.OUTPUT_NAMES)


def test_store_with_a_complete_foreign_seed_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A seed outside the preregistered list is a different design, not a resumable draw."""

    pairs = _pairs()
    _wire(monkeypatch, pairs, draws=2)
    MODULE.run(tmp_path, owner_approved=True, draws=2, batch_size=1)
    store = tmp_path / "draw_store"
    for name in MODULE.STORE_NAMES.values():
        path = store / name
        frame = pd.read_parquet(path)
        frame["seed"] = 1
        frame.to_parquet(path, index=False)

    with pytest.raises(CensusInputError, match="outside the preregistered list"):
        MODULE.run(tmp_path, owner_approved=True, draws=2)


def test_torn_batch_is_truncated_to_complete_seeds_and_rerun(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An interruption between the three writes must be recoverable, not fatal."""

    pairs = _pairs()
    _wire(monkeypatch, pairs, draws=3)
    MODULE.run(tmp_path, owner_approved=True, draws=3, batch_size=2)
    store = tmp_path / "draw_store"
    cells_path = store / MODULE.STORE_NAMES["placebo_cells"]
    cells = pd.read_parquet(cells_path)
    survivor, torn = sorted(set(cells["seed"].astype(int)))
    kept = pd.concat(
        [
            cells.loc[cells["seed"].astype(int).eq(survivor)],
            cells.loc[cells["seed"].astype(int).eq(torn)].iloc[:2],
        ],
        ignore_index=True,
    )
    kept.to_parquet(cells_path, index=False)

    loaded = MODULE._load_store(store)
    assert MODULE.complete_seeds(loaded) == {survivor}
    assert set(pd.read_parquet(store / MODULE.STORE_NAMES["placebo_final"])["seed"]) == {survivor}

    status = MODULE.run(tmp_path, owner_approved=True, draws=3)

    assert status["complete"] is True
    assert status["result"]["denominator"] == 3
    final = pd.read_parquet(tmp_path / MODULE.OUTPUT_NAMES["placebo_final"])
    assert final["seed"].tolist() == perm.preregistered_seeds(3)


def test_require_complete_store_rejects_a_short_frame() -> None:
    """Completion is checked across all three frames, not inferred from one."""

    seeds = [20260802, 20260803]
    frames = {
        "placebo_final": pd.DataFrame({"seed": seeds}),
        "placebo_cells": pd.DataFrame({"seed": [s for s in seeds for _ in range(6)]}),
        "mapping_digests": pd.DataFrame({"seed": seeds}),
    }
    MODULE.require_complete_store(frames, seeds)

    short = dict(frames)
    short["placebo_cells"] = frames["placebo_cells"].iloc[:-1]
    with pytest.raises(CensusInputError, match="preregistered seeds"):
        MODULE.require_complete_store(short, seeds)

    foreign = dict(frames)
    foreign["mapping_digests"] = pd.DataFrame({"seed": [20260802, 99]})
    with pytest.raises(CensusInputError, match="preregistered seeds"):
        MODULE.require_complete_store(foreign, seeds)


def test_run_is_bound_to_the_pinned_validation_design(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An edited protocol stops the run; the evaluated digest reaches the manifest."""

    pairs = _pairs()
    _wire(monkeypatch, pairs, draws=2)
    status = MODULE.run(tmp_path, owner_approved=True, draws=2)
    assert status["validation_design"]["path"] == MODULE.VALIDATION_DESIGN_PATH
    assert status["validation_design"]["sha256"] == MODULE.verify_validation_design()["sha256"]

    monkeypatch.setattr(
        MODULE,
        "verify_validation_design",
        lambda *_a, **_k: (_ for _ in ()).throw(
            CensusInputError("validation design digest mismatch")
        ),
    )
    with pytest.raises(CensusInputError, match="digest mismatch"):
        MODULE.run(tmp_path / "other", owner_approved=True, draws=2)


def test_verify_validation_design_detects_edited_bytes(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "studies/phase-iii-census").mkdir(parents=True)
    source = Path(MODULE.STUDY_MANIFEST_PATH)
    (root / MODULE.STUDY_MANIFEST_PATH).write_text(
        source.read_text(encoding="utf-8"), encoding="utf-8"
    )
    design = root / MODULE.VALIDATION_DESIGN_PATH
    design.write_text("edited protocol\n", encoding="utf-8")

    with pytest.raises(CensusInputError, match="digest mismatch"):
        MODULE.verify_validation_design(root)


def test_resume_under_changed_inputs_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Draws taken under different inputs must not be pooled into one result."""

    pairs = _pairs()
    _wire(monkeypatch, pairs, draws=3)
    MODULE.run(tmp_path, owner_approved=True, draws=3, batch_size=1)
    monkeypatch.setattr(
        MODULE, "_load_pairs", lambda: (pairs, {"pair_rows": len(pairs) + 1}, DATA_CUT)
    )
    monkeypatch.setattr(MODULE.perm, "run_permutation_draws", _refuse_draws)

    with pytest.raises(CensusInputError, match="does not match the one the draw store"):
        MODULE.run(tmp_path, owner_approved=True, draws=3)


def test_store_without_a_precondition_record_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pairs = _pairs()
    _wire(monkeypatch, pairs, draws=2)
    MODULE.run(tmp_path, owner_approved=True, draws=2, batch_size=1)
    (tmp_path / MODULE.PRECONDITION_NAME).unlink()
    monkeypatch.setattr(MODULE.perm, "run_permutation_draws", _refuse_draws)

    with pytest.raises(CensusInputError, match="no recorded precondition"):
        MODULE.run(tmp_path, owner_approved=True, draws=2)


def test_recorded_r15_constants_are_the_published_final_stage_values() -> None:
    """Guard the transcription of placebo-results-2026-08-03.md."""

    recorded = MODULE.R15_RECORDED
    assert recorded["assignment_mapping_sha256"] == (
        "c1c97a9c7f1c81105a17dc21888afb7493311605405272672608d950c9250119"
    )
    assert recorded["placebo_final"]["surviving_pairs"] == 546_242
    assert recorded["placebo_final"]["distinct_firms"] == 1_985
    assert recorded["placebo_final"]["distinct_contracts"] == 21_357
    assert recorded["placebo_final"]["total_obligated_dollars"] == 46_386_904_542.06
    assert recorded["actual_final"]["surviving_pairs"] == 727_292
    assert recorded["actual_final"]["distinct_firms"] == 2_369
    assert recorded["actual_final"]["distinct_contracts"] == 28_665
    assert recorded["actual_final"]["total_obligated_dollars"] == 55_080_851_466.46


def test_store_with_collapsed_assignment_identity_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """mapping_sha256 includes seed, so a planted collapsed null is only visible via identity."""

    pairs = _pairs()
    _wire(monkeypatch, pairs, draws=2)
    MODULE.run(tmp_path, owner_approved=True, draws=2)
    store = tmp_path / "draw_store"
    path = store / MODULE.STORE_NAMES["mapping_digests"]
    frame = pd.read_parquet(path)
    assert frame["mapping_sha256"].nunique() == 2
    assert frame["assignment_identity"].nunique() == 2
    planted = frame.copy()
    planted["assignment_identity"] = planted["assignment_identity"].iloc[0]
    planted.to_parquet(path, index=False)
    monkeypatch.setattr(MODULE.perm, "run_permutation_draws", _refuse_draws)

    with pytest.raises(CensusInputError, match="same assignment"):
        MODULE.run(tmp_path, owner_approved=True, draws=2)


def test_check_inputs_reports_each_phase_one_source_without_taking_a_draw(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The acceptance test for recovering the inputs: ready only on an exact match."""

    root = tmp_path / "repo"
    (root / "data").mkdir(parents=True)
    good = root / "data/good.parquet"
    good.write_bytes(b"exact recovered bytes")
    bad = root / "data/bad.parquet"
    bad.write_bytes(b"a later snapshot")
    monkeypatch.setattr(
        MODULE,
        "R15_RECORDED_INPUTS",
        {
            "data/good.parquet": {
                "rows": 1,
                "bytes": len(b"exact recovered bytes"),
                "sha256": hashlib.sha256(b"exact recovered bytes").hexdigest(),
            },
            "data/bad.parquet": {"rows": 1, "bytes": 99, "sha256": "0" * 64},
            "data/absent.parquet": {"rows": 1, "bytes": 1, "sha256": "1" * 64},
        },
    )

    report = MODULE.check_inputs(root)

    assert report["ready"] is False
    assert report["inputs"]["data/good.parquet"]["state"] == "match"
    assert report["inputs"]["data/bad.parquet"]["state"] == "digest_mismatch"
    assert report["inputs"]["data/absent.parquet"]["state"] == "missing"

    monkeypatch.setattr(
        MODULE,
        "R15_RECORDED_INPUTS",
        {
            "data/good.parquet": {
                "rows": 1,
                "bytes": good.stat().st_size,
                "sha256": _digest(good),
            },
            "data/bad.parquet": {"rows": 1, "bytes": bad.stat().st_size, "sha256": _digest(bad)},
        },
    )
    assert MODULE.check_inputs(root)["ready"] is True


def test_recorded_input_digests_are_the_published_materialization_values() -> None:
    """Guard the transcription of materialization-2026-02-06.md."""

    recorded = MODULE.R15_RECORDED_INPUTS
    contracts = recorded["data/transition/contracts_ingestion.parquet"]
    assert contracts["rows"] == 1_879_459
    assert contracts["bytes"] == 416_094_799
    assert contracts["sha256"] == (
        "c1518188ef674f3b301ef61be19f6db796a9389e4d03f1196280080f71803a98"
    )
    assert recorded["data/processed/phase_ii_awards.parquet"]["rows"] == 95_313
    assert recorded["data/processed/phase_iii_census_sbir_awards.parquet"]["rows"] == 219_500


def test_execution_code_digests_cover_the_per_draw_path() -> None:
    digests = MODULE.execution_code_digests()
    assert set(digests) == {"permutation_module", "runner_script"}
    assert digests["runner_script"] == _digest(
        MODULE.SCRIPT if hasattr(MODULE, "SCRIPT") else SCRIPT
    )
    assert digests["permutation_module"] == _digest(Path(perm.__file__))


def test_fingerprint_changes_when_the_execution_code_changes() -> None:
    """Revision 17: the code is part of what a resumed batch must agree on."""

    common = ({"revision": "x"}, {"path": "p", "sha256": "s"}, {"pair_rows": 3}, DATA_CUT)
    first = MODULE.run_fingerprint(*common, {"permutation_module": "a", "runner_script": "b"})
    edited = MODULE.run_fingerprint(*common, {"permutation_module": "a", "runner_script": "c"})
    assert first != edited
    assert (
        MODULE.run_fingerprint(*common, {"permutation_module": "a", "runner_script": "b"}) == first
    )


def test_resume_after_editing_the_per_draw_path_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pairs = _pairs()
    _wire(monkeypatch, pairs, draws=3)
    MODULE.run(tmp_path, owner_approved=True, draws=3, batch_size=1)
    monkeypatch.setattr(
        MODULE,
        "execution_code_digests",
        lambda: {"permutation_module": "edited", "runner_script": "edited"},
    )
    monkeypatch.setattr(MODULE.perm, "run_permutation_draws", _refuse_draws)

    with pytest.raises(CensusInputError, match="execution code"):
        MODULE.run(tmp_path, owner_approved=True, draws=3)


def test_manifest_reports_the_frozen_revision_rather_than_a_literal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A hardcoded revision string drifts silently at the next amendment."""

    pairs = _pairs()
    _wire(monkeypatch, pairs, draws=2)
    status = MODULE.run(tmp_path, owner_approved=True, draws=2)
    assert status["design_revision"] == FROZEN_SPEC_REVISION
    assert set(status["execution_code"]) == {"permutation_module", "runner_script"}
