"""Build a provider-neutral frozen study bundle from a study contract."""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from sbir_etl.quality.study_manifest import StudyManifest, load_study_manifest
from sbir_etl.utils.data.file_io import file_sha256

from .constraints import DEFAULT_CONSTRAINTS
from .models import (
    BUNDLE_SCHEMA_VERSION,
    BundleFile,
    FileRole,
    HashMismatchError,
    MissingInputError,
    StudyBundle,
    StudyBundleManifest,
)
from .safety import assert_safe_path_component, assert_safe_source_path


EPISTEMIC_TIER = "exploratory"


def current_git_commit(repository_root: Path) -> str:
    """Return HEAD for ``repository_root``, failing if git is unavailable."""

    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise MissingInputError(
            f"cannot determine git commit in {repository_root}: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def study_manifest_path(repository_root: Path, study_id: str) -> Path:
    # study_id reaches this path and the default output path; a separator or
    # dot segment in it could read a YAML outside studies/ or write outside
    # the promised study tree.
    assert_safe_path_component(study_id, label="study_id")
    return repository_root / "studies" / study_id / "study.yaml"


def load_study(repository_root: Path, study_id: str) -> StudyManifest:
    path = study_manifest_path(repository_root, study_id)
    if not path.is_file():
        raise MissingInputError(f"study manifest does not exist: {path}")
    return load_study_manifest(path)


def _repo_relative(path: Path, repository_root: Path) -> str:
    try:
        return path.resolve().relative_to(repository_root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _copy_file(source: Path, destination: Path) -> tuple[str, int]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    digest = file_sha256(destination)
    source_digest = file_sha256(source)
    if digest != source_digest:
        raise HashMismatchError(
            f"copied {source} to {destination} but hashes diverged: {source_digest} vs {digest}"
        )
    return digest, destination.stat().st_size


def _verify_frozen_artifact(
    source: Path,
    *,
    repository_root: Path,
    study: StudyManifest,
) -> None:
    relative = _repo_relative(source, repository_root)
    actual = file_sha256(source)
    for artifact in study.frozen_artifacts:
        if artifact.path == relative and artifact.sha256 != actual:
            raise HashMismatchError(
                f"frozen artifact hash mismatch for {relative}: "
                f"expected {artifact.sha256}, found {actual}"
            )


def _write_text(path: Path, content: str) -> tuple[str, int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return file_sha256(path), path.stat().st_size


def _research_question_markdown(study: StudyManifest) -> str:
    questions = "\n".join(f"- {item}" for item in study.research_questions)
    claims = "\n".join(f"- {item}" for item in study.permitted_claims)
    limitations = "\n".join(f"- {item}" for item in study.limitations)
    return (
        f"# {study.title}\n\n"
        f"Study ID: `{study.study_id}`\n\n"
        f"Source study `evidence_status`: `{study.evidence_status.value}`. "
        "This bundle and any provider output are exploratory and not citable. "
        "They do not inherit the study's permitted claims.\n\n"
        "## Estimand\n\n"
        f"{study.estimand.strip()}\n\n"
        "## Research questions\n\n"
        f"{questions}\n\n"
        "## Identity policy\n\n"
        f"- Strategy: {study.identity_policy.strategy}\n"
        f"- Version: {study.identity_policy.version}\n"
        "- Negative evidence allowed: "
        f"{str(study.identity_policy.negative_evidence_allowed).lower()}\n\n"
        "## Study-contract permitted claims (not authorized for this run)\n\n"
        f"{claims}\n\n"
        "## Limitations\n\n"
        f"{limitations}\n"
    )


def freeze_study_bundle(
    *,
    repository_root: Path,
    study_id: str,
    datasets: list[Path],
    output_dir: Path,
    prompt: Path | None = None,
    data_dictionary: Path | None = None,
    constraints: Path | None = None,
    git_commit: str | None = None,
    created_at: datetime | None = None,
) -> StudyBundle:
    """Copy declared inputs into ``output_dir`` and write ``manifest.json``.

    Only the files named here enter the bundle. The repository root, env
    files, credentials, and Neo4j stores are rejected before copy.
    """

    study = load_study(repository_root, study_id)
    if not datasets:
        raise MissingInputError("at least one dataset is required")

    output_dir.mkdir(parents=True, exist_ok=True)
    files: list[BundleFile] = []
    commit = git_commit or current_git_commit(repository_root)
    timestamp = created_at or datetime.now(UTC)

    for dataset in datasets:
        source = dataset if dataset.is_absolute() else repository_root / dataset
        if not source.is_file():
            raise MissingInputError(f"dataset does not exist: {source}")
        assert_safe_source_path(source, repository_root=repository_root)
        _verify_frozen_artifact(source, repository_root=repository_root, study=study)
        bundle_path = Path("data") / source.name
        digest, size = _copy_file(source, output_dir / bundle_path)
        files.append(
            BundleFile(
                path=bundle_path.as_posix(),
                source_path=_repo_relative(source, repository_root),
                sha256=digest,
                size_bytes=size,
                role=FileRole.DATASET,
            )
        )

    question_path = output_dir / "research_question.md"
    digest, size = _write_text(question_path, _research_question_markdown(study))
    files.append(
        BundleFile(
            path="research_question.md",
            source_path=None,
            sha256=digest,
            size_bytes=size,
            role=FileRole.RESEARCH_QUESTION,
        )
    )

    if constraints is not None:
        source = constraints if constraints.is_absolute() else repository_root / constraints
        if not source.is_file():
            raise MissingInputError(f"constraints file does not exist: {source}")
        assert_safe_source_path(source, repository_root=repository_root)
        digest, size = _copy_file(source, output_dir / "constraints.md")
        source_path = _repo_relative(source, repository_root)
    else:
        digest, size = _write_text(output_dir / "constraints.md", DEFAULT_CONSTRAINTS)
        source_path = None
    files.append(
        BundleFile(
            path="constraints.md",
            source_path=source_path,
            sha256=digest,
            size_bytes=size,
            role=FileRole.CONSTRAINTS,
        )
    )

    if prompt is not None:
        source = prompt if prompt.is_absolute() else repository_root / prompt
        if not source.is_file():
            raise MissingInputError(f"prompt file does not exist: {source}")
        assert_safe_source_path(source, repository_root=repository_root)
        digest, size = _copy_file(source, output_dir / "prompt.md")
        files.append(
            BundleFile(
                path="prompt.md",
                source_path=_repo_relative(source, repository_root),
                sha256=digest,
                size_bytes=size,
                role=FileRole.PROMPT,
            )
        )

    if data_dictionary is not None:
        source = (
            data_dictionary if data_dictionary.is_absolute() else repository_root / data_dictionary
        )
        if not source.is_file():
            raise MissingInputError(f"data dictionary does not exist: {source}")
        assert_safe_source_path(source, repository_root=repository_root)
        digest, size = _copy_file(source, output_dir / "data_dictionary.md")
        files.append(
            BundleFile(
                path="data_dictionary.md",
                source_path=_repo_relative(source, repository_root),
                sha256=digest,
                size_bytes=size,
                role=FileRole.DATA_DICTIONARY,
            )
        )

    files.sort(key=lambda item: item.path)
    manifest = StudyBundleManifest(
        schema_version=BUNDLE_SCHEMA_VERSION,
        study_id=study.study_id,
        git_commit=commit,
        created_at=timestamp,
        source_evidence_status=study.evidence_status.value,
        evidence_status="exploratory",
        citable=False,
        input_files=files,
    )
    payload = manifest.model_dump(mode="json")
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return StudyBundle(directory=output_dir, manifest=manifest)
