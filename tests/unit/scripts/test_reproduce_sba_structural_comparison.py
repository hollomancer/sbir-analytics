"""Tests for the SBA structural-comparison public reproduction command."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.data import reproduce_sba_structural_comparison as reproduction


ROOT = Path(__file__).resolve().parents[3]
STUDY_MANIFEST = ROOT / "studies/sba-annual-report-structural-comparison/study.yaml"


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
