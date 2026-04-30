"""Form D XML parser and confidence scorer for SBIR-EDGAR matching.

Parses SEC Form D XML filings into structured dicts and computes a
multi-signal confidence score for matching a Form D filing to an SBIR company.
"""

from __future__ import annotations

import re
from datetime import date
from xml.etree import ElementTree

from rapidfuzz import fuzz

from ...models.sec_edgar import FormDMatchConfidence

# Titles that should be stripped from PI names before matching
_STRIP_TITLES = re.compile(
    r"\b(Dr\.|Ph\.D\.|M\.D\.|Mr\.|Mrs\.|Ms\.|Jr\.|Sr\.)\b", re.IGNORECASE
)
# Single-letter initials like "R." (but not "Jr." etc., already handled above)
_STRIP_INITIALS = re.compile(r"\b[A-Z]\.\s*")

# Industry groups structurally incompatible with SBIR companies.
# Offerings with these groups are almost entirely name-collision false
# positives (85-100% low-tier).  Used by downstream analysis to exclude
# offerings; not applied during fetch so raw data stays complete.
#
# "Pooled Investment Fund" is excluded because these are VC/PE fund
# vehicles, not operating company raises.  Some funds are linked to real
# SBIR companies via shared persons/CIKs (71 cross-links found) — worth
# revisiting for investor-company relationship mapping.
EXCLUDED_INDUSTRY_GROUPS: frozenset[str] = frozenset({
    "Insurance",
    "Lodging and Conventions",
    "Other Travel",
    "Pooled Investment Fund",
    "Restaurants",
    "Retailing",
    "Tourism and Travel Services",
})

_SECURITIES_MAP = {
    "isDebtType": "debt",
    "isEquityType": "equity",
    "isOptionToAcquireType": "options",
    "isMineralPropertyType": "mineral_property",
    "isPooledInvestmentFundType": "pooled_fund",
    "isTenantInCommonType": "tenant_in_common",
    "isOtherType": "other",
}


def _text(el: ElementTree.Element | None, path: str, default: str | None = None) -> str | None:
    """Return stripped text at the given XPath, or default."""
    if el is None:
        return default
    node = el.find(path)
    if node is None or node.text is None:
        return default
    return node.text.strip() or default


def _bool(el: ElementTree.Element | None, path: str) -> bool:
    """Return True if the text at path is 'true' (case-insensitive)."""
    val = _text(el, path)
    return (val or "").lower() == "true"


def _float(el: ElementTree.Element | None, path: str) -> float | None:
    raw = _text(el, path)
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _int(el: ElementTree.Element | None, path: str) -> int | None:
    raw = _text(el, path)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _parse_date(val: str | None) -> date | None:
    if not val:
        return None
    try:
        return date.fromisoformat(val)
    except ValueError:
        return None


def parse_form_d_xml(
    xml_text: str,
    accession_number: str,
    filing_date: date,
) -> dict | None:
    """Parse Form D XML into a dict matching FormDOffering fields.

    Returns None on any parse error (invalid XML, missing entity name, etc.).
    """
    if not xml_text or not xml_text.strip():
        return None

    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return None

    issuer = root.find("primaryIssuer")
    if issuer is None:
        return None

    entity_name = _text(issuer, "entityName")
    if not entity_name:
        return None

    cik = _text(issuer, "cik", "")

    # Year of incorporation — nested under yearOfInc/value
    year_of_inc_str = _text(issuer, "yearOfInc/value")
    year_of_inc: int | None = None
    if year_of_inc_str:
        try:
            year_of_inc = int(year_of_inc_str)
        except ValueError:
            pass

    addr = issuer.find("issuerAddress")

    offering = root.find("offeringData")

    # Securities types
    sec_types_el = offering.find("typesOfSecuritiesOffered") if offering is not None else None
    securities_types: list[str] = []
    if sec_types_el is not None:
        for tag, label in _SECURITIES_MAP.items():
            if _bool(sec_types_el, tag):
                securities_types.append(label)

    # Federal exemption (first item element)
    fed_exemption: str | None = None
    if offering is not None:
        item_el = offering.find("federalExemptionsExclusions/item")
        if item_el is not None and item_el.text:
            fed_exemption = item_el.text.strip() or None

    # Date of first sale
    date_of_first_sale_str = (
        _text(offering, "typeOfFiling/dateOfFirstSale/value") if offering is not None else None
    )
    date_of_first_sale = _parse_date(date_of_first_sale_str)

    # Related persons
    related_persons: list[dict] = []
    for rp in root.findall("relatedPersonsList/relatedPersonInfo"):
        name_el = rp.find("relatedPersonName")
        first = _text(name_el, "firstName") or ""
        middle = _text(name_el, "middleName") or ""
        last = _text(name_el, "lastName") or ""
        full_name = " ".join(p for p in [first, middle, last] if p).strip()

        rp_addr = rp.find("relatedPersonAddress")
        rp_city = _text(rp_addr, "city")
        rp_state = _text(rp_addr, "stateOrCountry")

        relationships = [
            r.text.strip()
            for r in rp.findall("relatedPersonRelationshipList/relationship")
            if r.text
        ]
        title = ", ".join(relationships)

        related_persons.append(
            {
                "name": full_name,
                "title": title,
                "city": rp_city,
                "state": rp_state,
            }
        )

    return {
        "cik": cik or "",
        "accession_number": accession_number,
        "filing_date": filing_date,
        "entity_name": entity_name,
        "entity_type": _text(issuer, "entityType"),
        "year_of_inc": year_of_inc,
        "jurisdiction_of_inc": _text(issuer, "jurisdictionOfInc"),
        "street1": _text(addr, "street1") if addr is not None else None,
        "city": _text(addr, "city") if addr is not None else None,
        "state": _text(addr, "stateOrCountry") if addr is not None else None,
        "zip_code": _text(addr, "zipCode") if addr is not None else None,
        "phone": _text(issuer, "issuerPhoneNumber"),
        "industry_group": _text(offering, "industryGroup/industryGroupType") if offering is not None else None,
        "revenue_range": _text(offering, "issuerSize/revenueRange") if offering is not None else None,
        "date_of_first_sale": date_of_first_sale,
        "securities_types": securities_types,
        "federal_exemption": fed_exemption,
        "total_offering_amount": _float(offering, "offeringSalesAmounts/totalOfferingAmount") if offering is not None else None,
        "total_amount_sold": _float(offering, "offeringSalesAmounts/totalAmountSold") if offering is not None else None,
        "total_remaining": _float(offering, "offeringSalesAmounts/totalRemaining") if offering is not None else None,
        "minimum_investment": _float(offering, "minimumInvestmentAccepted") if offering is not None else None,
        "num_investors": _int(offering, "investors/totalNumberAlreadyInvested") if offering is not None else None,
        "has_non_accredited": _bool(offering, "investors/hasNonAccreditedInvestors") if offering is not None else None,
        "is_amendment": _bool(offering, "typeOfFiling/newOrAmendment/isAmendment") if offering is not None else False,
        "is_business_combination": _bool(offering, "businessCombinationTransaction/isBusinessCombinationTransaction") if offering is not None else False,
        "related_persons": related_persons,
    }


