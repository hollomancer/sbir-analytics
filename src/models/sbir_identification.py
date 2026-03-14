"""SBIR/STTR identification reference data for federal procurement and financial assistance.

This module provides authoritative identifiers for detecting SBIR/STTR awards
across USAspending contract (FPDS) and grant (FABS) data:

- FPDS ``research`` field codes (SR1–SR3, ST1–ST3) for contracts
- Assistance Listing Numbers (ALN, formerly CFDA) for grants
- Helper functions for classification

References:
    - FPDS Data Dictionary Element 10Q (FAR 35.106)
    - https://www.fpds.gov/help/Research.htm
    - SAM.gov Federal Assistance Listings
"""

from __future__ import annotations

from enum import Enum


# ---------------------------------------------------------------------------
# FPDS research field codes (contracts)
# ---------------------------------------------------------------------------


class SbirResearchCode(str, Enum):
    """FPDS ``research`` field values — exclusively SBIR/STTR identifiers.

    Despite the generic field name, the FPDS ``research`` field (Data Dictionary
    Element 10Q, FAR 35.106) contains *only* SBIR/STTR codes.  Non-SBIR/STTR
    contracts have this field blank/null.
    """

    SR1 = "SR1"  # SBIR Phase I
    SR2 = "SR2"  # SBIR Phase II
    SR3 = "SR3"  # SBIR Phase III
    ST1 = "ST1"  # STTR Phase I
    ST2 = "ST2"  # STTR Phase II
    ST3 = "ST3"  # STTR Phase III


#: Set of all valid research codes for SQL IN clauses / set membership tests
SBIR_RESEARCH_CODES: frozenset[str] = frozenset(code.value for code in SbirResearchCode)

#: SBIR-only codes (excludes STTR)
SBIR_ONLY_CODES: frozenset[str] = frozenset({"SR1", "SR2", "SR3"})

#: STTR-only codes
STTR_ONLY_CODES: frozenset[str] = frozenset({"ST1", "ST2", "ST3"})

#: Mapping from research code to (program, phase) tuple
RESEARCH_CODE_DETAIL: dict[str, tuple[str, int]] = {
    "SR1": ("SBIR", 1),
    "SR2": ("SBIR", 2),
    "SR3": ("SBIR", 3),
    "ST1": ("STTR", 1),
    "ST2": ("STTR", 2),
    "ST3": ("STTR", 3),
}


def parse_research_code(code: str | None) -> tuple[str, int] | None:
    """Parse an FPDS research code into (program, phase).

    Args:
        code: FPDS research field value (e.g. ``"SR2"``).

    Returns:
        ``("SBIR", 2)`` for ``"SR2"``, or ``None`` if not a valid code.
    """
    if not code:
        return None
    return RESEARCH_CODE_DETAIL.get(code.strip().upper())


# ---------------------------------------------------------------------------
# Assistance Listing Numbers (ALN / CFDA) for SBIR/STTR grants
# ---------------------------------------------------------------------------

#: ALN numbers that are *exclusively* or *primarily* SBIR/STTR programs.
#: For agencies like HHS/NIH where SBIR grants share ALNs with non-SBIR
#: programs, we list the most common ones but note they require additional
#: validation (e.g. cross-reference with SBIR.gov or description parsing).
SBIR_ASSISTANCE_LISTING_NUMBERS: dict[str, dict[str, list[str] | bool]] = {
    "USDA": {
        "alns": ["10.212"],
        "exclusive": True,  # ALN is exclusively SBIR/STTR
    },
    "DoD": {
        "alns": ["12.910", "12.911"],
        "exclusive": True,
    },
    "DOE": {
        "alns": ["81.049"],
        "exclusive": False,  # DOE Office of Science shares this ALN
    },
    "NASA": {
        "alns": ["43.002", "43.003"],
        "exclusive": True,
    },
    "NSF": {
        "alns": ["47.041", "47.084"],
        "exclusive": True,
    },
    "EPA": {
        "alns": ["66.511", "66.512"],
        "exclusive": True,
    },
    "DHS": {
        "alns": ["97.077"],
        "exclusive": True,
    },
    "DOT": {
        "alns": ["20.701"],
        "exclusive": False,  # shared with other transportation R&D
    },
    "ED": {
        "alns": ["84.133"],
        "exclusive": False,  # shared with NIDILRR non-SBIR grants
    },
    "HHS": {
        # NIH institutes each have their own ALN; these are the most common
        # ones used for SBIR/STTR. Not exclusive — same ALNs fund non-SBIR.
        "alns": [
            "93.855",  # NIAID
            "93.856",  # NCI Microbiology & Infectious Diseases
            "93.859",  # NIGMS Biomedical Research
            "93.837",  # NHLBI
            "93.847",  # NIDDK
            "93.853",  # NINDS
            "93.865",  # NICHD
            "93.866",  # NIA
            "93.867",  # NIDCD
            "93.879",  # NEI
            "93.242",  # NIMH
            "93.273",  # NIAAA
            "93.279",  # NIDA
            "93.395",  # NCI Cancer Treatment
            "93.393",  # NCI Cancer Cause & Prevention
            "93.394",  # NCI Cancer Detection
            "93.396",  # NCI Cancer Biology
            "93.399",  # NCI Cancer Control
        ],
        "exclusive": False,
    },
}

