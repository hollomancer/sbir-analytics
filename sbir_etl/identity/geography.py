"""Versioned identity for U.S. states, districts, and territories.

Epistemic tier: primitives. Canonical names and normalization profiles are
immutable contracts; output-changing behavior requires a new profile version.
"""

import re
from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Any


EPISTEMIC_TIER = "primitives"


class USJurisdictionProfile(StrEnum):
    """Named U.S. jurisdiction normalization behaviors.

    Profiles are frozen contracts. A behavior change requires a new member
    (e.g. ``STRICT_V2``), never an edit to an existing one.

    ``PERMISSIVE_PREFIX_V1`` is a documented bridge that preserves the patent
    transformer's legacy behavior for backward compatibility. It is not intended
    as a permanent contract: the exit condition is migrating the patent
    transformer to ``STRICT_V1`` once its input data has been cleaned to emit
    only canonical codes. Until that migration is complete, the profile must
    remain and callers must pass it explicitly.
    """

    STRICT_V1 = "us-jurisdiction-strict-v1"
    PERMISSIVE_PREFIX_V1 = "us-jurisdiction-permissive-prefix-v1"


US_JURISDICTION_NAMES_V1: Mapping[str, str] = MappingProxyType(
    {
        "AL": "Alabama",
        "AK": "Alaska",
        "AZ": "Arizona",
        "AR": "Arkansas",
        "CA": "California",
        "CO": "Colorado",
        "CT": "Connecticut",
        "DE": "Delaware",
        "FL": "Florida",
        "GA": "Georgia",
        "HI": "Hawaii",
        "ID": "Idaho",
        "IL": "Illinois",
        "IN": "Indiana",
        "IA": "Iowa",
        "KS": "Kansas",
        "KY": "Kentucky",
        "LA": "Louisiana",
        "ME": "Maine",
        "MD": "Maryland",
        "MA": "Massachusetts",
        "MI": "Michigan",
        "MN": "Minnesota",
        "MS": "Mississippi",
        "MO": "Missouri",
        "MT": "Montana",
        "NE": "Nebraska",
        "NV": "Nevada",
        "NH": "New Hampshire",
        "NJ": "New Jersey",
        "NM": "New Mexico",
        "NY": "New York",
        "NC": "North Carolina",
        "ND": "North Dakota",
        "OH": "Ohio",
        "OK": "Oklahoma",
        "OR": "Oregon",
        "PA": "Pennsylvania",
        "RI": "Rhode Island",
        "SC": "South Carolina",
        "SD": "South Dakota",
        "TN": "Tennessee",
        "TX": "Texas",
        "UT": "Utah",
        "VT": "Vermont",
        "VA": "Virginia",
        "WA": "Washington",
        "WV": "West Virginia",
        "WI": "Wisconsin",
        "WY": "Wyoming",
        "DC": "District of Columbia",
        "PR": "Puerto Rico",
        "VI": "Virgin Islands",
        "GU": "Guam",
        "AS": "American Samoa",
        "MP": "Northern Mariana Islands",
    }
)

VALID_US_JURISDICTION_CODES_V1 = frozenset(US_JURISDICTION_NAMES_V1)

# Explicit source variations used by current production consumers. Canonical
# names are added separately; aliases remain visible so additions are reviewed
# as changes to this profile rather than hidden inside callers.
US_JURISDICTION_VARIATIONS_V1: Mapping[str, str] = MappingProxyType(
    {
        "CALIF": "CA",
        "FLA": "FL",
        "MASS": "MA",
        "MICH": "MI",
        "PENN": "PA",
        "TEX": "TX",
        "WASH": "WA",
        "WASHINGTON DC": "DC",
        "D.C.": "DC",
        "N.Y.": "NY",
        "N.J.": "NJ",
        "N.C.": "NC",
        "S.C.": "SC",
        "N.D.": "ND",
        "S.D.": "SD",
        "W.V.": "WV",
        "N.H.": "NH",
        "N.M.": "NM",
        "R.I.": "RI",
        "U.S. VIRGIN ISLANDS": "VI",
        "UNITED STATES VIRGIN ISLANDS": "VI",
        "COMMONWEALTH OF THE NORTHERN MARIANA ISLANDS": "MP",
    }
)


def _label_key(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().upper()
    if text.lower() in {"", "nan", "nat", "none", "<na>"}:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9]+", " ", text)).strip()


def _alias_index() -> dict[str, str]:
    aliases = {_label_key(name): code for code, name in US_JURISDICTION_NAMES_V1.items()}
    aliases.update({_label_key(name): code for name, code in US_JURISDICTION_VARIATIONS_V1.items()})
    return aliases


_ALIASES_V1 = MappingProxyType(_alias_index())


def normalize_us_jurisdiction(
    value: Any,
    *,
    profile: USJurisdictionProfile = USJurisdictionProfile.STRICT_V1,
) -> str | None:
    """Return a two-letter jurisdiction code under an explicit profile.

    ``STRICT_V1`` accepts only canonical codes, names, and declared aliases.
    ``PERMISSIVE_PREFIX_V1`` preserves the patent transformer's legacy behavior:
    an arbitrary two-letter alphabetic value passes through, and otherwise the
    first canonical name beginning with the supplied prefix is selected.
    """

    key = _label_key(value)
    if not key:
        return None
    if key in VALID_US_JURISDICTION_CODES_V1:
        return key
    if key in _ALIASES_V1:
        return _ALIASES_V1[key]
    if profile is USJurisdictionProfile.STRICT_V1:
        return None

    compact = key.replace(" ", "")
    if len(compact) == 2 and compact.isalpha():
        return compact
    for code, name in US_JURISDICTION_NAMES_V1.items():
        if _label_key(name).startswith(key):
            return code
    return None


def us_jurisdiction_name(code: Any) -> str | None:
    """Return the canonical display name for a strict jurisdiction code."""

    normalized = normalize_us_jurisdiction(code)
    return US_JURISDICTION_NAMES_V1.get(normalized) if normalized else None


__all__ = [
    "EPISTEMIC_TIER",
    "US_JURISDICTION_NAMES_V1",
    "US_JURISDICTION_VARIATIONS_V1",
    "USJurisdictionProfile",
    "VALID_US_JURISDICTION_CODES_V1",
    "normalize_us_jurisdiction",
    "us_jurisdiction_name",
]
