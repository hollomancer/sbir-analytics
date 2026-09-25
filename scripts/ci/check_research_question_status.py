#!/usr/bin/env python3
"""Require reserved inventory Status ranks to have a matching study contract.

``docs/research-questions.md`` is a public API. The reserved ranks
``computable``, ``validated``, and ``citable`` may appear as Status claims only
when a ``studies/*/study.yaml`` lists that *section* ID (``B2``, ``F3``, …)
at the matching ``evidence_status`` (or higher). Authorization is per section,
not per question bullet: a study listing ``B2`` authorizes every reserved-rank
Status under ``### B2``.

Negations (``not computable``, ``never computable``, ``not yet validated``,
``no citable claim``, ``non-citable``, ``not estimable``) are refusals, not
ranks, and do not need a study. The negation has to lead — a rank word with
nothing negating it in front reads as a claim. The verb ``validates`` is not
the ``validated`` rank.

The ``### Start here`` audience box may link only to an explicit question
anchor whose Status is a reserved rank or a refusal. Section headings and
research-target questions are not start-here targets.

This is admission control for the inventory, not proof that a study's result
is correct. Exploratory studies do not authorize ``computable``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from sbir_etl.exceptions import ConfigurationError
from sbir_etl.quality.study_manifest import EvidenceStatus, StudyManifest, load_study_manifest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
INVENTORY_PATH = Path("docs/research-questions.md")

SECTION_HEADING = re.compile(r"^(#{2,4})\s+([A-F]\d+)\b")
ANY_HEADING = re.compile(r"^(#{1,6})\s")
STATUS_MARKER = re.compile(r"\*\*Status:\*\*")
STATUS_END = re.compile(r"^(\s*\*Deps:|#{1,6}\s|-\s+\*\*)")
START_HERE_HEADING = re.compile(r"^### Start here\b", re.IGNORECASE)
START_HERE_END = re.compile(r"^#{2,3}\s+")
START_HERE_LINK = re.compile(r"\]\(#([^)]+)\)")
EXPLICIT_ANCHOR = re.compile(r'<a\s+(?:[^>]*?\s)?id=["\']([^"\']+)["\']', re.I)
REFUSAL_STATUS = re.compile(r"\bnot\s+(?:computable|estimable)\b", re.IGNORECASE)

# Sections a study lists but the inventory does not link back, predating the
# discoverability check. A burndown list, not an exemption: an entry that no
# longer violates is itself reported, so the list can only shrink. Every entry
# needs a non-blank reason, so an exemption cannot be added without saying why.
DISCOVERABILITY_ALLOWLIST: dict[tuple[str, str], str] = {
    ("ma-discovery-recall", "A4"): "predates this check; no A4 bullet names the recall study",
    ("ma-discovery-recall", "F2"): "predates this check; no F2 bullet names the recall study",
    ("transition-scoring", "B2"): "predates this check; B2 describes the scorer without linking it",
    ("transition-scoring", "B3"): "predates this check; B3 describes the scorer without linking it",
    (
        "sbir-ma-dated-signal-study",
        "F1",
    ): "predates this check; no F1 bullet names the dated-signal study",
}

# Only the past-participle rank word counts. ``validates`` is the ordinary verb
# ("the review validates the cohort component") and is not a rank claim.
RANK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("computable", re.compile(r"\bcomputable\b", re.IGNORECASE)),
    ("validated", re.compile(r"\bvalidated\b", re.IGNORECASE)),
    ("citable", re.compile(r"\bcitable\b", re.IGNORECASE)),
)

# Negation is read compositionally rather than from a phrase list: a rank word
# is a refusal when a negating token leads it within the same clause ("not yet
# computable", "no longer computable", "never computable", "cannot be
# validated", "no citable claim") or when a negating prefix is attached
# ("non-citable"). ``unvalidated`` needs no rule — the rank patterns are
# word-bounded, so they never match inside it.
NEGATION_TOKEN = re.compile(
    r"\b(?:not|no|never|none|nor|neither|without|cannot|absent|lack(?:s|ed|ing)?"
    r"|[\w']+n't)\b",
    re.IGNORECASE,
)
NEGATING_PREFIX = re.compile(r"\bnon-\s*$", re.IGNORECASE)
CLAUSE_BREAK = re.compile(r"[.;:!?]")
WORD = re.compile(r"[\w'’]+")

# Words that may sit between the negating token and the rank word it governs.
NEGATION_WINDOW_WORDS = 4

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


def is_negated(text: str, rank_start: int) -> bool:
    """Return whether a negation leads the rank word beginning at ``rank_start``."""

    prefix = text[:rank_start]
    if NEGATING_PREFIX.search(prefix):
        return True
    clause = CLAUSE_BREAK.split(prefix)[-1]
    window = WORD.findall(clause)[-NEGATION_WINDOW_WORDS:]
    return any(NEGATION_TOKEN.fullmatch(word) for word in window)


def claimed_ranks(status_text: str) -> tuple[str, ...]:
    """Return reserved ranks asserted positively, ignoring negated mentions."""

    found: list[str] = []
    for rank, pattern in RANK_PATTERNS:
        mentions = pattern.finditer(status_text)
        if any(not is_negated(status_text, mention.start()) for mention in mentions):
            found.append(rank)
    return tuple(found)


def iter_status_blocks(markdown: str) -> Iterable[tuple[int, str | None, str]]:
    """Yield ``(line_number, section_id, status_text)`` for each Status block."""

    section_id: str | None = None
    section_level = 0
    lines = markdown.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        heading = SECTION_HEADING.match(line)
        other_heading = ANY_HEADING.match(line)
        if heading:
            section_id = heading.group(2).upper()
            section_level = len(heading.group(1))
        elif other_heading is not None and len(other_heading.group(1)) <= section_level:
            # A sibling or shallower heading that carries no A–F ID ends the
            # section. Deeper sub-headings (#### inside a ### section) stay in.
            section_id = None
            section_level = 0
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


def _section_spans(markdown: str) -> dict[str, tuple[int, int]]:
    """First and last line number of each ``### <SECTION>`` block."""
    lines = markdown.splitlines()
    starts: list[tuple[int, str]] = []
    for index, line in enumerate(lines, start=1):
        match = SECTION_HEADING.match(line)
        if match:
            starts.append((index, match.group(2).upper()))
    spans: dict[str, tuple[int, int]] = {}
    for position, (line_number, section) in enumerate(starts):
        end = starts[position + 1][0] - 1 if position + 1 < len(starts) else len(lines)
        # A section ID can head more than one block; widen to cover them all.
        first, last = spans.get(section, (line_number, end))
        spans[section] = (min(first, line_number), max(last, end))
    return spans


