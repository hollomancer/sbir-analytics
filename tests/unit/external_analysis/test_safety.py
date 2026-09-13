from __future__ import annotations

from pathlib import Path

import pytest

from sbir_analytics.external_analysis.base import run_external_analysis
from sbir_analytics.external_analysis.models import ExternalUploadNotAuthorized, UnsafeUploadError
from sbir_analytics.external_analysis.safety import (
    assert_safe_source_path,
    assert_upload_authorized,
)


def test_upload_authorization_is_required(repo: Path) -> None:
    with pytest.raises(ExternalUploadNotAuthorized, match="--allow-external-upload"):
        run_external_analysis(
            repository_root=repo,
            provider="edison",
            study_id="example-study",
            datasets=[repo / "data" / "derived" / "cohort.csv"],
            allow_external_upload=False,
            git_commit="abc",
        )


def test_bundle_only_does_not_require_upload_flag(repo: Path) -> None:
    run = run_external_analysis(
        repository_root=repo,
        provider="edison",
        study_id="example-study",
        datasets=[repo / "data" / "derived" / "cohort.csv"],
        allow_external_upload=False,
        bundle_only=True,
        git_commit="abc",
        output_dir=repo / "out",
    )
    assert run.status.value == "bundled"
    assert run.citable is False
    assert (repo / "out" / "bundle" / "manifest.json").is_file()


def test_env_file_is_rejected(repo: Path) -> None:
    env = repo / ".env"
    env.write_text("EDISON_API_KEY=secret\n", encoding="utf-8")
    with pytest.raises(UnsafeUploadError, match="restricted file"):
        assert_safe_source_path(env, repository_root=repo)


def test_repository_root_is_rejected(repo: Path) -> None:
    with pytest.raises(UnsafeUploadError, match="repository root"):
        assert_safe_source_path(repo, repository_root=repo)


def test_neo4j_data_is_rejected(repo: Path) -> None:
    store = repo / "neo4j" / "data" / "databases" / "neo4j" / "store"
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text("db", encoding="utf-8")
    with pytest.raises(UnsafeUploadError, match="neo4j/data"):
        assert_safe_source_path(store, repository_root=repo)


def test_assert_upload_authorized_fail_closed() -> None:
    with pytest.raises(ExternalUploadNotAuthorized):
        assert_upload_authorized(False)
    assert_upload_authorized(True)
