"""Shared analysis contracts for the modular analysis platform.

Epistemic tier: pipelines.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any


EPISTEMIC_TIER = "pipelines"

UNAVAILABLE_CHANNEL_LABEL = "Not computed — not zero"


class AnalysisKind(StrEnum):
    """Registered analysis kinds. Add values here, not one member per profile."""

    TECH_CENSUS = "tech_census"
    TRANSITION_COHORT = "transition_cohort"


class EvidenceChannelStage(StrEnum):
    COMPUTED = "computed"
    UNAVAILABLE = "unavailable"
    NOT_APPLICABLE = "not_applicable"


def unavailable_channel_label(
    stage: EvidenceChannelStage = EvidenceChannelStage.UNAVAILABLE,
) -> str:
    """Render an unavailable channel without implying a zero rate."""

    if stage is EvidenceChannelStage.UNAVAILABLE:
        return UNAVAILABLE_CHANNEL_LABEL
    return stage.value


@dataclass(frozen=True)
class SourceManifest:
    path: Path
    sha256: str | None = None


@dataclass(frozen=True)
class AwardCorpus:
    source_path: Path
    identity_profile: str = "sbir-source-v2"
    manifest: SourceManifest | None = None

    @classmethod
    def from_sbir_csv(cls, path: Path, *, sha256: str | None = None) -> AwardCorpus:
        return cls(
            source_path=path,
            manifest=SourceManifest(path=path, sha256=sha256),
        )


@dataclass(frozen=True)
class ReportingWindow:
    start: str | None = None
    end: str | None = None
    label: str = "unbounded"


@dataclass(frozen=True)
class ProfileEntry:
    profile_id: str
    analysis_kind: AnalysisKind
    config_path: Path
    taxonomy_version: str
    methodology_version: str
    dagster_asset: bool = False


@dataclass(frozen=True)
class AnalysisSpec:
    profile_id: str
    analysis_kind: AnalysisKind
    config_path: Path
    taxonomy_version: str
    methodology_version: str
    corpus: AwardCorpus
    window: ReportingWindow = field(default_factory=ReportingWindow)
    allow_methodology_change: bool = False


@dataclass
class AnalysisRun:
    spec: AnalysisSpec
    started_at: datetime
    finished_at: datetime
    taxonomy_version: str
    methodology_version: str
    source_sha256: str | None
    config_sha256: str | None
    metrics: dict[str, Any]
    output_dir: Path | None = None
    snapshot_path: Path | None = None

    def to_snapshot_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.spec.profile_id,
            "analysis_kind": self.spec.analysis_kind.value,
            "taxonomy_version": self.taxonomy_version,
            "methodology_version": self.methodology_version,
            "reporting_window": self.spec.window.label,
            "source_sha256": self.source_sha256,
            "config_sha256": self.config_sha256,
            "metrics": self.metrics,
            "started_at": self.started_at.astimezone(UTC).isoformat(),
            "finished_at": self.finished_at.astimezone(UTC).isoformat(),
        }
