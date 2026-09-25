#!/usr/bin/env python3
"""Reject active references to the retired graph service and package."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

# These paths are evidence about the retirement or frozen historical records.
# Keep this list exact. New archive paths do not become exempt automatically.
ALLOWED_PATHS = frozenset(
    {
        "CHANGELOG.md",
        "archive/neo4j/README.md",
        "docs/archive/deployment/actions-migration-plan.md",
        "docs/archive/development/cleanup-inventory.md",
        "docs/archive/development/source-layout-migration.md",
        "docs/archive/research/research-plan-alignment.md",
        "docs/archive/transition/mvp.md",
        "docs/archive/transition/usaspending-integration.md",
        "docs/decisions/ADR-002-etl-library-extraction.md",
        "docs/decisions/ADR-006-retire-neo4j.md",
        "docs/deployment/neo4j-retirement-cutover.md",
        "scripts/ci/check_retired_neo4j_references.py",
        "specs/archive/codebase-consolidation-refactor/design.md",
        "specs/archive/codebase-consolidation-refactor/requirements.md",
        "specs/archive/codebase-consolidation-refactor/tasks.md",
        "specs/archive/completed-features/form-d-pipeline/requirements.md",
        "specs/archive/completed-features/load-contract-nodes/COMPLETION_RECORD.md",
        "specs/archive/completed-features/load-contract-nodes/design.md",
        "specs/archive/completed-features/load-contract-nodes/requirements.md",
        "specs/archive/completed-features/load-contract-nodes/tasks.md",
        "specs/archive/completed-features/transition_detection/COMPLETION_RECORD.md",
        "specs/archive/completed-features/transition_detection/design.md",
        "specs/archive/completed-features/transition_detection/requirements.md",
        "specs/archive/completed-features/transition_detection/tasks.md",
        "specs/archive/completed-features/ucc1-financing-analysis/design.md",
        "specs/archive/completed-features/ucc1-financing-analysis/requirements.md",
        "specs/archive/completed-features/unify-company-into-organization/design.md",
        "specs/archive/completed-features/unify-company-into-organization/requirements.md",
        "specs/archive/completed-features/unify-company-into-organization/tasks.md",
        "specs/archive/completed-features/unify-graph-node-labels/design.md",
        "specs/archive/completed-features/unify-graph-node-labels/requirements.md",
        "specs/archive/completed-features/unify-graph-node-labels/tasks.md",
        "specs/archive/completed-migrations/openspec-to-kiro-migration/COMPLETION_RECORD.md",
        "specs/archive/completed-migrations/openspec-to-kiro-migration/tasks.md",
        "specs/archive/e2e-testing-enhancement/design.md",
        "specs/archive/e2e-testing-enhancement/requirements.md",
        "specs/archive/e2e-testing-enhancement/tasks.md",
        "specs/archive/superseded/mcp_interface/design.md",
        "specs/archive/superseded/mcp_interface/requirements.md",
        "specs/archive/superseded/mcp_interface/tasks.md",
        "specs/neo4j-retirement/design.md",
        "specs/neo4j-retirement/requirements.md",
        "specs/neo4j-retirement/tasks.md",
        "specs/status.md",
        "studies/sba-annual-report-structural-comparison/reviews/named-reader-review-5.md",
        "tests/unit/scripts/test_check_retired_neo4j_references.py",
    }
)

# The CI and Make invocations name this guard. Only these complete control
# lines are exempt; a prohibited command cannot hide behind a trailing comment.
ALLOWED_CONTROL_LINES = {
    "Makefile": re.compile(
        r"\s*\$\(call run,uv run python "
        r"scripts/ci/check_retired_neo4j_references\.py\)\s*"
    ),
    ".github/workflows/ci.yml": re.compile(
        r"\s*uv run python scripts/ci/check_retired_neo4j_references\.py\s*"
    ),
}

COMMON_PATTERNS = (
    (
        re.compile(r"\b(?:NEO4J_[A-Z0-9_]+|SBIR_ETL__NEO4J(?:__[A-Z0-9_]+)?|SKIP_NEO4J_LOADING)\b"),
        "retired environment key",
    ),
    (re.compile(r"\bbolt(?:\+s)?://", re.IGNORECASE), "retired connection URI"),
    (re.compile(r"\bcypher-shell\b", re.IGNORECASE), "retired database command"),
    (
        re.compile(
            r"\b(?:port|listen|expose|publish)(?:ed|ing)?\b[^\n]{0,40}"
            r"(?<![A-Za-z0-9])(?:7474|7687|17687)(?![A-Za-z0-9])",
            re.IGNORECASE,
        ),
        "retired service port",
    ),
    (
        re.compile(
            r"^\s*-\s*[\"']?(?:(?:127\.0\.0\.1|\$\{[^}]+\}):)?"
            r"(?:7474|7687|17687)(?::(?:7474|7687|17687))?[\"']?\s*$"
        ),
        "retired Compose port mapping",
    ),
    (
        re.compile(
            r"(?:packages/sbir-graph|scripts/neo4j|\.github/actions/(?:start|stop|wait)-neo4j)"
        ),
        "retired path",
    ),
    (
        re.compile(r"scripts/data/(?:reset_neo4j|run_neo4j)[A-Za-z0-9_./-]*"),
        "retired loader command",
    ),
    (re.compile(r"^\s*neo4j:\s*$", re.IGNORECASE), "retired Compose service"),
    (
        re.compile(r"\b(?:docker\s+(?:compose|run|exec)|make)\b[^\n]*\bneo4j\b"),
        "retired service command",
    ),
    (
        re.compile(r"\bpytest\b[^\n]*\s-m\s+[\"']?neo4j\b", re.IGNORECASE),
        "retired test-marker command",
    ),
    (
        re.compile(r"\b(?:pip|uv)\s+(?:install|add)\b[^\n]*\bneo4j\b", re.IGNORECASE),
        "retired dependency command",
    ),
)

IMPORT_PATTERN = (
    re.compile(r"^\s*(?:from|import)\s+(?:neo4j|sbir_graph)(?:\b|\.)"),
    "retired graph import",
)

DOC_PATTERNS = COMMON_PATTERNS + (IMPORT_PATTERN,)

CODE_PATTERNS = DOC_PATTERNS + (
    (re.compile(r"\bsbir_graph\.[A-Za-z_]"), "retired graph package"),
    (re.compile(r"\bNeo4j[A-Z][A-Za-z0-9_]*\b"), "retired graph symbol"),
    (re.compile(r"\bneo4j_[a-z][A-Za-z0-9_]*\b"), "retired graph symbol"),
    (re.compile(r"\.neo4j\b"), "retired graph configuration"),
    (re.compile(r"[\"']neo4j[\"']\s*:"), "retired graph configuration"),
    (
        re.compile(r"[\"'](?:neo4j(?:\[[^]]+\])?|sbir-graph)(?:[<>=~!][^\"']*)?[\"']"),
        "retired graph dependency",
    ),
    (
        re.compile(r"^\s*neo4j(?:\[[^]]+\])?\s*(?:[<>=~!]|$)", re.IGNORECASE),
        "retired graph dependency",
    ),
)


@dataclass(frozen=True)
class Violation:
    """One prohibited reference with stable CI output."""

    path: str
    line_number: int
    message: str
    line: str

    def format(self) -> str:
        return f"{self.path}:{self.line_number}: {self.message}: {self.line.strip()}"


def tracked_files(repository_root: Path = REPOSITORY_ROOT) -> list[Path]:
    """Return existing git-tracked files."""

    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return [
        repository_root / relative
        for relative in result.stdout.split("\0")
        if relative and (repository_root / relative).is_file()
    ]


def _relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _patterns_for(relative: str) -> tuple[tuple[re.Pattern[str], str], ...]:
    # Public and technical prose can name the retired system when explaining
    # history. Executable paths, credentials, ports, and commands remain banned.
    if relative.endswith((".md", ".rst")):
        return DOC_PATTERNS
    return CODE_PATTERNS


def scan_paths(paths: list[Path], *, root: Path = REPOSITORY_ROOT) -> list[Violation]:
    """Return prohibited active references from ``paths``."""

    violations: list[Violation] = []
    for path in paths:
        relative = _relative(path, root)
        if relative in ALLOWED_PATHS:
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        patterns = _patterns_for(relative)
        allowed_control_line = ALLOWED_CONTROL_LINES.get(relative)
        for line_number, line in enumerate(lines, 1):
            if allowed_control_line is not None and allowed_control_line.fullmatch(line):
                continue
            for pattern, message in patterns:
                if pattern.search(line):
                    violations.append(Violation(relative, line_number, message, line))
                    break
    return sorted(violations, key=lambda item: (item.path, item.line_number, item.message))


def scan(repository_root: Path = REPOSITORY_ROOT) -> list[Violation]:
    """Scan all tracked files in the repository."""

    return scan_paths(tracked_files(repository_root), root=repository_root)


def main() -> int:
    violations = scan()
    if violations:
        print("Active references to the retired graph runtime were found:")
        print("\n".join(violation.format() for violation in violations))
        return 1
    print("Retired graph reference check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
