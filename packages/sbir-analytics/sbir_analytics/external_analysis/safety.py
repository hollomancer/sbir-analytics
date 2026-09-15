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
    re.compile(r".*secrets\.json$", re.IGNORECASE),
    re.compile(r"^\.secrets\.baseline$"),
)

FORBIDDEN_PATH_FRAGMENTS = (
    (".git",),
    (".dagster_home",),
    ("neo4j", "data"),
    ("neo4j", "logs"),
)

UploadRule = Callable[[StudyBundle], list[str]]


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
    """Run the conservative default policy plus any later restriction hooks."""

    errors: list[str] = []
    for entry in bundle.manifest.input_files:
        bundled = bundle.directory / entry.path
        reason = forbidden_reason(bundled, repository_root=repository_root)
        if reason is not None:
            errors.append(f"{entry.path}: {reason}")
        if entry.source_path:
            source = repository_root / entry.source_path
            if source.exists():
                source_reason = forbidden_reason(source, repository_root=repository_root)
                if source_reason is not None:
                    errors.append(f"{entry.source_path}: {source_reason}")
    for rule in extra_rules:
        errors.extend(rule(bundle))
    if errors:
        raise UnsafeUploadError("upload policy rejected the bundle: " + "; ".join(errors))
