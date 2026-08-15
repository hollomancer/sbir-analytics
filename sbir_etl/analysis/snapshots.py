"""Transport-neutral analysis snapshots.

Epistemic tier: pipelines. No HTTP surface (ADR-004).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sbir_etl.analysis.contracts import AnalysisRun
from sbir_etl.utils.path_utils import ensure_parent_dir


EPISTEMIC_TIER = "pipelines"


def snapshot_path(root: Path, profile_id: str, period: str) -> Path:
    return root / "analysis_snapshots" / profile_id / f"{period}.json"


def write_snapshot(run: AnalysisRun, path: Path) -> Path:
    ensure_parent_dir(path)
    path.write_text(
        json.dumps(run.to_snapshot_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    run.snapshot_path = path
    return path


def load_snapshot(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def compare_snapshots(
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    allow_methodology_change: bool = False,
) -> list[str]:
    """Return mismatch reasons. Empty list means the gate passed."""

    errors: list[str] = []
    for key in ("methodology_version", "taxonomy_version", "reporting_window", "source_sha256"):
        if left.get(key) != right.get(key):
            if key == "methodology_version" and allow_methodology_change:
                continue
            errors.append(f"{key}: {left.get(key)!r} != {right.get(key)!r}")
    return errors
