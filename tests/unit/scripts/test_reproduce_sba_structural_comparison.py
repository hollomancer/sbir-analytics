"""Tests for the SBA structural-comparison public reproduction command."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.data import render_sba_structural_comparison as renderer
from scripts.data import reproduce_sba_structural_comparison as reproduction
from sbir_etl.quality.study_manifest import load_study_manifest
from sbir_etl.utils.data.file_io import file_sha256


ROOT = Path(__file__).resolve().parents[3]
STUDY_MANIFEST = ROOT / "studies/sba-annual-report-structural-comparison/study.yaml"
SUCCESSOR_MANIFEST = ROOT / "studies/sba-annual-report-structural-comparison-release/study.yaml"


def test_confirmatory_seal_verifies_archived_extractor_name() -> None:
    assert reproduction.verify_confirmatory_seal(ROOT, STUDY_MANIFEST) == 8


def test_confirmatory_seal_rejects_changed_component(tmp_path: Path) -> None:
    confirmatory = tmp_path / reproduction.CONFIRMATORY_DIRECTORY
    confirmatory.mkdir(parents=True)
    source = ROOT / reproduction.CONFIRMATORY_DIRECTORY
    for component in source.iterdir():
        if component.is_file():
            (confirmatory / component.name).write_bytes(component.read_bytes())
        elif component.is_dir():
            copied_directory = confirmatory / component.name
            copied_directory.mkdir()
            for dependency in component.iterdir():
                (copied_directory / dependency.name).write_bytes(dependency.read_bytes())
    (confirmatory / "validation-values.csv").write_text("changed\n", encoding="utf-8")

    with pytest.raises(reproduction.ReproductionFailure, match="hash differs"):
        reproduction.verify_confirmatory_seal(tmp_path, STUDY_MANIFEST)


def test_reproduce_rejects_an_unknown_study_before_touching_sources(tmp_path: Path) -> None:
    from scripts.data.render_sba_structural_comparison import PublicResultError

    with pytest.raises(PublicResultError, match="no renderer profile"):
        reproduction.reproduce(tmp_path, tmp_path, acquire=False, study_id="no-such-study")


def test_successor_make_wrapper_is_frozen_and_forwards_the_study_selector() -> None:
    manifest = load_study_manifest(SUCCESSOR_MANIFEST)
    frozen_hashes = {artifact.path: artifact.sha256 for artifact in manifest.frozen_artifacts}

    assert frozen_hashes["Makefile"] == file_sha256(ROOT / "Makefile")

    result = subprocess.run(
        [
            "make",
            "--no-print-directory",
            "-n",
            f"SBA_STUDY_ID={renderer.SUCCESSOR_STUDY_ID}",
            "reproduce-sba-structural",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert f"--study-id {renderer.SUCCESSOR_STUDY_ID}" in result.stdout
