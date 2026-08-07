#!/usr/bin/env python3
"""Enforce the epistemic-tier dependency lattice across first-party modules.

Tier declarations (``EPISTEMIC_TIER`` constants) state how much weight a module
can carry; this check makes their dependency consequences executable, so a
pipelines-tier module cannot quietly grow an exploratory import. Contracts:
docs/steering/epistemic-tiers.md. Spec: specs/epistemic-tier-enforcement/.

Resolution is static and per-file: a module's own top-level constant wins,
otherwise the nearest ancestor package ``__init__.py`` declaration within the
same package root, otherwise ``exploratory``. Declaring is voluntary; only the
consequences of declared tiers are enforced.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOTS = {
    "sbir_etl": Path("sbir_etl"),
    "sbir_ml": Path("packages/sbir-ml/sbir_ml"),
    "sbir_graph": Path("packages/sbir-graph/sbir_graph"),
    "sbir_analytics": Path("packages/sbir-analytics/sbir_analytics"),
    "scripts": Path("scripts"),
}
VALID_TIERS = frozenset({"primitives", "pipelines", "evidence", "exploratory"})
DEFAULT_TIER = "exploratory"
ALLOWED_TIER_IMPORTS = {
    "primitives": frozenset({"primitives"}),
    "pipelines": frozenset({"primitives", "pipelines"}),
    "evidence": frozenset({"primitives", "pipelines", "evidence"}),
    "exploratory": VALID_TIERS,
}

# Importer path -> imported first-party modules whose tier violation is
# tolerated. Every entry needs a reason and a removal condition; an entry that
# stops suppressing a violation fails the run so it cannot linger.
TIER_IMPORT_ALLOWLIST: dict[str, frozenset[str]] = {
    # Contestable CET-relevance screening called inline from a pipelines
    # module. Removed by spec R3/T3.1: the exploratory asset layer calls the
    # screen and passes screened data in as a parameter.
    "sbir_etl/supply_chain/defense_release.py": frozenset(
        {"sbir_etl.supply_chain.nsf_screen"}
    ),
    # Package init re-exports the exploratory screen, so importing the
    # pipelines-tier package imports the screen. Removed by spec R3/T3.2:
    # the re-export is dropped and callers import the module directly.
    "sbir_etl/supply_chain/__init__.py": frozenset(
        {"sbir_etl.supply_chain.nsf_screen"}
    ),
    # The census-facing pair builder carries a lazy in-function import of the
    # exploratory scorer for the non-census ranking path. Removed when the
    # scoring entry point moves into its own exploratory module (tracked in
    # the spec's T1.2 triage notes).
    "packages/sbir-analytics/sbir_analytics/assets/phase_iii_candidates/pairing.py": frozenset(
        {"sbir_analytics.assets.phase_iii_candidates.similarity"}
    ),
    # The NAICS strategy registry registers every strategy, including the
    # exploratory text-inference one, from pipelines-tier machinery. Removed
    # when registration of that strategy moves behind an exploratory
    # composition point or the strategy is validated and relabeled.
    "sbir_etl/enrichers/naics/fiscal/strategies/__init__.py": frozenset(
        {"sbir_etl.enrichers.naics.fiscal.strategies.text_inference"}
    ),
    "sbir_etl/enrichers/naics/fiscal/strategy_registry.py": frozenset(
        {"sbir_etl.enrichers.naics.fiscal.strategies.text_inference"}
    ),
}


@dataclass(frozen=True)
class TierViolation:
    """One forbidden cross-tier import, invalid declaration, or stale entry."""

    path: str
    line_number: int
    message: str

    def format(self) -> str:
        if self.line_number:
            return f"{self.path}:{self.line_number}: {self.message}"
        return f"{self.path}: {self.message}"


@dataclass
class ModuleIndex:
    """Dotted module name -> source file, with cached effective tiers."""

    repository_root: Path
    files_by_module: dict[str, Path] = field(default_factory=dict)
    modules_by_file: dict[Path, str] = field(default_factory=dict)
    _declared: dict[Path, str | None] = field(default_factory=dict)
    _effective: dict[Path, str] = field(default_factory=dict)
    invalid_declarations: list[TierViolation] = field(default_factory=list)

    def add(self, dotted: str, path: Path) -> None:
        self.files_by_module[dotted] = path
        self.modules_by_file[path] = dotted

    def declared_tier(self, path: Path) -> str | None:
        """Return the module's own top-level ``EPISTEMIC_TIER`` constant, if any."""

        if path in self._declared:
            return self._declared[path]
        tier: str | None = None
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            if not (isinstance(target, ast.Name) and target.id == "EPISTEMIC_TIER"):
                continue
            value = node.value
            if isinstance(value, ast.Constant) and value.value in VALID_TIERS:
                tier = value.value
            else:
                relative = path.relative_to(self.repository_root).as_posix()
                choices = ", ".join(sorted(VALID_TIERS))
                self.invalid_declarations.append(
                    TierViolation(
                        relative,
                        node.lineno,
                        f"EPISTEMIC_TIER must be a literal from: {choices}",
                    )
                )
        self._declared[path] = tier
        return tier

    def effective_tier(self, path: Path) -> str:
        """Own constant, else nearest ancestor package default, else exploratory."""

        if path in self._effective:
            return self._effective[path]
        tier = self.declared_tier(path)
        if tier is None:
            dotted = self.modules_by_file[path]
            parts = dotted.split(".")
            # A module file inherits from its package chain; an __init__.py is
            # the package, so its chain starts one level up.
            ancestors = parts[:-1]
            for depth in range(len(ancestors), 0, -1):
                ancestor = ".".join(ancestors[:depth])
                ancestor_path = self.files_by_module.get(ancestor)
                if ancestor_path is None:
                    continue
                declared = self.declared_tier(ancestor_path)
                if declared is not None:
                    tier = declared
                    break
        if tier is None:
            tier = DEFAULT_TIER
        self._effective[path] = tier
        return tier

    def resolve(self, dotted: str) -> Path | None:
        """Longest-prefix match of an imported name onto a first-party file."""

        parts = dotted.split(".")
        for depth in range(len(parts), 0, -1):
            path = self.files_by_module.get(".".join(parts[:depth]))
            if path is not None:
                return path
        return None


