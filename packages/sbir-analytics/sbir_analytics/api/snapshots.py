"""Persisted analytical snapshot contracts and read-only filesystem repository."""

from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError


class AnalysisKind(StrEnum):
    CET_PORTFOLIO = "cet_portfolio"
    TRANSITION_RATE = "transition_rate"
    FOLLOW_ON_MULTIPLIER = "follow_on_multiplier"


class SourceReference(BaseModel):
    name: str
    url: str
    version: str | None = None
    record_count: int | None = None
    access_method: str | None = None


class SnapshotMetadata(BaseModel):
    tool_name: str
    tool_version: str
    schema_version: str = "1"
    pipeline_run_id: str | None = None
    data_sources: list[SourceReference] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AnalyticsSnapshot(BaseModel):
    analysis_kind: AnalysisKind
    period: str = Field(pattern=r"^\d{4}(-Q[1-4])?$")
    as_of: str
    metadata: SnapshotMetadata
    result: dict[str, Any] | list[dict[str, Any]]


class SnapshotSummary(BaseModel):
    analysis_kind: AnalysisKind
    period: str
    as_of: str
    tool_name: str
    tool_version: str
    schema_version: str


class SnapshotNotFoundError(LookupError):
    pass


class IncompatibleSnapshotsError(ValueError):
    pass


class SnapshotStoreError(RuntimeError):
    pass


class FileSnapshotRepository:
    """Read validated snapshots from ``<root>/<kind>/<period>.json``."""

    def __init__(self, root: Path):
        self.root = root

    def _path(self, kind: AnalysisKind, period: str) -> Path:
        return self.root / kind.value / f"{period}.json"

    def get(self, kind: AnalysisKind, period: str) -> AnalyticsSnapshot:
        path = self._path(kind, period)
        if not path.is_file():
            raise SnapshotNotFoundError(f"No {kind.value} snapshot for {period}")
        try:
            return AnalyticsSnapshot.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, ValueError) as exc:
            raise SnapshotStoreError(f"Snapshot could not be read: {path.name}") from exc

    def list(self, kind: AnalysisKind | None = None) -> list[SnapshotSummary]:
        kinds = [kind] if kind else list(AnalysisKind)
        summaries: list[SnapshotSummary] = []
        for selected in kinds:
            directory = self.root / selected.value
            if not directory.is_dir():
                continue
            for path in directory.glob("*.json"):
                snapshot = self.get(selected, path.stem)
                summaries.append(
                    SnapshotSummary(
                        analysis_kind=snapshot.analysis_kind,
                        period=snapshot.period,
                        as_of=snapshot.as_of,
                        tool_name=snapshot.metadata.tool_name,
                        tool_version=snapshot.metadata.tool_version,
                        schema_version=snapshot.metadata.schema_version,
                    )
                )
        return sorted(summaries, key=lambda item: (item.analysis_kind, item.period))


def compare_snapshots(
    baseline: AnalyticsSnapshot, comparison: AnalyticsSnapshot
) -> dict[str, Any]:
    """Compare compatible snapshots without inventing domain-specific formulas."""

    if baseline.analysis_kind != comparison.analysis_kind:
        raise IncompatibleSnapshotsError("Analysis kinds differ")
    if baseline.metadata.schema_version != comparison.metadata.schema_version:
        raise IncompatibleSnapshotsError("Schema versions differ")
    if baseline.metadata.tool_name != comparison.metadata.tool_name:
        raise IncompatibleSnapshotsError("Methodologies differ")
    if baseline.metadata.tool_version != comparison.metadata.tool_version:
        raise IncompatibleSnapshotsError("Methodology versions differ")
    if not isinstance(baseline.result, dict) or not isinstance(comparison.result, dict):
        raise IncompatibleSnapshotsError("Comparison requires object-shaped results")

    deltas: dict[str, float] = {}
    for key in baseline.result.keys() & comparison.result.keys():
        before = baseline.result[key]
        after = comparison.result[key]
        if isinstance(before, (int, float)) and isinstance(after, (int, float)):
            deltas[key] = after - before
    return {
        "analysis_kind": baseline.analysis_kind,
        "baseline_period": baseline.period,
        "comparison_period": comparison.period,
        "baseline": baseline.result,
        "comparison": comparison.result,
        "numeric_deltas": deltas,
    }
