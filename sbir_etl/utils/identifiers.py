"""Canonical identifier normalizers for UEI, DUNS, and CAGE codes."""

from __future__ import annotations

from typing import Any

from sbir_etl.utils.coercion import _blank


def normalize_uei(v: Any) -> str | None:
    """Return a 12-char alphanumeric uppercased UEI, or None.

    Strips non-alphanumeric characters; returns None for blank/NA input
    or if the cleaned result is not exactly 12 characters.
    """
    if _blank(v):
        return None
    s = "".join(ch for ch in str(v) if ch.isalnum()).upper()
    return s if len(s) == 12 else None


def normalize_duns(v: Any) -> str | None:
    """Return a 9-digit DUNS string, or None.

    Strips non-digit characters; returns None for blank/NA input
    or if the cleaned result is not exactly 9 digits.
    """
    if _blank(v):
        return None
    digits = "".join(ch for ch in str(v) if ch.isdigit())
    return digits if len(digits) == 9 else None


def normalize_cage(v: Any) -> str | None:
    """Return a 5-character uppercased CAGE code, or None.

    Returns None for blank/NA input or if the value is not exactly 5 characters.
    """
    if _blank(v):
        return None
    s = str(v)
    return s.upper() if len(s) == 5 else None
