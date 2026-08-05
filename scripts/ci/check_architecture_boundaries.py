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

# The server download jobs landed while this guard was in review. They wrap
# pre-existing CLI implementations that have not yet been promoted into a
# package. Keep the exceptions exact so the guard prevents any additional
# package-to-scripts dependencies while that migration is completed.
TRANSITIONAL_SCRIPT_IMPORTS = {
    "packages/sbir-analytics/sbir_analytics/assets/jobs/source_downloads.py": frozenset(
        {
            "scripts.data.download_sam_gov",
            "scripts.data.download_sbir",
            "scripts.data.download_uspto",
            "scripts.data.download_uspto_browser",
            "scripts.usaspending.download_database",
        }
    )
}

# Package code also reached three scripts by spawning a Python subprocess. An
# import-only guard cannot see those dependency edges, so keep the temporary
# execution bridges just as exact as the import bridge above. Each entry is
# removed when its script implementation is exposed through a package API and
# the package caller invokes that API directly.
TRANSITIONAL_SCRIPT_EXECUTIONS = {
    "packages/sbir-analytics/sbir_analytics/assets/transition_report.py": frozenset(
        {"scripts/data/build_tech_area_cohort.py"}
    ),
    "packages/sbir-analytics/sbir_analytics/assets/jobs/weekly_awards_report.py": frozenset(
        {"scripts/data/weekly_awards_report.py"}
    ),
    "packages/sbir-analytics/sbir_analytics/assets/jobs/phase_transition_archive.py": (
        frozenset({"scripts/phase_transition_analysis.py"})
    ),
}


@dataclass(frozen=True)
class BoundaryViolation:
    """One forbidden first-party import."""

    path: str
    line_number: int
    source_package: str
    imported_module: str
    dependency_kind: str = "import"

    def format(self) -> str:
        action = "import" if self.dependency_kind == "import" else "execute"
        return (
            f"{self.path}:{self.line_number}: {self.source_package} may not {action} "
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


def _is_subprocess_call(node: ast.Call) -> bool:
    return (
        isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "subprocess"
        and node.func.attr in {"call", "check_call", "check_output", "Popen", "run"}
    )


def _literal_assignments(tree: ast.AST) -> dict[str, ast.AST]:
    """Map single-target assigned names to their value expressions.

    Callers routinely build the command in a local before spawning it
    (``cmd = [sys.executable, str(script)]``; ``subprocess.run(cmd)``), so
    inspecting only the call arguments would miss the path. A name assigned
    more than once is dropped rather than guessed at.
    """

    assignments: dict[str, ast.AST] = {}
    shadowed: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        if target.id in assignments:
            shadowed.add(target.id)
            continue
        assignments[target.id] = node.value
    for name in shadowed:
        del assignments[name]
    return assignments


def _path_literal_parts(
    node: ast.AST,
    assignments: dict[str, ast.AST] | None = None,
    _seen: frozenset[str] = frozenset(),
) -> list[str]:
    """Return literal pieces of a ``Path`` division or command argument."""

    def recurse(child: ast.AST, seen: frozenset[str] = _seen) -> list[str]:
        return _path_literal_parts(child, assignments, seen)

    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.Name) and assignments is not None:
        if node.id in _seen or node.id not in assignments:
            return []
        return _path_literal_parts(assignments[node.id], assignments, _seen | {node.id})
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return recurse(node.left) + recurse(node.right)
    if isinstance(node, (ast.List, ast.Tuple)):
        parts: list[str] = []
        for element in node.elts:
            parts.extend(recurse(element))
        return parts
    if isinstance(node, ast.Call):
        parts: list[str] = []
        for argument in node.args:
            parts.extend(recurse(argument))
        return parts
    return []


def _argv_elements(node: ast.AST, assignments: dict[str, ast.AST]) -> list[ast.AST]:
    """Split a command argument into the expressions worth testing on their own.

    An argv list is one argument but many paths. Flattening it would join the
    script with the flags that follow it (``scripts/x.py/--area/q``), so each
    element is tested separately; a bare string command is tested whole.
    """

    resolved = node
    seen: set[str] = set()
    while isinstance(resolved, ast.Name) and resolved.id in assignments:
        if resolved.id in seen:
            break
        seen.add(resolved.id)
        resolved = assignments[resolved.id]
    if isinstance(resolved, (ast.List, ast.Tuple)):
        return list(resolved.elts)
    return [resolved]


def _script_target(node: ast.AST, assignments: dict[str, ast.AST] | None = None) -> str | None:
    """Normalize a literal path expression to a repository ``scripts/*.py`` target."""

    pieces = _path_literal_parts(node, assignments)
    for piece in pieces:
        normalized = piece.replace("\\", "/").strip()
        marker = normalized.find("scripts/")
        if marker >= 0 and normalized[marker:].endswith(".py"):
            return normalized[marker:]

    normalized_parts = [piece.strip("/\\") for piece in pieces if piece.strip("/\\")]
    if "scripts" not in normalized_parts:
        return None
    scripts_index = normalized_parts.index("scripts")
    candidate = "/".join(normalized_parts[scripts_index:])
    return candidate if candidate.endswith(".py") else None


def executed_script_paths(path: Path) -> list[tuple[str, int]]:
    """Extract literal repository Python scripts invoked through ``subprocess``.

    Only the arguments of a ``subprocess`` call are inspected, resolved through
    single-assignment locals. Detection stays literal: a path assembled with
    ``os.path.join``, rebound more than once, or returned from a helper is not
    visible to static analysis. This accepted limit mirrors the import guard;
    document any such pattern in the transitional allowlist so it is not
    mistaken for a gap in the check.
    """

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    assignments = _literal_assignments(tree)
    targets: dict[str, int] = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and _is_subprocess_call(node)):
            continue
        for argument in (*node.args, *(keyword.value for keyword in node.keywords)):
            for element in _argv_elements(argument, assignments):
                if target := _script_target(element, assignments):
                    targets.setdefault(target, node.lineno)
    return sorted(targets.items(), key=lambda item: (item[1], item[0]))


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
                if imported_module in TRANSITIONAL_SCRIPT_IMPORTS.get(relative, ()):
                    continue
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
        for script_target, line_number in executed_script_paths(path):
            if script_target in TRANSITIONAL_SCRIPT_EXECUTIONS.get(relative, ()):
                continue
            violations.append(
                BoundaryViolation(
                    relative,
                    line_number,
                    source_package,
                    script_target,
                    dependency_kind="execute",
                )
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
