import hashlib
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from sbir_etl.quality.study_manifest import EvidenceStatus, load_study_manifest
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


def test_repository_study_manifests_are_valid() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    manifests = sorted((repository_root / "studies").glob("*/study.yaml"))

    assert manifests
    assert all(
        validate_manifest_file(path, repository_root=repository_root) == [] for path in manifests
    )
