#!/usr/bin/env python3
"""Repository hygiene checks for stale paths and archive dependencies."""

from __future__ import annotations

from dataclasses import dataclass
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
AUTOMATION_PREFIXES = (".github/", "scripts/", "sbir_etl/", "packages/", "tests/")
SCANNED_FILES = {"Makefile", ".pre-commit-config.yaml"}
EXCLUDED_HISTORICAL_DOCUMENTS = {"docs/decisions/ADR-002-etl-library-extraction.md"}
EXCLUDED_SCAN_FILES = {
    "tests/unit/scripts/test_repository_hygiene.py",
}
REMOVED_SRC_PATTERNS = (
    re.compile(r"--cov=src(?:\b|/)"),
    re.compile(r"\bsrc\.definitions(?:_ml)?\b"),
    re.compile(r"(?:^|[\s'\"(=:/])src/[A-Za-z0-9_.*?/-]+"),
)
LIVE_DOC_DIR_PREFIXES = ("docs/steering/", "docs/development/", "docs/testing/")
LIVE_DOC_STALE_PATTERNS = (
    (
        re.compile(r"--cov=src(?:\b|/)"),
        "removed source-root coverage target",
    ),
    (
        re.compile(r"\bsrc\.[A-Za-z0-9_.]+\b"),
        "removed source-root Python module path",
    ),
    (
        re.compile(r"(?:^|[\s'\"(=:/`])src/[A-Za-z0-9_][A-Za-z0-9_.*?/-]*"),
        "removed source-root file path",
    ),
    (
        re.compile(r"\bpoetry\s+run\b"),
        "Poetry command in live docs",
    ),
    (
        re.compile(
            r"(?:^|[\s'\"(=:/])(?:python\s+-m\s+)?black\s+(?:--|[A-Za-z0-9_.-]+)"
        ),
        "Black command in live docs",
    ),
)
ARCHIVE_REFERENCE_PATTERNS = (
    re.compile(r"scripts/archive(?:/|\b)"),
    re.compile(r"scripts\.archive(?:\.|\b)"),
)
MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]]+\]\(([^)]+)\)")


@dataclass(frozen=True)
class Violation:
    """A repository hygiene violation with enough context for CI output."""

    path: str
    line_number: int
    message: str
    line: str

    def format(self) -> str:
        """Format a violation for stable, grep-friendly CI logs."""
        return f"{self.path}:{self.line_number}: {self.message}: {self.line.strip()}"


def tracked_automation_files() -> list[Path]:
    """Return tracked automation files covered by the source-root policy."""
    return [path for path in tracked_files() if _is_automation_file(_relative_to_repository(path))]


def tracked_files() -> list[Path]:
    """Return tracked repository files."""
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [REPOSITORY_ROOT / relative for relative in result.stdout.splitlines()]


def __file_relative__() -> str:
    return str(Path(__file__).resolve().relative_to(REPOSITORY_ROOT))


def _relative_to_repository(path: Path, root: Path = REPOSITORY_ROOT) -> str:
    return path.resolve().relative_to(root).as_posix()


def _is_automation_file(relative: str) -> bool:
    if relative in EXCLUDED_HISTORICAL_DOCUMENTS or relative in EXCLUDED_SCAN_FILES:
        return False
    if relative == __file_relative__():
        return False
    return relative in SCANNED_FILES or relative.startswith(AUTOMATION_PREFIXES)


def _is_live_doc_file(relative: str) -> bool:
    if not relative.endswith(".md"):
        return False
    if relative.startswith(("docs/archive/", "specs/archive/")):
        return False
    if relative.startswith(LIVE_DOC_DIR_PREFIXES):
        return True
    if relative.startswith("docs/") and relative.count("/") == 1:
        return True
    return relative.startswith("specs/")


def _is_archive_guard_file(relative: str) -> bool:
    if relative in EXCLUDED_SCAN_FILES or relative == __file_relative__():
        return False
    if relative.startswith(("scripts/archive/", "tests/unit/scripts/archive/")):
        return False
    return relative in SCANNED_FILES or relative.startswith(AUTOMATION_PREFIXES)


def _read_text_lines(path: Path) -> list[str] | None:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return None


