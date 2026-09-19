"""Adapter from the SBA annual-report study to generic preflight facts."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from sbir_etl.config.yaml_io import read_yaml_mapping
from sbir_etl.quality.study_manifest import load_study_manifest

from scripts.ci.validate_study_manifests import validate_manifest_file

from .models import (
    ClaimContract,
    EvidenceItem,
    EvidenceLabel,
    EvidenceReference,
    PreflightInput,
    ReadinessFacts,
    RequiredSourceOutcome,
    SourceOutcome,
)


EPISTEMIC_TIER = "exploratory"
STUDY_PATH = "studies/sba-annual-report-tables/study.yaml"
SOURCES_PATH = "studies/sba-annual-report-tables/sources.yaml"
CLAIMS_PATH = "specs/jev-preflight/annual-report-claims.yaml"


class AnnualReportClaimSet(BaseModel):
    """Versioned claim set for the first study application."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    claims: list[ClaimContract]


def _reference(path: str, field: str) -> list[EvidenceReference]:
    return [EvidenceReference(path=path, field=field)]


def load_annual_report_claims(repository_root: Path) -> dict[str, ClaimContract]:
    """Load the two versioned annual-report claim contracts."""

    raw = read_yaml_mapping(repository_root / CLAIMS_PATH, description="preflight claim set")
    claim_set = AnnualReportClaimSet.model_validate(raw)
    claims = {claim.case_id: claim for claim in claim_set.claims}
    if len(claims) != len(claim_set.claims):
        raise ValueError("duplicate annual-report preflight case_id")
    return claims


def build_annual_report_preflight(repository_root: Path, case_id: str) -> PreflightInput:
    """Build deterministic facts from the current annual-report study contracts."""

    claims = load_annual_report_claims(repository_root)
    try:
        claim = claims[case_id]
    except KeyError as exc:
        raise ValueError(f"unknown annual-report preflight case: {case_id}") from exc

    manifest_path = repository_root / STUDY_PATH
    manifest = load_study_manifest(manifest_path)
    if claim.narrower_claim and claim.narrower_claim not in manifest.permitted_claims:
        raise ValueError(
            f"narrower claim for {case_id!r} is not an exact permitted_claim in {STUDY_PATH}"
        )
    sources = read_yaml_mapping(repository_root / SOURCES_PATH, description="study sources")
    reference_errors = validate_manifest_file(manifest_path, repository_root=repository_root)
    inputs_pinned = not reference_errors
    definitions_complete = sources.get("gate_satisfied") is True

    if claim.required_source_outcome is RequiredSourceOutcome.PUBLISHED_SAMPLE_REPRODUCTION:
        impossible = (
            sources.get("published_sample_verdict") == "blocked"
            and sources.get("exact_vintage_reproduction") == "impossible_no_surviving_vintage"
        )
        source_outcome = SourceOutcome.IMPOSSIBLE if impossible else SourceOutcome.REMEDIABLE
        source_detail = (
            "No report-era SBIR.gov export survives; the study fixes the published-sample "
            "verdict at blocked."
            if impossible
            else "The published-sample source outcome is not established as impossible."
        )
        source_label = EvidenceLabel.BLOCKED if impossible else EvidenceLabel.UNSUPPORTED
        source_refs = [
            EvidenceReference(path=SOURCES_PATH, field="published_sample_verdict"),
            EvidenceReference(path=SOURCES_PATH, field="exact_vintage_reproduction"),
            EvidenceReference(path=STUDY_PATH, field="materialization.blockers[0]"),
        ]
    else:
        available = (
            sources.get("published_sample_method") == "vintage_tolerant_structural_check"
            and definitions_complete
        )
        source_outcome = SourceOutcome.AVAILABLE if available else SourceOutcome.REMEDIABLE
        source_detail = (
            "The study declares a current-snapshot structural check and accounts for all required "
            "definitions."
            if available
            else "The structural-check source contract is incomplete."
        )
        source_label = EvidenceLabel.OBSERVED if available else EvidenceLabel.UNSUPPORTED
        source_refs = [
            EvidenceReference(path=SOURCES_PATH, field="published_sample_method"),
            EvidenceReference(path=SOURCES_PATH, field="gate_satisfied"),
        ]

    evidence = [
        EvidenceItem(
            fact_id="source_outcome",
            label=source_label,
            value=source_outcome.value,
            detail=source_detail,
            references=source_refs,
        ),
        EvidenceItem(
            fact_id="inputs_pinned",
            label=EvidenceLabel.OBSERVED if inputs_pinned else EvidenceLabel.UNSUPPORTED,
            value=inputs_pinned,
            detail=(
                "Every frozen artifact path and hash validates."
                if inputs_pinned
                else f"Study manifest reference errors: {'; '.join(reference_errors)}"
            ),
            references=_reference(STUDY_PATH, "frozen_artifacts"),
        ),
        EvidenceItem(
            fact_id="definitions_complete",
            label=EvidenceLabel.OBSERVED if definitions_complete else EvidenceLabel.UNSUPPORTED,
            value=definitions_complete,
            detail=(
                "The capture gate records all nine required definitions as accounted for."
                if definitions_complete
                else "The capture gate does not account for every required definition."
            ),
            references=_reference(SOURCES_PATH, "gate_satisfied"),
        ),
        EvidenceItem(
            fact_id="validation_complete",
            label=EvidenceLabel.OBSERVED,
            value=not claim.validation_required,
            detail=(
                "This claim contract does not require a validation promotion."
                if not claim.validation_required
                else "The claim contract requires validation."
            ),
            references=_reference(CLAIMS_PATH, f"claims[{case_id}].validation_required"),
        ),
        EvidenceItem(
            fact_id="current_evidence_status",
            label=EvidenceLabel.OBSERVED,
            value=manifest.evidence_status.value,
            detail=f"The study declares evidence_status: {manifest.evidence_status.value}.",
            references=_reference(STUDY_PATH, "evidence_status"),
        ),
    ]
    return PreflightInput(
        claim=claim,
        facts=ReadinessFacts(
            source_outcome=source_outcome,
            inputs_pinned=inputs_pinned,
            definitions_complete=definitions_complete,
            validation_complete=not claim.validation_required,
            current_evidence_status=manifest.evidence_status,
        ),
        evidence=evidence,
    )