def validate_study_discoverability(
    markdown: str,
    studies: dict[str, set[str]],
    *,
    path: str,
) -> list[StatusViolation]:
    """Require a section a study lists to link back to that study.

    ``load_question_study_ranks`` reads the inventory-to-study direction: a
    reserved rank needs a manifest. This is the other direction. A manifest
    that lists ``F3`` is claiming the inventory routes a reader from ``### F3``
    to it, and nothing checked that the link exists — so a study could declare
    a section it was unreachable from.
    """

    spans = _section_spans(markdown)
    lines = markdown.splitlines()
    violations: list[StatusViolation] = [
        StatusViolation(
            path=path,
            line_number=1,
            message=f"discoverability allowlist entry {entry} has no reason; state why",
        )
        for entry, reason in sorted(DISCOVERABILITY_ALLOWLIST.items())
        if not reason.strip()
    ]
    still_violating: set[tuple[str, str]] = set()
    for section in sorted(studies):
        span = spans.get(section)
        if span is None:
            violations.append(
                StatusViolation(
                    path=path,
                    line_number=1,
                    message=(
                        f"{', '.join(sorted(studies[section]))} lists {section}, but the "
                        f"inventory has no ### {section} section"
                    ),
                )
            )
            continue
        first, last = span
        body = "\n".join(lines[first - 1 : last])
        for study_id in sorted(studies[section]):
            if f"studies/{study_id}/" not in body:
                if (study_id, section) in DISCOVERABILITY_ALLOWLIST:
                    still_violating.add((study_id, section))
                    continue
                violations.append(
                    StatusViolation(
                        path=path,
                        line_number=first,
                        message=(
                            f"{study_id} lists {section} in research_questions, but "
                            f"### {section} does not link studies/{study_id}/; add the "
                            f"link or drop {section} from the manifest"
                        ),
                    )
                )
    violations.extend(
        StatusViolation(
            path=path,
            line_number=1,
            message=(
                f"stale allowlist entry ({reason}): {entry[0]} now reaches {entry[1]}; "
                "remove it from DISCOVERABILITY_ALLOWLIST"
            ),
        )
        for entry, reason in sorted(DISCOVERABILITY_ALLOWLIST.items())
        if entry not in still_violating
    )
    return violations


def load_question_study_ids(*, repository_root: Path = REPOSITORY_ROOT) -> dict[str, set[str]]:
    """Map each study-listed section ID to the study IDs that list it."""

    listed: dict[str, set[str]] = {}
    for path in sorted((repository_root / "studies").glob("*/study.yaml")):
        manifest = load_study_manifest(path)
        if manifest.evidence_status is EvidenceStatus.RETIRED:
            continue
        for question in manifest.research_questions:
            listed.setdefault(question.strip().upper(), set()).add(manifest.study_id)
    return listed


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
        authorized = authorizing_status(manifest)
        for question in manifest.research_questions:
            key = question.strip().upper()
            current = best.get(key)
            if current is None or STATUS_RANK[authorized] > STATUS_RANK[current]:
                best[key] = authorized
    return best


