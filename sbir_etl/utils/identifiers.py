"""Canonical domain identifier normalizers.

Epistemic tier: primitives. Identity primitives depend on these UEI/DUNS/CAGE
normalizers, so output-changing behavior requires a versioned change under the
primitives contract, not the utils package default.
"""

from __future__ import annotations

import re
from enum import StrEnum
from numbers import Integral
from typing import Any

from sbir_etl.utils.coercion import _blank


EPISTEMIC_TIER = "primitives"


def normalize_uspto_identifier(value: Any) -> str | None:
    """Normalize an identifier carried by a USPTO record.

    This preserves the permissive USPTO ingestion contract: trim surrounding
    whitespace, remove characters other than Unicode word characters and
    hyphens, and uppercase the result. It does not validate identifier type or
    length; use the UEI, DUNS, and CAGE normalizers below when validation is
    required.
    """
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    return re.sub(r"[^\w\-]", "", normalized).upper()


def normalize_uei(v: Any) -> str | None:
    """Return a 12-char alphanumeric uppercased UEI, or None.

    Strips non-alphanumeric characters; returns None for blank/NA input
    or if the cleaned result is not exactly 12 characters.
    """
    if _blank(v):
        return None
    s = "".join(ch for ch in str(v) if ch.isalnum()).upper()
    return s if len(s) == 12 else None


class DunsProfile(StrEnum):
    """Named, versioned DUNS normalization behavior.

    ``DUNS_V1`` keeps digits and requires exactly 9 of them. ``DUNS_V2`` also
    repairs a DUNS that was read as a number and rejects placeholder values.
    """

    DUNS_V1 = "duns-v1"
    DUNS_V2 = "duns-v2"


_DUNS_AS_DECIMAL_TEXT = re.compile(r"^\s*(\d{1,9})\.0+\s*$")


def _is_placeholder(key: str) -> bool:
    """A key of one repeated character (000000000, 999999999) is a placeholder."""
    return len(set(key)) == 1


def _duns_digits(v: Any) -> str | None:
    if _blank(v):
        return None
    digits = "".join(ch for ch in str(v) if ch.isdigit())
    return digits if len(digits) == 9 else None


def normalize_duns(v: Any, profile: DunsProfile = DunsProfile.DUNS_V1) -> str | None:
    """Return a 9-digit DUNS string, or None.

    ``DUNS_V1`` (default): strip non-digit characters; return None for
    blank/NA input or if the result is not exactly 9 digits. A value such as
    "12345678.0" becomes "123456780" under this profile.

    ``DUNS_V2``: a DUNS read as a number (pandas without ``dtype=str``) loses
    its leading zeros and may carry ".0", so whole numbers are formatted back
    to 9 digits. A string such as "12345678.0" is that number written as text
    and gets the same treatment, so it becomes "012345678". A plain 8-digit
    string stays invalid: text sources keep leading zeros, so a short string
    is a truncated DUNS, not a number. A key of one repeated digit, such as
    000000000 or 999999999, is a placeholder and returns None.
    """
    profile = DunsProfile(profile)
    if profile is DunsProfile.DUNS_V1:
        return _duns_digits(v)
    if isinstance(v, Integral) and not isinstance(v, bool):
        v = f"{int(v):09d}"
    elif isinstance(v, float) and v.is_integer():
        v = f"{int(v):09d}"
    elif isinstance(v, str) and (whole := _DUNS_AS_DECIMAL_TEXT.match(v)):
        v = f"{int(whole.group(1)):09d}"
    key = _duns_digits(v)
    return None if key is None or _is_placeholder(key) else key


def normalize_cage(v: Any) -> str | None:
    """Return a 5-character uppercased CAGE code, or None.

    Returns None for blank/NA input or if the value is not exactly 5 characters.
    """
    if _blank(v):
        return None
    s = str(v)
    return s.upper() if len(s) == 5 else None
