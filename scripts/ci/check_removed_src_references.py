#!/usr/bin/env python3
"""Reject executable automation references to the removed ``src/`` source root."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCANNED_PREFIXES = (".github/", "scripts/", "sbir_etl/", "packages/", "tests/")
SCANNED_FILES = {"Makefile", ".pre-commit-config.yaml"}
EXCLUDED_HISTORICAL_DOCUMENTS = {"docs/decisions/ADR-002-etl-library-extraction.md"}
PATTERNS = (
    re.compile(r"--cov=src(?:\b|/)"),
    re.compile(r"\bsrc\.definitions(?:_ml)?\b"),
    re.compile(r"(?:^|[\s'\"(=:/])src/[A-Za-z0-9_.*?/-]+"),
)


def tracked_automation_files() -> list[Path]:
    """Return tracked automation files covered by the source-root policy."""
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    paths = []
    for relative in result.stdout.splitlines():
        if relative in EXCLUDED_HISTORICAL_DOCUMENTS or relative == __file_relative__():
            continue
        if relative in SCANNED_FILES or relative.startswith(SCANNED_PREFIXES):
            paths.append(REPOSITORY_ROOT / relative)
    return paths


def __file_relative__() -> str:
    return str(Path(__file__).resolve().relative_to(REPOSITORY_ROOT))


def main() -> int:
    """Report removed source-root references and return a failing status when found."""
    violations: list[str] = []
    for path in tracked_automation_files():
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(lines, 1):
            if any(pattern.search(line) for pattern in PATTERNS):
                violations.append(
                    f"{path.relative_to(REPOSITORY_ROOT)}:{line_number}: {line.strip()}"
                )

    if violations:
        print("Executable references to the removed src/ source root were found:")
        print("\n".join(violations))
        return 1

    print("No executable references to the removed src/ source root found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