#: Flat set of all SBIR/STTR ALNs (for quick membership tests)
ALL_SBIR_ALNS: frozenset[str] = frozenset(
    aln
    for agency_info in SBIR_ASSISTANCE_LISTING_NUMBERS.values()
    for aln in agency_info["alns"]  # type: ignore[union-attr]
)

#: ALNs that are exclusively SBIR/STTR (high-confidence identification)
EXCLUSIVE_SBIR_ALNS: frozenset[str] = frozenset(
    aln
    for agency_info in SBIR_ASSISTANCE_LISTING_NUMBERS.values()
    if agency_info["exclusive"]
    for aln in agency_info["alns"]  # type: ignore[union-attr]
)


def is_sbir_grant(cfda_number: str | None, *, strict: bool = False) -> bool:
    """Check whether a CFDA/ALN number indicates an SBIR/STTR grant.

    Args:
        cfda_number: The Assistance Listing Number (e.g. ``"12.910"``).
        strict: If ``True``, only match ALNs that are *exclusively* SBIR/STTR.
                If ``False``, match any ALN associated with SBIR programs
                (may include some non-SBIR grants for agencies like HHS).

    Returns:
        ``True`` if the ALN is associated with SBIR/STTR programs.
    """
    if not cfda_number:
        return False
    normalized = cfda_number.strip()
    if strict:
        return normalized in EXCLUSIVE_SBIR_ALNS
    return normalized in ALL_SBIR_ALNS


def classify_sbir_award(
    *,
    research_code: str | None = None,
    cfda_number: str | None = None,
    description: str | None = None,
) -> dict[str, object] | None:
    """Classify an award as SBIR/STTR using available identifiers.

    Checks identifiers in order of reliability:
    1. FPDS ``research`` field (authoritative for contracts)
    2. Assistance Listing Number (authoritative for exclusive-ALN grants)
    3. Description text parsing (fallback heuristic)

    Args:
        research_code: FPDS research field value.
        cfda_number: Assistance Listing Number.
        description: Award description text for heuristic parsing.

    Returns:
        Dict with ``program``, ``phase``, ``method``, ``confidence`` keys,
        or ``None`` if no SBIR/STTR classification can be made.
    """
    # 1. FPDS research field — authoritative
    parsed = parse_research_code(research_code)
    if parsed:
        program, phase = parsed
        return {
            "program": program,
            "phase": phase,
            "method": "fpds_research_field",
            "confidence": 1.0,
        }

    # 2. ALN — authoritative for exclusive ALNs, high-confidence for others
    if cfda_number and is_sbir_grant(cfda_number):
        exclusive = is_sbir_grant(cfda_number, strict=True)
        return {
            "program": "SBIR/STTR",  # ALN doesn't distinguish SBIR vs STTR
            "phase": None,  # ALN doesn't indicate phase
            "method": "assistance_listing_number",
            "confidence": 1.0 if exclusive else 0.8,
        }

    # 3. Description heuristic — lowest confidence
    if description:
        result = _parse_sbir_from_description(description)
        if result:
            return result

    return None


def _parse_sbir_from_description(description: str) -> dict[str, object] | None:
    """Parse SBIR/STTR indicators from award description text."""
    import re

    desc_upper = description.upper()

    # Must contain SBIR or STTR keyword
    is_sbir = "SBIR" in desc_upper
    is_sttr = "STTR" in desc_upper

    if not (is_sbir or is_sttr):
        # Check for less specific indicators
        if not any(
            kw in desc_upper for kw in ("SMALL BUSINESS INNOVATION", "SMALL BUSINESS TECHNOLOGY")
        ):
            return None

    program = "STTR" if is_sttr and not is_sbir else "SBIR" if is_sbir else "SBIR/STTR"

    # Extract phase
    phase_patterns = [
        (r"\bPHASE\s*III\b", 3),
        (r"\bPHASE\s*3\b", 3),
        (r"\bPHASE\s*II\b", 2),
        (r"\bPHASE\s*2\b", 2),
        (r"\bPHASE\s*I\b", 1),
        (r"\bPHASE\s*1\b", 1),
    ]

    phase = None
    for pattern, p in phase_patterns:
        if re.search(pattern, desc_upper):
            phase = p
            break

    return {
        "program": program,
        "phase": phase,
        "method": "description_parsing",
        "confidence": 0.7 if phase else 0.5,
    }


__all__ = [
    "ALL_SBIR_ALNS",
    "EXCLUSIVE_SBIR_ALNS",
    "RESEARCH_CODE_DETAIL",
    "SBIR_ASSISTANCE_LISTING_NUMBERS",
    "SBIR_ONLY_CODES",
    "SBIR_RESEARCH_CODES",
    "STTR_ONLY_CODES",
    "SbirResearchCode",
    "classify_sbir_award",
    "is_sbir_grant",
    "parse_research_code",
]
