"""Write provider artifacts under the study's exploratory tree."""

from __future__ import annotations

import json
from pathlib import Path

from sbir_etl.quality.study_manifest import sha256_file

from .models import ExternalAnalysisRun, PromotionAttemptError, ProviderArtifact


EPISTEMIC_TIER = "exploratory"

INCOMPLETE_MARKER = "INCOMPLETE"


def default_output_dir(
    repository_root: Path,
    *,
    study_id: str,
    provider: str,
    run_id: str,
) -> Path:
    return repository_root / "studies" / study_id / "exploratory" / "external" / provider / run_id


def artifact_relative_path(name: str, *, used: set[str]) -> Path:
    """Map a provider filename onto the exploratory run layout."""

    lowered = Path(name).name.lower()
    if lowered.endswith(".ipynb"):
        candidate = "analysis.ipynb"
    elif lowered.endswith(".md") and "report" in lowered:
        candidate = "report.md"
    elif lowered.endswith((".png", ".jpg", ".jpeg", ".svg", ".pdf")):
        candidate = f"figures/{Path(name).name}"
    else:
        candidate = f"artifacts/{Path(name).name}"
    if candidate in used:
        stem = Path(candidate)
        candidate = f"{stem.stem}-{len(used)}{stem.suffix}"
        if "/" in str(stem):
            candidate = f"{stem.parent}/{Path(candidate).name}"
    used.add(candidate)
    return Path(candidate)


def write_run_record(output_dir: Path, run: ExternalAnalysisRun) -> Path:
    if run.evidence_status != "exploratory" or run.citable is not False:
        raise PromotionAttemptError(
            "external analysis results cannot be written as validated or citable"
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "run.json"
    payload = run.model_dump(mode="json")
    if payload.get("citable") is not False or payload.get("evidence_status") != "exploratory":
        raise PromotionAttemptError(
            "external analysis results cannot be written as validated or citable"
        )
    lowered_keys = {key.lower() for key in payload}
    if "api_key" in lowered_keys or "edison_api_key" in lowered_keys:
        raise PromotionAttemptError("refusing to persist an API key in run metadata")
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_artifacts(output_dir: Path, artifacts: list[ProviderArtifact]) -> list[Path]:
    used: set[str] = set()
    written: list[Path] = []
    for artifact in artifacts:
        relative = artifact_relative_path(artifact.name, used=used)
        path = output_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(artifact.content)
        written.append(path)
    return written


def mark_incomplete(output_dir: Path, reason: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / INCOMPLETE_MARKER
    path.write_text(reason.rstrip() + "\n", encoding="utf-8")
    return path


def copy_bundle_manifest(bundle_manifest: Path, output_dir: Path) -> Path:
    destination = output_dir / "input_manifest.json"
    destination.write_bytes(bundle_manifest.read_bytes())
    if sha256_file(destination) != sha256_file(bundle_manifest):
        raise PromotionAttemptError("input_manifest.json hash diverged while copying")
    return destination
