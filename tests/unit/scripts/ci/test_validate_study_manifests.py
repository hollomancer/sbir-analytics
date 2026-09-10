"""Tests for the study-manifest CI validator."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
_spec = importlib.util.spec_from_file_location(
    "validate_study_manifests", REPO_ROOT / "scripts" / "ci" / "validate_study_manifests.py"
)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

from sbir_etl.quality.study_manifest import (  # noqa: E402
    EvidenceStatus,
    StudyManifest,
    ValidationDesign,
)


def _manifest(status: EvidenceStatus, *, design: ValidationDesign | None) -> StudyManifest:
    return StudyManifest(
        schema_version=1,
        study_id="example-study",
        title="Example",
        evidence_status=status,
        research_questions=["F2"],
        estimand="An example estimand.",
        frozen_artifacts=[{"path": "studies/example/design.md", "sha256": "0" * 64}],
        implementation=[{"path": "sbir_etl/quality/study_manifest.py", "symbol": "StudyManifest"}],
        identity_policy={
            "strategy": "RECIPIENT_V1",
            "version": "recipient-v1",
            "negative_evidence_allowed": False,
        },
        materialization={"allowed": True, "blockers": []},
        permitted_claims=["Nothing numeric."],
        limitations=["Exploratory."],
        validation_design=design,
    )


DESIGN = ValidationDesign(
    addressable_population="1,514 pairs",
    expected_yield="~2.3%",
    decision_threshold="10 pairs",
    threshold_derivation="CI lower bound clears 1.5% at k>=10",
)


@pytest.mark.parametrize("status", [EvidenceStatus.VALIDATED, EvidenceStatus.CITABLE])
def test_validated_and_citable_require_a_validation_design(status: EvidenceStatus) -> None:
    """A study claiming its design passed must say what the design was."""
    errors = _mod.validation_design_errors(_manifest(status, design=None))
    assert any("validation_design" in e for e in errors)


@pytest.mark.parametrize("status", [EvidenceStatus.VALIDATED, EvidenceStatus.CITABLE])
def test_validated_and_citable_pass_when_present(status: EvidenceStatus) -> None:
    assert _mod.validation_design_errors(_manifest(status, design=DESIGN)) == []


@pytest.mark.parametrize(
    "status",
    [EvidenceStatus.EXPLORATORY, EvidenceStatus.REPRODUCIBLE, EvidenceStatus.RETIRED],
)
def test_lower_statuses_do_not_require_it(status: EvidenceStatus) -> None:
    """A census has no pass/fail threshold and must not be forced to invent one."""
    assert _mod.validation_design_errors(_manifest(status, design=None)) == []
