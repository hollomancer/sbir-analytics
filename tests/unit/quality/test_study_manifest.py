import hashlib
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from sbir_etl.quality.study_manifest import (
    EvidenceStatus,
    ValidationDesign,
    load_study_manifest,
)
from scripts.ci.validate_study_manifests import validate_manifest_file


def _write(root: Path, relative: str, content: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _manifest(artifact_sha256: str) -> dict:
    return {
        "schema_version": 1,
        "study_id": "example-study",
        "title": "Example study",
        "evidence_status": "reproducible",
        "research_questions": ["B2"],
        "estimand": "Count observable examples.",
        "frozen_artifacts": [
            {"path": "specs/example.md", "sha256": artifact_sha256},
        ],
        "implementation": [
            {"path": "sbir_etl/example.py", "symbol": "run_study"},
        ],
        "identity_policy": {
            "strategy": "exact identifier",
            "version": "v1",
            "negative_evidence_allowed": False,
        },
        "materialization": {"allowed": False, "blockers": ["Validation is incomplete."]},
        "permitted_claims": ["The study can be reproduced."],
        "limitations": ["The result is not citable."],
    }


def test_load_study_manifest_parses_versioned_contract(tmp_path: Path) -> None:
    artifact_sha256 = "a" * 64
    path = _write(
        tmp_path,
        "example-study/study.yaml",
        yaml.safe_dump(_manifest(artifact_sha256)),
    )

    manifest = load_study_manifest(path)

    assert manifest.schema_version == 1
    assert manifest.evidence_status is EvidenceStatus.REPRODUCIBLE
    assert manifest.frozen_artifacts[0].sha256 == artifact_sha256


def test_closed_materialization_gate_requires_a_blocker(tmp_path: Path) -> None:
    raw = _manifest("a" * 64)
    raw["materialization"] = {"allowed": False, "blockers": []}
    path = _write(tmp_path, "example-study/study.yaml", yaml.safe_dump(raw))

    with pytest.raises(ValidationError, match="must name at least one blocker"):
        load_study_manifest(path)


def test_open_materialization_gate_rejects_stale_blockers(tmp_path: Path) -> None:
    raw = _manifest("a" * 64)
    raw["materialization"] = {"allowed": True, "blockers": ["Stale blocker."]}
    path = _write(tmp_path, "example-study/study.yaml", yaml.safe_dump(raw))

    with pytest.raises(ValidationError, match="open materialization gate cannot name blockers"):
        load_study_manifest(path)


def test_manifest_reference_validation_checks_hash_and_symbol(tmp_path: Path) -> None:
    artifact = _write(tmp_path, "specs/example.md", "frozen design\n")
    _write(tmp_path, "sbir_etl/example.py", "def run_study():\n    return None\n")
    raw = _manifest(hashlib.sha256(artifact.read_bytes()).hexdigest())
    manifest_path = _write(
        tmp_path,
        "studies/example-study/study.yaml",
        yaml.safe_dump(raw),
    )

    assert validate_manifest_file(manifest_path, repository_root=tmp_path) == []

    raw["frozen_artifacts"][0]["sha256"] = "0" * 64
    raw["implementation"][0]["symbol"] = "missing"
    manifest_path.write_text(yaml.safe_dump(raw), encoding="utf-8")

    errors = validate_manifest_file(manifest_path, repository_root=tmp_path)
    assert any("hash mismatch" in error for error in errors)
    assert any("symbol 'missing' is missing" in error for error in errors)


@pytest.mark.parametrize(
    "module_source",
    [
        "def run_study():\n    return None\n",
        "async def run_study():\n    return None\n",
        "class run_study:\n    pass\n",
        "from factory import build\n\nrun_study = build('census')\n",
        "from factory import Asset, build\n\nrun_study: Asset = build('census')\n",
        "import dagster\n\n@dagster.asset\ndef run_study():\n    return None\n",
    ],
    ids=["def", "async_def", "class", "assign", "annotated_assign", "decorated"],
)
def test_implementation_symbol_accepts_every_module_level_binding_form(
    tmp_path: Path, module_source: str
) -> None:
    """A factory-built or annotated asset is present, not a missing implementation."""

    artifact = _write(tmp_path, "specs/example.md", "frozen design\n")
    _write(tmp_path, "sbir_etl/example.py", module_source)
    raw = _manifest(hashlib.sha256(artifact.read_bytes()).hexdigest())
    manifest_path = _write(tmp_path, "studies/example-study/study.yaml", yaml.safe_dump(raw))

    assert validate_manifest_file(manifest_path, repository_root=tmp_path) == []


def test_implementation_symbol_still_rejects_names_bound_only_inside_a_function(
    tmp_path: Path,
) -> None:
    artifact = _write(tmp_path, "specs/example.md", "frozen design\n")
    _write(
        tmp_path, "sbir_etl/example.py", "def outer():\n    run_study = 1\n    return run_study\n"
    )
    raw = _manifest(hashlib.sha256(artifact.read_bytes()).hexdigest())
    manifest_path = _write(tmp_path, "studies/example-study/study.yaml", yaml.safe_dump(raw))

    errors = validate_manifest_file(manifest_path, repository_root=tmp_path)
    assert any("symbol 'run_study' is missing" in error for error in errors)


def test_repository_study_manifests_are_valid() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    manifests = sorted((repository_root / "studies").glob("*/study.yaml"))

    assert manifests
    assert all(
        validate_manifest_file(path, repository_root=repository_root) == [] for path in manifests
    )


def test_validation_design_requires_all_four_fields() -> None:
    """A threshold with no derivation is incomplete by construction."""
    complete = ValidationDesign(
        addressable_population="1,514 Form-D-missing pairs naming an acquirer",
        expected_yield="~2.3% of eligible pairs, from pilot 9/342 and confirmatory 13/503",
        decision_threshold="10 distinct strict medium/high pairs",
        threshold_derivation="95% CI lower bound clears 1.5% at n=362 when k>=10",
    )
    assert complete.decision_threshold == "10 distinct strict medium/high pairs"

    for missing in (
        "addressable_population",
        "expected_yield",
        "decision_threshold",
        "threshold_derivation",
    ):
        fields = {
            "addressable_population": "x",
            "expected_yield": "x",
            "decision_threshold": "x",
            "threshold_derivation": "x",
        }
        del fields[missing]
        with pytest.raises(ValidationError):
            ValidationDesign(**fields)


def test_validation_design_rejects_empty_strings() -> None:
    """An empty derivation is the same defect wearing a value."""
    with pytest.raises(ValidationError):
        ValidationDesign(
            addressable_population="x",
            expected_yield="x",
            decision_threshold="x",
            threshold_derivation="",
        )


@pytest.mark.parametrize(
    ("blank_field", "blank_value"),
    [
        ("addressable_population", "   "),
        ("expected_yield", "  "),
        ("decision_threshold", " "),
        ("threshold_derivation", "\t"),
    ],
)
def test_validation_design_rejects_whitespace_only_strings(
    blank_field: str, blank_value: str
) -> None:
    """A whitespace-only value satisfies min_length=1 but states nothing.

    A manifest claiming ``evidence_status: validated`` must not be able to pass
    this gate by filling a field with spaces or a tab.
    """
    fields = {
        "addressable_population": "x",
        "expected_yield": "x",
        "decision_threshold": "x",
        "threshold_derivation": "x",
    }
    fields[blank_field] = blank_value

    with pytest.raises(ValidationError, match="must not be blank"):
        ValidationDesign(**fields)


VALIDATION_DESIGN = {
    "addressable_population": "Every row in the frozen cohort.",
    "expected_yield": "At least 95% source coverage.",
    "decision_threshold": "All reconciliations pass and coverage is at least 95%.",
    "threshold_derivation": "The frozen design identifies 95% as the minimum useful coverage.",
}


@pytest.mark.parametrize("status", [EvidenceStatus.VALIDATED, EvidenceStatus.CITABLE])
def test_promoted_manifest_requires_validation_design(
    tmp_path: Path, status: EvidenceStatus
) -> None:
    raw = _manifest("a" * 64)
    raw["evidence_status"] = status.value
    path = _write(tmp_path, "example-study/study.yaml", yaml.safe_dump(raw))

    with pytest.raises(ValidationError, match="requires a validation_design block"):
        load_study_manifest(path)

    errors = validate_manifest_file(path, repository_root=tmp_path)
    assert any("requires a validation_design block" in error for error in errors)


@pytest.mark.parametrize("status", [EvidenceStatus.VALIDATED, EvidenceStatus.CITABLE])
def test_promoted_manifest_loads_with_validation_design(
    tmp_path: Path, status: EvidenceStatus
) -> None:
    raw = _manifest("a" * 64)
    raw["evidence_status"] = status.value
    raw["validation_design"] = VALIDATION_DESIGN
    path = _write(tmp_path, "example-study/study.yaml", yaml.safe_dump(raw))

    manifest = load_study_manifest(path)

    assert manifest.evidence_status is status
    assert manifest.validation_design is not None
