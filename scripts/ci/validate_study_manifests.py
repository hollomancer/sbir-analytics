#!/usr/bin/env python3
"""Validate versioned study contracts and their repository references."""

import ast
import hashlib
import json
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from sbir_etl.exceptions import ConfigurationError
from sbir_etl.quality.study_manifest import StudyManifest, load_study_manifest

from scripts.ci.released_studies import (
    ReleasedStudyError,
    load_released_studies,
    released_study_root,
    verify_current_release_subtree,
    verify_release_checksums,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _repository_path(relative: str, repository_root: Path) -> Path:
    candidate = (repository_root / relative).resolve()
    try:
        candidate.relative_to(repository_root.resolve())
    except ValueError as exc:
        raise ValueError(f"path escapes repository root: {relative}") from exc
    return candidate


def _module_symbols(path: Path) -> set[str]:
    """Collect module-level symbol names an implementation reference may name.

    Covers definitions and module-level bindings, so an asset built by a factory
    (`census = build_asset(...)`) is not reported as a missing implementation merely
    because it is an assignment rather than a `def`.
    """

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.AsyncFunctionDef, ast.ClassDef, ast.FunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(target.id for target in node.targets if isinstance(target, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


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
        if artifact.external_source:
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

    errors.extend(_evaluated_design_errors(manifest, repository_root=repository_root))
    errors.extend(_claim_approval_errors(manifest, repository_root=repository_root))
    return errors


def _claim_approval_errors(
    manifest: StudyManifest,
    *,
    repository_root: Path,
) -> list[str]:
    """The pinned review has to name the study and the boundary it approves.

    The manifest schema checks that the review file is pinned and that the
    boundary digest matches the manifest text. It cannot read the review, so
    an editor could widen a claim, recompute the digest, and keep the old
    review. Requiring the review to contain the study ID and the digest means
    a changed boundary also needs a changed, re-pinned review.
    """
    approval = manifest.claim_approval
    if approval is None:
        return []

    errors: list[str] = []
    if approval.approved_on > datetime.now(UTC).date():
        errors.append(f"claim_approval.approved_on {approval.approved_on} is in the future")
    try:
        path = _repository_path(approval.review_path, repository_root)
    except ValueError as exc:
        return [*errors, str(exc)]
    if not path.is_file():
        return errors
    review = path.read_text(encoding="utf-8")
    if manifest.study_id not in review:
        errors.append(
            f"claim_approval review {approval.review_path} does not name study "
            f"{manifest.study_id!r}"
        )
    if approval.claim_boundary_sha256 not in review:
        errors.append(
            f"claim_approval review {approval.review_path} does not contain "
            "claim_boundary_sha256; the review must record the boundary it approves"
        )
    return errors


def _evaluated_design_errors(
    manifest: StudyManifest,
    *,
    repository_root: Path,
) -> list[str]:
    """The design a result names must be the design the run actually read.

    The capture CLI verifies the protocol against HEAD and against
    ``frozen_artifacts`` before it runs, and nothing stopped the protocol being
    edited and re-pinned afterwards. That is how the held-out 1501-2500 design
    came to be pinned about ten hours after the replay it was supposed to have
    preregistered, with every run-time check passing.

    A run manifest that records ``protocol_sha256`` closes it: the recorded
    bytes are what the run read, so a later edit stops matching.
    """
    result = manifest.validation_result
    if result is None:
        return []

    errors: list[str] = []
    for artifact in manifest.frozen_artifacts:
        if not artifact.path.endswith("run-manifest.json"):
            continue
        try:
            path = _repository_path(artifact.path, repository_root)
        except ValueError:
            continue
        if not path.is_file():
            continue
        try:
            run = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(run, dict):
            continue
        recorded = run.get("protocol_sha256")
        if not isinstance(recorded, str) or not recorded:
            continue
        if recorded != result.design_sha256:
            errors.append(
                f"validation_result.design_sha256 {result.design_sha256[:12]}... does not "
                f"match protocol_sha256 {recorded[:12]}... recorded by {artifact.path}; "
                "the evaluated design was changed after the run"
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
    except (OSError, ValueError, ValidationError, ConfigurationError) as exc:
        return [f"invalid manifest: {exc}"]
    return validate_manifest_references(
        manifest,
        manifest_path=path,
        repository_root=repository_root,
    )


def validate_repository_manifests(
    repository_root: Path = REPOSITORY_ROOT,
) -> tuple[int, list[str]]:
    """Validate active studies at HEAD and released studies in immutable trees."""

    manifests = sorted((repository_root / "studies").glob("*/study.yaml"))
    if not manifests:
        return 0, ["No study manifests found under studies/*/study.yaml"]
    try:
        releases = load_released_studies(repository_root)
    except (OSError, ValueError, ReleasedStudyError) as exc:
        return len(manifests), [f"invalid released-study registry: {exc}"]

    failures: list[str] = []
    seen_releases: set[str] = set()
    with ExitStack() as stack:
        released_roots: dict[str, Path] = {}
        for path in manifests:
            study_id = path.parent.name
            binding = releases.get(study_id)
            validation_root = repository_root
            validation_path = path
            if binding is not None:
                try:
                    validation_root = released_roots.setdefault(
                        study_id,
                        stack.enter_context(released_study_root(repository_root, binding)),
                    )
                except (OSError, ReleasedStudyError) as exc:
                    failures.append(f"{path.relative_to(repository_root)}: {exc}")
                    continue
                validation_path = validation_root / "studies" / study_id / "study.yaml"
                failures.extend(
                    f"{path.relative_to(repository_root)}: {error}"
                    for error in verify_release_checksums(validation_root, binding)
                )
                failures.extend(
                    f"{path.relative_to(repository_root)}: {error}"
                    for error in verify_current_release_subtree(
                        repository_root,
                        validation_root,
                        binding,
                    )
                )
                seen_releases.add(study_id)
            failures.extend(
                f"{path.relative_to(repository_root)}: {error}"
                for error in validate_manifest_file(
                    validation_path,
                    repository_root=validation_root,
                )
            )

    missing = sorted(set(releases) - seen_releases)
    failures.extend(
        f"released-study registry names missing study: {study_id}" for study_id in missing
    )
    return len(manifests), failures


def main() -> int:
    count, failures = validate_repository_manifests()
    if failures:
        print("Study manifest validation failed:")
        print("\n".join(failures))
        return 1
    print(f"Validated {count} study manifest(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
