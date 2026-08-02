"""Versioned contracts for research studies and externally citable evidence."""

from enum import StrEnum
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvidenceStatus(StrEnum):
    """The review and reproducibility level reached by a study."""

    EXPLORATORY = "exploratory"
    REPRODUCIBLE = "reproducible"
    VALIDATED = "validated"
    CITABLE = "citable"
    RETIRED = "retired"


class FrozenArtifact(BaseModel):
    """A repository artifact whose exact bytes are part of the study contract."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ImplementationReference(BaseModel):
    """A checked-in implementation entry point supporting the study."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    symbol: str = Field(min_length=1)


class IdentityPolicy(BaseModel):
    """The entity-resolution contract used by the study."""

    model_config = ConfigDict(extra="forbid")

    strategy: str = Field(min_length=1)
    version: str = Field(min_length=1)
    negative_evidence_allowed: bool


class MaterializationGate(BaseModel):
    """Whether production outputs may currently be generated or quoted."""

    model_config = ConfigDict(extra="forbid")

    allowed: bool
    blockers: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_blocker_when_closed(self) -> "MaterializationGate":
        if not self.allowed and not self.blockers:
            raise ValueError("a closed materialization gate must name at least one blocker")
        return self


class StudyManifest(BaseModel):
    """The machine-checkable epistemic contract for one study."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    study_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    title: str = Field(min_length=1)
    evidence_status: EvidenceStatus
    research_questions: list[str] = Field(min_length=1)
    estimand: str = Field(min_length=1)
    frozen_artifacts: list[FrozenArtifact] = Field(min_length=1)
    implementation: list[ImplementationReference] = Field(min_length=1)
    identity_policy: IdentityPolicy
    materialization: MaterializationGate
    permitted_claims: list[str] = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)


def load_study_manifest(path: Path) -> StudyManifest:
    """Load and validate a study manifest from YAML."""

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"study manifest must contain a YAML mapping: {path}")
    return StudyManifest.model_validate(raw)


__all__ = [
    "EvidenceStatus",
    "FrozenArtifact",
    "IdentityPolicy",
    "ImplementationReference",
    "MaterializationGate",
    "StudyManifest",
    "load_study_manifest",
]
