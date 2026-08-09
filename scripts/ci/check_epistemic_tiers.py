#!/usr/bin/env python3
"""Require every active specification to declare a valid epistemic target tier."""

import re
from dataclasses import dataclass
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SPECS_ROOT = REPOSITORY_ROOT / "specs"
VALID_TIERS = frozenset({"primitives", "pipelines", "evidence", "exploratory"})
TIER_DECLARATION = re.compile(
    r"^\*\*Target epistemic tier:\*\*\s*`?([A-Za-z]+)`?\s*$",
    flags=re.MULTILINE,
)
FENCE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")
EXCLUDED_SPEC_DIRECTORIES = frozenset({"archive"})


@dataclass(frozen=True)
class TierDeclarationViolation:
    """One missing, duplicate, or invalid specification declaration."""

    path: str
    message: str

    def format(self) -> str:
        return f"{self.path}: {self.message}"


def _outside_fenced_code(markdown: str) -> str:
    """Return Markdown content outside fenced code blocks."""

    retained: list[str] = []
    marker: tuple[str, int] | None = None
    for line in markdown.splitlines():
        match = FENCE.match(line)
        if marker is None:
            if match:
                fence = match.group(1)
                marker = fence[0], len(fence)
            else:
                retained.append(line)
            continue
        if match and match.group(1)[0] == marker[0] and len(match.group(1)) >= marker[1]:
            marker = None
    return "\n".join(retained)


def validate_spec_directory(
    spec_directory: Path,
    *,
    repository_root: Path = REPOSITORY_ROOT,
) -> list[TierDeclarationViolation]:
    """Validate the canonical declaration for one active specification."""

    requirements = spec_directory / "requirements.md"
    relative = requirements.relative_to(repository_root).as_posix()
    if not requirements.is_file():
        return [
            TierDeclarationViolation(
                relative,
                "active spec is missing requirements.md and its target epistemic tier",
            )
        ]

    markdown = _outside_fenced_code(requirements.read_text(encoding="utf-8"))
    declarations = TIER_DECLARATION.findall(markdown)
    if not declarations:
        return [
            TierDeclarationViolation(
                relative,
                "missing '**Target epistemic tier:** <tier>' declaration",
            )
        ]
    if len(declarations) > 1:
        return [TierDeclarationViolation(relative, "multiple target tier declarations")]

    tier = declarations[0]
    if tier not in VALID_TIERS:
        choices = ", ".join(sorted(VALID_TIERS))
        return [
            TierDeclarationViolation(
                relative,
                f"invalid target tier {tier!r}; expected one of: {choices}",
            )
        ]
    return []


def scan_specs(
    *,
    specs_root: Path = SPECS_ROOT,
    repository_root: Path = REPOSITORY_ROOT,
) -> list[TierDeclarationViolation]:
    """Validate every non-archived top-level specification directory."""

    violations: list[TierDeclarationViolation] = []
    for directory in sorted(path for path in specs_root.iterdir() if path.is_dir()):
        if directory.name in EXCLUDED_SPEC_DIRECTORIES:
            continue
        violations.extend(validate_spec_directory(directory, repository_root=repository_root))
    return violations


def main() -> int:
    violations = scan_specs()
    if violations:
        print("Epistemic tier declaration violations were found:")
        print("\n".join(violation.format() for violation in violations))
        return 1
    print("Epistemic tier declaration checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
