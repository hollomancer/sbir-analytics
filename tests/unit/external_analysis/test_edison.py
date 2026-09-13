from __future__ import annotations

import sys
from pathlib import Path

import pytest

from sbir_analytics.external_analysis.base import run_external_analysis
from sbir_analytics.external_analysis.edison import (
    EdisonProvider,
    analysis_environment_config,
    data_entry_uri,
)
from sbir_analytics.external_analysis.models import (
    EdisonSupportNotInstalled,
    MissingApiKey,
    ProviderFailure,
)
from tests.unit.external_analysis.conftest import FakeEdisonClient


def test_data_entry_uri_is_provider_neutral() -> None:
    assert data_entry_uri("storage-1") == "data_entry:storage-1"
    assert analysis_environment_config("storage-1") == {
        "language": "PYTHON",
        "data_storage_uris": ["data_entry:storage-1"],
    }


def test_edison_submit_uses_data_entry_uri(repo: Path) -> None:
    client = FakeEdisonClient()
    run = run_external_analysis(
        repository_root=repo,
        provider=EdisonProvider(client=client, poll_interval=0, sleep=lambda _: None),
        study_id="example-study",
        datasets=[repo / "data" / "derived" / "cohort.csv"],
        allow_external_upload=True,
        git_commit="abc",
        output_dir=repo / "out",
    )
    assert client.uploads
    assert client.uploads[0]["as_collection"] is True
    task = client.tasks[0]
    assert task["runtime_config"]["environment_config"]["data_storage_uris"] == [
        "data_entry:storage-1"
    ]
    assert task["runtime_config"]["max_steps"] == 30
    assert run.trajectory_id == "traj-1"
    assert run.citable is False
    assert run.evidence_status == "exploratory"


def test_provider_failure_is_surfaced(repo: Path) -> None:
    client = FakeEdisonClient(fail=True)
    with pytest.raises(ProviderFailure, match="failed"):
        run_external_analysis(
            repository_root=repo,
            provider=EdisonProvider(client=client, poll_interval=0, sleep=lambda _: None),
            study_id="example-study",
            datasets=[repo / "data" / "derived" / "cohort.csv"],
            allow_external_upload=True,
            git_commit="abc",
            output_dir=repo / "out-fail",
        )
    assert (repo / "out-fail" / "INCOMPLETE").is_file()
    run_payload = (repo / "out-fail" / "run.json").read_text(encoding="utf-8")
    assert '"status": "incomplete"' in run_payload
    assert "api_key" not in run_payload


def test_missing_api_key_fails_closed(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EDISON_API_KEY", raising=False)
    provider = EdisonProvider(poll_interval=0, sleep=lambda _: None)
    monkeypatch.setattr(
        "sbir_analytics.external_analysis.edison._import_edison",
        lambda: (object, object, object, object),
    )
    with pytest.raises(MissingApiKey, match="EDISON_API_KEY"):
        run_external_analysis(
            repository_root=repo,
            provider=provider,
            study_id="example-study",
            datasets=[repo / "data" / "derived" / "cohort.csv"],
            allow_external_upload=True,
            git_commit="abc",
            output_dir=repo / "out-key",
        )


def test_missing_optional_dependency_has_useful_error() -> None:
    if "edison_client" in sys.modules:
        pytest.skip("edison-client is installed in this environment")
    from sbir_analytics.external_analysis.edison import _import_edison

    with pytest.raises(EdisonSupportNotInstalled, match="Edison support is not installed"):
        _import_edison()


def test_api_key_is_not_persisted(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDISON_API_KEY", "super-secret-key")
    client = FakeEdisonClient()
    run = run_external_analysis(
        repository_root=repo,
        provider=EdisonProvider(client=client, poll_interval=0, sleep=lambda _: None),
        study_id="example-study",
        datasets=[repo / "data" / "derived" / "cohort.csv"],
        allow_external_upload=True,
        git_commit="abc",
        output_dir=repo / "out-secret",
    )
    written = (Path(run.output_dir) / "run.json").read_text(encoding="utf-8")
    manifest = (Path(run.output_dir) / "input_manifest.json").read_text(encoding="utf-8")
    assert "super-secret-key" not in written
    assert "super-secret-key" not in manifest
    assert "EDISON_API_KEY" not in written
