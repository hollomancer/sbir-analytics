#!/usr/bin/env python3
"""Prevent unreviewed company-name scoring outside ``sbir_etl.identity``."""

import ast
import subprocess
from dataclasses import dataclass
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
REVIEWED_DIRECT_SCORER_FILES = frozenset(
    {
        "sbir_etl/identity/company_names.py",
        # PatentAssignmentTransformer scores grant-number strings, not company identity.
        "sbir_etl/transformers/patent_transformer.py",
        # Form D confidence compares principal-investigator and related-person names.
        "sbir_etl/enrichers/sec_edgar/form_d_scoring.py",
        # Contract tests compare shared adapters with the upstream scorer implementation.
        "tests/unit/identity/test_company_names.py",
    }
)


@dataclass(frozen=True)
class IdentityBoundaryViolation:
    path: str
    line_number: int
    message: str

    def format(self) -> str:
        return f"{self.path}:{self.line_number}: {self.message}"


def _uses_direct_rapidfuzz_scorer(node: ast.AST) -> bool:
    if isinstance(node, ast.ImportFrom):
        if node.module == "rapidfuzz" and any(alias.name == "fuzz" for alias in node.names):
            return True
        return bool(node.module and node.module.startswith("rapidfuzz.distance"))
    # ``import rapidfuzz`` reaches fuzz and distance through attribute access, so
    # it bypasses the guard unless the bare package import is flagged too.
    # ``rapidfuzz.process`` stays allowed for the same reason ``from rapidfuzz
    # import process`` does: it drives the search while the scorer is supplied
    # from ``sbir_etl.identity``.
    return isinstance(node, ast.Import) and any(
        alias.name == "rapidfuzz" or alias.name.startswith(("rapidfuzz.fuzz", "rapidfuzz.distance"))
        for alias in node.names
    )


def scan_file(
    path: Path, *, repository_root: Path = REPOSITORY_ROOT
) -> list[IdentityBoundaryViolation]:
    """Find direct scorer imports in one unreviewed Python file."""

    relative = path.resolve().relative_to(repository_root.resolve()).as_posix()
    if relative in REVIEWED_DIRECT_SCORER_FILES or relative.startswith(
        ("scripts/archive/", "tests/unit/scripts/archive/")
    ):
        return []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        IdentityBoundaryViolation(
            path=relative,
            line_number=node.lineno,
            message=(
                "direct RapidFuzz scorer bypasses sbir_etl.identity; use the shared "
                "similarity contract or document a reviewed non-company exception"
            ),
        )
        for node in ast.walk(tree)
        if _uses_direct_rapidfuzz_scorer(node)
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


def scan_repository(*, repository_root: Path = REPOSITORY_ROOT) -> list[IdentityBoundaryViolation]:
    violations: list[IdentityBoundaryViolation] = []
    for path in tracked_python_files(repository_root=repository_root):
        violations.extend(scan_file(path, repository_root=repository_root))
    return sorted(violations, key=lambda violation: (violation.path, violation.line_number))


def main() -> int:
    violations = scan_repository()
    if violations:
        print("Company identity boundary violations were found:")
        print("\n".join(violation.format() for violation in violations))
        return 1
    print("Company identity boundary checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
