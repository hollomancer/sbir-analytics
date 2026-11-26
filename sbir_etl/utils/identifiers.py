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
    repairs a DUNS that was read as a number, rejects malformed values instead
    of pulling digits out of them, and rejects placeholder values.
    """

    DUNS_V1 = "duns-v1"
    DUNS_V2 = "duns-v2"


_DUNS_AS_DECIMAL_TEXT = re.compile(r"^\s*([0-9]{1,9})\.0+\s*$")
_DUNS_SEPARATORS = re.compile(r"[\s-]")
_DUNS_KEY = re.compile(r"[0-9]{9}")


def _is_placeholder(key: str) -> bool:
    """A key of one repeated character (000000000, 999999999) is a placeholder."""
    return len(set(key)) == 1


def _duns_v1(v: Any) -> str | None:
    if _blank(v):
        return None
    digits = "".join(ch for ch in str(v) if ch.isdigit())
    return digits if len(digits) == 9 else None


def _duns_v2(v: Any) -> str | None:
    if _blank(v) or isinstance(v, bool):
        return None
    if isinstance(v, Integral):
        if int(v) < 0:
            return None
        text = f"{int(v):09d}"
    elif isinstance(v, float):
        if v < 0 or not v.is_integer():
            return None
        text = f"{int(v):09d}"
    else:
        text = str(v)
        if whole := _DUNS_AS_DECIMAL_TEXT.match(text):
            text = f"{int(whole.group(1)):09d}"
        else:
            text = _DUNS_SEPARATORS.sub("", text)
    if not _DUNS_KEY.fullmatch(text) or _is_placeholder(text):
        return None
    return text


def normalize_duns(v: Any, profile: DunsProfile = DunsProfile.DUNS_V1) -> str | None:
    """Return a 9-digit DUNS string, or None.

    ``DUNS_V1`` (default): strip non-digit characters; return None for
    blank/NA input or if the result is not exactly 9 digits. A value such as
    "12345678.0" becomes "123456780" under this profile.

    ``DUNS_V2``:

    - A DUNS read as a number (pandas without ``dtype=str``) loses its leading
      zeros and may carry ".0", so whole non-negative numbers are formatted
      back to 9 digits. A string such as "12345678.0" is that number written
      as text and gets the same treatment, so it becomes "012345678".
    - Other text keeps only whitespace and hyphens as separators. After they
      are removed, the value must be exactly 9 ASCII digits. Letters, other
      punctuation, a non-zero fractional part, and non-ASCII digits make the
      value malformed, so it returns None.
    - A plain 8-digit string stays invalid: text sources keep leading zeros,
      so a short string is a truncated DUNS, not a number.
    - A key of one repeated digit, such as 000000000 or 999999999, is a
      placeholder and returns None.
    """
    profile = DunsProfile(profile)
    if profile is DunsProfile.DUNS_V1:
        return _duns_v1(v)
    return _duns_v2(v)


def normalize_cage(v: Any) -> str | None:
    """Return a 5-character uppercased CAGE code, or None.

    Returns None for blank/NA input or if the value is not exactly 5 characters.
    """
    if _blank(v):
        return None
    s = str(v)
    return s.upper() if len(s) == 5 else None


_NAICS_AS_DECIMAL_TEXT = re.compile(r"^([0-9]+)\.0+$")
_NAICS_CODE = re.compile(r"[1-9][0-9]{1,5}")


def normalize_naics(v: Any) -> str | None:
    """Return a 2- to 6-digit NAICS code string, or None.

    - Surrounding whitespace is removed.
    - A code read as a number may carry ".0" (``541712.0``). That float
      artifact is repaired, for numbers and for text, so it becomes "541712".
    - The result must be 2 to 6 ASCII digits. Letters, hyphens, other
      punctuation, and a non-zero fractional part make the value malformed, so
      it returns None. Digits are not pulled out of malformed text.
    - The code is never padded. "5417" stays "5417". A caller that needs a
      fixed width pads for its own lookup.
    - No NAICS code starts with 0, so a leading zero (for example the padded
      value "005417") returns None.
    """
    if _blank(v) or isinstance(v, bool):
        return None
    if isinstance(v, Integral):
        text = str(int(v))
    elif isinstance(v, float):
        if not v.is_integer():
            return None
        text = str(int(v))
    else:
        text = str(v).strip()
        if whole := _NAICS_AS_DECIMAL_TEXT.match(text):
            text = whole.group(1)
    return text if _NAICS_CODE.fullmatch(text) else None
