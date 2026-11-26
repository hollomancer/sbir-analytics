#!/usr/bin/env python3
"""Prevent production code from bypassing the shared configuration reader.

Two bypasses are checked: direct PyYAML document reads, and direct environment
reads of ``SBIR_ETL__PATHS__*`` variables (use ``sbir_etl.config.loader.data_root``
or ``get_config`` instead).
"""

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
CANONICAL_PATHS_ENV_READERS = frozenset({"sbir_etl/config/loader.py"})
PATHS_ENV_PREFIX = "SBIR_ETL__PATHS__"
# Every PyYAML entry point that parses a document. Matching only ``safe_load``
# would let the pre-``safe_load`` idiom ``yaml.load(f, Loader=yaml.SafeLoader)``
# through, which is the form most likely to be written from habit.
PYYAML_READERS = frozenset(
    {
        "safe_load",
        "safe_load_all",
        "load",
        "load_all",
        "full_load",
        "full_load_all",
        "unsafe_load",
        "unsafe_load_all",
    }
)


@dataclass(frozen=True)
class ConfigBoundaryViolation:
    """One direct PyYAML read outside the configuration primitive."""

    path: str
    line_number: int
    function_name: str

    def format(self) -> str:
        return (
            f"{self.path}:{self.line_number}: direct yaml.{self.function_name} bypasses the "
            "configuration primitive; use sbir_etl.config.yaml_io.read_yaml_mapping "
            "or sbir_etl.config.get_config"
        )


@dataclass(frozen=True)
class PathsEnvViolation:
    """One direct environment read of a ``SBIR_ETL__PATHS__*`` variable outside the loader."""

    path: str
    line_number: int
    variable: str

    def format(self) -> str:
        return (
            f"{self.path}:{self.line_number}: direct environment read of {self.variable} "
            "bypasses the configuration primitive; use sbir_etl.config.loader.data_root "
            "or sbir_etl.config.get_config"
        )


def _paths_env_name(node: ast.expr | None, constants: dict[str, str]) -> str | None:
    """Return the ``SBIR_ETL__PATHS__*`` name this expression holds, or None."""

    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        value = node.value
    elif isinstance(node, ast.Name) and node.id in constants:
        value = constants[node.id]
    else:
        return None
    return value if value.startswith(PATHS_ENV_PREFIX) else None


def _paths_env_reads(tree: ast.Module) -> list[tuple[int, str]]:
    """Return (line, variable) for each read of a ``SBIR_ETL__PATHS__*`` variable.

    Matches ``os.getenv(X)``, ``os.environ.get(X)``, ``os.environ[X]``, and the
    same calls through ``from os import getenv, environ``. ``X`` is a string
    literal or a module-level name bound to one.
    """

    constants = {
        target.id: node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    os_aliases: set[str] = set()
    getenv_aliases: set[str] = set()
    environ_aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "os":
                    os_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module == "os":
            for alias in node.names:
                if alias.name == "getenv":
                    getenv_aliases.add(alias.asname or alias.name)
                elif alias.name == "environ":
                    environ_aliases.add(alias.asname or alias.name)

    def is_environ(node: ast.expr) -> bool:
        if isinstance(node, ast.Name):
            return node.id in environ_aliases
        return (
            isinstance(node, ast.Attribute)
            and node.attr == "environ"
            and isinstance(node.value, ast.Name)
            and node.value.id in os_aliases
        )

    def is_getenv(node: ast.expr) -> bool:
        if isinstance(node, ast.Name):
            return node.id in getenv_aliases
        if isinstance(node, ast.Attribute) and node.attr == "getenv":
            return isinstance(node.value, ast.Name) and node.value.id in os_aliases
        return isinstance(node, ast.Attribute) and node.attr == "get" and is_environ(node.value)

    reads: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        key: ast.expr | None = None
        if isinstance(node, ast.Call) and node.args and is_getenv(node.func):
            key = node.args[0]
        elif (
            isinstance(node, ast.Subscript)
            and isinstance(node.ctx, ast.Load)
            and is_environ(node.value)
        ):
            key = node.slice
        variable = _paths_env_name(key, constants)
        if variable is not None and isinstance(node, ast.expr):
            reads.append((node.lineno, variable))
    return reads


def _reader_aliases(tree: ast.AST) -> tuple[set[str], dict[str, str]]:
    """Return yaml module aliases and directly imported reader aliases by local name."""

    module_aliases: set[str] = set()
    function_aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "yaml":
                    module_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module == "yaml":
            for alias in node.names:
                if alias.name in PYYAML_READERS:
                    function_aliases[alias.asname or alias.name] = alias.name
    return module_aliases, function_aliases


def _read_function_name(
    node: ast.Call,
    *,
    module_aliases: set[str],
    function_aliases: dict[str, str],
) -> str | None:
    """Return the PyYAML reader this call invokes, or None when it is not one."""

    function = node.func
    if isinstance(function, ast.Name):
        return function_aliases.get(function.id)
    if (
        isinstance(function, ast.Attribute)
        and function.attr in PYYAML_READERS
        and isinstance(function.value, ast.Name)
        and function.value.id in module_aliases
    ):
        return function.attr
    return None


def scan_file(
    path: Path, *, repository_root: Path = REPOSITORY_ROOT
) -> list[ConfigBoundaryViolation | PathsEnvViolation]:
    """Find direct PyYAML document reads and paths-variable reads in one production file."""

    relative = path.resolve().relative_to(repository_root.resolve()).as_posix()
    if relative.startswith(IGNORED_PREFIXES):
        return []

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations: list[ConfigBoundaryViolation | PathsEnvViolation] = []
    if relative not in CANONICAL_PATHS_ENV_READERS:
        violations.extend(
            PathsEnvViolation(relative, line, variable) for line, variable in _paths_env_reads(tree)
        )
    if relative in CANONICAL_YAML_READERS:
        return violations

    module_aliases, function_aliases = _reader_aliases(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function_name = _read_function_name(
            node,
            module_aliases=module_aliases,
            function_aliases=function_aliases,
        )
        if function_name is not None:
            violations.append(ConfigBoundaryViolation(relative, node.lineno, function_name))
    return violations


def tracked_python_files(*, repository_root: Path = REPOSITORY_ROOT) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "*.py"],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return [repository_root / relative for relative in result.stdout.splitlines()]


def scan_repository(
    *, repository_root: Path = REPOSITORY_ROOT
) -> list[ConfigBoundaryViolation | PathsEnvViolation]:
    violations: list[ConfigBoundaryViolation | PathsEnvViolation] = []
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