def _scan_line_patterns(
    paths: list[Path],
    *,
    root: Path,
    patterns: tuple[tuple[re.Pattern[str], str], ...],
) -> list[Violation]:
    violations: list[Violation] = []
    for path in paths:
        lines = _read_text_lines(path)
        if lines is None:
            continue
        relative = _relative_to_repository(path, root)
        for line_number, line in enumerate(lines, 1):
            for pattern, message in patterns:
                if pattern.search(line):
                    violations.append(Violation(relative, line_number, message, line))
                    break
    return violations


def scan_removed_src_references(
    paths: list[Path], *, root: Path = REPOSITORY_ROOT
) -> list[Violation]:
    """Find removed ``src`` root references in executable automation."""
    return _scan_line_patterns(
        paths,
        root=root,
        patterns=tuple(
            (pattern, "removed src source-root reference") for pattern in REMOVED_SRC_PATTERNS
        ),
    )


def scan_live_doc_stale_content(
    paths: list[Path], *, root: Path = REPOSITORY_ROOT
) -> list[Violation]:
    """Find stale executable paths and commands in live docs/specs."""
    live_docs = [path for path in paths if _is_live_doc_file(_relative_to_repository(path, root))]
    return _scan_line_patterns(live_docs, root=root, patterns=LIVE_DOC_STALE_PATTERNS)


def scan_archive_references(paths: list[Path], *, root: Path = REPOSITORY_ROOT) -> list[Violation]:
    """Find live-code references to archived scripts."""
    guard_files = [
        path for path in paths if _is_archive_guard_file(_relative_to_repository(path, root))
    ]
    return _scan_line_patterns(
        guard_files,
        root=root,
        patterns=tuple(
            (pattern, "live code references scripts/archive")
            for pattern in ARCHIVE_REFERENCE_PATTERNS
        ),
    )


def _extract_markdown_link_target(raw_target: str) -> str:
    target = raw_target.strip()
    if target.startswith("<") and ">" in target:
        return target[1:].split(">", 1)[0]
    return target.split(maxsplit=1)[0]


def _is_external_or_anchor_link(target: str) -> bool:
    lower = target.lower()
    return (
        not target
        or target.startswith("#")
        or lower.startswith(("http://", "https://", "mailto:", "tel:", "app://"))
    )


def _resolve_markdown_target(source_path: Path, target: str, root: Path) -> Path | None:
    normalized = unquote(target).split("#", 1)[0].split("?", 1)[0]
    if not normalized:
        return None
    if normalized.startswith("/"):
        return root / normalized.lstrip("/")
    return source_path.parent / normalized


def scan_missing_live_doc_links(
    paths: list[Path], *, root: Path = REPOSITORY_ROOT
) -> list[Violation]:
    """Find local Markdown links in live docs/specs that point nowhere."""
    violations: list[Violation] = []
    live_docs = [path for path in paths if _is_live_doc_file(_relative_to_repository(path, root))]
    for path in live_docs:
        lines = _read_text_lines(path)
        if lines is None:
            continue
        relative = _relative_to_repository(path, root)
        for line_number, line in enumerate(lines, 1):
            for match in MARKDOWN_LINK_RE.finditer(line):
                target = _extract_markdown_link_target(match.group(1))
                if _is_external_or_anchor_link(target):
                    continue
                resolved = _resolve_markdown_target(path, target, root)
                if resolved is not None and not resolved.exists():
                    violations.append(
                        Violation(
                            relative, line_number, f"missing local Markdown link {target}", line
                        )
                    )
    return violations


def _print_section(title: str, violations: list[Violation]) -> None:
    if not violations:
        return
    print(title)
    print("\n".join(violation.format() for violation in violations))


def main() -> int:
    """Report repository hygiene violations and return a failing status when found."""
    paths = tracked_files()
    violations_by_section = [
        (
            "Executable references to the removed src/ source root were found:",
            scan_removed_src_references(
                [path for path in paths if _is_automation_file(_relative_to_repository(path))]
            ),
        ),
        (
            "Stale live-doc paths or commands were found:",
            scan_live_doc_stale_content(paths),
        ),
        (
            "Missing local Markdown links were found in live docs/specs:",
            scan_missing_live_doc_links(paths),
        ),
        (
            "Live code references archived scripts:",
            scan_archive_references(paths),
        ),
    ]

    if any(violations for _, violations in violations_by_section):
        for title, violations in violations_by_section:
            _print_section(title, violations)
        return 1

    print("Repository hygiene checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
