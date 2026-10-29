"""Classified vocabulary for the SBIR.gov award export ``Phase`` column.

Epistemic tier: primitives. One implementation of the two phase rules, with
versioned behavior: adding a spelling to the vocabulary is a reviewed change
recorded in ``docs/data/awards-refresh.md``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import MappingProxyType


EPISTEMIC_TIER = "primitives"

_NULL_PHASE_TOKENS = frozenset({"", "<NA>", "NAN", "NONE", "NULL", r"\N"})
_PHASE_LABELS = frozenset({"I", "II", "III"})

# The literal ``Phase`` spellings the public export is known to emit, keyed
# exactly as written, and the phase each one counts as. SBIR.gov added the
# direct-to-Phase-II value in the 2026-10-21 vintage by relabelling 3,303 rows
# that the 2026-09-17 vintage carried as plain ``Phase II``; the award rows
# themselves are unchanged, so this is a vocabulary change rather than new
# awards. The live export emits an en dash (U+2013); the ASCII hyphen is
# accepted so an upstream punctuation change is not an outage.
#
# Counting policy: a direct-to-Phase-II award is a Phase II award. It skips
# Phase I rather than being a different instrument, and SBA's published tables
# count it under Phase II.
DIRECT_TO_PHASE_II_LABELS: frozenset[str] = frozenset(
    {
        "Phase II \u2013 Direct to Phase II",
        "Phase II - Direct to Phase II",
    }
)
SBIR_PHASE_VOCABULARY: Mapping[str, str] = MappingProxyType(
    {
        "Phase I": "I",
        "Phase II": "II",
        "Phase III": "III",
        **dict.fromkeys(sorted(DIRECT_TO_PHASE_II_LABELS), "II"),
    }
)
_VOCABULARY_BY_FOLDED_LABEL: Mapping[str, str] = MappingProxyType(
    {" ".join(label.split()).upper(): phase for label, phase in SBIR_PHASE_VOCABULARY.items()}
)


def _phase_text(value: object) -> str | None:
    """Return the whitespace-collapsed, upper-cased label, or None if absent."""

    if value is None or (isinstance(value, float) and value != value):
        return None
    text = " ".join(str(value).split()).upper()
    return None if text in _NULL_PHASE_TOKENS else text


def normalize_sbir_phase(value: object) -> str | None:
    """Return the exact SBIR.gov ``Phase`` label as ``"I"``, ``"II"``, ``"III"``, or None.

    Accepts the bare numeral or the ``Phase <numeral>`` form after collapsing
    whitespace and folding case. Any other value is None: digits (``"2"``),
    suffix-coded labels (``"Phase II - Direct to Phase II"``), and ranges
    (``"Phase I/II"``) are not silently mapped to a base phase.

    This answers *what the source field literally says*. For any population
    count, table reconciliation, or phase filter use
    :func:`sbir_phase_for_counting`, which applies the counting policy that a
    direct-to-Phase-II award counts as Phase II.
    """

    text = _phase_text(value)
    if text is None:
        return None
    if text.startswith("PHASE "):
        text = text.removeprefix("PHASE ").strip()
    return text if text in _PHASE_LABELS else None


def sbir_phase_for_counting(value: object) -> str | None:
    """Return the phase a source label counts as, or None when unclassified.

    This is the counting rule: the classified vocabulary first, then the exact
    rule in :func:`normalize_sbir_phase`. Both rules fold whitespace and case
    the same way, so they differ only on the direct-to-Phase-II spellings,
    which count as ``"II"`` here and are None there.

    None means the label is outside both rules. Callers should treat it as a
    loud failure rather than as "no phase"; see :func:`unknown_sbir_phase_values`.
    """

    text = _phase_text(value)
    if text is None:
        return None
    phase = _VOCABULARY_BY_FOLDED_LABEL.get(text)
    return phase if phase is not None else normalize_sbir_phase(text)


def unknown_sbir_phase_values(values: Iterable[object]) -> list[str]:
    """Return the sorted distinct labels that :func:`sbir_phase_for_counting` rejects.

    Blank and sentinel values are not reported. A non-empty result means the
    export introduced a ``Phase`` spelling this repository has not classified;
    the caller should fail loudly rather than guess which phase it counts as,
    because guessing silently moves award populations.
    """

    unknown: set[str] = set()
    for value in values:
        text = _phase_text(value)
        if text is None or sbir_phase_for_counting(text) is not None:
            continue
        unknown.add(text)
    return sorted(unknown)


__all__ = [
    "DIRECT_TO_PHASE_II_LABELS",
    "EPISTEMIC_TIER",
    "SBIR_PHASE_VOCABULARY",
    "normalize_sbir_phase",
    "sbir_phase_for_counting",
    "unknown_sbir_phase_values",
]
