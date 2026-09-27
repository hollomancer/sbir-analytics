"""The count stage pins its inputs against the manifest it is given."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from scripts.data import run_sba_structural_comparison as count_stage
from sbir_etl.exceptions import ConfigurationError


ROOT = Path(__file__).resolve().parents[3]
OLD_STUDY = "studies/sba-annual-report-structural-comparison"


def _copy_repository_pins(destination: Path) -> None:
    """Copy only the repository files the count stage pins, not the raw sources."""
    for relative in (
        f"{OLD_STUDY}/study.yaml",
        f"{OLD_STUDY}/source-manifest.json",
        f"{OLD_STUDY}/validation-design-v1.md",
        f"{OLD_STUDY}/validation-population-v1.csv",
        "studies/sba-annual-report-tables/award-export-2026-09-17.meta.json",
        "studies/sba-annual-report-tables/data/awards_by_state_fy20.csv",
        "studies/sba-annual-report-tables/data/awards_by_state_fy21.csv",
        "studies/sba-annual-report-tables/data/awards_by_state_fy22.csv",
        count_stage.PRODUCER.as_posix(),
    ):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)


def test_build_production_inputs_defaults_to_the_released_manifest(tmp_path: Path) -> None:
    _copy_repository_pins(tmp_path)

    inputs = count_stage.build_production_inputs(tmp_path, tmp_path)

    assert inputs.implementation.reference == count_stage.PRODUCER.as_posix()


def test_build_production_inputs_pins_against_the_given_manifest(tmp_path: Path) -> None:
    _copy_repository_pins(tmp_path)
    successor = tmp_path / "studies/successor/study.yaml"
    successor.parent.mkdir(parents=True)
    raw = yaml.safe_load((tmp_path / OLD_STUDY / "study.yaml").read_text(encoding="utf-8"))
    raw["study_id"] = "successor"
    sentinel_sha256 = "f" * 64
    producer_reference = count_stage.PRODUCER.as_posix()
    producer_pin = next(
        artifact for artifact in raw["frozen_artifacts"] if artifact["path"] == producer_reference
    )
    producer_pin["sha256"] = sentinel_sha256
    successor.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    inputs = count_stage.build_production_inputs(tmp_path, tmp_path, study_manifest_path=successor)

    assert inputs.implementation.reference == count_stage.PRODUCER.as_posix()
    assert inputs.implementation.sha256 == sentinel_sha256


def test_build_production_inputs_rejects_a_missing_manifest(tmp_path: Path) -> None:
    _copy_repository_pins(tmp_path)

    with pytest.raises(ConfigurationError):
        count_stage.build_production_inputs(
            tmp_path, tmp_path, study_manifest_path=tmp_path / "studies/none/study.yaml"
        )
