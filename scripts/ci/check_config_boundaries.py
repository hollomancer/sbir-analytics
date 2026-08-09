#!/usr/bin/env python3
"""Prevent production code from bypassing the shared YAML configuration reader."""

from __future__ import annotations

import ast
import subprocess
from dataclasses import dataclass
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_YAML_READERS = frozenset(
    {
        "sbir_etl/config/loader.py",
        "sbir_etl/config/yaml_io.py",
    }
)
IGNORED_PREFIXES = ("scripts/archive/", "tests/")


@dataclass(frozen=True)
class ConfigBoundaryViolation:
    """One direct PyYAML read outside the configuration primitive."""

    path: str
    line_number: int

    def format(self) -> str:
        return (
            f"{self.path}:{self.line_number}: direct yaml.safe_load bypasses the "
            "configuration primitive; use sbir_etl.config.yaml_io.read_yaml_mapping "
            "or sbir_etl.config.get_config"
        )


def _safe_load_aliases(tree: ast.AST) -> tuple[set[str], set[str]]:
    """Return aliases for the yaml module and directly imported safe_load function."""

    module_aliases: set[str] = set()
    function_aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "yaml":
                    module_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module == "yaml":
            for alias in node.names:
                if alias.name == "safe_load":
                    function_aliases.add(alias.asname or alias.name)
    return module_aliases, function_aliases


def _is_safe_load_call(
    node: ast.Call,
    *,
    module_aliases: set[str],
    function_aliases: set[str],
) -> bool:
    function = node.func
    if isinstance(function, ast.Name):
        return function.id in function_aliases
    return (
        isinstance(function, ast.Attribute)
        and function.attr == "safe_load"
        and isinstance(function.value, ast.Name)
        and function.value.id in module_aliases
    )


def scan_file(
    path: Path, *, repository_root: Path = REPOSITORY_ROOT
) -> list[ConfigBoundaryViolation]:
    """Find direct ``yaml.safe_load`` calls in one production Python file."""

    relative = path.resolve().relative_to(repository_root.resolve()).as_posix()
    if relative in CANONICAL_YAML_READERS or relative.startswith(IGNORED_PREFIXES):
        return []

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    module_aliases, function_aliases = _safe_load_aliases(tree)
    return [
        ConfigBoundaryViolation(relative, node.lineno)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and _is_safe_load_call(
            node,
            module_aliases=module_aliases,
            function_aliases=function_aliases,
        )
    ]


def tracked_python_files(*, repository_root: Path = REPOSITORY_ROOT) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "*.py"],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return [repository_root / relative for relative in result.stdout.splitlines()]


def scan_repository(*, repository_root: Path = REPOSITORY_ROOT) -> list[ConfigBoundaryViolation]:
    violations: list[ConfigBoundaryViolation] = []
    for path in tracked_python_files(repository_root=repository_root):
        violations.extend(scan_file(path, repository_root=repository_root))
    return sorted(violations, key=lambda violation: (violation.path, violation.line_number))


def main() -> int:
    violations = scan_repository()
    if violations:
        print("Configuration boundary violations were found:")
        print("\n".join(violation.format() for violation in violations))
        return 1
    print("Configuration boundary checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
