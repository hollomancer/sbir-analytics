#!/usr/bin/env python3
"""Prevent duplicate identity implementations outside ``sbir_etl.identity``."""

import ast
import re
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
CANONICAL_COMPANY_NAME_FILE = "sbir_etl/identity/company_names.py"
# Function names that read as a company-name normalizer. A function matching
# this pattern must delegate to the versioned primitive rather than carry its
# own rule, so a new fork cannot reach main without a named profile.
COMPANY_NAME_FUNCTION_PATTERN = re.compile(r"^_{0,2}(norm|normalize|normalized)(_[a-z0-9]+)*_name$")
COMPANY_NAME_PRIMITIVE_SYMBOLS = frozenset({"normalize_company_name", "CompanyNameProfile"})
# Normalizers that do not resolve company identity. Each entry is reviewed:
# person names and U.S. state names are different concepts with their own
# contracts, so they do not belong to a company-name profile.
REVIEWED_NON_COMPANY_NORMALIZERS = frozenset(
    {
        # Form D confidence compares principal-investigator and related-person names.
        ("sbir_etl/enrichers/sec_edgar/form_d_scoring.py", "_normalize_name"),
        # State names resolve through sbir_etl.identity.geography, not a company profile.
        ("sbir_etl/transformers/fiscal/refresh_state_rates.py", "_normalize_state_name"),
        # STTR spinout linkage scores inventor and principal-investigator names.
        ("scripts/sttr_spinout_linkage/kernel.py", "_normalize_person_name"),
    }
)
CANONICAL_IDENTIFIER_FILE = "sbir_etl/utils/identifiers.py"
# Function names that read as a UEI or DUNS cleaner. These identifiers have one
# implementation, the versioned primitive in sbir_etl.utils.identifiers; a new
# cleaner must use normalize_uei or normalize_duns with a named DunsProfile.
IDENTIFIER_CLEANER_FUNCTION_PATTERN = re.compile(
    r"^_{0,2}(clean|norm|normalize|normalized)_?(uei|duns)$"
)
REVIEWED_IDENTIFIER_CLEANER_FILES = frozenset(
    {
        # Frozen canonical-merge implementation; its output is pinned by golden files.
        "sbir_etl/identity/canonical_merge.py",
    }
)
REVIEWED_IDENTIFIER_CLEANERS = frozenset(
    {
        # Treats any populated UEI text as present evidence for verification tiers,
        # and its tests use 13-character UEIs. Migrating changes T1 assignment, so it
        # needs its own reviewed change.
        ("sbir_etl/ot_consortium/classifier.py", "_norm_uei"),
    }
)
# Keeping every digit of a value is not a DUNS rule: 12345678.0 becomes the
# different DUNS 123456780, and 123456789A becomes 123456789. A digit-only
# extraction is flagged when it touches a name or column that says "duns", or
# when a local helper that does one is applied to such a value.
DIGIT_ONLY_PATTERNS = frozenset({r"\D", r"\D+", "[^0-9]", "[^0-9]+", r"[^\d]", r"[^\d]+"})
REVIEWED_DUNS_DIGIT_EXTRACTION_FILES = frozenset(
    {
        # Known instances of the same pattern. Moving them to DUNS_V2 changes
        # their lookup keys, so each needs its own reviewed change.
        "sbir_etl/extractors/sbir_gov_api.py",
        "scripts/data/build_supplier_share_census.py",
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


def _forks_company_name_normalization(node: ast.AST) -> bool:
    """Return True for a company-name normalizer that carries its own rule.

    A function is treated as delegating when it names the primitive, names a
    profile, or calls a sibling normalizer that must itself delegate.
    """

    if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
        return False
    if not COMPANY_NAME_FUNCTION_PATTERN.match(node.name):
        return False
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id in COMPANY_NAME_PRIMITIVE_SYMBOLS:
            return False
        if isinstance(child, ast.Attribute) and child.attr in COMPANY_NAME_PRIMITIVE_SYMBOLS:
            return False
        if (
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and COMPANY_NAME_FUNCTION_PATTERN.match(child.func.id)
        ):
            return False
    return True


def _is_digit_only_extraction(node: ast.AST) -> bool:
    """Return True for ``re.sub(r"\\D", "", x)`` or ``"".join(c for c in x if c.isdigit())``."""

    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr in {"sub", "replace"} and len(node.args) >= 2:
        pattern, replacement = node.args[0], node.args[1]
        return (
            isinstance(pattern, ast.Constant)
            and pattern.value in DIGIT_ONLY_PATTERNS
            and isinstance(replacement, ast.Constant)
            and replacement.value == ""
        )
    if node.func.attr == "join" and len(node.args) == 1:
        comprehension = node.args[0]
        if isinstance(comprehension, (ast.GeneratorExp, ast.ListComp)):
            return any(
                isinstance(condition, ast.Call)
                and isinstance(condition.func, ast.Attribute)
                and condition.func.attr == "isdigit"
                for generator in comprehension.generators
                for condition in generator.ifs
            )
    return False


def _mentions_duns(node: ast.AST) -> bool:
    for child in ast.walk(node):
        text = None
        if isinstance(child, ast.Name):
            text = child.id
        elif isinstance(child, ast.Attribute):
            text = child.attr
        elif isinstance(child, ast.Constant) and isinstance(child.value, str):
            text = child.value
        if text is not None and "duns" in text.lower():
            return True
    return False


def _duns_digit_extraction_lines(tree: ast.AST) -> set[int]:
    """Return lines where a DUNS value is cleaned by keeping only its digits."""

    lines: set[int] = set()
    digit_helpers: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            extractions = [child for child in ast.walk(node) if _is_digit_only_extraction(child)]
            if extractions:
                digit_helpers.add(node.name)
            if "duns" in node.name.lower():
                lines.update(getattr(child, "lineno", 0) for child in extractions)
        elif _is_digit_only_extraction(node) and _mentions_duns(node):
            lines.add(getattr(node, "lineno", 0))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callees = [node.func, *node.args, *(keyword.value for keyword in node.keywords)]
        uses_helper = any(
            isinstance(callee, ast.Name) and callee.id in digit_helpers for callee in callees
        )
        if uses_helper and _mentions_duns(node):
            lines.add(node.lineno)
    return lines


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
        if (
            relative != CANONICAL_COMPANY_NAME_FILE
            and isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
            and (relative, node.name) not in REVIEWED_NON_COMPANY_NORMALIZERS
            and _forks_company_name_normalization(node)
        ):
            violations.append(
                IdentityBoundaryViolation(
                    path=relative,
                    line_number=node.lineno,
                    message=(
                        f"{node.name} normalizes company names outside "
                        "sbir_etl.identity.company_names; call normalize_company_name with a "
                        "named CompanyNameProfile, or add a reviewed non-company exception"
                    ),
                )
            )
        if (
            relative != CANONICAL_IDENTIFIER_FILE
            and relative not in REVIEWED_IDENTIFIER_CLEANER_FILES
            and isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
            and IDENTIFIER_CLEANER_FUNCTION_PATTERN.match(node.name)
            and (relative, node.name) not in REVIEWED_IDENTIFIER_CLEANERS
        ):
            violations.append(
                IdentityBoundaryViolation(
                    path=relative,
                    line_number=node.lineno,
                    message=(
                        f"{node.name} cleans a UEI or DUNS outside sbir_etl.utils.identifiers; "
                        "call normalize_uei, or normalize_duns with a named DunsProfile"
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
    if (
        relative != CANONICAL_IDENTIFIER_FILE
        and relative not in REVIEWED_IDENTIFIER_CLEANER_FILES
        and relative not in REVIEWED_DUNS_DIGIT_EXTRACTION_FILES
    ):
        violations.extend(
            IdentityBoundaryViolation(
                path=relative,
                line_number=line_number,
                message=(
                    "DUNS cleaned by keeping only its digits; call normalize_duns with "
                    "profile=DunsProfile.DUNS_V2"
                ),
            )
            for line_number in sorted(_duns_digit_extraction_lines(tree))
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
