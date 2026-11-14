"""Tests for immutable released-study tree resolution."""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Literal

import pytest
import yaml

from scripts.ci.released_studies import (
    ChecksumErratum,
    ReleasedStudyError,
    load_released_studies,
    released_study_root,
    resolve_release_revision,
    verify_current_release_subtree,
    verify_release_checksums,
)
from scripts.ci.validate_study_manifests import validate_repository_manifests


ROOT = Path(__file__).resolve().parents[3]
STUDY_ID = "sba-annual-report-structural-comparison"


def _run_git(repository_root: Path, *arguments: str) -> str:
    result = subprocess.run(
        [
            "git",
            "-c",
            "user.name=Release Test",
            "-c",
            "user.email=release@example.invalid",
            *arguments,
        ],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _initialize_repository(repository_root: Path) -> tuple[str, str]:
    _run_git(repository_root, "init", "--quiet")
    (repository_root / "tracked.txt").write_text("release\n", encoding="utf-8")
    _run_git(repository_root, "add", "tracked.txt")
    _run_git(repository_root, "commit", "--quiet", "--message", "release")
    return (
        _run_git(repository_root, "rev-parse", "HEAD"),
        _run_git(repository_root, "rev-parse", "HEAD^{tree}"),
    )


def _example_binding(source_revision: str, tree_oid: str):
    return replace(
        load_released_studies(ROOT)[STUDY_ID],
        study_id="example-study",
        tag="v1.0.0",
        source_revision=source_revision,
        tree_oid=tree_oid,
        checksum_manifest="studies/example-study/release/checksums.sha256",
        checksum_errata=(),
    )


def test_current_release_binding_resolves_the_reviewed_tree() -> None:
    binding = load_released_studies(ROOT)[STUDY_ID]

    revision = resolve_release_revision(ROOT, binding)

    assert revision == f"refs/tags/{binding.tag}"
    assert binding.source_revision == "15e11ed45c3ce5adf6a2441bdd0092a255dc730f"
    assert binding.tree_oid == "0d8e2c6709abaaf9c3eab710ddd063911e7a2871"


def test_release_binding_rejects_a_missing_tag(tmp_path: Path) -> None:
    source_revision, tree_oid = _initialize_repository(tmp_path)
    binding = _example_binding(source_revision, tree_oid)

    with pytest.raises(ReleasedStudyError, match="missing or unreadable"):
        resolve_release_revision(tmp_path, binding)


def test_release_binding_rejects_a_lightweight_tag(tmp_path: Path) -> None:
    source_revision, tree_oid = _initialize_repository(tmp_path)
    binding = _example_binding(source_revision, tree_oid)
    _run_git(tmp_path, "tag", binding.tag)

    with pytest.raises(ReleasedStudyError, match="not annotated"):
        resolve_release_revision(tmp_path, binding)


def test_released_tree_passes_its_checksum_inventory() -> None:
    binding = load_released_studies(ROOT)[STUDY_ID]

    with released_study_root(ROOT, binding) as release_root:
        assert verify_release_checksums(release_root, binding) == []
        assert (release_root / "studies" / STUDY_ID / "study.yaml").is_file()


def test_registry_rejects_unknown_fields(tmp_path: Path) -> None:
    studies = tmp_path / "studies"
    studies.mkdir()
    (studies / "releases.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "releases": {
                    "example": {
                        "tag": "v1.0.0",
                        "source_revision": "a" * 40,
                        "tree_oid": "b" * 40,
                        "checksum_manifest": "studies/example/checksums.sha256",
                        "surprise": True,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ReleasedStudyError, match="unknown field"):
        load_released_studies(tmp_path)


def test_checksum_inventory_rejects_parent_traversal(tmp_path: Path) -> None:
    binding = replace(load_released_studies(ROOT)[STUDY_ID], checksum_errata=())
    inventory = tmp_path / binding.checksum_manifest
    inventory.parent.mkdir(parents=True)
    inventory.write_text(f"{'a' * 64}  ../outside\n", encoding="utf-8")

    assert verify_release_checksums(tmp_path, binding) == [
        "checksum line 1 escapes the release tree",
        "release checksum inventory is empty",
    ]


def test_checksum_inventory_accepts_only_the_exact_declared_erratum(tmp_path: Path) -> None:
    release_bytes = b"release tree bytes\n"
    inventory_bytes = b"reviewed branch bytes\n"
    release_sha256 = hashlib.sha256(release_bytes).hexdigest()
    inventory_sha256 = hashlib.sha256(inventory_bytes).hexdigest()
    base = load_released_studies(ROOT)[STUDY_ID]
    binding = replace(
        base,
        checksum_manifest="checksums.sha256",
        checksum_errata=(
            ChecksumErratum(
                path="Makefile",
                inventory_sha256=inventory_sha256,
                release_sha256=release_sha256,
                reason="immutable squash-merge erratum",
            ),
        ),
    )
    (tmp_path / "Makefile").write_bytes(release_bytes)
    (tmp_path / "checksums.sha256").write_text(f"{inventory_sha256}  Makefile\n", encoding="utf-8")

    assert verify_release_checksums(tmp_path, binding) == []

    other_bytes = b"another value\n"
    other_sha256 = hashlib.sha256(other_bytes).hexdigest()
    (tmp_path / "Makefile").write_bytes(other_bytes)
    assert verify_release_checksums(tmp_path, binding) == [
        "release checksum mismatch for Makefile: "
        f"expected {inventory_sha256}, found "
        f"{other_sha256}",
        "declared release checksum erratum was not observed: Makefile",
    ]


def test_checksum_inventory_rejects_an_unused_erratum(tmp_path: Path) -> None:
    matching_bytes = b"matching\n"
    matching_sha256 = hashlib.sha256(matching_bytes).hexdigest()
    base = load_released_studies(ROOT)[STUDY_ID]
    binding = replace(
        base,
        checksum_manifest="checksums.sha256",
        checksum_errata=(
            ChecksumErratum(
                path="Makefile",
                inventory_sha256=matching_sha256,
                release_sha256=matching_sha256,
                reason="must be observed",
            ),
        ),
    )
    (tmp_path / "Makefile").write_bytes(matching_bytes)
    (tmp_path / "checksums.sha256").write_text(f"{matching_sha256}  Makefile\n", encoding="utf-8")

    assert verify_release_checksums(tmp_path, binding) == [
        "declared release checksum erratum was not observed: Makefile"
    ]


def _write_example_study_release(repository_root: Path) -> None:
    design = repository_root / "specs/example.md"
    design.parent.mkdir(parents=True)
    design.write_text("frozen design\n", encoding="utf-8")

    implementation = repository_root / "sbir_etl/example.py"
    implementation.parent.mkdir(parents=True)
    implementation.write_text("def run_study():\n    return None\n", encoding="utf-8")

    study_root = repository_root / "studies/example-study"
    study_root.mkdir(parents=True)
    manifest = {
        "schema_version": 1,
        "study_id": "example-study",
        "title": "Example study",
        "evidence_status": "reproducible",
        "research_questions": ["B2"],
        "estimand": "Count observable examples.",
        "frozen_artifacts": [
            {
                "path": "specs/example.md",
                "sha256": hashlib.sha256(design.read_bytes()).hexdigest(),
            }
        ],
        "implementation": [{"path": "sbir_etl/example.py", "symbol": "run_study"}],
        "identity_policy": {
            "strategy": "exact identifier",
            "version": "v1",
            "negative_evidence_allowed": False,
        },
        "materialization": {"allowed": False, "blockers": ["Validation is incomplete."]},
        "permitted_claims": ["The study can be reproduced."],
        "limitations": ["The result is not citable."],
    }
    manifest_path = study_root / "study.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    (study_root / "README.md").write_text("# Example study\n", encoding="utf-8")

    inventory = study_root / "release/checksums.sha256"
    inventory.parent.mkdir()
    manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    inventory.write_text(
        f"{manifest_sha256}  studies/example-study/study.yaml\n",
        encoding="utf-8",
    )


def _initialize_study_release(repository_root: Path):
    _run_git(repository_root, "init", "--quiet")
    _write_example_study_release(repository_root)
    _run_git(repository_root, "add", ".")
    _run_git(repository_root, "commit", "--quiet", "--message", "release study")
    _run_git(repository_root, "tag", "--annotate", "v1.0.0", "--message", "release study")
    source_revision = _run_git(repository_root, "rev-parse", "HEAD")
    tree_oid = _run_git(repository_root, "rev-parse", "HEAD^{tree}")
    binding = _example_binding(source_revision, tree_oid)

    (repository_root / "studies/releases.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "releases": {
                    binding.study_id: {
                        "tag": binding.tag,
                        "source_revision": binding.source_revision,
                        "tree_oid": binding.tree_oid,
                        "checksum_manifest": binding.checksum_manifest,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return binding


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("change", "differs from v1.0.0"),
        ("remove", "is missing path from v1.0.0"),
        ("add", "has path absent from v1.0.0"),
    ],
)
def test_repository_validation_rejects_released_study_subtree_drift(
    tmp_path: Path,
    mutation: Literal["change", "remove", "add"],
    expected: str,
) -> None:
    binding = _initialize_study_release(tmp_path)
    study_root = tmp_path / "studies" / binding.study_id

    count, errors = validate_repository_manifests(tmp_path)
    assert count == 1
    assert errors == []

    if mutation == "change":
        (study_root / "study.yaml").write_text("{}\n", encoding="utf-8")
    elif mutation == "remove":
        (study_root / "README.md").unlink()
    else:
        (study_root / "unexpected.txt").write_text("drift\n", encoding="utf-8")

    count, errors = validate_repository_manifests(tmp_path)
    assert count == 1
    assert any(expected in error for error in errors)


def test_current_release_subtree_rejects_symbolic_links(tmp_path: Path) -> None:
    binding = _initialize_study_release(tmp_path)
    with released_study_root(tmp_path, binding) as release_root:
        current_link = tmp_path / "studies" / binding.study_id / "linked"
        current_link.symlink_to(tmp_path / "tracked.txt")

        assert verify_current_release_subtree(tmp_path, release_root, binding) == [
            "current released-study packet contains a symbolic link: linked",
        ]


def test_current_release_subtree_rejects_a_symbolic_link_root(tmp_path: Path) -> None:
    binding = _initialize_study_release(tmp_path)
    current_root = tmp_path / "studies" / binding.study_id
    linked_root = tmp_path / "linked-study"
    current_root.rename(linked_root)
    current_root.symlink_to(linked_root, target_is_directory=True)

    with released_study_root(tmp_path, binding) as release_root:
        assert verify_current_release_subtree(tmp_path, release_root, binding) == [
            "current released-study packet is a symbolic link: studies/example-study",
        ]