def build_index(
    *,
    repository_root: Path = REPOSITORY_ROOT,
    package_roots: dict[str, Path] = PACKAGE_ROOTS,
) -> ModuleIndex:
    """Index every first-party module under the declared package roots."""

    index = ModuleIndex(repository_root=repository_root)
    for package, relative_root in package_roots.items():
        root = repository_root / relative_root
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            relative_parts = path.relative_to(root).with_suffix("").parts
            if relative_parts[-1] == "__init__":
                relative_parts = relative_parts[:-1]
            index.add(".".join((package, *relative_parts)).rstrip("."), path)
    return index


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


def imported_modules(path: Path, dotted: str, index: ModuleIndex) -> list[tuple[str, int]]:
    """Extract first-party import edges, resolving relative and from-imports.

    ``from package import name`` names a submodule at least as often as a
    symbol, and the submodule may sit in a different tier than the package
    ``__init__``; each alias is therefore tried as a module first, falling
    back to the package itself.
    """

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    edges: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            edges.extend((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parts = dotted.split(".")
                package_parts = parts if path.name == "__init__.py" else parts[:-1]
                if node.level - 1 > len(package_parts):
                    continue
                base_parts = (
                    package_parts[: len(package_parts) - (node.level - 1)]
                    if node.level > 1
                    else package_parts
                )
                base = ".".join((*base_parts, *(node.module.split(".") if node.module else ())))
            else:
                base = node.module or ""
            if not base:
                continue
            resolved_any = False
            for alias in node.names:
                candidate = f"{base}.{alias.name}"
                if candidate in index.files_by_module:
                    edges.append((candidate, node.lineno))
                    resolved_any = True
            if not resolved_any:
                edges.append((base, node.lineno))
        elif isinstance(node, ast.Call):
            if dynamic := _literal_dynamic_import(node):
                edges.append(dynamic)
    return edges


def scan_repository(
    *,
    repository_root: Path = REPOSITORY_ROOT,
    package_roots: dict[str, Path] = PACKAGE_ROOTS,
    allowlist: dict[str, frozenset[str]] = TIER_IMPORT_ALLOWLIST,
) -> list[TierViolation]:
    """Check every first-party import edge against the tier dependency policy."""

    index = build_index(repository_root=repository_root, package_roots=package_roots)
    violations: list[TierViolation] = []
    used_allowlist: set[tuple[str, str]] = set()

    for dotted, path in sorted(index.files_by_module.items()):
        importer_tier = index.effective_tier(path)
        allowed = ALLOWED_TIER_IMPORTS[importer_tier]
        relative = path.relative_to(repository_root).as_posix()
        for imported_name, line_number in imported_modules(path, dotted, index):
            target = index.resolve(imported_name)
            if target is None or target == path:
                continue
            imported_tier = index.effective_tier(target)
            if imported_tier in allowed:
                continue
            target_module = index.modules_by_file[target]
            if target_module in allowlist.get(relative, frozenset()):
                used_allowlist.add((relative, target_module))
                continue
            violations.append(
                TierViolation(
                    relative,
                    line_number,
                    f"{importer_tier} module may not import "
                    f"{imported_tier} module {target_module}",
                )
            )

    for allowed_path, modules in sorted(allowlist.items()):
        for module in sorted(modules):
            if (allowed_path, module) not in used_allowlist:
                violations.append(
                    TierViolation(
                        allowed_path,
                        0,
                        f"stale tier allowlist entry for {module} "
                        "(edge absent or no longer a violation)",
                    )
                )

    violations.extend(index.invalid_declarations)
    return sorted(violations, key=lambda item: (item.path, item.line_number, item.message))


def main() -> int:
    violations = scan_repository()
    if violations:
        print("Epistemic tier boundary violations were found:")
        print("\n".join(violation.format() for violation in violations))
        return 1
    print("Epistemic tier boundary checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
