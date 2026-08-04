#!/usr/bin/env python3
"""Validate synchronized SemVer metadata and an optional Git release tag."""

import argparse
import re
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROJECTS = {
    "sbir-etl": ROOT / "pyproject.toml",
    "sbir-analytics": ROOT / "packages/sbir-analytics/pyproject.toml",
    "sbir-graph": ROOT / "packages/sbir-graph/pyproject.toml",
    "sbir-ml": ROOT / "packages/sbir-ml/pyproject.toml",
}
LOCK_FILE = ROOT / "uv.lock"
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def load_toml(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def validate(tag: str | None = None) -> list[str]:
    errors: list[str] = []
    project_versions = {
        name: load_toml(path)["project"]["version"] for name, path in PROJECTS.items()
    }

    for name, version in project_versions.items():
        if not SEMVER.fullmatch(version):
            errors.append(f"{name} has non-SemVer version {version!r}")

    versions = set(project_versions.values())
    if len(versions) != 1:
        details = ", ".join(f"{name}={version}" for name, version in project_versions.items())
        errors.append(f"project versions are not synchronized: {details}")

    lock_packages = {
        package["name"]: package["version"]
        for package in load_toml(LOCK_FILE)["package"]
        if package["name"] in PROJECTS
    }
    for name, version in project_versions.items():
        locked = lock_packages.get(name)
        if locked != version:
            errors.append(f"uv.lock has {name}={locked!r}; expected {version!r}")

    if tag and len(versions) == 1:
        expected_tag = f"v{next(iter(versions))}"
        if tag != expected_tag:
            errors.append(f"release tag {tag!r} does not match expected {expected_tag!r}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", help="Release tag to compare with project metadata")
    args = parser.parse_args()

    errors = validate(args.tag)
    if errors:
        for error in errors:
            print(f"versioning error: {error}", file=sys.stderr)
        return 1

    version = load_toml(PROJECTS["sbir-etl"])["project"]["version"]
    suffix = f" and tag {args.tag}" if args.tag else ""
    print(f"versioning check passed for {version}{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
