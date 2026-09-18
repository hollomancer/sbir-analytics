from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from sbir_analytics.external_analysis.base import run_external_analysis
from sbir_analytics.external_analysis.edison import EdisonProvider
from sbir_analytics.external_analysis.models import ExternalAnalysisRun
from sbir_analytics.external_analysis.results import default_output_dir, write_run_record
from tests.unit.external_analysis.conftest import FakeEdisonClient


def test_returned_artifacts_land_under_exploratory_path(repo: Path) -> None:
    client = FakeEdisonClient()
    run = run_external_analysis(
        repository_root=repo,
        provider=EdisonProvider(client=client, poll_interval=0, sleep=lambda _: None),
        study_id="example-study",
        datasets=[repo / "data" / "derived" / "cohort.csv"],
        allow_external_upload=True,
        git_commit="abc",
    )
    expected = default_output_dir(
        repo, study_id="example-study", provider="edison", run_id="traj-1"
    )
    assert Path(run.output_dir) == expected
    assert (expected / "analysis.ipynb").is_file()
    assert (expected / "figures" / "figure.png").is_file()
    assert (expected / "run.json").is_file()
    assert (expected / "input_manifest.json").is_file()
    assert (expected / "prompt.md").is_file()
    payload = json.loads((expected / "run.json").read_text(encoding="utf-8"))
    assert payload["evidence_status"] == "exploratory"
    assert payload["citable"] is False
    assert payload["provider"] == "edison"
    assert payload["executor"] == "analysis"
    assert payload["trajectory_id"] == "traj-1"


def test_external_results_cannot_be_written_as_citable(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        ExternalAnalysisRun(
            provider="edison",
            executor="analysis",
            run_id="x",
            git_commit="abc",
            input_manifest_sha256="a" * 64,
            evidence_status="validated",  # type: ignore[arg-type]
            citable=False,
            status="success",
            output_dir=str(tmp_path),
        )
    with pytest.raises(ValidationError):
        ExternalAnalysisRun(
            provider="edison",
            executor="analysis",
            run_id="x",
            git_commit="abc",
            input_manifest_sha256="a" * 64,
            citable=True,  # type: ignore[arg-type]
            status="success",
            output_dir=str(tmp_path),
        )


def test_write_run_record_rejects_api_key_field(tmp_path: Path) -> None:
    run = ExternalAnalysisRun(
        provider="edison",
        executor="analysis",
        run_id="x",
        git_commit="abc",
        input_manifest_sha256="a" * 64,
        status="success",
        output_dir=str(tmp_path),
    )
    path = write_run_record(tmp_path, run)
    assert "api_key" not in path.read_text(encoding="utf-8")
