"""Classified vocabulary for SBIR/STTR *program* provenance.

Epistemic tier: primitives. One implementation of the program rules, with
versioned behavior: adding a spelling or a source code to the vocabulary is a
reviewed change.

Two independent sources state the program directly:

- The SBIR.gov award export ``Program`` column, which is the canonical
  program field for an SBIR.gov award row.
- FPDS Element 10Q (the ``research`` field), whose ``SR*`` codes mean SBIR and
  ``ST*`` codes mean STTR. The phase digit is read by the phase rules; here
  only the program letter pair matters.

Nothing else states the program. Firm, agency, NAICS/PSC, a paired Phase II
award, and the identifier basis that produced a match are all *correlates*;
deriving program from any of them is imputation and this module deliberately
offers no function that does it. When neither source is present the answer is
None, and None must be carried as unknown rather than resolved -- see
:func:`program_specific_measure`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, TypeVar


EPISTEMIC_TIER = "primitives"

SbirProgram = Literal["SBIR", "STTR"]

_NULL_PROGRAM_TOKENS = frozenset({"", "<NA>", "NAN", "NONE", "NULL", r"\N"})

# The literal ``Program`` spellings the SBIR.gov export is known to emit,
# keyed exactly as written (after whitespace folding and case folding).
SBIR_PROGRAM_VOCABULARY: Mapping[str, SbirProgram] = MappingProxyType(
    {
        "SBIR": "SBIR",
        "STTR": "STTR",
    }
)

# FPDS Element 10Q ``research`` codes. The first two letters carry the
# program: ``SR`` = SBIR, ``ST`` = STTR. The trailing digit is the phase and
# is classified by the phase rules, not here, so every phase is listed
# explicitly rather than matched by prefix -- an unrecognized code must fall
# through to None instead of being decoded by a pattern we never verified.
FPDS_RESEARCH_PROGRAM_CODES: Mapping[str, SbirProgram] = MappingProxyType(
    {
        "SR1": "SBIR",
        "SR2": "SBIR",
        "SR3": "SBIR",
        "ST1": "STTR",
        "ST2": "STTR",
        "ST3": "STTR",
    }
)


def _program_text(value: object) -> str | None:
    """Return the whitespace-collapsed, upper-cased label, or None if absent."""

    if value is None or (isinstance(value, float) and value != value):
        return None
    text = " ".join(str(value).split()).upper()
    return None if text in _NULL_PROGRAM_TOKENS else text


def normalize_sbir_program(value: object) -> SbirProgram | None:
    """Return the exact SBIR.gov ``Program`` label as ``"SBIR"``, ``"STTR"``, or None.

    Exact match only, after folding whitespace and case. A combined or
    ambiguous label (``"SBIR/STTR"``) is None: it names two programs, and
    picking one by substring order would assign a program the source never
    stated. This is deliberately stricter than the lenient
    ``Award.validate_program`` validator, which exists to preserve a record
    rather than to establish provenance.
    """

    text = _program_text(value)
    if text is None:
        return None
    return SBIR_PROGRAM_VOCABULARY.get(text)


def program_from_fpds_research_code(value: object) -> SbirProgram | None:
    """Return the program a 10Q ``research`` code states, or None.

    ``SR3`` -> ``"SBIR"``, ``ST3`` -> ``"STTR"``, and likewise for the Phase I
    and Phase II codes. Any other value -- including a descriptive phase
    string such as ``"PHASE III"``, which states a phase but no program --
    is None.
    """

    text = _program_text(value)
    if text is None:
        return None
    return FPDS_RESEARCH_PROGRAM_CODES.get(text)


def unknown_sbir_program_values(values: Iterable[object]) -> list[str]:
    """Return the sorted distinct labels that :func:`normalize_sbir_program` rejects.

    Blank and sentinel values are not reported. A non-empty result means a
    source emitted a ``Program`` spelling this repository has not classified;
    the caller should surface it rather than guess, because guessing silently
    moves award populations between programs.
    """

    unknown: set[str] = set()
    for value in values:
        text = _program_text(value)
        if text is None or normalize_sbir_program(text) is not None:
            continue
        unknown.add(text)
    return sorted(unknown)


T = TypeVar("T")


@dataclass(frozen=True)
class ProgramMeasure:
    """A program-specific rate with its unknown-program stratum reported beside it.

    ``numerator`` and ``denominator`` count only records whose program is
    known and equals the requested program. ``unknown_program`` counts records
    carrying no program at all; they are excluded from *both* numerator and
    denominator and are never redistributed. ``total`` is every record
    considered, so ``total - denominator - unknown_program`` is the count
    belonging to a different, known program.
    """

    program: SbirProgram
    numerator: int
    denominator: int
    unknown_program: int
    total: int

    @property
    def rate(self) -> float | None:
        """Numerator over denominator, or None when the denominator is empty."""

        if self.denominator == 0:
            return None
        return self.numerator / self.denominator

    @property
    def program_coverage(self) -> float | None:
        """Share of considered records whose program is known, or None if empty.

        Report this with every :attr:`rate`. A rate computed over a population
        with low program coverage is a rate over the coded subset, not over the
        program.
        """

        if self.total == 0:
            return None
        return (self.total - self.unknown_program) / self.total


def program_specific_measure(
    records: Iterable[T],
    program: SbirProgram,
    *,
    program_of: Callable[[T], object],
    event_of: Callable[[T], bool],
) -> ProgramMeasure:
    """Count a program-specific rate under the unknown-program exclusion policy.

    The policy, implemented here rather than described in prose so that every
    caller gets it:

    1. A record whose program is unknown (None, blank, or an unclassified
       spelling) enters neither the numerator nor the denominator. It is
       counted in ``unknown_program`` so the exclusion is visible.
    2. A record belonging to a different known program enters neither.
    3. Only a record whose program is known and equal to ``program`` enters the
       denominator, and the numerator when ``event_of`` is true.

    ``program_of`` is applied through :func:`normalize_sbir_program`, so a
    caller cannot accidentally admit an unclassified spelling by returning a
    raw source string.
    """

    numerator = 0
    denominator = 0
    unknown = 0
    total = 0
    for record in records:
        total += 1
        record_program = normalize_sbir_program(program_of(record))
        if record_program is None:
            unknown += 1
            continue
        if record_program != program:
            continue
        denominator += 1
        if event_of(record):
            numerator += 1
    return ProgramMeasure(
        program=program,
        numerator=numerator,
        denominator=denominator,
        unknown_program=unknown,
        total=total,
    )


__all__ = [
    "EPISTEMIC_TIER",
    "FPDS_RESEARCH_PROGRAM_CODES",
    "SBIR_PROGRAM_VOCABULARY",
    "ProgramMeasure",
    "SbirProgram",
    "normalize_sbir_program",
    "program_from_fpds_research_code",
    "program_specific_measure",
    "unknown_sbir_program_values",
]
