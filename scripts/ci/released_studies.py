"""Resolve completed studies against their immutable release trees.

The moving repository may change dependencies and documentation after a study
release. Released study contracts still validate against the exact Git tree
that contains the reviewed packet. Active studies continue to validate against
the current checkout.
"""

from __future__ import annotations

import hashlib
import io
import subprocess
import tarfile
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from sbir_etl.config.yaml_io import read_yaml_mapping


REGISTRY_PATH = Path("studies/releases.yaml")


class ReleasedStudyError(ValueError):
    """Raised when a release binding or immutable tree cannot be verified."""


@dataclass(frozen=True)
class ChecksumErratum:
    """One exact, documented mismatch in an immutable release inventory."""

    path: str
    inventory_sha256: str
    release_sha256: str
    reason: str


@dataclass(frozen=True)
class ReleasedStudy:
    """One study bound to a reviewed Git tree and release checksum inventory."""

    study_id: str
    tag: str
    source_revision: str
    tree_oid: str
    checksum_manifest: str
    checksum_errata: tuple[ChecksumErratum, ...] = ()


def _require_text(record: Mapping[str, Any], field: str, *, study_id: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ReleasedStudyError(f"released study {study_id!r} has invalid {field!r}")
    return value


def _require_sha256(value: Any, *, field: str, study_id: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ReleasedStudyError(f"released study {study_id!r} has invalid SHA-256 in {field!r}")
    return value


def _safe_relative_path(value: Any, *, field: str, study_id: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReleasedStudyError(f"released study {study_id!r} has invalid {field!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise ReleasedStudyError(f"released study {study_id!r} has unsafe {field!r}")
    return value


def _load_checksum_errata(value: Any, *, study_id: str) -> tuple[ChecksumErratum, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ReleasedStudyError(f"released study {study_id!r} checksum_errata must be a list")
    parsed: list[ChecksumErratum] = []
    seen_paths: set[str] = set()
    expected_fields = {"path", "inventory_sha256", "release_sha256", "reason"}
    for index, record in enumerate(value):
        if not isinstance(record, dict) or set(record) != expected_fields:
            raise ReleasedStudyError(
                f"released study {study_id!r} checksum erratum {index} must contain "
                f"exactly: {', '.join(sorted(expected_fields))}"
            )
        path = _safe_relative_path(record["path"], field="checksum erratum path", study_id=study_id)
        if path in seen_paths:
            raise ReleasedStudyError(
                f"released study {study_id!r} repeats checksum erratum path {path!r}"
            )
        seen_paths.add(path)
        parsed.append(
            ChecksumErratum(
                path=path,
                inventory_sha256=_require_sha256(
                    record["inventory_sha256"],
                    field="checksum erratum inventory_sha256",
                    study_id=study_id,
                ),
                release_sha256=_require_sha256(
                    record["release_sha256"],
                    field="checksum erratum release_sha256",
                    study_id=study_id,
                ),
                reason=_require_text(record, "reason", study_id=study_id),
            )
        )
    return tuple(parsed)


def load_released_studies(repository_root: Path) -> dict[str, ReleasedStudy]:
    """Load the strict release-tree registry from the current checkout."""

    raw = read_yaml_mapping(repository_root / REGISTRY_PATH)
    if raw.get("schema_version") != 1:
        raise ReleasedStudyError("studies/releases.yaml must use schema_version: 1")
    releases = raw.get("releases")
    if not isinstance(releases, dict) or not releases:
        raise ReleasedStudyError("studies/releases.yaml must declare at least one release")

    parsed: dict[str, ReleasedStudy] = {}
    for study_id, value in releases.items():
        if not isinstance(study_id, str) or not study_id.strip() or not isinstance(value, dict):
            raise ReleasedStudyError("released-study entries must map study IDs to records")
        extra = set(value) - {
            "tag",
            "source_revision",
            "tree_oid",
            "checksum_manifest",
            "checksum_errata",
        }
        if extra:
            raise ReleasedStudyError(
                f"released study {study_id!r} has unknown field(s): {', '.join(sorted(extra))}"
            )
        binding = ReleasedStudy(
            study_id=study_id,
            tag=_require_text(value, "tag", study_id=study_id),
            source_revision=_require_text(value, "source_revision", study_id=study_id),
            tree_oid=_require_text(value, "tree_oid", study_id=study_id),
            checksum_manifest=_safe_relative_path(
                _require_text(value, "checksum_manifest", study_id=study_id),
                field="checksum_manifest",
                study_id=study_id,
            ),
            checksum_errata=_load_checksum_errata(value.get("checksum_errata"), study_id=study_id),
        )
        if len(binding.source_revision) != 40 or any(
            character not in "0123456789abcdef" for character in binding.source_revision
        ):
            raise ReleasedStudyError(
                f"released study {study_id!r} source_revision must be a full Git SHA"
            )
        if len(binding.tree_oid) != 40 or any(
            character not in "0123456789abcdef" for character in binding.tree_oid
        ):
            raise ReleasedStudyError(
                f"released study {study_id!r} tree_oid must be a full Git object ID"
            )
        parsed[study_id] = binding
    return parsed


def _git(repository_root: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *arguments],
        cwd=repository_root,
        check=check,
        capture_output=True,
    )


def _tree_for(repository_root: Path, revision: str) -> str:
    try:
        result = _git(repository_root, "rev-parse", f"{revision}^{{tree}}")
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode("utf-8", errors="replace").strip()
        raise ReleasedStudyError(f"cannot resolve release revision {revision!r}: {detail}") from exc
    return result.stdout.decode("ascii").strip()


def _commit_for(repository_root: Path, revision: str) -> str:
    try:
        result = _git(repository_root, "rev-parse", f"{revision}^{{commit}}")
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode("utf-8", errors="replace").strip()
        raise ReleasedStudyError(f"cannot resolve release commit {revision!r}: {detail}") from exc
    return result.stdout.decode("ascii").strip()


def resolve_release_revision(repository_root: Path, binding: ReleasedStudy) -> str:
    """Resolve an exact annotated tag that matches the registered commit and tree."""

    source_tree = _tree_for(repository_root, binding.source_revision)
    if source_tree != binding.tree_oid:
        raise ReleasedStudyError(
            f"released study {binding.study_id!r} source tree differs: "
            f"expected {binding.tree_oid}, found {source_tree}"
        )

    tag_reference = f"refs/tags/{binding.tag}"
    tag_type = _git(repository_root, "cat-file", "-t", tag_reference, check=False)
    if tag_type.returncode != 0:
        detail = tag_type.stderr.decode("utf-8", errors="replace").strip()
        suffix = f": {detail}" if detail else ""
        raise ReleasedStudyError(f"release tag {binding.tag!r} is missing or unreadable{suffix}")
    if tag_type.stdout.decode("ascii").strip() != "tag":
        raise ReleasedStudyError(f"release tag {binding.tag!r} is not annotated")
    tag_commit = _commit_for(repository_root, tag_reference)
    if tag_commit != binding.source_revision:
        raise ReleasedStudyError(
            f"release tag {binding.tag!r} resolves to commit {tag_commit}, "
            f"expected {binding.source_revision}"
        )
    tag_tree = _tree_for(repository_root, tag_reference)
    if tag_tree != binding.tree_oid:
        raise ReleasedStudyError(
            f"release tag {binding.tag!r} resolves to tree {tag_tree}, expected {binding.tree_oid}"
        )
    return tag_reference


def _subtree_files(root: Path, *, label: str) -> tuple[dict[str, Path], list[str]]:
    """Return regular files below ``root`` and reject links or special entries."""

    files: dict[str, Path] = {}
    errors: list[str] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            errors.append(f"{label} contains a symbolic link: {relative}")
        elif path.is_file():
            files[relative] = path
        elif not path.is_dir():
            errors.append(f"{label} contains an unsupported entry: {relative}")
    return files, errors


def verify_current_release_subtree(
    repository_root: Path,
    release_root: Path,
    binding: ReleasedStudy,
) -> list[str]:
    """Reject path or byte drift in a released study packet copied on the moving branch."""

    relative_root = Path("studies") / binding.study_id
    current_subtree = repository_root / relative_root
    release_subtree = release_root / relative_root
    if current_subtree.is_symlink():
        return [f"current released-study packet is a symbolic link: {relative_root.as_posix()}"]
    if not current_subtree.is_dir():
        return [f"current released-study packet is missing: {relative_root.as_posix()}"]
    if release_subtree.is_symlink():
        return [
            f"release tag {binding.tag!r} study packet is a symbolic link: "
            f"{relative_root.as_posix()}"
        ]
    if not release_subtree.is_dir():
        return [f"release tag {binding.tag!r} is missing study packet: {relative_root.as_posix()}"]

    current_files, errors = _subtree_files(
        current_subtree,
        label="current released-study packet",
    )
    release_files, release_errors = _subtree_files(
        release_subtree,
        label=f"release tag {binding.tag!r} study packet",
    )
    errors.extend(release_errors)

    current_paths = set(current_files)
    release_paths = set(release_files)
    for relative in sorted(release_paths - current_paths):
        path = (relative_root / relative).as_posix()
        errors.append(f"current released-study packet is missing path from {binding.tag}: {path}")
    for relative in sorted(current_paths - release_paths):
        path = (relative_root / relative).as_posix()
        errors.append(f"current released-study packet has path absent from {binding.tag}: {path}")
    for relative in sorted(current_paths & release_paths):
        current_sha256 = hashlib.sha256(current_files[relative].read_bytes()).hexdigest()
        release_sha256 = hashlib.sha256(release_files[relative].read_bytes()).hexdigest()
        if current_sha256 != release_sha256:
            path = (relative_root / relative).as_posix()
            errors.append(f"current released-study packet differs from {binding.tag}: {path}")
    return errors


def _safe_members(archive: tarfile.TarFile) -> list[tarfile.TarInfo]:
    members = archive.getmembers()
    for member in members:
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts or member.issym() or member.islnk():
            raise ReleasedStudyError(f"unsafe path in release archive: {member.name}")
    return members


def _extract_archive(archive: tarfile.TarFile, root: Path) -> None:
    """Extract regular Git archive entries without accepting links or devices."""

    for member in _safe_members(archive):
        destination = root / member.name
        if member.isdir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        if not member.isfile():
            raise ReleasedStudyError(f"unsupported entry in release archive: {member.name}")
        source = archive.extractfile(member)
        if source is None:
            raise ReleasedStudyError(f"cannot read release archive entry: {member.name}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read())


@contextmanager
def released_study_root(
    repository_root: Path,
    binding: ReleasedStudy,
) -> Iterator[Path]:
    """Extract and yield the verified immutable tree for one released study."""

    revision = resolve_release_revision(repository_root, binding)
    try:
        archived = _git(repository_root, "archive", "--format=tar", revision)
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode("utf-8", errors="replace").strip()
        raise ReleasedStudyError(f"cannot archive release revision {revision!r}: {detail}") from exc

    with tempfile.TemporaryDirectory(prefix=f"released-study-{binding.study_id}-") as temporary:
        root = Path(temporary)
        with tarfile.open(fileobj=io.BytesIO(archived.stdout), mode="r:") as archive:
            _extract_archive(archive, root)
        yield root


def verify_release_checksums(root: Path, binding: ReleasedStudy) -> list[str]:
    """Return checksum-inventory failures from an extracted release tree."""

    inventory = root / binding.checksum_manifest
    if not inventory.is_file():
        return [f"release checksum inventory is missing: {binding.checksum_manifest}"]
    errors: list[str] = []
    seen: set[str] = set()
    errata = {record.path: record for record in binding.checksum_errata}
    used_errata: set[str] = set()
    for line_number, line in enumerate(inventory.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            expected, relative = line.split("  ", 1)
        except ValueError:
            errors.append(f"checksum line {line_number} is malformed")
            continue
        if len(expected) != 64 or any(
            character not in "0123456789abcdef" for character in expected
        ):
            errors.append(f"checksum line {line_number} has an invalid SHA-256")
            continue
        path = PurePosixPath(relative)
        if path.is_absolute() or ".." in path.parts:
            errors.append(f"checksum line {line_number} escapes the release tree")
            continue
        if relative in seen:
            errors.append(f"checksum inventory repeats path: {relative}")
            continue
        seen.add(relative)
        candidate = root / relative
        if not candidate.is_file():
            errors.append(f"release checksum path is missing: {relative}")
            continue
        actual = hashlib.sha256(candidate.read_bytes()).hexdigest()
        if actual != expected:
            erratum = errata.get(relative)
            if (
                erratum is not None
                and erratum.inventory_sha256 == expected
                and erratum.release_sha256 == actual
            ):
                used_errata.add(relative)
                continue
            errors.append(
                f"release checksum mismatch for {relative}: expected {expected}, found {actual}"
            )
    for erratum_path in sorted(set(errata) - used_errata):
        errors.append(f"declared release checksum erratum was not observed: {erratum_path}")
    if not seen:
        errors.append("release checksum inventory is empty")
    return errors
