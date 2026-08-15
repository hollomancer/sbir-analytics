"""Analysis runner shell. Strategies are injected by callers.

Epistemic tier: pipelines. Do not import exploratory census or cohort engines
from this module.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sbir_etl.analysis.contracts import AnalysisRun, AnalysisSpec
from sbir_etl.analysis.snapshots import compare_snapshots, load_snapshot, write_snapshot


EPISTEMIC_TIER = "pipelines"

Strategy = Callable[[AnalysisSpec], Mapping[str, Any]]


def _sha256_file(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def materialize_analysis(
    spec: AnalysisSpec,
    *,
    strategy: Strategy,
    snapshot_root: Path | None = None,
    period: str = "latest",
    frozen_snapshot: Path | None = None,
) -> AnalysisRun:
    """Run an injected strategy and pin hashes on the resulting ``AnalysisRun``."""

    config_sha = _sha256_file(spec.config_path)
    source_sha = spec.corpus.manifest.sha256 if spec.corpus.manifest else None
    if source_sha is None:
        source_sha = _sha256_file(spec.corpus.source_path)

    if frozen_snapshot is not None and frozen_snapshot.is_file():
        expected = load_snapshot(frozen_snapshot)
        observed = {
            "methodology_version": spec.methodology_version,
            "taxonomy_version": spec.taxonomy_version,
            "reporting_window": spec.window.label,
            "source_sha256": source_sha,
        }
        mismatches = compare_snapshots(
            expected,
            observed,
            allow_methodology_change=spec.allow_methodology_change,
        )
        if mismatches:
            raise ValueError("refusing silent calibration drift: " + "; ".join(mismatches))

    started = datetime.now(UTC)
    payload = dict(strategy(spec))
    finished = datetime.now(UTC)
    output_dir = Path(payload["output_dir"]) if payload.get("output_dir") else None
    metrics = {k: v for k, v in payload.items() if k != "output_dir"}
    run = AnalysisRun(
        spec=spec,
        started_at=started,
        finished_at=finished,
        taxonomy_version=spec.taxonomy_version,
        methodology_version=spec.methodology_version,
        source_sha256=source_sha,
        config_sha256=config_sha,
        metrics=metrics,
        output_dir=output_dir,
    )
    if snapshot_root is not None:
        write_snapshot(run, snapshot_root / spec.profile_id / f"{period}.json")
    return run
