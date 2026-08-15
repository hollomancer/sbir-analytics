#!/usr/bin/env python3
"""Require every active specification to declare a valid epistemic target tier.

Evidence-tier specs must also satisfy a minimal paperwork contract: an
amendments log that records SHA-256 freeze enforcement (a 64-hex digest and/or
explicit raw-byte freeze language), and an explicit estimand field in
requirements.md. This gate does not prove runtime SHA or blocking asset-check
enforcement. Specs that only want the label without the contract should declare
``pipelines`` or ``exploratory`` instead.
"""

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
ESTIMAND_DECLARATION = re.compile(
    r"^\*\*(?:Declared )?Estimand:\*\*\s+\S",
    flags=re.MULTILINE | re.IGNORECASE,
)
SHA256_DIGEST = re.compile(r"\b[0-9a-f]{64}\b", flags=re.IGNORECASE)
# Census-style freezes compile expected digests into the asset and intentionally
# omit embedding them in amendments.md (self-hashing). Accept that paperwork form.
SHA256_FREEZE_LANGUAGE = re.compile(
    r"(?:raw-byte\s+SHA-256|SHA-256[^\n.]{0,80}(?:freeze|verif))",
    flags=re.IGNORECASE,
)
FENCE = re.compile(r"^[ \t]*(?P<fence>`{3,}|~{3,})(?P<suffix>.*)$")
EXCLUDED_SPEC_DIRECTORIES = frozenset({"archive"})


@dataclass(frozen=True)
class TierDeclarationViolation:
    """One missing, duplicate, or invalid specification declaration."""

    path: str
    message: str

    def format(self) -> str:
        return f"{self.path}: {self.message}"


def _outside_fenced_code(markdown: str) -> str:
    """Return Markdown content outside complete fenced code blocks.

    Unterminated candidate fences are retained. A malformed example must not
    hide a real declaration later in the specification.
    """

    retained: list[str] = []
    pending: list[str] = []
    marker: tuple[str, int] | None = None
    for line in markdown.splitlines():
        match = FENCE.match(line)
        if marker is None:
            if match and not (
                match.group("fence").startswith("`") and "`" in match.group("suffix")
            ):
                fence = match.group("fence")
                marker = fence[0], len(fence)
                pending = [line]
            else:
                retained.append(line)
            continue
        pending.append(line)
        if (
            match
            and match.group("fence")[0] == marker[0]
            and len(match.group("fence")) >= marker[1]
            and not match.group("suffix").strip()
        ):
            marker = None
            pending = []
    retained.extend(pending)
    return "\n".join(retained)


def _evidence_contract_violations(
    spec_directory: Path,
    *,
    repository_root: Path,
) -> list[TierDeclarationViolation]:
    """Minimal evidence-tier paperwork: amendments SHA language + declared estimand."""

    violations: list[TierDeclarationViolation] = []
    requirements = spec_directory / "requirements.md"
    relative_req = requirements.relative_to(repository_root).as_posix()
    amendments = spec_directory / "amendments.md"
    relative_amd = (spec_directory / "amendments.md").relative_to(repository_root).as_posix()

    if not amendments.is_file():
        violations.append(
            TierDeclarationViolation(
                relative_amd,
                "evidence-tier specs require amendments.md with SHA-256 freeze paperwork",
            )
        )
    else:
        amd_text = amendments.read_text(encoding="utf-8")
        if not (SHA256_DIGEST.search(amd_text) or SHA256_FREEZE_LANGUAGE.search(amd_text)):
            violations.append(
                TierDeclarationViolation(
                    relative_amd,
                    "evidence-tier amendments.md must record a SHA-256 freeze digest "
                    "or explicit raw-byte SHA-256 freeze verification language",
                )
            )

    req_text = _outside_fenced_code(requirements.read_text(encoding="utf-8"))
    if not ESTIMAND_DECLARATION.search(req_text):
        violations.append(
            TierDeclarationViolation(
                relative_req,
                "evidence-tier specs require '**Declared estimand:** …' "
                "(or '**Estimand:** …')",
            )
        )
    return violations


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

    if tier == "evidence":
        return _evidence_contract_violations(spec_directory, repository_root=repository_root)
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