def authorizing_status(manifest: StudyManifest) -> EvidenceStatus:
    """Return the inventory rank a manifest authorizes.

    The manifest rank ``validated`` means the preregistered test ran as written
    and its outcome is on the record; it does not mean the threshold was met.
    The inventory word ``Validated`` in ``docs/research-questions.md`` does mean
    that -- it defines the rank as a design that has passed. A study that
    honestly records a miss therefore authorizes only ``computable``, so a
    failed method cannot surface as a validated answer.

    ``citable`` already requires ``threshold_met`` at the schema level, so it
    needs no demotion here.
    """
    if manifest.evidence_status is not EvidenceStatus.VALIDATED:
        return manifest.evidence_status
    result = manifest.validation_result
    if result is not None and not result.threshold_met:
        return EvidenceStatus.REPRODUCIBLE
    return manifest.evidence_status


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
    """Return Status claims that lack a study at the required rank.

    Known limitation: authorization binds to the section ID, and a section
    holds several distinct question bullets. A study listing ``B2`` therefore
    authorizes a reserved rank on every B2 bullet, not only the bullet the
    study actually covers. The sharper rule is to bind each claim to the bullet
    that makes it, which needs stable per-bullet IDs in the inventory and a
    ``research_questions`` schema in ``study.yaml`` that can name them; both are
    out of scope here.
    """

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


def iter_start_here_fragments(markdown: str) -> list[tuple[int, str]]:
    """Return ``(line_number, fragment)`` for links in the Start here box."""

    fragments: list[tuple[int, str]] = []
    in_box = False
    for line_number, line in enumerate(markdown.splitlines(), start=1):
        if START_HERE_HEADING.match(line):
            in_box = True
            continue
        if in_box and START_HERE_END.match(line) and not START_HERE_HEADING.match(line):
            break
        if not in_box:
            continue
        fragments.extend((line_number, match.group(1)) for match in START_HERE_LINK.finditer(line))
    return fragments


def _anchor_line_numbers(markdown: str) -> dict[str, int]:
    found: dict[str, int] = {}
    for line_number, line in enumerate(markdown.splitlines(), start=1):
        for match in EXPLICIT_ANCHOR.finditer(line):
            found.setdefault(match.group(1), line_number)
    return found


def _status_after(markdown: str, start_line: int) -> str | None:
    """Return the next Status block after ``start_line``, if it belongs to that question."""

    lines = markdown.splitlines()
    index = start_line - 1
    while index < len(lines):
        line = lines[index]
        if index > start_line - 1 and (line.startswith("#") or line.startswith("- **")):
            return None
        marker = STATUS_MARKER.search(line)
        if marker is None:
            index += 1
            continue
        block = [line[marker.end() :]]
        index += 1
        while index < len(lines):
            nxt = lines[index]
            if STATUS_MARKER.search(nxt) or STATUS_END.match(nxt):
                break
            block.append(nxt)
            index += 1
        return " ".join(part.strip() for part in block if part.strip())
    return None


def start_here_status_is_allowed(status_text: str) -> bool:
    """Start-here Status must be a reserved rank or an explicit refusal."""

    return bool(claimed_ranks(status_text) or REFUSAL_STATUS.search(status_text))


def validate_start_here(
    markdown: str, *, path: str = INVENTORY_PATH.as_posix()
) -> list[StatusViolation]:
    """Require Start here links to land on a question with a legal Status."""

    anchors = _anchor_line_numbers(markdown)
    violations: list[StatusViolation] = []
    for line_number, fragment in iter_start_here_fragments(markdown):
        target = anchors.get(fragment)
        if target is None:
            violations.append(
                StatusViolation(
                    path=path,
                    line_number=line_number,
                    message=(
                        f"Start here link #{fragment} has no explicit "
                        f'<a id="{fragment}"> question anchor'
                    ),
                )
            )
            continue
        status = _status_after(markdown, target)
        if status is None:
            violations.append(
                StatusViolation(
                    path=path,
                    line_number=line_number,
                    message=(f"Start here link #{fragment} has no Status on the anchored question"),
                )
            )
            continue
        if start_here_status_is_allowed(status):
            continue
        excerpt = re.sub(r"\s+", " ", status).strip()
        if len(excerpt) > 160:
            excerpt = excerpt[:157] + "..."
        violations.append(
            StatusViolation(
                path=path,
                line_number=line_number,
                message=(
                    f"Start here link #{fragment} must target a reserved Status "
                    f"rank or an explicit refusal (Not computable / Not estimable): "
                    f"{excerpt}"
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
        listed = load_question_study_ids(repository_root=repository_root)
    except (OSError, ValueError, ConfigurationError) as exc:
        return [
            StatusViolation(
                path=INVENTORY_PATH.as_posix(),
                line_number=1,
                message=f"cannot load inventory or study manifests: {exc}",
            )
        ]
    return [
        *validate_inventory(markdown, ranks, path=INVENTORY_PATH.as_posix()),
        *validate_start_here(markdown, path=INVENTORY_PATH.as_posix()),
        *validate_study_discoverability(markdown, listed, path=INVENTORY_PATH.as_posix()),
    ]


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
