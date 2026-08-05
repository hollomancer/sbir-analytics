#!/usr/bin/env python3
"""Prevent duplicate identity implementations outside ``sbir_etl.identity``."""

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
        # Same-work detector scores award titles and abstracts, not company
        # identity; its firm names already go through normalize_name.
        "scripts/data/find_same_work_awards.py",
        # Contract tests compare shared adapters with the upstream scorer implementation.
        "tests/unit/identity/test_company_names.py",
    }
)
CANONICAL_JURISDICTION_FILE = "sbir_etl/identity/geography.py"
CANONICAL_EXACT_AWARD_IDENTITY_FILE = "sbir_etl/identity/exact_awards.py"
EXACT_AWARD_IDENTITY_SYMBOLS = frozenset(
    {"resolve_award_identities", "reconcile_award_identity_attempts"}
)
JURISDICTION_PAIR_MARKERS = frozenset(
    {
        ("ALABAMA", "AL"),
        ("CALIFORNIA", "CA"),
        ("MASSACHUSETTS", "MA"),
        ("NEW YORK", "NY"),
        ("TEXAS", "TX"),
        ("DISTRICT OF COLUMBIA", "DC"),
        ("PUERTO RICO", "PR"),
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


def _jurisdiction_mapping_pairs(node: ast.AST) -> int:
    """Count recognizable name/code pairs in a literal mapping."""

    if not isinstance(node, ast.Dict):
        return 0
    pairs = 0
    for key, value in zip(node.keys, node.values, strict=True):
        if not (
            isinstance(key, ast.Constant)
            and isinstance(key.value, str)
            and isinstance(value, ast.Constant)
            and isinstance(value.value, str)
        ):
            continue
        literal_pair = (key.value.strip().upper(), value.value.strip().upper())
        if (
            literal_pair in JURISDICTION_PAIR_MARKERS
            or literal_pair[::-1] in JURISDICTION_PAIR_MARKERS
        ):
            pairs += 1
    return pairs


def scan_file(
    path: Path, *, repository_root: Path = REPOSITORY_ROOT
) -> list[IdentityBoundaryViolation]:
    """Find direct scorer imports in one unreviewed Python file."""

    relative = path.resolve().relative_to(repository_root.resolve()).as_posix()
    if relative.startswith(("scripts/archive/", "tests/unit/scripts/archive/")):
        return []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations: list[IdentityBoundaryViolation] = []
    for node in ast.walk(tree):
        if relative not in REVIEWED_DIRECT_SCORER_FILES and _uses_direct_rapidfuzz_scorer(node):
            violations.append(
                IdentityBoundaryViolation(
                    path=relative,
                    line_number=getattr(node, "lineno", 0),
                    message=(
                        "direct RapidFuzz scorer bypasses sbir_etl.identity; use the shared "
                        "similarity contract or document a reviewed non-company exception"
                    ),
                )
            )
        if relative != CANONICAL_JURISDICTION_FILE and _jurisdiction_mapping_pairs(node) >= 5:
            violations.append(
                IdentityBoundaryViolation(
                    path=relative,
                    line_number=getattr(node, "lineno", 0),
                    message=(
                        "U.S. jurisdiction map bypasses sbir_etl.identity.geography; "
                        "use a named normalization profile"
                    ),
                )
            )
        if (
            relative != CANONICAL_EXACT_AWARD_IDENTITY_FILE
            and isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
            and node.name in EXACT_AWARD_IDENTITY_SYMBOLS
        ):
            violations.append(
                IdentityBoundaryViolation(
                    path=relative,
                    line_number=node.lineno,
                    message=(
                        "exact award-key resolver bypasses sbir_etl.identity.exact_awards; "
                        "use the versioned primitive"
                    ),
                )
            )
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
