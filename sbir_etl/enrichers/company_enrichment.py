"""Company-level enrichment functions.

Provides USAspending federal award lookups, SAM.gov entity registration
checks, and FPDS contract description retrieval. Each lookup function
returns a typed dataclass on success or ``None`` on failure.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from loguru import logger

from sbir_etl.enrichers.fpds_atom import FPDSAtomClient
from sbir_etl.enrichers.pi_enrichment import _is_sbir_award_type
from sbir_etl.enrichers.rate_limiting import RateLimiter
from sbir_etl.enrichers.sync_wrappers import SyncSAMGovClient, SyncUSAspendingClient

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class FederalAwardSummary:
    """Summary of a company's federal awards from USAspending.

    Separates SBIR/STTR awards from non-SBIR federal work. Non-SBIR
    awards to a company with SBIR history are potential follow-on /
    Phase III commercialization signals.
    """

    total_awards: int
    total_funding: float
    agencies: list[str]
    award_types: list[str]  # e.g. contracts, grants, IDVs
    date_range: tuple[str | None, str | None]
    # Follow-on analysis
    sbir_award_count: int = 0
    sbir_funding: float = 0.0
    non_sbir_award_count: int = 0
    non_sbir_funding: float = 0.0
    non_sbir_agencies: list[str] = field(default_factory=list)
    non_sbir_sample_descriptions: list[str] = field(default_factory=list)
    naics_codes: list[str] = field(default_factory=list)


@dataclass
class USARecipientProfile:
    """Key data from a USAspending recipient profile."""

    recipient_id: str
    name: str
    uei: str | None
    parent_name: str | None
    parent_uei: str | None
    location_state: str | None
    location_congressional_district: str | None
    business_types: list[str]
    total_transaction_amount: float
    total_transactions: int


@dataclass
class SAMEntityRecord:
    """Key SAM.gov entity registration data for diligence."""

    uei: str
    legal_business_name: str
    dba_name: str | None
    registration_status: str | None
    expiration_date: str | None
    business_type: str | None
    entity_structure: str | None
    naics_codes: list[str]
    cage_code: str | None
    exclusion_status: str | None
    state: str | None
    congressional_district: str | None


# ---------------------------------------------------------------------------
# USAspending helpers
# ---------------------------------------------------------------------------

# Abbreviation patterns for fuzzy name matching
_ABBREVIATIONS = {
    r"\bIntl\.?\b": "International",
    r"\bInt'l\.?\b": "International",
    r"\bInc\.?\b": "Incorporated",
    r"\bCorp\.?\b": "Corporation",
    r"\bLtd\.?\b": "Limited",
    r"\bLLC\.?\b": "Limited Liability Company",
    r"\bTech\.?\b": "Technology",
    r"\bMfg\.?\b": "Manufacturing",
    r"\bSvcs\.?\b": "Services",
    r"\bDev\.?\b": "Development",
}


def usaspending_autocomplete(
    company_name: str,
    *,
    rate_limiter: RateLimiter | None = None,
) -> dict[str, str] | None:
    """Use USAspending recipient autocomplete for fuzzy company name matching.

    Generates name variations (abbreviation expansion, punctuation normalization,
    suffix removal) and tries each against the autocomplete endpoint until a match
    with a UEI or resolved name is found.
    """
    if not company_name or not company_name.strip():
        return None

    # Generate name variations, ordered most-to-least specific
    variations: list[str] = [company_name.strip()]

    # Expand abbreviations
    expanded = company_name
    for pattern, replacement in _ABBREVIATIONS.items():
        expanded = re.sub(pattern, replacement, expanded, flags=re.IGNORECASE)
    if expanded != company_name:
        variations.append(expanded.strip())

    # Normalize punctuation
    normalized = expanded.replace("/", " AND ").replace("&", " AND ")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if normalized not in variations:
        variations.append(normalized)

    # Remove legal suffixes for broadest match
    base = re.sub(
        r",?\s*(Inc\.?|Incorporated|LLC|Ltd\.?|Limited|Corp\.?|Corporation|Company|Co\.?)$",
        "", normalized, flags=re.IGNORECASE,
    ).strip().rstrip(",").strip()
    if base and base not in variations and len(base) >= 10:
        variations.append(base)

    # Add uppercase versions (USAspending often stores uppercase)
    upper_vars = [v.upper() for v in variations[:2] if v.upper() != v]
    variations = variations[:2] + upper_vars + variations[2:]

    # Deduplicate preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for v in variations:
        key = v.lower()
        if key not in seen and len(v) >= 5:
            seen.add(key)
            unique.append(v)

    logger.debug(
        "USAspending autocomplete: {} name variations for '{}'",
        len(unique), company_name,
    )

    best_candidate = None

    usa = SyncUSAspendingClient()
    try:
        for idx, name in enumerate(unique, 1):
            try:
                if rate_limiter:
                    rate_limiter.wait_if_needed()
                data = usa.autocomplete_recipient(name, limit=5)
                results = data.get("results", [])
                if not results:
                    continue
                match = results[0]
                matched_name = match.get("legal_business_name", "")
                matched_uei = match.get("uei")
                if matched_uei and str(matched_uei).strip().lower() not in ("", "nan", "none"):
                    logger.debug(
                        "USAspending autocomplete matched '{}' "
                        "(variation {}: '{}') → '{}' UEI={}",
                        company_name, idx, name, matched_name, matched_uei,
                    )
                    return {"uei": matched_uei, "name": matched_name}
                if matched_name and best_candidate is None:
                    best_candidate = {"uei": matched_uei, "name": matched_name}
            except Exception:
                continue
    finally:
        usa.close()

    if best_candidate:
        logger.debug(
            "USAspending autocomplete: best candidate for '{}' → '{}' (no UEI)",
            company_name, best_candidate["name"],
        )
        return best_candidate

    logger.debug(
        "USAspending autocomplete: no match for '{}' after {} variations",
        company_name, len(unique),
    )
    return None


def usaspending_search(
    company_name: str,
    search_text: str,
    label: str,
    *,
    rate_limiter: RateLimiter | None = None,
) -> list[dict] | None:
    """Execute USAspending spending_by_award searches for a company.

    Makes separate requests for contracts and grants/other (USAspending
    requires award_type_codes from a single group per request), then
    merges the results.

    Returns the combined results list on success, or None on error.
    """
    fields = [
        "Award ID",
        "Recipient Name",
        "Award Amount",
        "Awarding Agency",
        "Award Type",
        "Start Date",
        "Description",
        "CFDA Number",
        "naics_code",
    ]
    # USAspending requires award_type_codes from one group only.
    type_groups = [
        ("contracts", ["A", "B", "C", "D"]),
        ("grants", ["02", "03", "04", "05"]),
        ("other_financial_assistance", ["06", "10"]),
        ("loans", ["07", "08"]),
        ("direct_payments", ["09", "11"]),
    ]

    all_results: list[dict] = []
    logger.debug(
        "USAspending query for '{}' ({}='{}'): POST /search/spending_by_award/",
        company_name, label, search_text,
    )

    usa = SyncUSAspendingClient()
    try:
        for group_name, codes in type_groups:
            try:
                if rate_limiter:
                    rate_limiter.wait_if_needed()
                data = usa.search_awards(
                    filters={
                        "award_type_codes": codes,
                        "recipient_search_text": [search_text],
                    },
                    fields=fields,
                    limit=50,
                    sort="Award ID",
                )
                group_results = data.get("results", [])
                logger.debug(
                    "USAspending [{} via {}/{}]: {} results",
                    company_name, label, group_name, len(group_results),
                )
                all_results.extend(group_results)
            except Exception as e:
                logger.debug(
                    "USAspending [{}] {}/{} error: {}",
                    company_name, label, group_name, e,
                )
                continue
    finally:
        usa.close()

    logger.debug(
        "USAspending [{} via {}]: {} total results",
        company_name, label, len(all_results),
    )
    return all_results if all_results else None


def lookup_company_federal_awards(
    company_name: str,
    uei: str | None = None,
    *,
    rate_limiter: RateLimiter | None = None,
) -> FederalAwardSummary | None:
    """Query USAspending for all federal awards to a company.

    Tries UEI first (most reliable), then falls back to company name search,
    then fuzzy autocomplete match.

    Separates SBIR/STTR awards from non-SBIR federal work. Non-SBIR
    contracts and grants to a company with SBIR history are the strongest
    signal of successful commercialization / Phase III transition.
    """
    if not company_name:
        return None

    # Cascading lookup: UEI → exact name → fuzzy autocomplete match
    results = None
    if uei:
        results = usaspending_search(company_name, uei, "UEI", rate_limiter=rate_limiter)
    if not results:
        results = usaspending_search(company_name, company_name, "name", rate_limiter=rate_limiter)
    if not results:
        match = usaspending_autocomplete(company_name, rate_limiter=rate_limiter)
        if match:
            search_key = match["uei"] if match.get("uei") else match["name"]
            label = "autocomplete-UEI" if match.get("uei") else "autocomplete-name"
            results = usaspending_search(company_name, search_key, label, rate_limiter=rate_limiter)
    if not results:
        return None

    agencies: set[str] = set()
    award_types: set[str] = set()
    total_funding = 0.0
    dates: list[str] = []

    sbir_count = 0
    sbir_funding = 0.0
    non_sbir_count = 0
    non_sbir_funding = 0.0
    non_sbir_agencies: set[str] = set()
    non_sbir_descriptions: list[str] = []
    naics_codes: set[str] = set()

    for r in results:
        ag = r.get("Awarding Agency", "")
        if ag:
            agencies.add(ag)
        at = r.get("Award Type", "")
        if at:
            award_types.add(at)
        try:
            amount = float(r.get("Award Amount", 0) or 0)
        except (ValueError, TypeError):
            amount = 0.0
        total_funding += amount
        d = r.get("Start Date", "")
        if d:
            dates.append(d)

        desc = str(r.get("Description", "") or "")
        cfda = str(r.get("CFDA Number", "") or "")
        naics = str(r.get("naics_code", "") or "").strip()
        if naics:
            naics_codes.add(naics)

        if _is_sbir_award_type(desc, cfda):
            sbir_count += 1
            sbir_funding += amount
        else:
            non_sbir_count += 1
            non_sbir_funding += amount
            if ag:
                non_sbir_agencies.add(ag)
            if desc and len(non_sbir_descriptions) < 5:
                if len(desc) > 200:
                    desc = desc[:200] + "..."
                non_sbir_descriptions.append(
                    f"{desc} ({ag}, {at}, ${amount:,.0f})"
                )

    return FederalAwardSummary(
        total_awards=len(results),
        total_funding=total_funding,
        agencies=sorted(agencies),
        award_types=sorted(award_types),
        date_range=(min(dates) if dates else None, max(dates) if dates else None),
        sbir_award_count=sbir_count,
        sbir_funding=sbir_funding,
        non_sbir_award_count=non_sbir_count,
        non_sbir_funding=non_sbir_funding,
        non_sbir_agencies=sorted(non_sbir_agencies),
        non_sbir_sample_descriptions=non_sbir_descriptions,
        naics_codes=sorted(naics_codes),
    )


# ---------------------------------------------------------------------------
# USAspending recipient profile
# ---------------------------------------------------------------------------


def lookup_usaspending_recipient(
    company_name: str,
    uei: str | None = None,
    *,
    rate_limiter: RateLimiter | None = None,
) -> USARecipientProfile | None:
    """Look up a company's USAspending recipient profile.

    Two-step: POST /recipient/ to find the hash ID, then GET /recipient/{id}/
    for the full profile. Tries UEI first, then company name.
    """
    if not company_name:
        return None

    search_terms = []
    if uei:
        search_terms.append(uei)
    search_terms.append(company_name)

    recipient_id = None

    usa = SyncUSAspendingClient()
    try:
        for term in search_terms:
            logger.debug("USAspending recipient search: keyword='{}'", term)
            try:
                if rate_limiter:
                    rate_limiter.wait_if_needed()
                results = usa.search_recipients(term, limit=5)
                if results:
                    recipient_id = results[0].get("id")
                    logger.debug(
                        "USAspending recipient matched '{}' → '{}' id={}",
                        term, results[0].get("name"), recipient_id,
                    )
                    break
            except Exception as e:
                logger.debug("USAspending recipient search error for '{}': {}", term, e)
                continue

        if not recipient_id:
            logger.debug("USAspending recipient: no match for '{}'", company_name)
            return None

        # Fetch the full profile
        logger.debug("USAspending recipient profile: GET /recipient/{}/?year=all", recipient_id)
        try:
            if rate_limiter:
                rate_limiter.wait_if_needed()
            profile = usa.get_recipient_profile(recipient_id)
        except Exception as e:
            logger.debug("USAspending recipient profile error: {}", e)
            return None
        if not profile:
            return None
    finally:
        usa.close()

    location = profile.get("location") or {}

    return USARecipientProfile(
        recipient_id=recipient_id,
        name=profile.get("name") or company_name,
        uei=profile.get("uei"),
        parent_name=profile.get("parent_name"),
        parent_uei=profile.get("parent_uei"),
        location_state=location.get("state_code"),
        location_congressional_district=location.get("congressional_code"),
        business_types=profile.get("business_types") or [],
        total_transaction_amount=float(profile.get("total_transaction_amount") or 0),
        total_transactions=int(profile.get("total_transactions") or 0),
    )


# ---------------------------------------------------------------------------
# SAM.gov entity lookup
# ---------------------------------------------------------------------------


def lookup_sam_entity(
    company_name: str,
    uei: str | None = None,
    cage: str | None = None,
    *,
    rate_limiter: RateLimiter | None = None,
) -> SAMEntityRecord | None:
    """Query SAM.gov Entity Information API for company registration data.

    Tries UEI first (exact match), then CAGE, then name search.
    Requires SAM_GOV_API_KEY environment variable.
    """
    api_key = os.environ.get("SAM_GOV_API_KEY", "")
    if not api_key:
        return None

    entity = None

    sam = SyncSAMGovClient()
    try:
        if uei:
            logger.debug("SAM.gov [{}]: lookup by UEI={}", company_name, uei)
            try:
                if rate_limiter:
                    rate_limiter.wait_if_needed()
                entity = sam.get_entity_by_uei(uei)
            except Exception as e:
                logger.debug("SAM.gov [{}]: UEI lookup error: {}", company_name, e)

        if not entity and cage:
            logger.debug("SAM.gov [{}]: lookup by CAGE={}", company_name, cage)
            try:
                if rate_limiter:
                    rate_limiter.wait_if_needed()
                entity = sam.get_entity_by_cage(cage)
            except Exception as e:
                logger.debug("SAM.gov [{}]: CAGE lookup error: {}", company_name, e)

        if not entity and company_name:
            logger.debug("SAM.gov [{}]: name search", company_name)
            try:
                if rate_limiter:
                    rate_limiter.wait_if_needed()
                results = sam.search_entities(
                    legal_business_name=company_name,
                    registration_status="A",
                    limit=1,
                )
                entity = results[0] if results else None
            except Exception as e:
                logger.debug("SAM.gov [{}]: name search error: {}", company_name, e)
    finally:
        sam.close()

    if not entity:
        methods_tried = []
        if uei:
            methods_tried.append(f"UEI={uei}")
        if cage:
            methods_tried.append(f"CAGE={cage}")
        methods_tried.append(f"name='{company_name}'")
        logger.info(
            "SAM.gov: no entity found for {} (tried: {})",
            company_name, ", ".join(methods_tried),
        )
        return None

    # Extract fields — SAM.gov API nests data under various keys
    core = entity.get("entityRegistration", entity)
    address = entity.get("coreData", {}).get("physicalAddress", {})
    business_types = entity.get("coreData", {}).get("businessTypes", {})

    naics_list = entity.get("coreData", {}).get("naicsCodeList", [])
    if isinstance(naics_list, list):
        naics_codes = [
            str(n.get("naicsCode", "")) for n in naics_list if n.get("naicsCode")
        ]
    else:
        naics_codes = []

    return SAMEntityRecord(
        uei=core.get("ueiSAM", ""),
        legal_business_name=core.get("legalBusinessName", ""),
        dba_name=core.get("dbaName"),
        registration_status=core.get("registrationStatus"),
        expiration_date=core.get("registrationExpirationDate"),
        business_type=(
            business_types.get("businessTypeList", [{}])[0].get("businessType")
            if isinstance(business_types.get("businessTypeList"), list)
            and business_types.get("businessTypeList")
            else None
        ),
        entity_structure=core.get("entityStructureDesc"),
        naics_codes=naics_codes,
        cage_code=core.get("cageCode"),
        exclusion_status=core.get("exclusionStatusFlag"),
        state=address.get("stateOrProvinceCode"),
        congressional_district=address.get("congressionalDistrict"),
    )


def lookup_sam_entity_with_fallback(
    company_name: str,
    uei: str | None = None,
    cage: str | None = None,
    *,
    rate_limiter: RateLimiter | None = None,
    fallback_rate_limiter: RateLimiter | None = None,
) -> SAMEntityRecord | None:
    """Query SAM.gov with USAspending recipient fallback.

    First tries :func:`lookup_sam_entity`. If that returns ``None``, attempts
    to build a partial :class:`SAMEntityRecord` from USAspending recipient
    data so callers always get best-effort entity information even during
    SAM.gov maintenance windows.
    """
    result = lookup_sam_entity(
        company_name, uei=uei, cage=cage, rate_limiter=rate_limiter,
    )
    if result is not None:
        return result

    logger.info(
        "No SAM.gov entity result for '{}'; falling back to USAspending recipient profile",
        company_name,
    )

    profile = lookup_usaspending_recipient(
        company_name, uei=uei, rate_limiter=fallback_rate_limiter,
    )
    if profile is None:
        return None

    return SAMEntityRecord(
        uei=profile.uei or "",
        legal_business_name=profile.name,
        dba_name=None,
        registration_status=None,
        expiration_date=None,
        business_type=profile.business_types[0] if profile.business_types else None,
        entity_structure=None,
        naics_codes=[],
        cage_code=None,
        exclusion_status=None,
        state=profile.location_state,
        congressional_district=profile.location_congressional_district,
    )


def lookup_usaspending_recipient_with_fallback(
    company_name: str,
    uei: str | None = None,
    *,
    rate_limiter: RateLimiter | None = None,
    fallback_rate_limiter: RateLimiter | None = None,
) -> USARecipientProfile | None:
    """Query USAspending recipient with SAM.gov entity fallback.

    First tries :func:`lookup_usaspending_recipient`. If that returns ``None``,
    attempts to build a partial :class:`USARecipientProfile` from SAM.gov
    entity data so callers always get best-effort recipient information even
    when USAspending is unavailable.
    """
    result = lookup_usaspending_recipient(
        company_name, uei=uei, rate_limiter=rate_limiter,
    )
    if result is not None:
        return result

    logger.info(
        "No USAspending recipient result for '{}'; falling back to SAM.gov entity data",
        company_name,
    )

    entity = lookup_sam_entity(
        company_name, uei=uei, rate_limiter=fallback_rate_limiter,
    )
    if entity is None:
        return None

    return USARecipientProfile(
        recipient_id="",
        name=entity.legal_business_name,
        uei=entity.uei,
        parent_name=None,
        parent_uei=None,
        location_state=entity.state,
        location_congressional_district=entity.congressional_district,
        business_types=[entity.business_type] if entity.business_type else [],
        total_transaction_amount=0.0,
        total_transactions=0,
    )


# ---------------------------------------------------------------------------
# FPDS contract descriptions
# ---------------------------------------------------------------------------


def fetch_fpds_descriptions(
    contract_ids: list[str],
    *,
    rate_limiter: RateLimiter | None = None,
) -> dict[str, str]:
    """Fetch contract descriptions from FPDS Atom Feed (public, no API key).

    Only accepts contract PIIDs — assistance FAINs (e.g. DE-*) are not
    indexed in FPDS and should be filtered out before calling this function.
    """
    if not contract_ids:
        return {}

    logger.debug("FPDS: querying {} contract IDs", len(contract_ids))

    with FPDSAtomClient(rate_limiter=rate_limiter) as fpds:
        try:
            results = fpds.get_descriptions(contract_ids)
        except Exception as e:
            logger.debug("FPDS error: {}", e)
            results = {}
    logger.debug("FPDS: {}/{} descriptions found", len(results), len(contract_ids))
    return results


def fetch_usaspending_contract_descriptions(
    awards: list[dict],
    *,
    rate_limiter: RateLimiter | None = None,
    fpds_rate_limiter: RateLimiter | None = None,
) -> dict[str, str]:
    """Fetch contract descriptions from USAspending for awards with contract numbers.

    Returns a dict keyed by contract number with the award description text.
    Used as supplementary LLM context when solicitation topic data is unavailable.

    Falls back to FPDS Atom Feed for contract PIIDs that fail at USAspending.
    """
    # Use shared award-ID classification when available, inline fallback otherwise.
    try:
        from sbir_etl.enrichers.usaspending.client import build_award_type_groups
    except ImportError:
        def build_award_type_groups(ids):  # type: ignore[misc]
            piids, fains, unknown = [], [], []
            seen: set[str] = set()
            for raw in ids:
                s = raw.strip()
                if not s or s in seen:
                    continue
                seen.add(s)
                if re.match(r"^DE-", s, re.IGNORECASE):
                    fains.append(s)
                elif re.match(r"^[A-Z]{2}\d", s):
                    piids.append(s)
                else:
                    unknown.append(s)
            groups = []
            if piids:
                groups.append((piids, "contracts", ["A", "B", "C", "D"]))
            if fains:
                groups.append((fains, "assistance", ["02", "03", "04", "05"]))
            for uid in unknown:
                groups.append(([uid], "contracts", ["A", "B", "C", "D"]))
                groups.append(([uid], "assistance", ["02", "03", "04", "05"]))
            return groups

    raw_ids = [str(a.get("Contract", "")).strip() for a in awards]
    raw_ids = [c for c in raw_ids if c]
    if not raw_ids:
        return {}

    requests_to_make = build_award_type_groups(raw_ids)
    all_ids = list({aid for ids, _, _ in requests_to_make for aid in ids})

    logger.debug(
        "USAspending contract desc: {} IDs in {} groups",
        len(all_ids), len(requests_to_make),
    )
    results: dict[str, str] = {}
    failed_ids: set[str] = set()

    _method_config = {
        "search_awards": {
            "fields": ["Award ID", "Description", "Awarding Agency", "Award Type"],
            "sort": "Award ID",
            "desc_key": "Description",
        },
        "search_transactions": {
            "fields": ["Award ID", "Transaction Description", "Awarding Agency", "Award Type"],
            "sort": "Award ID",
            "desc_key": "Transaction Description",
        },
    }

    def _extract_descriptions(data: dict, desc_key: str = "Description") -> None:
        for r in data.get("results", []):
            aid = str(r.get("Award ID", "")).strip()
            desc = str(r.get(desc_key, "")).strip()
            if aid and desc and aid not in results:
                if len(desc) > 500:
                    desc = desc[:500] + "..."
                results[aid] = desc

    usa = SyncUSAspendingClient()
    try:
        for ids, group_name, codes in requests_to_make:
            filters = {"award_ids": list(ids), "award_type_codes": codes}
            logger.debug(
                "USAspending contract desc: {} ({} IDs: {})",
                group_name, len(ids), ids[:3],
            )
            data = None
            used_method = "search_awards"
            for method in ("search_awards", "search_transactions"):
                cfg = _method_config[method]
                try:
                    if rate_limiter:
                        rate_limiter.wait_if_needed()
                    data = getattr(usa, method)(
                        filters=filters,
                        fields=cfg["fields"],
                        limit=len(ids),
                        sort=cfg["sort"],
                        order="desc",
                    )
                    num_results = len(data.get("results", []))
                    logger.debug(
                        "USAspending {}/{}: {} results",
                        method, group_name, num_results,
                    )
                    used_method = method
                    break
                except Exception as e:
                    logger.debug("USAspending {}/{} failed: {}", method, group_name, e)
                    continue
            if data is None:
                failed_ids.update(ids)
                continue
            _extract_descriptions(data, _method_config[used_method]["desc_key"])
    except Exception as e:
        failed_ids.update(cid for cid in all_ids if cid not in results)
        logger.warning("USAspending contract desc error: {}", e)
    finally:
        usa.close()

    # FPDS Atom Feed fallback for contract PIIDs that failed at USAspending.
    fpds_eligible = [
        cid for cid in failed_ids
        if cid not in results and not re.match(r"^DE-", cid, re.IGNORECASE)
    ]
    if fpds_eligible:
        logger.debug(
            "USAspending failed for {} IDs, {} eligible for FPDS fallback",
            len(failed_ids), len(fpds_eligible),
        )
        fpds_results = fetch_fpds_descriptions(
            fpds_eligible, rate_limiter=fpds_rate_limiter or rate_limiter,
        )
        if fpds_results:
            results.update(fpds_results)
            logger.info(
                "FPDS fallback recovered {}/{} descriptions",
                len(fpds_results), len(fpds_eligible),
            )

    logger.debug(
        "Contract descriptions: {}/{} found (USAspending + FPDS)",
        len(results), len(all_ids),
    )
    return results
