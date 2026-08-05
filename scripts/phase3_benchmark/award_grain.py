"""Award-grain attribution: link a notice to the specific prior award it cites.

The firm-grain corpus (query = a firm's longest abstract, attributed by firm
name) underperforms because the study's own finding is that **award-level
matching beats firm-level** (0.844 vs 0.809), and firm-name attribution admits
boilerplate false positives (a portal operator's name is in every BAA).

Sole-source J&As cite the prior SBIR contract number in-text ("SBIR Phase I
contract number HQ085022C0009"). Extracting that number and resolving it against
``award_data.csv`` attributes the notice to **one specific award** — dispositive,
no name ambiguity — and yields **that award's** abstract as the topically-matched
query. Measured: 44/53 recovered J&As resolve this way.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

import pandas as pd


# Federal contract PIIDs: a 4-6 char alphanumeric prefix, a 2-digit FY, a single
# contract-type letter, and a 3-4 digit serial (dashes/spaces optional). Covers
# the DoD forms that dominate SBIR J&As (N00014-20-C-0055, HQ085022C0009,
# FA8650-19-C-1234, W911NF-18-C-0100).
_PIID_RE = re.compile(r"\b([A-Z0-9]{4,6}[- ]?\d{2}[- ]?[A-Z][- ]?\d{3,4})\b")

MIN_PIID_LEN = 10


def normalize_piid(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def extract_cited_piids(text: object) -> set[str]:
    """Contract PIIDs cited in free text, normalized, >= MIN_PIID_LEN chars."""

    if text is None:
        return set()
    found = {normalize_piid(match) for match in _PIID_RE.findall(str(text).upper())}
    return {piid for piid in found if len(piid) >= MIN_PIID_LEN}


def build_award_index(award_data: pd.DataFrame) -> dict[str, dict[str, str]]:
    """Map normalized SBIR contract number → {abstract, company, uei}.

    Keeps the first award carrying a usable (>50 char) abstract for each
    contract key; contracts without one are skipped (they cannot be a query).
    """

    index: dict[str, dict[str, str]] = {}
    for _, row in award_data.iterrows():
        key = normalize_piid(row.get("Contract"))
        if len(key) < MIN_PIID_LEN or key in index:
            continue
        abstract = str(row.get("Abstract") or "")
        if len(abstract) <= 50:
            continue
        index[key] = {
            "abstract": abstract,
            "company": str(row.get("Company") or ""),
            "uei": str(row.get("UEI") or ""),
        }
    return index


def attribute_by_citation(
    description: object,
    award_index: dict[str, dict[str, str]],
) -> tuple[str, dict[str, str]] | None:
    """Resolve the first cited PIID that indexes to a known award.

    Returns ``(piid, award_record)`` — the specific prior award the notice
    continues — or None when no cited PIID resolves.
    """

    for piid in sorted(extract_cited_piids(description)):
        award = award_index.get(piid)
        if award is not None:
            return piid, award
    return None


def award_index_from_csv(path: str, contract_keys: Iterable[str] | None = None) -> dict[str, dict]:
    """Load ``award_data.csv`` into an award index (optionally pre-filtered)."""

    frame = pd.read_csv(path, usecols=["Contract", "UEI", "Abstract", "Company"], dtype=str)
    if contract_keys is not None:
        wanted = set(contract_keys)
        frame = frame.loc[frame["Contract"].map(normalize_piid).isin(wanted)]
    return build_award_index(frame)


__all__ = [
    "attribute_by_citation",
    "award_index_from_csv",
    "build_award_index",
    "extract_cited_piids",
    "normalize_piid",
]
