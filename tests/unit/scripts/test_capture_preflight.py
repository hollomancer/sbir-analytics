"""A promotion-intended capture must be reconstructable from git afterwards.

Both gates here exist because of one run. The held-out 1501-2500 cut captured
948 of 1000 pairs with uncommitted producer changes, and its design was pinned
about ten hours after the replay it was supposed to have preregistered. Every
run-time check passed at the time, because neither condition was checked.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts" / "data"))

from run_ma_discovery_sample import CutProtocol, dirty_tree_errors  # noqa: E402


def _protocol(intended_rank: str) -> CutProtocol:
    return CutProtocol(
        protocol_id="test-cut",
        protocol_md="studies/example/protocol.md",
        skip_pairs=0,
        max_candidates=10,
        queries_per_pair=1,
        stop_when="dated_confirm",
        strict_recall=True,
        fail_on_gate=True,
        search_backend_capture="brave",
        search_backend_rerun="snippets",
        confirm="llm",
        events_path="data/events.jsonl",
        events_sha256="0" * 64,
        output_dir="data/out",
        intended_rank=intended_rank,
        recall_floor=10,
        precision_fp_cap=0.25,
        cost_per_pair_cap_usd=0.10,
    )


@pytest.mark.parametrize("rank", ["reproducible", "validated", "citable"])
def test_dirty_tree_refuses_a_promotion_intended_capture(rank: str) -> None:
    errors = dirty_tree_errors(_protocol(rank), dirty=True)

    assert errors
    assert "uncommitted changes" in errors[0]
    assert rank in errors[0]


def test_dirty_tree_is_allowed_for_an_exploratory_capture() -> None:
    """Exploratory work does not have to be reconstructable, so it is not gated."""
    assert dirty_tree_errors(_protocol("exploratory"), dirty=True) == []


@pytest.mark.parametrize("rank", ["exploratory", "validated"])
def test_a_clean_tree_never_blocks(rank: str) -> None:
    assert dirty_tree_errors(_protocol(rank), dirty=False) == []


def test_unknown_git_state_refuses_a_promotion_intended_capture() -> None:
    """Silence is not cleanliness; an unusable git is not evidence of a clean tree."""
    errors = dirty_tree_errors(_protocol("validated"), dirty=None)

    assert errors
    assert "cannot determine" in errors[0]


def test_unknown_git_state_is_allowed_for_exploratory() -> None:
    assert dirty_tree_errors(_protocol("exploratory"), dirty=None) == []


def test_no_protocol_means_no_gate() -> None:
    """A run without --protocol makes no rank claim and is not gated."""
    assert dirty_tree_errors(None, dirty=True) == []


def _write_study(tmp_path: Path, *, design_sha: str, recorded_sha: str | None) -> Path:
    """Build a study whose run manifest records the protocol bytes it read."""
    study_dir = tmp_path / "studies" / "example"
    study_dir.mkdir(parents=True)
    design = study_dir / "design.md"
    design.write_text("frozen design\n", encoding="utf-8")

    run: dict[str, object] = {"study_id": "example"}
    if recorded_sha is not None:
        run["protocol_sha256"] = recorded_sha
    run_manifest = study_dir / "run-manifest.json"
    run_manifest.write_text(json.dumps(run), encoding="utf-8")

    import hashlib

    def sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    manifest = {
        "schema_version": 1,
        "study_id": "example",
        "title": "Example",
        "evidence_status": "exploratory",
        "research_questions": ["B2"],
        "estimand": "Count examples.",
        "frozen_artifacts": [
            {"path": "studies/example/design.md", "sha256": sha(design)},
            {"path": "studies/example/run-manifest.json", "sha256": sha(run_manifest)},
        ],
        "implementation": [{"path": "sbir_etl/__init__.py", "symbol": "__version__"}],
        "identity_policy": {
            "strategy": "exact",
            "version": "v1",
            "negative_evidence_allowed": False,
        },
        "materialization": {"allowed": False, "blockers": ["Incomplete."]},
        "permitted_claims": ["Reproducible."],
        "limitations": ["Not citable."],
        "validation_design": {
            "addressable_population": "x",
            "expected_yield": "y",
            "decision_threshold": "z",
            "threshold_derivation": "w",
            "threshold_basis": "proportion",
            "threshold_value": 0.5,
        },
        "validation_result": {
            "design_path": "studies/example/design.md",
            "design_sha256": design_sha,
            "evaluated_on": "2026-09-09",
            "metric": "recall",
            "numerator": 4,
            "denominator": 10,
            "interval_low": 0.168,
            "interval_high": 0.687,
            "interval_method": "Wilson 95%",
            "threshold_met": False,
            "confirmatory": False,
        },
    }
    import yaml

    path = study_dir / "study.yaml"
    path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    return path


def test_design_changed_after_the_run_is_detected(tmp_path: Path) -> None:
    """The exact failure: a design pinned after the run it preregistered."""
    from scripts.ci.validate_study_manifests import validate_manifest_file

    path = _write_study(tmp_path, design_sha="a" * 64, recorded_sha="b" * 64)

    errors = validate_manifest_file(path, repository_root=tmp_path)

    assert any("changed after the run" in e for e in errors), errors


def test_matching_design_and_recorded_protocol_passes(tmp_path: Path) -> None:
    from scripts.ci.validate_study_manifests import validate_manifest_file

    path = _write_study(tmp_path, design_sha="a" * 64, recorded_sha="a" * 64)

    assert not [
        e
        for e in validate_manifest_file(path, repository_root=tmp_path)
        if "changed after the run" in e
    ]


def test_a_run_manifest_without_a_recorded_protocol_is_not_flagged(tmp_path: Path) -> None:
    """Older manifests predate the field; absence is not a mismatch."""
    from scripts.ci.validate_study_manifests import validate_manifest_file

    path = _write_study(tmp_path, design_sha="a" * 64, recorded_sha=None)

    assert not [
        e
        for e in validate_manifest_file(path, repository_root=tmp_path)
        if "changed after the run" in e
    ]
