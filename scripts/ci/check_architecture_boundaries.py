#!/usr/bin/env python3
"""Enforce the repository's first-party Python dependency direction.

The package layout is intentionally layered.  This check makes that direction
an executable contract so a convenient local import cannot quietly turn into a
new architectural back-edge.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FIRST_PARTY_PACKAGES = frozenset({"sbir_etl", "sbir_ml", "sbir_graph", "sbir_analytics"})
PACKAGE_ROOTS = {
    "sbir_etl": Path("sbir_etl"),
    "sbir_ml": Path("packages/sbir-ml/sbir_ml"),
    "sbir_graph": Path("packages/sbir-graph/sbir_graph"),
    "sbir_analytics": Path("packages/sbir-analytics/sbir_analytics"),
}
ALLOWED_FIRST_PARTY_IMPORTS = {
    "sbir_etl": frozenset(),
    "sbir_ml": frozenset({"sbir_etl"}),
    "sbir_graph": frozenset(),
    "sbir_analytics": frozenset({"sbir_etl", "sbir_ml", "sbir_graph"}),
}


@dataclass(frozen=True)
class BoundaryViolation:
    """One forbidden first-party import."""

    path: str
    line_number: int
    source_package: str
    imported_module: str

    def format(self) -> str:
        return (
            f"{self.path}:{self.line_number}: {self.source_package} may not import "
            f"{self.imported_module}"
        )


def _literal_dynamic_import(node: ast.Call) -> tuple[str, int] | None:
    """Return literal ``import_module``/``__import__`` targets when visible to AST."""

    is_import_module = (
        isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "importlib"
        and node.func.attr == "import_module"
    ) or (isinstance(node.func, ast.Name) and node.func.id == "import_module")
    is_dunder_import = isinstance(node.func, ast.Name) and node.func.id == "__import__"
    if not (is_import_module or is_dunder_import) or not node.args:
        return None
    argument = node.args[0]
    if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
        return argument.value, node.lineno
    return None


def imported_modules(path: Path) -> list[tuple[str, int]]:
    """Extract absolute static imports and literal dynamic imports from ``path``."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imports.append((node.module, node.lineno))
        elif isinstance(node, ast.Call):
            if dynamic_import := _literal_dynamic_import(node):
                imports.append(dynamic_import)
    return imports


def scan_package(
    source_package: str,
    source_root: Path,
    *,
    repository_root: Path = REPOSITORY_ROOT,
) -> list[BoundaryViolation]:
    """Find forbidden imports below one first-party source root."""

    allowed = ALLOWED_FIRST_PARTY_IMPORTS[source_package]
    violations: list[BoundaryViolation] = []
    for path in sorted(source_root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        relative = path.resolve().relative_to(repository_root.resolve()).as_posix()
        for imported_module, line_number in imported_modules(path):
            target = imported_module.split(".", 1)[0]
            if target == "scripts":
                violations.append(
                    BoundaryViolation(relative, line_number, source_package, imported_module)
                )
            elif (
                target in FIRST_PARTY_PACKAGES
                and target != source_package
                and target not in allowed
            ):
                violations.append(
                    BoundaryViolation(relative, line_number, source_package, imported_module)
                )
    return violations


def scan_repository(*, repository_root: Path = REPOSITORY_ROOT) -> list[BoundaryViolation]:
    """Scan every first-party package using the declared dependency policy."""

    violations: list[BoundaryViolation] = []
    for source_package, relative_root in PACKAGE_ROOTS.items():
        violations.extend(
            scan_package(
                source_package,
                repository_root / relative_root,
                repository_root=repository_root,
            )
        )
    return sorted(violations, key=lambda item: (item.path, item.line_number))


def main() -> int:
    violations = scan_repository()
    if violations:
        print("First-party architecture boundary violations were found:")
        print("\n".join(violation.format() for violation in violations))
        return 1
    print("Architecture boundary checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
