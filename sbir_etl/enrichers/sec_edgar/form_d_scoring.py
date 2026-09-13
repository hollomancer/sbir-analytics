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

FORM_D_TIER_RULE_PERSON_OR_ZIP_V1 = "person-or-zip-v1"
FORM_D_TIER_RULE_CORROBORATED_PERSON_V2 = "corroborated-person-v2"
FORM_D_TIER_RULE_VERSION = FORM_D_TIER_RULE_CORROBORATED_PERSON_V2
FORM_D_TIER_RULE_VERSIONS: frozenset[str] = frozenset(
    {
        FORM_D_TIER_RULE_PERSON_OR_ZIP_V1,
        FORM_D_TIER_RULE_CORROBORATED_PERSON_V2,
    }
)


class FormDTierRuleError(ValueError):
    """A stored confidence tier is absent or uses the wrong named rule."""


def require_form_d_rule_version(
    observed_rule_version: object,
    *,
    expected_rule_version: str = FORM_D_TIER_RULE_VERSION,
    context: str = "Form D record",
) -> str:
    """Require one explicit rule version on a detail or derived cohort row."""

    if expected_rule_version not in FORM_D_TIER_RULE_VERSIONS:
        supported = ", ".join(sorted(FORM_D_TIER_RULE_VERSIONS))
        raise FormDTierRuleError(
            f"Unsupported expected Form D tier rule {expected_rule_version!r}; "
            f"supported rules: {supported}"
        )
    if observed_rule_version != expected_rule_version:
        raise FormDTierRuleError(
            f"{context} uses Form D tier rule {observed_rule_version!r}; expected "
            f"{expected_rule_version!r}. Rescore the complete input first with "
            "scripts/data/rescore_form_d_details.py."
        )
    return expected_rule_version


def require_form_d_tier_rule(
    match_confidence: object,
    *,
    expected_rule_version: str = FORM_D_TIER_RULE_VERSION,
    context: str = "Form D record",
) -> dict:
    """Return a confidence mapping only when its tier rule is explicit and expected.

    Stored Form D rows predate rule versioning. Consumers must fail closed instead
    of interpreting an unversioned historical tier as the current rule.
    """

    if not isinstance(match_confidence, dict):
        raise FormDTierRuleError(f"{context} has no match_confidence object")
    observed = match_confidence.get("rule_version")
    require_form_d_rule_version(
        observed,
        expected_rule_version=expected_rule_version,
        context=context,
    )
    return match_confidence


# Titles that should be stripped from PI names before matching
_STRIP_TITLES = re.compile(r"\b(Dr\.|Ph\.D\.|M\.D\.|Mr\.|Mrs\.|Ms\.|Jr\.|Sr\.)\b", re.IGNORECASE)
# Single-letter initials like "R." (but not "Jr." etc., already handled above)
_STRIP_INITIALS = re.compile(r"\b[A-Z]\.\s*")

# Industry groups structurally incompatible with SBIR companies.
# Offerings with these groups are almost entirely name-collision false
# positives (85-100% low-tier).  Used by downstream analysis to exclude
# offerings; not applied during fetch so raw data stays complete.
#
# "Pooled Investment Fund" is excluded because these are VC/PE fund
# vehicles, not operating-company raises. Shared-person or shared-CIK links
# remain identity-review flags; they do not establish a portfolio relationship.
EXCLUDED_INDUSTRY_GROUPS: frozenset[str] = frozenset(
    {
        "Insurance",
        "Lodging and Conventions",
        "Other Travel",
        "Pooled Investment Fund",
        "Restaurants",
        "Retailing",
        "Tourism and Travel Services",
    }
)

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
        "industry_group": _text(offering, "industryGroup/industryGroupType")
        if offering is not None
        else None,
        "revenue_range": _text(offering, "issuerSize/revenueRange")
        if offering is not None
        else None,
        "date_of_first_sale": date_of_first_sale,
        "securities_types": securities_types,
        "federal_exemption": fed_exemption,
        "total_offering_amount": _float(offering, "offeringSalesAmounts/totalOfferingAmount")
        if offering is not None
        else None,
        "total_amount_sold": _float(offering, "offeringSalesAmounts/totalAmountSold")
        if offering is not None
        else None,
        "total_remaining": _float(offering, "offeringSalesAmounts/totalRemaining")
        if offering is not None
        else None,
        "minimum_investment": _float(offering, "minimumInvestmentAccepted")
        if offering is not None
        else None,
        "num_investors": _int(offering, "investors/totalNumberAlreadyInvested")
        if offering is not None
        else None,
        "has_non_accredited": _bool(offering, "investors/hasNonAccreditedInvestors")
        if offering is not None
        else None,
        "is_amendment": _bool(offering, "typeOfFiling/newOrAmendment/isAmendment")
        if offering is not None
        else False,
        "is_business_combination": _bool(
            offering, "businessCombinationTransaction/isBusinessCombinationTransaction"
        )
        if offering is not None
        else False,
        "related_persons": related_persons,
    }


