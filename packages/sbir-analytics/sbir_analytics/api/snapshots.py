"""Persisted analytical snapshot contracts and read-only filesystem repository."""

import math
import os
import re
import tempfile
from dataclasses import asdict, is_dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field, ValidationError

from sbir_analytics.tools.base import ToolResult


_PERIOD_PATTERN = re.compile(r"^\d{4}(-Q[1-4])?$")


class AnalysisKind(StrEnum):
    CET_PORTFOLIO = "cet_portfolio"
    TRANSITION_RATE = "transition_rate"
    FOLLOW_ON_MULTIPLIER = "follow_on_multiplier"
    # One kind per tech-census area (same granularity as the kinds above --
    # each represents one specific, periodically-refreshed analysis, not a
    # parameterized family). Add one line here per new
    # config/tech_census/<area>.yaml as areas are added.
    TECH_CENSUS_DRONE_MANUFACTURING = "tech_census_drone_manufacturing"


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
        self.root = root.resolve()

    def _directory(self, kind: AnalysisKind) -> Path:
        directories = {
            AnalysisKind.CET_PORTFOLIO: "cet_portfolio",
            AnalysisKind.TRANSITION_RATE: "transition_rate",
            AnalysisKind.FOLLOW_ON_MULTIPLIER: "follow_on_multiplier",
            AnalysisKind.TECH_CENSUS_DRONE_MANUFACTURING: "tech_census_drone_manufacturing",
        }
        return self.root / directories[kind]

    @staticmethod
    def _validate_period(period: str) -> None:
        if not _PERIOD_PATTERN.fullmatch(period):
            raise SnapshotStoreError("Invalid snapshot period")

    def _find_path(self, kind: AnalysisKind, period: str) -> Path | None:
        """Find a snapshot without using request data as a path expression."""

        self._validate_period(period)
        directory = self._directory(kind)
        if not directory.is_dir():
            return None
        expected_name = f"{period}.json"
        try:
            for candidate in directory.iterdir():
                if candidate.name != expected_name:
                    continue
                resolved = candidate.resolve(strict=True)
                resolved.relative_to(self.root)
                return resolved
        except (OSError, RuntimeError, ValueError) as exc:
            raise SnapshotStoreError("Snapshot path is not safe") from exc
        return None

    def get(self, kind: AnalysisKind, period: str) -> AnalyticsSnapshot:
        path = self._find_path(kind, period)
        if path is None or not path.is_file():
            raise SnapshotNotFoundError(f"No {kind.value} snapshot for {period}")
        try:
            return AnalyticsSnapshot.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, ValueError) as exc:
            raise SnapshotStoreError(f"Snapshot could not be read: {path.name}") from exc

    def list(self, kind: AnalysisKind | None = None) -> list[SnapshotSummary]:
        kinds = [kind] if kind else list(AnalysisKind)
        summaries: list[SnapshotSummary] = []
        for selected in kinds:
            directory = self._directory(selected)
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

    def readiness(self) -> str:
        """Report whether the configured read store is safe and accessible."""

        try:
            if self.root.exists() and not self.root.is_dir():
                raise SnapshotStoreError("Snapshot root is not a directory")
            return "ready" if self.root.exists() else "empty"
        except OSError as exc:
            raise SnapshotStoreError("Snapshot store is unavailable") from exc


def _json_safe(value: Any) -> Any:
    """Normalize analytical results, including pandas/numpy values, for JSON snapshots."""

    if isinstance(value, pd.DataFrame):
        return [_json_safe(record) for record in value.to_dict(orient="records")]
    if isinstance(value, (pd.Series, pd.Index, np.ndarray)):
        return [_json_safe(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return _json_safe(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return value


def snapshot_from_tool_result(
    analysis_kind: AnalysisKind,
    period: str,
    result: ToolResult,
    *,
    pipeline_run_id: str | None = None,
    as_of: datetime | None = None,
) -> AnalyticsSnapshot:
    """Convert an existing analytics ``ToolResult`` into the snapshot contract."""

    metadata = result.metadata
    return snapshot_from_result(
        analysis_kind,
        period,
        result.data,
        metadata=SnapshotMetadata(
            tool_name=metadata.tool_name,
            tool_version=metadata.tool_version,
            pipeline_run_id=pipeline_run_id,
            data_sources=[
                SourceReference.model_validate(source.to_dict()) for source in metadata.data_sources
            ],
            warnings=list(metadata.warnings),
        ),
        as_of=as_of,
    )


def snapshot_from_result(
    analysis_kind: AnalysisKind,
    period: str,
    result: Any,
    *,
    metadata: SnapshotMetadata,
    as_of: datetime | None = None,
) -> AnalyticsSnapshot:
    """Build a snapshot for deterministic results that do not use ``ToolResult``."""

    return AnalyticsSnapshot(
        analysis_kind=analysis_kind,
        period=period,
        as_of=(as_of or datetime.now(UTC)).isoformat(),
        metadata=metadata,
        result=_json_safe(result),
    )


def write_snapshot(
    root: Path,
    snapshot: AnalyticsSnapshot,
    *,
    overwrite: bool = False,
) -> Path:
    """Atomically persist a validated snapshot for the read-only API to consume."""

    repository = FileSnapshotRepository(root)
    repository._validate_period(snapshot.period)
    directory = repository._directory(snapshot.analysis_kind)
    directory.mkdir(parents=True, exist_ok=True)
    directory = directory.resolve(strict=True)
    try:
        directory.relative_to(repository.root)
    except ValueError as exc:
        raise SnapshotStoreError("Snapshot destination is not safe") from exc

    target = directory / f"{snapshot.period}.json"
    if target.exists() and not overwrite:
        raise SnapshotStoreError("Snapshot already exists")

    payload = snapshot.model_dump_json(indent=2)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=directory,
            prefix=".snapshot-",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        os.replace(temporary, target)
    except OSError as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise SnapshotStoreError("Snapshot could not be written") from exc
    return target


def compare_snapshots(baseline: AnalyticsSnapshot, comparison: AnalyticsSnapshot) -> dict[str, Any]:
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
