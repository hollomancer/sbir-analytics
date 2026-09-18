"""External-upload safety boundary.

Upload is fail-closed. The orchestrator must see an explicit
``--allow-external-upload`` before any network call. Even then, only files
already copied into the frozen bundle are eligible, and a conservative path
policy rejects credentials, env files, Neo4j stores, and whole-tree dumps.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from pathlib import Path

from sbir_etl.utils.data.file_io import file_sha256

from .models import ExternalUploadNotAuthorized, StudyBundle, UnsafeUploadError


EPISTEMIC_TIER = "exploratory"

FORBIDDEN_NAME_PATTERNS = (
    re.compile(r"^\.env$"),
    re.compile(r"^\.env\..+"),
    re.compile(r".*\.pem$"),
    re.compile(r".*\.key$"),
    re.compile(r"^id_rsa$"),
    re.compile(r"^id_rsa\.pub$"),
    re.compile(r".*credentials.*", re.IGNORECASE),
    re.compile(r".*api[_-]?key.*", re.IGNORECASE),
    re.compile(r".*secret.*", re.IGNORECASE),
    re.compile(r"^\.netrc$"),
)

# One path segment: no separators, no dot segments, no leading dot. Applied to
# study IDs, provider names, and provider-supplied run IDs before they touch a
# filesystem path.
SAFE_PATH_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

FORBIDDEN_PATH_FRAGMENTS = (
    (".git",),
    (".dagster_home",),
    ("neo4j", "data"),
    ("neo4j", "logs"),
)

UploadRule = Callable[[StudyBundle], list[str]]


def assert_safe_path_component(value: str, *, label: str) -> str:
    """Fail closed unless ``value`` is one safe path segment.

    Study IDs, provider names, and provider-returned run IDs are interpolated
    into paths under ``studies/``; a value carrying a separator or a dot
    segment could read or write outside that tree.
    """

    if not SAFE_PATH_COMPONENT.fullmatch(value) or value in {".", ".."}:
        raise UnsafeUploadError(f"{label} {value!r} is not a safe path component")
    return value


def _posix_parts(path: Path) -> tuple[str, ...]:
    return Path(path.as_posix()).parts


def forbidden_reason(path: Path, *, repository_root: Path) -> str | None:
    """Return a reason ``path`` must not be uploaded, or None if it is eligible."""

    resolved = path.resolve()
    repo = repository_root.resolve()
    if resolved == repo:
        return "refusing to upload the repository root"
    if resolved.is_dir():
        return f"refusing to upload a directory; name files explicitly: {path}"
    name = resolved.name
    for pattern in FORBIDDEN_NAME_PATTERNS:
        if pattern.match(name):
            return f"refusing to upload restricted file {name!r}"
    parts = _posix_parts(resolved)
    for fragment in FORBIDDEN_PATH_FRAGMENTS:
        for index in range(len(parts) - len(fragment) + 1):
            if parts[index : index + len(fragment)] == fragment:
                return f"refusing to upload path under {'/'.join(fragment)}"
    try:
        relative = resolved.relative_to(repo)
    except ValueError:
        relative = None
    if relative is not None and relative.as_posix() in {"data", "data/raw"}:
        return "refusing to upload an unrequested raw-data directory"
    return None


def assert_safe_source_path(path: Path, *, repository_root: Path) -> None:
    """Fail closed if ``path`` is not an explicit, eligible file."""

    if not path.exists():
        return
    reason = forbidden_reason(path, repository_root=repository_root)
    if reason is not None:
        raise UnsafeUploadError(reason)


def assert_upload_authorized(allow_external_upload: bool) -> None:
    """Fail closed before any network request unless the operator opted in."""

    if not allow_external_upload:
        raise ExternalUploadNotAuthorized(
            "external upload is not authorized; pass --allow-external-upload "
            "after reviewing the frozen bundle"
        )


def evaluate_upload_policy(
    bundle: StudyBundle,
    *,
    repository_root: Path,
    extra_rules: Sequence[UploadRule] = (),
) -> None:
    """Run the conservative default policy plus any later restriction hooks.

    The provider uploads the whole bundle directory, so the policy checks the
    directory against the manifest in both directions: every listed file must
    still carry its frozen digest and size, and every file on disk must be
    listed. A bundle edited, symlinked, or added to after freezing is
    rejected rather than submitted.
    """

    errors: list[str] = []
    listed_paths: set[str] = set()
    for entry in bundle.manifest.input_files:
        listed_paths.add(entry.path)
        bundled = bundle.directory / entry.path
        if bundled.is_symlink():
            errors.append(f"{entry.path}: refusing to upload a symlink")
            continue
        if not bundled.is_file():
            errors.append(f"{entry.path}: listed in the manifest but missing from the bundle")
            continue
        reason = forbidden_reason(bundled, repository_root=repository_root)
        if reason is not None:
            errors.append(f"{entry.path}: {reason}")
        actual_size = bundled.stat().st_size
        if actual_size != entry.size_bytes:
            errors.append(
                f"{entry.path}: size changed after freezing "
                f"({entry.size_bytes} -> {actual_size} bytes)"
            )
        elif file_sha256(bundled) != entry.sha256:
            errors.append(f"{entry.path}: content changed after freezing (sha256 mismatch)")
        if entry.source_path:
            source = repository_root / entry.source_path
            if source.exists():
                source_reason = forbidden_reason(source, repository_root=repository_root)
                if source_reason is not None:
                    errors.append(f"{entry.source_path}: {source_reason}")
    for on_disk in sorted(bundle.directory.rglob("*")):
        if on_disk.is_dir():
            continue
        relative = on_disk.relative_to(bundle.directory).as_posix()
        if relative == "manifest.json":
            continue
        if relative not in listed_paths:
            errors.append(f"{relative}: present in the bundle but not in the manifest")
    for rule in extra_rules:
        errors.extend(rule(bundle))
    if errors:
        raise UnsafeUploadError("upload policy rejected the bundle: " + "; ".join(errors))
