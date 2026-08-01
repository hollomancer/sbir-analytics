"""Structural ranking features ported from the transition-ranker scoring core.

From the fusion ladder in ``specs/phase3-match-benchmark/transition-ranker.md``
(commit ``2bc346a6``): identifier cross-ref lifted award↔notice retrieval AUC
0.779 → 0.795 as a learned feature, and a single hit is near-dispositive,
reader-verifiable evidence — the notice text cites the firm's own SBIR
contract / topic / tracking number.
"""

from __future__ import annotations

import re
from collections.abc import Iterable


_IDENTIFIER_MIN_LENGTH = 6

_NKEY_RE = re.compile(r"[^A-Z0-9]")


def normalize_identifier(value: object) -> str:
    """Collapse an identifier or free text to bare uppercase alphanumerics."""

    return _NKEY_RE.sub("", str(value).upper())


def id_xref(notice_text: object, firm_identifiers: Iterable[object]) -> float:
    """1.0 iff the notice text cites one of the firm's SBIR identifiers.

    Identifiers shorter than 6 normalized characters are ignored — too short to
    be a meaningful contract/topic/tracking number and prone to false hits.
    """

    if notice_text is None:
        return 0.0
    haystack = normalize_identifier(notice_text)
    if not haystack:
        return 0.0
    for identifier in firm_identifiers:
        if identifier is None:
            continue
        needle = normalize_identifier(identifier)
        if len(needle) >= _IDENTIFIER_MIN_LENGTH and needle in haystack:
            return 1.0
    return 0.0


__all__ = ["id_xref", "normalize_identifier"]
