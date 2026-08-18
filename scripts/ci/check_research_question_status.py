#!/usr/bin/env python3
"""Require reserved inventory Status ranks to have a matching study contract.

``docs/research-questions.md`` is a public API. The reserved ranks
``computable``, ``validated``, and ``citable`` may appear as Status claims only
when a ``studies/*/study.yaml`` lists that *section* ID (``B2``, ``F3``, …)
at the matching ``evidence_status`` (or higher). Authorization is per section,
not per question bullet: a study listing ``B2`` authorizes every reserved-rank
Status under ``### B2``.

Negations (``not computable``, ``never computable``, ``non-citable``) are
refusals, not ranks, and do not need a study. The verb ``validates`` is not
the ``validated`` rank.

This is admission control for the inventory, not proof that a study's result
is correct. Exploratory studies do not authorize ``computable``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from sbir_etl.exceptions import ConfigurationError
from sbir_etl.quality.study_manifest import EvidenceStatus, load_study_manifest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
INVENTORY_PATH = Path("docs/research-questions.md")

ANY_HEADING = re.compile(r"^#{2,4}\s+")
SECTION_HEADING = re.compile(r"^#{2,4}\s+([A-F]\d+)\b")
STATUS_MARKER = re.compile(r"\*\*Status:\*\*")
STATUS_END = re.compile(r"^(\s*\*Deps:|#{1,6}\s|-\s+\*\*)")

# Strip these before looking for a positive rank so denials do not count.
# A short negation window covers "not currently computable" / "never
# computable" without exempting the noun phrase "citable claim".
DENIAL_PHRASES = (
    re.compile(
        r"\b(?:not|no|never|cannot)\W+(?:\w+\W+){0,3}?(?:computable|validated|citable)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bnon-(?:computable|validated|citable)\b", re.IGNORECASE),
    re.compile(r"\bunvalidated\b", re.IGNORECASE),
    re.compile(r"\bnot\s+approved\s+for\s+citation\b", re.IGNORECASE),
    re.compile(r"\bany\b[^.]*\bcitable\b[^.]*\bblocked\b", re.IGNORECASE),
)

RANK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("computable", re.compile(r"\bcomputable\b", re.IGNORECASE)),
    ("validated", re.compile(r"\bvalidated\b", re.IGNORECASE)),
    ("citable", re.compile(r"\bcitable\b", re.IGNORECASE)),
)

# Minimum study evidence_status that authorizes each reserved inventory rank.
REQUIRED_STUDY_STATUS: dict[str, EvidenceStatus] = {
    "computable": EvidenceStatus.REPRODUCIBLE,
    "validated": EvidenceStatus.VALIDATED,
    "citable": EvidenceStatus.CITABLE,
}

STATUS_RANK: dict[EvidenceStatus, int] = {
    EvidenceStatus.RETIRED: -1,
    EvidenceStatus.EXPLORATORY: 0,
    EvidenceStatus.REPRODUCIBLE: 1,
    EvidenceStatus.VALIDATED: 2,
    EvidenceStatus.CITABLE: 3,
}


@dataclass(frozen=True)
class StatusClaim:
    """One reserved rank claimed by a Status block."""

    line_number: int
    section_id: str | None
    rank: str
    excerpt: str


@dataclass(frozen=True)
class StatusViolation:
    """One Status claim that lacks a study at the required rank."""

    path: str
    line_number: int
    message: str

    def format(self) -> str:
        return f"{self.path}:{self.line_number}: {self.message}"


def claimed_ranks(status_text: str) -> tuple[str, ...]:
    """Return reserved ranks asserted after denial phrases are removed."""

    remainder = status_text
    for pattern in DENIAL_PHRASES:
        remainder = pattern.sub(" ", remainder)
    found: list[str] = []
    for rank, pattern in RANK_PATTERNS:
        if pattern.search(remainder):
            found.append(rank)
    return tuple(found)


def iter_status_blocks(markdown: str) -> Iterable[tuple[int, str | None, str]]:
    """Yield ``(line_number, section_id, status_text)`` for each Status block."""

    section_id: str | None = None
    lines = markdown.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if ANY_HEADING.match(line):
            heading = SECTION_HEADING.match(line)
            section_id = heading.group(1).upper() if heading else None
        marker = STATUS_MARKER.search(line)
        if marker is None:
            index += 1
            continue
        start_line = index + 1
        block = [line[marker.end() :]]
        index += 1
        while index < len(lines):
            nxt = lines[index]
            if STATUS_MARKER.search(nxt) or STATUS_END.match(nxt):
                break
            block.append(nxt)
            index += 1
        yield start_line, section_id, " ".join(part.strip() for part in block if part.strip())


def collect_status_claims(markdown: str) -> list[StatusClaim]:
    """Collect reserved-rank claims from an inventory document."""

    claims: list[StatusClaim] = []
    for line_number, section_id, text in iter_status_blocks(markdown):
        excerpt = re.sub(r"\s+", " ", text).strip()
        if len(excerpt) > 160:
            excerpt = excerpt[:157] + "..."
        for rank in claimed_ranks(text):
            claims.append(
                StatusClaim(
                    line_number=line_number,
                    section_id=section_id,
                    rank=rank,
                    excerpt=excerpt,
                )
            )
    return claims


def load_question_study_ranks(
    *, repository_root: Path = REPOSITORY_ROOT
) -> dict[str, EvidenceStatus]:
    """Map each study-listed section ID to the highest live evidence status.

    A study that lists ``B2`` authorizes reserved ranks for every Status
    block under ``### B2``, not only the bullet whose estimand it covers.
    """

    best: dict[str, EvidenceStatus] = {}
    for path in sorted((repository_root / "studies").glob("*/study.yaml")):
        manifest = load_study_manifest(path)
        if manifest.evidence_status is EvidenceStatus.RETIRED:
            continue
        for question in manifest.research_questions:
            key = question.strip().upper()
            current = best.get(key)
            if current is None or STATUS_RANK[manifest.evidence_status] > STATUS_RANK[current]:
                best[key] = manifest.evidence_status
    return best


def study_authorizes(status: EvidenceStatus | None, required: EvidenceStatus) -> bool:
    """Return whether ``status`` meets or exceeds ``required``."""

    if status is None or STATUS_RANK[status] < 0:
        return False
    return STATUS_RANK[status] >= STATUS_RANK[required]


def validate_inventory(
    markdown: str,
    question_ranks: dict[str, EvidenceStatus],
    *,
    path: str = INVENTORY_PATH.as_posix(),
) -> list[StatusViolation]:
    """Return Status claims that lack a study at the required rank."""

    violations: list[StatusViolation] = []
    for claim in collect_status_claims(markdown):
        required = REQUIRED_STUDY_STATUS[claim.rank]
        if claim.section_id is None:
            violations.append(
                StatusViolation(
                    path=path,
                    line_number=claim.line_number,
                    message=(
                        f"Status claims {claim.rank!r} outside a numbered A–F "
                        f"section: {claim.excerpt}"
                    ),
                )
            )
            continue
        actual = question_ranks.get(claim.section_id)
        if study_authorizes(actual, required):
            continue
        actual_label = actual.value if actual is not None else "none"
        violations.append(
            StatusViolation(
                path=path,
                line_number=claim.line_number,
                message=(
                    f"Status claims {claim.rank!r} for {claim.section_id}, but "
                    f"the highest matching study is {actual_label!r} "
                    f"(need {required.value!r} or higher): {claim.excerpt}"
                ),
            )
        )
    return violations


def validate_repository(*, repository_root: Path = REPOSITORY_ROOT) -> list[StatusViolation]:
    """Validate the tracked inventory against live study manifests."""

    inventory = repository_root / INVENTORY_PATH
    try:
        markdown = inventory.read_text(encoding="utf-8")
        ranks = load_question_study_ranks(repository_root=repository_root)
    except (OSError, ValueError, ConfigurationError) as exc:
        return [
            StatusViolation(
                path=INVENTORY_PATH.as_posix(),
                line_number=1,
                message=f"cannot load inventory or study manifests: {exc}",
            )
        ]
    return validate_inventory(markdown, ranks, path=INVENTORY_PATH.as_posix())


def main() -> int:
    violations = validate_repository()
    if violations:
        print("Research-question Status claims lack a matching study contract:")
        print("\n".join(violation.format() for violation in violations))
        return 1
    print("Research-question Status ranks match study contracts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
