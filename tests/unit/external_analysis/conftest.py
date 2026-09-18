"""Shared fixtures for external-analysis unit tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from sbir_etl.utils.data.file_io import file_sha256 as sha256_file


def write_study(root: Path, study_id: str = "example-study") -> Path:
    """Write a loadable study contract under ``root/studies/<id>/``."""

    design = root / "specs" / "example.md"
    design.parent.mkdir(parents=True, exist_ok=True)
    design.write_text("frozen design\n", encoding="utf-8")
    implementation = root / "sbir_etl" / "example.py"
    implementation.parent.mkdir(parents=True, exist_ok=True)
    implementation.write_text("def run_study():\n    return None\n", encoding="utf-8")
    study_dir = root / "studies" / study_id
    study_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "study_id": study_id,
        "title": "Example study",
        "evidence_status": "reproducible",
        "research_questions": ["B2"],
        "estimand": "Count observable examples.",
        "frozen_artifacts": [
            {"path": "specs/example.md", "sha256": sha256_file(design)},
        ],
        "implementation": [
            {"path": "sbir_etl/example.py", "symbol": "run_study"},
        ],
        "identity_policy": {
            "strategy": "exact identifier",
            "version": "v1",
            "negative_evidence_allowed": False,
        },
        "materialization": {"allowed": False, "blockers": ["Validation is incomplete."]},
        "permitted_claims": ["The study can be reproduced."],
        "limitations": ["The result is not citable."],
    }
    path = study_dir / "study.yaml"
    path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    return path


class FakeEdisonClient:
    """In-memory stand-in for ``EdisonClient``. No network."""

    def __init__(self, *, fail: bool = False, status: str = "success") -> None:
        self.fail = fail
        self._status = status
        self.uploads: list[dict] = []
        self.tasks: list[object] = []
        self.fetches: list[str] = []

    async def astore_file_content(self, **kwargs):
        self.uploads.append(kwargs)
        return SimpleNamespace(data_storage=SimpleNamespace(id="storage-1"))

    def create_task(self, task):
        self.tasks.append(task)
        return "traj-1"

    def get_task(self, trajectory_id, verbose=False, lite=False):
        if self.fail:
            return SimpleNamespace(status="failed", environment_frame={})
        if not verbose:
            return SimpleNamespace(status=self._status)
        return SimpleNamespace(
            status=self._status,
            environment_frame={
                "state": {
                    "state": {"answer": "13 of 19 held-out pairs; exploratory only."},
                    "info": {
                        "output_data": [
                            {"entry_id": "out-nb", "name": "analysis.ipynb"},
                            {"entry_id": "out-fig", "name": "figure.png"},
                        ]
                    },
                }
            },
        )

    async def afetch_data_from_storage(self, data_storage_id):
        self.fetches.append(data_storage_id)
        if data_storage_id == "out-nb":
            return SimpleNamespace(content=b'{"cells": []}')
        return SimpleNamespace(content=b"png-bytes")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    write_study(tmp_path)
    dataset = tmp_path / "data" / "derived" / "cohort.csv"
    dataset.parent.mkdir(parents=True, exist_ok=True)
    dataset.write_text("firm_id,phase\nA,III\n", encoding="utf-8")
    prompt = tmp_path / "studies" / "example-study" / "external_prompt.md"
    prompt.write_text("Describe the cohort. Do not claim causation.\n", encoding="utf-8")
    return tmp_path
