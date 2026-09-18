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


def test_path_traversal_in_study_id_is_rejected(repo: Path) -> None:
    """A study_id carrying separators or dot segments must fail before any
    path under studies/ is constructed, not read a YAML elsewhere."""

    from sbir_analytics.external_analysis.bundle import study_manifest_path
    from sbir_analytics.external_analysis.results import default_output_dir

    for bad in ("../outside", "a/b", "..", ".hidden", "a\\b"):
        with pytest.raises(UnsafeUploadError, match="safe path component"):
            study_manifest_path(repo, bad)
        with pytest.raises(UnsafeUploadError, match="safe path component"):
            default_output_dir(repo, study_id=bad, provider="edison", run_id="r1")

    with pytest.raises(UnsafeUploadError, match="run_id"):
        default_output_dir(repo, study_id="example-study", provider="edison", run_id="../../escape")


def test_api_key_filenames_are_rejected(repo: Path) -> None:
    from sbir_analytics.external_analysis.safety import forbidden_reason

    for name in ("api_key.txt", "EDISON_API_KEY.txt", "client-secret.json", "my.key", ".netrc"):
        target = repo / name
        target.write_text("x", encoding="utf-8")
        assert forbidden_reason(target, repository_root=repo) is not None, name


def _frozen_bundle(repo: Path):
    from sbir_analytics.external_analysis.bundle import freeze_study_bundle

    return freeze_study_bundle(
        repository_root=repo,
        study_id="example-study",
        datasets=[repo / "data" / "derived" / "cohort.csv"],
        output_dir=repo / "out" / "bundle",
        git_commit="abc",
    )


def test_policy_rejects_content_changed_after_freezing(repo: Path) -> None:
    from sbir_analytics.external_analysis.safety import evaluate_upload_policy

    bundle = _frozen_bundle(repo)
    # Same size, different bytes: the digest check must catch what the size
    # check cannot.
    target = bundle.directory / "data" / "cohort.csv"
    original = target.read_text(encoding="utf-8")
    target.write_text(original[:-2] + "X\n", encoding="utf-8")
    with pytest.raises(UnsafeUploadError, match="content changed after freezing"):
        evaluate_upload_policy(bundle, repository_root=repo)


def test_policy_rejects_unlisted_files_in_the_bundle(repo: Path) -> None:
    """The provider uploads the whole directory, so a file added after
    freezing — a stray credential, an .env — must fail the policy even
    though the manifest never listed it."""

    from sbir_analytics.external_analysis.safety import evaluate_upload_policy

    bundle = _frozen_bundle(repo)
    (bundle.directory / "stray.txt").write_text("not in the manifest\n", encoding="utf-8")
    with pytest.raises(UnsafeUploadError, match="not in the manifest"):
        evaluate_upload_policy(bundle, repository_root=repo)


def test_policy_rejects_symlinked_manifest_entries(repo: Path) -> None:
    from sbir_analytics.external_analysis.safety import evaluate_upload_policy

    bundle = _frozen_bundle(repo)
    target = bundle.directory / "data" / "cohort.csv"
    outside = repo / "outside.csv"
    outside.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
    target.unlink()
    target.symlink_to(outside)
    with pytest.raises(UnsafeUploadError, match="symlink"):
        evaluate_upload_policy(bundle, repository_root=repo)


def test_staging_run_ids_are_unique_within_a_second(repo: Path) -> None:
    runs = [
        run_external_analysis(
            repository_root=repo,
            provider="edison",
            study_id="example-study",
            datasets=[repo / "data" / "derived" / "cohort.csv"],
            allow_external_upload=False,
            bundle_only=True,
            git_commit="abc",
        )
        for _ in range(2)
    ]
    assert runs[0].run_id != runs[1].run_id
    assert runs[0].output_dir != runs[1].output_dir
