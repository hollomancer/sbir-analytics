"""Provider-neutral types for frozen study bundles and imported runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


EPISTEMIC_TIER = "exploratory"

BUNDLE_SCHEMA_VERSION = 1


class ExternalAnalysisError(Exception):
    """Fail-closed error for external analysis."""


class ExternalUploadNotAuthorized(ExternalAnalysisError):
    """Raised when a network upload is attempted without an explicit opt-in."""


class MissingApiKey(ExternalAnalysisError):
    """Raised when the provider API key is absent from the environment."""


class EdisonSupportNotInstalled(ExternalAnalysisError):
    """Raised when the optional Edison extra has not been installed."""


class UnsafeUploadError(ExternalAnalysisError):
    """Raised when a path is not eligible for external upload."""


class HashMismatchError(ExternalAnalysisError):
    """Raised when a copied or frozen file's SHA-256 does not match."""


class MissingInputError(ExternalAnalysisError):
    """Raised when a required study, dataset, or prompt file is missing."""


class ProviderFailure(ExternalAnalysisError):
    """Raised when the provider reports a failed or unusable task."""


class InvalidProviderResponse(ExternalAnalysisError):
    """Raised when a provider response cannot be interpreted."""


class PromotionAttemptError(ExternalAnalysisError):
    """Raised when external output tries to claim validated or citable status."""


class FileRole(StrEnum):
    """Role of one file inside a frozen study bundle."""

    DATASET = "dataset"
    MANIFEST = "manifest"
    DATA_DICTIONARY = "data_dictionary"
    RESEARCH_QUESTION = "research_question"
    CONSTRAINTS = "constraints"
    PROMPT = "prompt"


class BundleFile(BaseModel):
    """One file recorded in a frozen study bundle."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    source_path: str | None = None
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)
    role: FileRole


class StudyBundleManifest(BaseModel):
    """Provider-neutral record of what was frozen for an external run.

    ``evidence_status`` and ``citable`` describe *this bundle's outputs*, not
    the source study contract. They are fixed at exploratory / not citable.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = BUNDLE_SCHEMA_VERSION
    study_id: str = Field(min_length=1)
    git_commit: str = Field(min_length=1)
    created_at: datetime
    source_evidence_status: str = Field(min_length=1)
    evidence_status: Literal["exploratory"] = "exploratory"
    citable: Literal[False] = False
    input_files: list[BundleFile] = Field(min_length=1)

    @model_validator(mode="after")
    def refuse_self_promotion(self) -> StudyBundleManifest:
        if self.evidence_status != "exploratory" or self.citable is not False:
            raise ValueError("external analysis output cannot promote itself")
        return self


@dataclass(frozen=True)
class StudyBundle:
    """A directory of frozen files plus its bundle manifest."""

    directory: Path
    manifest: StudyBundleManifest

    @property
    def manifest_path(self) -> Path:
        return self.directory / "manifest.json"


class RunStatus(StrEnum):
    """Lifecycle of one external-analysis run."""

    BUNDLED = "bundled"
    SUBMITTED = "submitted"
    SUCCESS = "success"
    FAILED = "failed"
    INCOMPLETE = "incomplete"


class ExternalAnalysisRun(BaseModel):
    """Provenance for one imported provider run.

    Rerunning a provider is not expected to reproduce analytical conclusions.
    This record is enough to know what was submitted, not to treat the
    result as deterministic.
    """

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1)
    executor: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    trajectory_id: str | None = None
    git_commit: str = Field(min_length=1)
    input_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    submitted_at: datetime | None = None
    completed_at: datetime | None = None
    evidence_status: Literal["exploratory"] = "exploratory"
    citable: Literal[False] = False
    status: RunStatus
    output_dir: str = Field(min_length=1)
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def refuse_self_promotion(self) -> ExternalAnalysisRun:
        if self.evidence_status != "exploratory" or self.citable is not False:
            raise ValueError("external analysis output cannot promote itself")
        return self


class ProviderJob(BaseModel):
    """Handle returned by ``submit`` and consumed by ``status`` / ``fetch_results``."""

    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(min_length=1)
    storage_id: str | None = None


class ProviderArtifact(BaseModel):
    """One file fetched from a provider."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    content: bytes
