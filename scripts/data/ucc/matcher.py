#!/usr/bin/env python3
"""UCC debtor-side fuzzy matching with address + person-name filters.

Filters extractor output to rows where the cohort firm matches the
debtor side of the filing (not the secured party — CA portal free-text
search returns hits on both fields).

Match decision combines three signals:
  1. Name similarity (Jaro-Winkler on normalized names)
  2. Address overlap (cohort firm's state/city vs filing debtor address)
  3. Person-name rejection (filings where the debtor is clearly a
     natural person, not the cohort entity, e.g. "AADITI MUJUMDAR" matching
     "AADI, LLC")

Pilot Phase 0 empirical motivation: 3 of 9 CA-organized cohort firms
(6K, AADI, Abom) returned 100% false-positive search hits — different
entities sharing a name token. Address-based disambiguation eliminates
most of these because the spurious matches are in different cities than
the cohort firm.

Reuses sbir_etl.enrichers.matching for name normalization + similarity.
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from sbir_etl.enrichers.matching import (  # noqa: E402
    ENHANCED_ABBREVIATIONS,
    SUFFIX_TOKENS,
    apply_enhanced_abbreviations,
    jaro_winkler_similarity,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ucc._common import data_path  # noqa: E402

# Name-tier thresholds (Jaro-Winkler 0..1)
TIER_MEDIUM_THRESHOLD = 0.92
TIER_LOW_THRESHOLD = 0.85

# Combined-score required for a final accept (after address + person filters)
ACCEPT_COMBINED_SCORE = 0.75

# Person-name detection: if a debtor name has no entity suffix and looks
# like First [Middle] Last, it's almost certainly a natural person, not
# the cohort firm.
_PERSON_NAME_RE = re.compile(
    r"^[A-Z][A-Za-z'’-]+(?:\s+[A-Z][A-Za-z'’-]*\.?){0,2}\s+[A-Z][A-Za-z'’-]+$"
)
_ENTITY_INDICATORS = {
    "inc", "incorporated", "llc", "l.l.c", "ltd", "limited",
    "corp", "corporation", "co", "company", "lp", "llp",
    "trust", "fund", "association", "partners", "partnership",
    "holdings", "group", "industries", "systems", "solutions",
    "technologies", "research", "sciences", "biosciences",
    "pharmaceuticals", "therapeutics", "labs", "laboratory",
    "bank", "capital", "ventures",
}


def normalize_name(name: str) -> str:
    """Lowercase, strip punctuation, expand abbreviations, drop suffix tokens."""
    if not name:
        return ""
    n = re.sub(r"[^a-z0-9 ]+", " ", name.lower())
    n = apply_enhanced_abbreviations(n, ENHANCED_ABBREVIATIONS)
    tokens = [t for t in n.split() if t not in SUFFIX_TOKENS]
    return " ".join(tokens).strip()


def classify_match(name_a: str, name_b: str) -> tuple[str, float]:
    """Return (tier, score) where tier ∈ {high, medium, low, drop}.

    Score is normalized to 0..1 (sbir_etl's jaro_winkler_similarity
    returns 0..100; we scale here).
    """
    a = normalize_name(name_a)
    b = normalize_name(name_b)
    if not a or not b:
        return ("drop", 0.0)
    if a == b:
        return ("high", 1.0)
    score = jaro_winkler_similarity(a, b) / 100.0
    if score >= TIER_MEDIUM_THRESHOLD:
        return ("medium", score)
    if score >= TIER_LOW_THRESHOLD:
        return ("low", score)
    return ("drop", score)


def looks_like_person_name(name: str) -> bool:
    """Heuristic: does this debtor name look like a natural person, not an entity?

    True iff:
      - Name has no recognizable entity-indicator tokens (after punctuation strip)
      - Name matches "First [Middle [Middle]] Last" — 2 to 4 capitalized tokens
    """
    if not name:
        return False
    # Strip all punctuation, lowercase, tokenize, check for entity indicators
    cleaned = re.sub(r"[^A-Za-z0-9 ]+", " ", name).strip()
    lowered_tokens = {t.lower() for t in cleaned.split()}
    if lowered_tokens & _ENTITY_INDICATORS:
        return False
    tokens = cleaned.split()
    if not 2 <= len(tokens) <= 4:
        return False
    if not all(t[:1].isupper() for t in tokens if t):
        return False
    return bool(_PERSON_NAME_RE.match(cleaned)) or _looks_like_caps_person(cleaned)


def _looks_like_caps_person(name: str) -> bool:
    """Backup heuristic for ALL-CAPS names like 'AADITI MUJUMDAR'."""
    tokens = name.split()
    if not 2 <= len(tokens) <= 4:
        return False
    # All tokens are alphabetic-only (no digits or special chars), length >= 2
    if not all(t.isalpha() and len(t) >= 2 for t in tokens):
        return False
    # Reject geographically/industrially descriptive words
    descriptive = {"PACIFIC", "ATLANTIC", "NORTH", "SOUTH", "EAST", "WEST",
                   "NEW", "OLD", "GLOBAL", "INTERNATIONAL", "AMERICAN",
                   "FIRST", "UNITED", "ADVANCED", "GENERAL"}
    if any(t.upper() in descriptive for t in tokens):
        return False
    return True


def address_city_state(address: str | None) -> tuple[str, str]:
    """Extract (city, state) from a CA UCC-style address.

    Address format observed: "STREET, CITY, ST  ZIP" with double space.
    Returns ("", "") if parse fails.
    """
    if not address:
        return ("", "")
    # Match the last two comma-separated chunks; the final one starts with state
    parts = [p.strip() for p in address.split(",")]
    if len(parts) < 2:
        return ("", "")
    last = parts[-1].strip()
    # Last chunk should be "ST ZIP" or just "ST"
    m = re.match(r"^([A-Z]{2})(?:\s+\S+)?$", last)
    if not m:
        return ("", "")
    state = m.group(1)
    # City is the second-to-last chunk
    city = parts[-2].strip().upper() if len(parts) >= 2 else ""
    return (city, state)


# SBIR awards data carries full state names ("Massachusetts"); CA UCC API
# returns 2-letter postal codes ("MA"). Normalize both before comparison.
_STATE_TO_POSTAL = {
    "ALABAMA": "AL", "ALASKA": "AK", "ARIZONA": "AZ", "ARKANSAS": "AR",
    "CALIFORNIA": "CA", "COLORADO": "CO", "CONNECTICUT": "CT", "DELAWARE": "DE",
    "FLORIDA": "FL", "GEORGIA": "GA", "HAWAII": "HI", "IDAHO": "ID",
    "ILLINOIS": "IL", "INDIANA": "IN", "IOWA": "IA", "KANSAS": "KS",
    "KENTUCKY": "KY", "LOUISIANA": "LA", "MAINE": "ME", "MARYLAND": "MD",
    "MASSACHUSETTS": "MA", "MICHIGAN": "MI", "MINNESOTA": "MN", "MISSISSIPPI": "MS",
    "MISSOURI": "MO", "MONTANA": "MT", "NEBRASKA": "NE", "NEVADA": "NV",
    "NEW HAMPSHIRE": "NH", "NEW JERSEY": "NJ", "NEW MEXICO": "NM", "NEW YORK": "NY",
    "NORTH CAROLINA": "NC", "NORTH DAKOTA": "ND", "OHIO": "OH", "OKLAHOMA": "OK",
    "OREGON": "OR", "PENNSYLVANIA": "PA", "RHODE ISLAND": "RI",
    "SOUTH CAROLINA": "SC", "SOUTH DAKOTA": "SD", "TENNESSEE": "TN", "TEXAS": "TX",
    "UTAH": "UT", "VERMONT": "VT", "VIRGINIA": "VA", "WASHINGTON": "WA",
    "WEST VIRGINIA": "WV", "WISCONSIN": "WI", "WYOMING": "WY",
    "DISTRICT OF COLUMBIA": "DC", "PUERTO RICO": "PR",
}


def to_postal(state: str | None) -> str:
    """Return the 2-letter postal abbreviation for any state input form."""
    if not state:
        return ""
    s = state.strip().upper()
    if len(s) == 2:
        return s
    return _STATE_TO_POSTAL.get(s, s[:2])


def address_overlap_score(
    cohort_state: str | None,
    filing_address: str | None,
    cohort_city: str | None = None,
) -> float:
    """Score 0..1 for how well the filing debtor's address matches the cohort firm's.

    Logic:
      - State mismatch → 0.0 (hard reject)
      - State match only → 0.5 (partial credit)
      - State + city match → 1.0
      - State match + city mismatch → 0.4
      - State match + no cohort city to compare → 0.5
    """
    cohort_postal = to_postal(cohort_state)
    if not cohort_postal:
        return 0.0
    filing_city, filing_state = address_city_state(filing_address)
    if not filing_state:
        return 0.0
    if filing_state.upper() != cohort_postal:
        return 0.0
    if cohort_city and filing_city:
        if filing_city.upper() == cohort_city.upper():
            return 1.0
        return 0.4
    return 0.5


def is_debtor_side_match(cohort_row: dict, filing: dict) -> bool:
    """Decide whether this UCC filing is a real debtor-side match for the cohort firm.

    Combines name similarity, address overlap, and person-name rejection.
    Order matters: name match is computed first; person-name heuristic only
    applies when the name is NOT an exact normalized match to the cohort
    firm (so "ACTIVE MOTIF" matching "ACTIVE MOTIF, INC." isn't rejected
    just because it structurally looks like "First Last").
    """
    cohort_name = cohort_row.get("company_name", "")
    cohort_state = cohort_row.get("state")
    cohort_city = cohort_row.get("city")
    debtor_name = filing.get("debtor_name", "")
    secured_party = filing.get("secured_party_name", "")

    # Filter 1: name similarity to debtor side
    debtor_tier, debtor_score = classify_match(cohort_name, debtor_name)
    if debtor_tier == "drop":
        return False

    # Filter 2: reject natural-person debtors ONLY when not an exact name match
    if debtor_tier != "high" and looks_like_person_name(debtor_name):
        return False

    # Filter 3: prefer debtor side over secured-party side
    sp_tier, sp_score = classify_match(cohort_name, secured_party)
    if sp_score > debtor_score:
        return False  # filing's match strength is on the secured-party side

    # Filter 4: address overlap (only if we have cohort state)
    if cohort_state:
        addr_score = address_overlap_score(
            cohort_state, filing.get("debtor_address"), cohort_city,
        )
        if addr_score == 0.0:
            # State mismatch is a hard reject — different debtor
            return False

    return True


def match_extraction(filing: dict, cohort_row: dict) -> dict | None:
    """Return a UCCMatch dict if the filing passes all filters; else None."""
    if not is_debtor_side_match(cohort_row, filing):
        return None
    cohort_name = cohort_row["company_name"]
    tier, score = classify_match(cohort_name, filing.get("debtor_name", ""))
    if tier in ("drop", "low"):
        return None  # headline excludes low-confidence matches
    return {
        "filing": filing,
        "cohort_company_name": cohort_name,
        "match_confidence": tier,
        "match_score": round(score, 4),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path,
                        default=data_path("ucc1_pilot_raw.jsonl"))
    parser.add_argument("--cohort", type=Path,
                        default=data_path("ucc1_pilot_ca_org_cohort.jsonl"))
    parser.add_argument("--out", type=Path,
                        default=data_path("ucc1_pilot_matches.jsonl"))
    args = parser.parse_args()

    cohort_by_name = {}
    with args.cohort.open() as f:
        for line in f:
            r = json.loads(line)
            cohort_by_name[r["company_name"]] = r

    matched = 0
    dropped = 0
    with args.raw.open() as raw_f, args.out.open("w") as out_f:
        for line in raw_f:
            filing = json.loads(line)
            cohort_name = filing.pop("cohort_company_name", None) or filing["debtor_name"]
            cohort_row = cohort_by_name.get(cohort_name)
            if cohort_row is None:
                # Fall back to a minimal cohort row inferred from the filing
                cohort_row = {"company_name": cohort_name}
            match = match_extraction(filing, cohort_row)
            if match is None:
                dropped += 1
                continue
            out_f.write(json.dumps(match) + "\n")
            matched += 1

    print(f"Matched: {matched} | Dropped: {dropped}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
