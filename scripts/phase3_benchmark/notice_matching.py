"""Firm-attribution matching for Phase III notice recovery.

The rich SBIR text lives in pre-award notices (Solicitation / Presolicitation /
Special Notice / Sources Sought — median ~4k chars in the archive), which are
keyed by firm identity, not the downstream contract PIID. Attribution is
therefore by firm, high-precision-first:

1. ``piid_cite`` — the notice cites the firm's own SBIR/contract PIID.
2. ``name_in_awardee`` — the notice's Awardee field is the firm.
3. ``name_in_desc`` — the firm's full normalized name appears in an
   SBIR-mentioning description.

Full-name (not token) matching avoids the generic-token false positives that a
naive token match produces (e.g. "Technology Service Corp" → "service").
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sbir_etl.identity import CompanyNameProfile, normalize_company_name

_NKEY_RE = re.compile(r"[^A-Z0-9]")

# Minimum lengths guard against short, ambiguous keys matching by chance.
MIN_NAME_KEY = 8
MIN_PIID_KEY = 10


def normalize_key(value: object) -> str:
    """Collapse text to bare uppercase alphanumerics."""

    return _NKEY_RE.sub("", str(value or "").upper())


def normalize_firm_name(name: object) -> str:
    """Normalize a firm name for matching: drop legal suffixes, then keyify."""

    return normalize_company_name(name, profile=CompanyNameProfile.NOTICE_KEY_V1)


@dataclass(frozen=True)
class FirmKey:
    firm: str
    name_key: str
    piids: frozenset[str]


def build_firm_keys(records: list[dict[str, object]]) -> list[FirmKey]:
    """Build match keys from seed firm records, dropping firms with no usable key."""

    firms: list[FirmKey] = []
    for record in records:
        name_key = normalize_firm_name(record.get("firm"))
        raw_piids = record.get("piids") or []
        piids = frozenset(
            key
            for key in (normalize_key(p) for p in raw_piids)  # type: ignore[attr-defined]
            if len(key) >= MIN_PIID_KEY
        )
        if len(name_key) < MIN_NAME_KEY and not piids:
            continue
        firms.append(FirmKey(firm=str(record.get("firm") or ""), name_key=name_key, piids=piids))
    return firms


def attribute_notice(
    description: str,
    awardee: str,
    firms: list[FirmKey],
) -> tuple[str, str] | None:
    """Attribute an SBIR-mentioning notice to a seed firm, or None.

    Caller is responsible for the "sbir" gate; this applies the ranked rules.
    """

    desc_key = normalize_key(description)
    awardee_key = normalize_key(awardee)
    best: tuple[str, str] | None = None
    best_rank = 99
    for firm in firms:
        if firm.piids and any(piid in desc_key for piid in firm.piids):
            return firm.firm, "piid_cite"  # rank 0 — dispositive, stop early
        if len(firm.name_key) >= MIN_NAME_KEY:
            if firm.name_key in awardee_key and best_rank > 1:
                best, best_rank = (firm.firm, "name_in_awardee"), 1
            elif firm.name_key in desc_key and best_rank > 2:
                best, best_rank = (firm.firm, "name_in_desc"), 2
    return best


__all__ = [
    "FirmKey",
    "attribute_notice",
    "build_firm_keys",
    "normalize_firm_name",
    "normalize_key",
]
