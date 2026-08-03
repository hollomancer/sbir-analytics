#!/usr/bin/env python3
"""Repository hygiene checks for stale paths and archive dependencies."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import re
import subprocess
import unicodedata
from pathlib import Path
from urllib.parse import unquote


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
AUTOMATION_PREFIXES = (".github/", "scripts/", "sbir_etl/", "packages/", "tests/")
SCANNED_FILES = {"Makefile", ".pre-commit-config.yaml"}
EXCLUDED_HISTORICAL_DOCUMENTS = {"docs/decisions/ADR-002-etl-library-extraction.md"}
EXCLUDED_SCAN_FILES = {
    "scripts/ci/check_identity_boundaries.py",
    "tests/unit/scripts/test_repository_hygiene.py",
}
REMOVED_SRC_PATTERNS = (
    re.compile(r"--cov=src(?:\b|/)"),
    re.compile(r"\bsrc\.definitions(?:_ml)?\b"),
    re.compile(r"(?:^|[\s'\"(=:/])src/[A-Za-z0-9_.*?/-]+"),
)
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
        re.compile(r"(?:^|[\s'\"(=:/])(?:python\s+-m\s+)?black\s+(?:--|[A-Za-z0-9_.-]+)"),
        "Black command in live docs",
    ),
)
ARCHIVE_REFERENCE_PATTERNS = (
    re.compile(r"scripts/archive(?:/|\b)"),
    re.compile(r"scripts\.archive(?:\.|\b)"),
)
MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]]+\]\(([^)]+)\)")
MARKDOWN_REFERENCE_LINK_RE = re.compile(r"^\s*\[[^\]]+\]:\s*(\S+)")
MARKDOWN_HEADING_RE = re.compile(r"^ {0,3}#{1,6}\s+(.+?)\s*#*\s*$")
MARKDOWN_EXPLICIT_ANCHOR_RE = re.compile(r'<a\s+(?:[^>]*?\s)?(?:id|name)=["\']([^"\']+)["\']', re.I)
SPEC_STATUS_ENTRY_RE = re.compile(r"^- \*\*`([^`]+)`\s+—", re.MULTILINE)


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
    paths = [REPOSITORY_ROOT / relative for relative in result.stdout.splitlines()]
    return [path for path in paths if path.exists()]


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
    if relative.startswith("docs/"):
        return True
    return relative.startswith("specs/")


def _is_documentation_file(relative: str) -> bool:
    """Return whether a tracked Markdown file belongs to project documentation."""
    return relative == "README.md" or (
        relative.endswith(".md") and relative.startswith(("docs/", "specs/"))
    )


def _is_archive_guard_file(relative: str) -> bool:
    if relative in EXCLUDED_SCAN_FILES or relative == __file_relative__():
        return False
    if relative.startswith(("scripts/archive/", "tests/unit/scripts/archive/")):
        return False
    return relative in SCANNED_FILES or relative.startswith(
        (*AUTOMATION_PREFIXES, "docs/deployment/")
    )


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
    """Find operational references to archived scripts."""
    guard_files = [
        path for path in paths if _is_archive_guard_file(_relative_to_repository(path, root))
    ]
    return _scan_line_patterns(
        guard_files,
        root=root,
        patterns=tuple(
            (pattern, "operational file references scripts/archive")
            for pattern in ARCHIVE_REFERENCE_PATTERNS
        ),
    )


def _extract_markdown_link_target(raw_target: str) -> str:
    target = raw_target.strip()
    if target.startswith("<") and ">" in target:
        return target[1:].split(">", 1)[0]
    return target.split(maxsplit=1)[0]


def _is_external_link(target: str) -> bool:
    lower = target.lower()
    return not target or lower.startswith(("http://", "https://", "mailto:", "tel:", "app://"))


def _resolve_markdown_target(source_path: Path, target: str, root: Path) -> Path | None:
    normalized = unquote(target).split("#", 1)[0].split("?", 1)[0]
    if not normalized:
        return source_path
    if normalized.startswith("/"):
        return root / normalized.lstrip("/")
    return source_path.parent / normalized


def _github_heading_slug(heading: str) -> str:
    """Return the stable subset of GitHub's heading-slug behavior used by repository docs."""
    text = re.sub(r"<[^>]+>", "", heading)
    text = re.sub(r"!?\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = text.replace("`", "").replace("*", "").replace("~", "")
    characters: list[str] = []
    for character in text.strip().lower():
        category = unicodedata.category(character)
        if character in {"-", "_"} or character.isspace() or category[0] in {"L", "N"}:
            characters.append(character)
    # GitHub replaces each whitespace character rather than collapsing a run;
    # punctuation between two spaces therefore produces a double hyphen.
    return re.sub(r"\s", "-", "".join(characters))


def _markdown_anchors(path: Path) -> set[str]:
    """Collect generated heading anchors and explicit HTML anchors from one Markdown file."""
    lines = _read_text_lines(path)
    if lines is None:
        return set()
    anchors: set[str] = set()
    slug_counts: dict[str, int] = {}
    for line in lines:
        for explicit in MARKDOWN_EXPLICIT_ANCHOR_RE.findall(line):
            anchors.add(unquote(explicit))
        heading_match = MARKDOWN_HEADING_RE.match(line)
        if heading_match is None:
            continue
        base_slug = _github_heading_slug(heading_match.group(1))
        if not base_slug:
            continue
        duplicate_index = slug_counts.get(base_slug, 0)
        slug_counts[base_slug] = duplicate_index + 1
        anchors.add(base_slug if duplicate_index == 0 else f"{base_slug}-{duplicate_index}")
    return anchors


def scan_missing_doc_links(paths: list[Path], *, root: Path = REPOSITORY_ROOT) -> list[Violation]:
    """Find local Markdown links or fragments in project docs that point nowhere."""
    violations: list[Violation] = []
    anchors_by_path: dict[Path, set[str]] = {}
    docs = [path for path in paths if _is_documentation_file(_relative_to_repository(path, root))]
    for path in docs:
        lines = _read_text_lines(path)
        if lines is None:
            continue
        relative = _relative_to_repository(path, root)
        for line_number, line in enumerate(lines, 1):
            raw_targets = [match.group(1) for match in MARKDOWN_LINK_RE.finditer(line)]
            if reference_match := MARKDOWN_REFERENCE_LINK_RE.match(line):
                raw_targets.append(reference_match.group(1))
            for raw_target in raw_targets:
                target = _extract_markdown_link_target(raw_target)
                if _is_external_link(target):
                    continue
                resolved = _resolve_markdown_target(path, target, root)
                if resolved is not None and not resolved.exists():
                    violations.append(
                        Violation(
                            relative, line_number, f"missing local Markdown link {target}", line
                        )
                    )
                    continue
                fragment = (
                    unquote(target.split("#", 1)[1].split("?", 1)[0]) if "#" in target else ""
                )
                if not fragment or resolved is None or resolved.suffix.lower() != ".md":
                    continue
                resolved_path = resolved.resolve()
                anchors = anchors_by_path.setdefault(
                    resolved_path, _markdown_anchors(resolved_path)
                )
                if fragment not in anchors:
                    violations.append(
                        Violation(
                            relative,
                            line_number,
                            f"missing Markdown anchor #{fragment} in {target.split('#', 1)[0] or relative}",
                            line,
                        )
                    )
    return violations


def scan_spec_registry(*, root: Path = REPOSITORY_ROOT) -> list[Violation]:
    """Require every top-level feature spec to appear exactly once in the status registry."""
    specs_root = root / "specs"
    registry_path = specs_root / "status.md"
    if not registry_path.exists():
        return [Violation("specs/status.md", 1, "missing specification status registry", "")]

    tracked_specs = {
        path.name
        for path in specs_root.iterdir()
        if (path.is_dir() and path.name != "archive")
        or (
            path.is_file()
            and path.suffix == ".md"
            and path.name not in {"REQUIREMENTS_TEMPLATE.md", "status.md"}
        )
    }
    registry_text = registry_path.read_text(encoding="utf-8")
    registered_entries = SPEC_STATUS_ENTRY_RE.findall(registry_text)
    registered_specs = set(registered_entries)

    violations: list[Violation] = []
    for name in sorted(tracked_specs - registered_specs):
        violations.append(
            Violation(
                "specs/status.md",
                1,
                f"top-level spec is missing from status registry: {name}",
                name,
            )
        )
    for name in sorted(registered_specs - tracked_specs):
        violations.append(
            Violation(
                "specs/status.md",
                1,
                f"status registry references a missing top-level spec: {name}",
                name,
            )
        )
    for name, count in sorted(Counter(registered_entries).items()):
        if count > 1:
            violations.append(
                Violation(
                    "specs/status.md",
                    1,
                    f"status registry contains duplicate entries for: {name}",
                    name,
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
            "Missing local Markdown links were found in project documentation:",
            scan_missing_doc_links(paths),
        ),
        (
            "The specification status registry is incomplete:",
            scan_spec_registry(),
        ),
        (
            "Operational files reference archived scripts:",
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