def _normalize_name(name: str) -> str:
    """Strip titles and single-letter initials for fuzzy matching."""
    cleaned = _STRIP_TITLES.sub("", name)
    cleaned = _STRIP_INITIALS.sub("", cleaned)
    return " ".join(cleaned.split())


def compute_form_d_confidence(
    name_score: float,
    pi_names: list[str],
    related_persons: list[dict],
    sbir_state: str | None,
    biz_states: list[str],
    earliest_sbir_award_year: int,
    form_d_dates: list[date],
    year_of_inc: int | None,
    sbir_zip: str | None = None,
    form_d_zips: list[str] | None = None,
) -> FormDMatchConfidence:
    """Score match confidence between a Form D filing and an SBIR company.

    Combines signals: entity name match, PI-to-executive name match,
    address match, state overlap, temporal plausibility, and
    year-of-incorporation sanity.
    """

    # --- Signal 1: Person matching ---
    person_score: float | None = None
    person_match_detail: str | None = None

    if pi_names and related_persons:
        best_score = 0.0
        best_detail: str | None = None

        for pi in pi_names:
            pi_norm = _normalize_name(pi)
            for rp in related_persons:
                rp_name = rp.get("name", "")
                rp_norm = _normalize_name(rp_name)
                if not pi_norm or not rp_norm:
                    continue
                score = fuzz.token_set_ratio(pi_norm, rp_norm) / 100.0
                if score > best_score:
                    best_score = score
                    title = rp.get("title", "")
                    role_label = title.split(",")[0] if title else "Person"
                    best_detail = (
                        f"PI '{pi}' <> {role_label} '{rp_name}' ({int(score * 100)}%)"
                    )

        if best_detail is not None:
            person_score = best_score
            person_match_detail = best_detail

    # --- Signal 2: State overlap ---
    state_score: float | None = None
    if sbir_state and biz_states:
        state_score = 1.0 if sbir_state in biz_states else 0.0

    # --- Signal 3: Address (ZIP code) match ---
    address_score: float | None = None
    if sbir_zip and form_d_zips:
        sbir_zip_5 = sbir_zip.strip()[:5]
        address_score = (
            1.0
            if any(z.strip()[:5] == sbir_zip_5 for z in form_d_zips if z)
            else 0.0
        )

    # --- Signal 4: Temporal plausibility ---
    temporal_score: float | None = None
    if form_d_dates:
        earliest_fd_year = min(d.year for d in form_d_dates)
        gap = earliest_sbir_award_year - earliest_fd_year
        if gap <= 2:
            temporal_score = 1.0
        elif gap <= 5:
            temporal_score = 0.5
        else:
            temporal_score = 0.0

    # --- Signal 5: Year of incorporation ---
    year_of_inc_score: float | None = None
    if year_of_inc is not None:
        year_of_inc_score = 1.0 if year_of_inc <= earliest_sbir_award_year else 0.0

    # --- Composite (for within-tier ranking, not tier assignment) ---
    composite = (
        0.15 * name_score
        + 0.35 * (person_score if person_score is not None else 0.5)
        + 0.15 * (address_score if address_score is not None else 0.5)
        + 0.15 * (state_score if state_score is not None else 0.5)
        + 0.10 * (temporal_score if temporal_score is not None else 0.5)
        + 0.10 * (year_of_inc_score if year_of_inc_score is not None else 0.5)
    )

    # --- Tier (rule-based on discrete signal combinations) ---
    # Person match and address (ZIP) match are independent confirmation
    # signals — either one is sufficient for high tier.  This is critical
    # for HHS/NIH companies where the PI is often an academic collaborator
    # who does not appear as an officer on the Form D filing.
    ps = person_score if person_score is not None else 0.5
    ads = address_score if address_score is not None else 0.5
    ss = state_score if state_score is not None else 0.5
    if ps >= 0.7 or ads >= 1.0:
        tier = "high"
    elif ss >= 0.5:
        tier = "medium"
    else:
        tier = "low"

    return FormDMatchConfidence(
        tier=tier,
        score=round(composite, 4),
        name_score=name_score,
        person_score=person_score,
        person_match_detail=person_match_detail,
        state_score=state_score,
        address_score=address_score,
        temporal_score=temporal_score,
        year_of_inc_score=year_of_inc_score,
    )
