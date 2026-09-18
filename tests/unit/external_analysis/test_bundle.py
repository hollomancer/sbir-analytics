from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sbir_analytics.external_analysis.bundle import freeze_study_bundle
from sbir_analytics.external_analysis.models import HashMismatchError, MissingInputError
from sbir_etl.utils.data.file_io import file_sha256 as sha256_file


def test_bundle_hashes_are_deterministic(repo: Path) -> None:
    dataset = repo / "data" / "derived" / "cohort.csv"
    created = datetime(2026, 9, 13, tzinfo=UTC)
    first = freeze_study_bundle(
        repository_root=repo,
        study_id="example-study",
        datasets=[dataset],
        output_dir=repo / "bundle-a",
        prompt=repo / "studies" / "example-study" / "external_prompt.md",
        git_commit="abc123",
        created_at=created,
    )
    second = freeze_study_bundle(
        repository_root=repo,
        study_id="example-study",
        datasets=[dataset],
        output_dir=repo / "bundle-b",
        prompt=repo / "studies" / "example-study" / "external_prompt.md",
        git_commit="abc123",
        created_at=created,
    )

    assert [item.sha256 for item in first.manifest.input_files] == [
        item.sha256 for item in second.manifest.input_files
    ]
    assert sha256_file(first.manifest_path) == sha256_file(second.manifest_path)


def test_bundle_records_study_provenance_and_is_not_citable(repo: Path) -> None:
    bundle = freeze_study_bundle(
        repository_root=repo,
        study_id="example-study",
        datasets=[repo / "data" / "derived" / "cohort.csv"],
        output_dir=repo / "bundle",
        git_commit="deadbeef",
        created_at=datetime(2026, 9, 13, tzinfo=UTC),
    )
    payload = json.loads(bundle.manifest_path.read_text(encoding="utf-8"))

    assert payload["study_id"] == "example-study"
    assert payload["git_commit"] == "deadbeef"
    assert payload["schema_version"] == 1
    assert payload["source_evidence_status"] == "reproducible"
    assert payload["evidence_status"] == "exploratory"
    assert payload["citable"] is False
    assert "api_key" not in payload
    roles = {item["role"] for item in payload["input_files"]}
    assert "dataset" in roles
    assert "constraints" in roles
    assert "research_question" in roles


def test_missing_dataset_fails_closed(repo: Path) -> None:
    with pytest.raises(MissingInputError, match="does not exist"):
        freeze_study_bundle(
            repository_root=repo,
            study_id="example-study",
            datasets=[repo / "missing.csv"],
            output_dir=repo / "bundle",
            git_commit="abc",
        )


def test_frozen_artifact_mismatch_fails_closed(repo: Path) -> None:
    design = repo / "specs" / "example.md"
    freeze_study_bundle(
        repository_root=repo,
        study_id="example-study",
        datasets=[design],
        output_dir=repo / "bundle-ok",
        git_commit="abc",
    )
    design.write_text("tampered\n", encoding="utf-8")
    with pytest.raises(HashMismatchError, match="frozen artifact hash mismatch"):
        freeze_study_bundle(
            repository_root=repo,
            study_id="example-study",
            datasets=[design],
            output_dir=repo / "bundle-bad",
            git_commit="abc",
        )