def _normalize_name(name: str) -> str:
    """Strip titles and single-letter initials for fuzzy matching."""
    cleaned = _STRIP_TITLES.sub("", name)
    cleaned = _STRIP_INITIALS.sub("", cleaned)
    return " ".join(cleaned.split())


def assign_form_d_tier(
    *,
    person_score: float | None,
    address_score: float | None,
    state_score: float | None,
    rule_version: str = FORM_D_TIER_RULE_VERSION,
) -> str:
    """Assign a confidence tier under a named, versioned rule.

    ``person-or-zip-v1`` preserves the historical 2026-04-23 behavior so
    old materializations remain interpretable. ``corroborated-person-v2``
    is the current rule: a fuzzy person-name hit needs an exact ZIP or state
    overlap to reach high, while an exact ZIP remains sufficient by itself.
    """

    if rule_version not in FORM_D_TIER_RULE_VERSIONS:
        supported = ", ".join(sorted(FORM_D_TIER_RULE_VERSIONS))
        raise ValueError(
            f"Unsupported Form D tier rule {rule_version!r}; expected one of {supported}"
        )

    person_hit = person_score is not None and person_score >= 0.7
    address_hit = address_score is not None and address_score >= 1.0
    state_hit = state_score is not None and state_score >= 1.0

    if rule_version == FORM_D_TIER_RULE_PERSON_OR_ZIP_V1:
        if person_hit or address_hit:
            return "high"
    elif address_hit or (person_hit and state_hit):
        return "high"

    # Missing state evidence historically received the neutral 0.5 value and
    # therefore remained medium. Preserve that behavior in both named rules.
    if state_score is None or state_score >= 0.5 or person_hit:
        return "medium"
    return "low"


def describe_form_d_signal_scope(offerings: list[dict]) -> dict[str, object]:
    """Describe the filing/CIK scope from which record-level signals were pooled.

    The legacy detail producer computes one confidence object after pooling every
    parsed offering attached to an SBIR company. This metadata makes that scope
    explicit; it does not imply that corroborating signals occurred in one filing.
    """

    ciks = sorted(
        {
            str(offering.get("cik") or "").strip().lstrip("0")
            for offering in offerings
            if str(offering.get("cik") or "").strip().lstrip("0")
        }
    )
    return {
        "unit": "company-record",
        "offering_count": len(offerings),
        "distinct_ciks": ciks,
        "signals_may_span_filings": len(offerings) > 1,
        "signals_may_span_ciks": len(ciks) > 1,
    }


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
    rule_version: str = FORM_D_TIER_RULE_VERSION,
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
                    best_detail = f"PI '{pi}' <> {role_label} '{rp_name}' ({int(score * 100)}%)"

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
        address_score = 1.0 if any(z.strip()[:5] == sbir_zip_5 for z in form_d_zips if z) else 0.0

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
    # An exact ZIP match is sufficient for record-level high under the named
    # rule. It is not identity validation: addresses can be shared, and the
    # legacy company record can pool signals across filings or CIKs.
    #
    # A fuzzy person-name match is not comparable in strength: ordinary name
    # variation (a nickname, an initial, two people sharing a common given
    # name) clears any threshold that also catches real matches — a
    # companion audit found no score that separates the two populations.
    # So a person match alone reaches only medium, the same tier a bare
    # state overlap gets. It reaches high only in conjunction with a second,
    # independent corroborating signal (exact ZIP, or state overlap paired
    # with the person hit). Corroboration is checked against the actual
    # signal values, never the 0.5 defaults substituted below for missing
    # signals in the medium-tier check — two absent signals must not combine
    # into a promotion.
    tier = assign_form_d_tier(
        person_score=person_score,
        address_score=address_score,
        state_score=state_score,
        rule_version=rule_version,
    )

    return FormDMatchConfidence(
        rule_version=rule_version,
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
