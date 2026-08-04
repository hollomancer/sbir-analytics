"""Versioned identity for one public SBIR/STTR award.

Epistemic tier: primitives. Changes that alter an emitted key require a new
``SbirAwardKeyProfile`` member; existing profiles are immutable contracts.
"""

import hashlib
import re
from datetime import date
from enum import StrEnum
from typing import Any, Protocol

import pandas as pd


EPISTEMIC_TIER = "primitives"


class AwardRow(Protocol):
    """Minimal mapping interface accepted by the identity functions."""

    def get(self, key: str, default: Any = None) -> Any: ...


class SbirAwardKeyProfile(StrEnum):
    """Named, immutable SBIR award-key behaviors."""

    SBIR_SOURCE_V2 = "sbir-source-v2"


SBIR_AWARD_KEY_VERSION = SbirAwardKeyProfile.SBIR_SOURCE_V2.value

# Mutable report content such as title, abstract, amount, and recorded end
# date deliberately stays out of the identity. Changes to those fields are
# source editions of the same stable award.
SBIR_AWARD_KEY_FIELDS: tuple[tuple[str, ...], ...] = (
    ("Agency Tracking Number", "agency_tracking_number"),
    ("Contract", "contract_number", "contract"),
    ("Agency", "agency"),
    ("Branch", "branch", "sub_agency"),
    ("Phase", "phase"),
    ("Program", "program"),
    ("Proposal Award Date", "award_date", "proposal_award_date"),
    ("Solicitation Number", "solicitation_number"),
)


def _display(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple, dict)):
        try:
            if bool(pd.isna(value)):
                return None
        except (TypeError, ValueError):
            pass
    text = str(value).strip()
    return text if text and text.lower() not in {"nan", "nat", "none", "<na>"} else None


def _row_value(row: AwardRow, *names: str) -> str | None:
    for name in names:
        if (value := _display(row.get(name))) is not None:
            return value
    return None


def _identity_component(value: Any) -> str:
    return re.sub(r"\s+", " ", _display(value) or "").strip().upper()


def _canonical_award_date(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    match = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?:\D|$)", text)
    parts: tuple[str, str, str] | None
    if match is None:
        match = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})(?:\D|$)", text)
        parts = (match.group(3), match.group(1), match.group(2)) if match else None
    else:
        parts = (match.group(1), match.group(2), match.group(3))
    if parts is None:
        return value
    try:
        year, month, day = (int(part) for part in parts)
        return date(year, month, day).isoformat()
    except ValueError:
        return value


def sbir_award_public_id(row: AwardRow) -> str | None:
    """Return a readable public identifier without treating it as award grain."""

    return _row_value(
        row,
        "Agency Tracking Number",
        "agency_tracking_number",
        "Contract",
        "contract_number",
        "contract",
        "award_id",
    )


def sbir_award_grain_key(
    row: AwardRow,
    *,
    profile: SbirAwardKeyProfile = SbirAwardKeyProfile.SBIR_SOURCE_V2,
) -> str:
    """Return the stable identity of one SBIR/STTR award.

    Existing keys are accepted only when their version exactly matches the
    requested profile. This prevents a normalized snapshot from silently
    crossing an identity migration.
    """

    if existing := _row_value(row, "award_key"):
        if _row_value(row, "award_key_version") != profile.value:
            raise ValueError(
                "pre-migration award_key cannot be reused; regenerate identity from raw awards"
            )
        return existing

    recipient = (
        _row_value(row, "UEI", "uei", "recipient_uei")
        or _row_value(row, "Duns", "duns", "recipient_duns")
        or _row_value(row, "Company", "company", "recipient_name")
    )
    values: list[str | None] = []
    for names in SBIR_AWARD_KEY_FIELDS:
        value = _row_value(row, *names)
        values.append(_canonical_award_date(value) if names[0] == "Proposal Award Date" else value)
    material = "|".join(_identity_component(value) for value in ("sbir", recipient, *values))
    return hashlib.sha256(material.encode()).hexdigest()[:24]


def stable_sbir_award_id(
    row: AwardRow,
    *,
    profile: SbirAwardKeyProfile = SbirAwardKeyProfile.SBIR_SOURCE_V2,
) -> str:
    """Return the public ID or a deterministic fallback derived from award grain."""

    natural = sbir_award_public_id(row)
    return (
        natural
        if natural is not None
        else "sbir-" + sbir_award_grain_key(row, profile=profile)[:20]
    )


__all__ = [
    "EPISTEMIC_TIER",
    "SBIR_AWARD_KEY_FIELDS",
    "SBIR_AWARD_KEY_VERSION",
    "SbirAwardKeyProfile",
    "sbir_award_grain_key",
    "sbir_award_public_id",
    "stable_sbir_award_id",
]
