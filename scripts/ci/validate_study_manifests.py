#!/usr/bin/env python3
"""Validate versioned study contracts and their repository references."""

import ast
import hashlib
from pathlib import Path

from pydantic import ValidationError

from sbir_etl.quality.study_manifest import StudyManifest, load_study_manifest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
STUDIES_ROOT = REPOSITORY_ROOT / "studies"


def _repository_path(relative: str, repository_root: Path) -> Path:
    candidate = (repository_root / relative).resolve()
    try:
        candidate.relative_to(repository_root.resolve())
    except ValueError as exc:
        raise ValueError(f"path escapes repository root: {relative}") from exc
    return candidate


def _module_symbols(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.AsyncFunctionDef, ast.ClassDef, ast.FunctionDef))
    }


def validate_manifest_references(
    manifest: StudyManifest,
    *,
    manifest_path: Path,
    repository_root: Path = REPOSITORY_ROOT,
) -> list[str]:
    """Return all broken hashes, paths, and implementation symbols."""

    errors: list[str] = []
    if manifest_path.parent.name != manifest.study_id:
        errors.append(
            f"study_id {manifest.study_id!r} does not match directory {manifest_path.parent.name!r}"
        )

    for artifact in manifest.frozen_artifacts:
        try:
            path = _repository_path(artifact.path, repository_root)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if not path.is_file():
            errors.append(f"frozen artifact does not exist: {artifact.path}")
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != artifact.sha256:
            errors.append(
                f"frozen artifact hash mismatch for {artifact.path}: "
                f"expected {artifact.sha256}, found {actual}"
            )

    for reference in manifest.implementation:
        try:
            path = _repository_path(reference.path, repository_root)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if not path.is_file():
            errors.append(f"implementation path does not exist: {reference.path}")
            continue
        try:
            symbols = _module_symbols(path)
        except (OSError, SyntaxError) as exc:
            errors.append(f"cannot inspect implementation {reference.path}: {exc}")
            continue
        if reference.symbol not in symbols:
            errors.append(
                f"implementation symbol {reference.symbol!r} is missing from {reference.path}"
            )
    return errors


def validate_manifest_file(
    path: Path,
    *,
    repository_root: Path = REPOSITORY_ROOT,
) -> list[str]:
    """Load one manifest and return stable, user-facing validation errors."""

    try:
        manifest = load_study_manifest(path)
    except (OSError, ValueError, ValidationError) as exc:
        return [f"invalid manifest: {exc}"]
    return validate_manifest_references(
        manifest,
        manifest_path=path,
        repository_root=repository_root,
    )


def main() -> int:
    manifests = sorted(STUDIES_ROOT.glob("*/study.yaml"))
    if not manifests:
        print("No study manifests found under studies/*/study.yaml")
        return 1

    failures: list[str] = []
    for path in manifests:
        relative = path.relative_to(REPOSITORY_ROOT).as_posix()
        failures.extend(f"{relative}: {error}" for error in validate_manifest_file(path))
    if failures:
        print("Study manifest validation failed:")
        print("\n".join(failures))
        return 1
    print(f"Validated {len(manifests)} study manifest(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
