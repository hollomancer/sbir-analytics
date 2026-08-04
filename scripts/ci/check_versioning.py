#!/usr/bin/env python3
"""Validate synchronized SemVer metadata and an optional Git release tag."""

import argparse
import ast
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
RUNTIME_VERSION_FILE = ROOT / "sbir_etl/__init__.py"
BASE_CONFIG_FILE = ROOT / "config/base.yaml"
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def load_toml(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def load_python_string(path: Path, variable: str) -> str:
    """Read a module-level string assignment without importing project code."""
    module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == variable for target in node.targets):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                return node.value.value
            break
    raise ValueError(f"{path} does not define {variable} as a string literal")


def load_base_pipeline_version(path: Path) -> str:
    """Read ``pipeline.version`` from the simple top-level YAML mapping."""
    in_pipeline = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if not line[0].isspace():
            if in_pipeline:
                break
            in_pipeline = line == "pipeline:"
            continue
        if in_pipeline and line.lstrip().startswith("version:"):
            value = line.split(":", 1)[1].strip().strip("\"'")
            if value:
                return value
            break
    raise ValueError(f"{path} does not define pipeline.version")


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

    if len(versions) == 1:
        expected_version = next(iter(versions))
        try:
            runtime_versions = {
                "sbir_etl.__version__": load_python_string(RUNTIME_VERSION_FILE, "__version__"),
                "config/base.yaml pipeline.version": load_base_pipeline_version(BASE_CONFIG_FILE),
            }
        except (OSError, SyntaxError, ValueError) as exc:
            errors.append(f"could not read runtime version metadata: {exc}")
        else:
            for source, runtime_version in runtime_versions.items():
                if runtime_version != expected_version:
                    errors.append(f"{source} is {runtime_version!r}; expected {expected_version!r}")

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
