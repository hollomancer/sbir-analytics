"""Company-level enrichment functions.

Provides USAspending federal award lookups, SAM.gov entity registration
checks, and FPDS contract description retrieval. Each lookup returns a
typed dataclass on success or ``None`` on failure.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from sbir_etl.enrichers.pi_enrichment import _is_sbir_award_type
from sbir_etl.enrichers.rate_limiting import RateLimiter
from sbir_etl.enrichers.sync_wrappers import (
    SyncFPDSAtomClient,
    SyncSAMGovClient,
    SyncUSAspendingClient,
)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class FederalAwardSummary:
    """Summary of a company's federal awards from USAspending.

    Separates SBIR/STTR from non-SBIR federal work. Non-SBIR awards to a
    company with SBIR history are potential follow-on / Phase III signals.
    """

    total_awards: int
    total_funding: float
    agencies: list[str]
    award_types: list[str]
    date_range: tuple[str | None, str | None]
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
# Helpers
# ---------------------------------------------------------------------------

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

_SUFFIX_STRIP = re.compile(
    r",?\s*(Inc\.?|Incorporated|LLC|Ltd\.?|Limited|Corp\.?|Corporation|Company|Co\.?)$",
    re.IGNORECASE,
)


def _name_variations(company_name: str) -> list[str]:
    """Generate fuzzy-matchable name variants, ordered most→least specific."""
    if not company_name or not company_name.strip():
        return []

    variations: list[str] = [company_name.strip()]

    expanded = company_name
    for pattern, repl in _ABBREVIATIONS.items():
        expanded = re.sub(pattern, repl, expanded, flags=re.IGNORECASE)
    if expanded != company_name:
        variations.append(expanded.strip())

    normalized = re.sub(r"\s+", " ", expanded.replace("/", " AND ").replace("&", " AND ")).strip()
    if normalized not in variations:
        variations.append(normalized)

    base = _SUFFIX_STRIP.sub("", normalized).strip().rstrip(",").strip()
    if base and base not in variations and len(base) >= 10:
        variations.append(base)

    # USAspending often stores names in uppercase; add upper-case variants of the
    # first two (most specific) variations.
    upper_vars = [v.upper() for v in variations[:2] if v.upper() != v]
    variations = variations[:2] + upper_vars + variations[2:]

    seen: set[str] = set()
    unique: list[str] = []
    for v in variations:
        key = v.lower()
        if key not in seen and len(v) >= 5:
            seen.add(key)
            unique.append(v)
    return unique


def _is_valid_uei(value: object) -> bool:
    return bool(value) and str(value).strip().lower() not in ("", "nan", "none")


def _wait(rate_limiter: RateLimiter | None) -> None:
    if rate_limiter:
        rate_limiter.wait_if_needed()


# ---------------------------------------------------------------------------
# USAspending name resolution
# ---------------------------------------------------------------------------


def usaspending_autocomplete(
    company_name: str,
    *,
    rate_limiter: RateLimiter | None = None,
) -> dict[str, str] | None:
    """Use USAspending recipient autocomplete for fuzzy company-name matching."""
    variations = _name_variations(company_name)
    if not variations:
        return None

    logger.debug(
        "USAspending autocomplete: {} name variations for '{}'",
        len(variations),
        company_name,
    )

    best_candidate: dict[str, str] | None = None
    usa = SyncUSAspendingClient()
    try:
        for idx, name in enumerate(variations, 1):
            try:
                _wait(rate_limiter)
                results = usa.autocomplete_recipient(name, limit=5).get("results", [])
            except Exception:
                continue
            if not results:
                continue
            match = results[0]
            matched_name = match.get("legal_business_name", "")
            matched_uei = match.get("uei")
            if _is_valid_uei(matched_uei):
                logger.debug(
                    "USAspending autocomplete matched '{}' (variation {}: '{}') → '{}' UEI={}",
                    company_name,
                    idx,
                    name,
                    matched_name,
                    matched_uei,
                )
                return {"uei": matched_uei, "name": matched_name}
            if matched_name and best_candidate is None:
                best_candidate = {"uei": matched_uei, "name": matched_name}
    finally:
        usa.close()

    if best_candidate:
        logger.debug(
            "USAspending autocomplete: best candidate for '{}' → '{}' (no UEI)",
            company_name,
            best_candidate["name"],
        )
        return best_candidate

    logger.debug(
        "USAspending autocomplete: no match for '{}' after {} variations",
        company_name,
        len(variations),
    )
    return None


# Award-type groupings used by /search/spending_by_award (one group per request).
_AWARD_TYPE_GROUPS = [
    ("contracts", ["A", "B", "C", "D"]),
    ("grants", ["02", "03", "04", "05"]),
    ("other_financial_assistance", ["06", "10"]),
    ("loans", ["07", "08"]),
    ("direct_payments", ["09", "11"]),
]


def usaspending_search(
    company_name: str,
    search_text: str,
    label: str,
    *,
    rate_limiter: RateLimiter | None = None,
) -> list[dict] | None:
    """Execute USAspending /search/spending_by_award queries across award-type groups."""
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
    logger.debug(
        "USAspending query for '{}' ({}='{}'): POST /search/spending_by_award/",
        company_name,
        label,
        search_text,
    )

    all_results: list[dict] = []
    usa = SyncUSAspendingClient()
    try:
        for group_name, codes in _AWARD_TYPE_GROUPS:
            try:
                _wait(rate_limiter)
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
                    company_name,
                    label,
                    group_name,
                    len(group_results),
                )
                all_results.extend(group_results)
            except Exception as e:
                logger.debug(
                    "USAspending [{}] {}/{} error: {}",
                    company_name,
                    label,
                    group_name,
                    e,
                )
    finally:
        usa.close()

    logger.debug(
        "USAspending [{} via {}]: {} total results",
        company_name,
        label,
        len(all_results),
    )
    return all_results or None


def lookup_company_federal_awards(
    company_name: str,
    uei: str | None = None,
    *,
    rate_limiter: RateLimiter | None = None,
) -> FederalAwardSummary | None:
    """Query USAspending for all federal awards to a company.

    Tries UEI first, then exact company-name search, then fuzzy autocomplete
    match. Separates SBIR/STTR from non-SBIR awards (non-SBIR contracts/grants
    to an SBIR-history firm are the strongest commercialization signal).
    """
    if not company_name:
        return None

    results = (
        uei and usaspending_search(company_name, uei, "UEI", rate_limiter=rate_limiter)
    ) or usaspending_search(company_name, company_name, "name", rate_limiter=rate_limiter)
    if not results:
        if match := usaspending_autocomplete(company_name, rate_limiter=rate_limiter):
            search_key = match["uei"] if match.get("uei") else match["name"]
            label = "autocomplete-UEI" if match.get("uei") else "autocomplete-name"
            results = usaspending_search(company_name, search_key, label, rate_limiter=rate_limiter)
    if not results:
        return None

    agencies: set[str] = set()
    award_types: set[str] = set()
    naics_codes: set[str] = set()
    non_sbir_agencies: set[str] = set()
    non_sbir_descriptions: list[str] = []
    dates: list[str] = []
    total_funding = sbir_funding = non_sbir_funding = 0.0
    sbir_count = non_sbir_count = 0

    for r in results:
        ag = r.get("Awarding Agency", "")
        at = r.get("Award Type", "")
        d = r.get("Start Date", "")
        desc = str(r.get("Description", "") or "")
        cfda = str(r.get("CFDA Number", "") or "")
        naics = str(r.get("naics_code", "") or "").strip()
        try:
            amount = float(r.get("Award Amount", 0) or 0)
        except (ValueError, TypeError):
            amount = 0.0

        if ag:
            agencies.add(ag)
        if at:
            award_types.add(at)
        if d:
            dates.append(d)
        if naics:
            naics_codes.add(naics)
        total_funding += amount

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
                non_sbir_descriptions.append(f"{desc} ({ag}, {at}, ${amount:,.0f})")

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

    search_terms = [t for t in (uei, company_name) if t]
    recipient_id = None
    profile: dict | None = None

    usa = SyncUSAspendingClient()
    try:
        for term in search_terms:
            logger.debug("USAspending recipient search: keyword='{}'", term)
            try:
                _wait(rate_limiter)
                results = usa.search_recipients(term, limit=5)
                if results:
                    recipient_id = results[0].get("id")
                    logger.debug(
                        "USAspending recipient matched '{}' → '{}' id={}",
                        term,
                        results[0].get("name"),
                        recipient_id,
                    )
                    break
            except Exception as e:
                logger.debug("USAspending recipient search error for '{}': {}", term, e)

        if not recipient_id:
            logger.debug("USAspending recipient: no match for '{}'", company_name)
            return None

        logger.debug("USAspending recipient profile: GET /recipient/{}/?year=all", recipient_id)
        try:
            _wait(rate_limiter)
            profile = usa.get_recipient_profile(recipient_id)
        except Exception as e:
            logger.debug("USAspending recipient profile error: {}", e)
            return None
    finally:
        usa.close()

    if not profile:
        return None

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
    """Query SAM.gov Entity Information API. Tries UEI → CAGE → name search.

    Requires SAM_GOV_API_KEY env var; returns None if unset.
    """
    if not os.environ.get("SAM_GOV_API_KEY"):
        return None

    entity = None
    sam = SyncSAMGovClient()
    try:
        # Try each identifier in priority order; stop on first hit.
        attempts: list[tuple[str, object, Callable[[], Any]]] = []
        if uei:
            attempts.append(("UEI", uei, lambda: sam.get_entity_by_uei(uei)))
        if cage:
            attempts.append(("CAGE", cage, lambda: sam.get_entity_by_cage(cage)))
        if company_name:

            def _name_lookup() -> Any:
                results = sam.search_entities(
                    legal_business_name=company_name,
                    registration_status="A",
                    limit=1,
                )
                return results[0] if results else None

            attempts.append(
                (
                    "name",
                    company_name,
                    _name_lookup,
                )
            )

        for label, value, action in attempts:
            logger.debug("SAM.gov [{}]: lookup by {}={}", company_name, label, value)
            try:
                _wait(rate_limiter)
                entity = action()
            except Exception as e:
                logger.debug("SAM.gov [{}]: {} lookup error: {}", company_name, label, e)
                entity = None
            if entity:
                break
    finally:
        sam.close()

    if not entity:
        tried = ", ".join(
            filter(
                None,
                [
                    f"UEI={uei}" if uei else None,
                    f"CAGE={cage}" if cage else None,
                    f"name='{company_name}'",
                ],
            )
        )
        logger.info("SAM.gov: no entity found for {} (tried: {})", company_name, tried)
        return None

    core = entity.get("entityRegistration", entity)
    core_data = entity.get("coreData", {}) or {}
    address = core_data.get("physicalAddress", {}) or {}

    naics_list = core_data.get("naicsCodeList") or []
    naics_codes = [
        str(n.get("naicsCode", ""))
        for n in naics_list
        if isinstance(n, dict) and n.get("naicsCode")
    ]

    business_type_list = (core_data.get("businessTypes") or {}).get("businessTypeList") or []
    business_type = (
        business_type_list[0].get("businessType")
        if business_type_list and isinstance(business_type_list[0], dict)
        else None
    )

    return SAMEntityRecord(
        uei=core.get("ueiSAM", ""),
        legal_business_name=core.get("legalBusinessName", ""),
        dba_name=core.get("dbaName"),
        registration_status=core.get("registrationStatus"),
        expiration_date=core.get("registrationExpirationDate"),
        business_type=business_type,
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
    """Query SAM.gov; on miss, build a partial record from USAspending recipient data."""
    if result := lookup_sam_entity(company_name, uei=uei, cage=cage, rate_limiter=rate_limiter):
        return result

    logger.info(
        "No SAM.gov entity result for '{}'; falling back to USAspending recipient profile",
        company_name,
    )
    profile = lookup_usaspending_recipient(
        company_name, uei=uei, rate_limiter=fallback_rate_limiter
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
    """Query USAspending recipient; on miss, build a partial record from SAM.gov data."""
    if result := lookup_usaspending_recipient(company_name, uei=uei, rate_limiter=rate_limiter):
        return result

    logger.info(
        "No USAspending recipient result for '{}'; falling back to SAM.gov entity data",
        company_name,
    )
    entity = lookup_sam_entity(company_name, uei=uei, rate_limiter=fallback_rate_limiter)
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
# FPDS / USAspending contract descriptions
# ---------------------------------------------------------------------------


def fetch_fpds_descriptions(
    contract_ids: list[str],
    *,
    rate_limiter: RateLimiter | None = None,
) -> dict[str, str]:
    """Fetch contract descriptions from FPDS Atom Feed (PIIDs only — no FAINs)."""
    if not contract_ids:
        return {}
    logger.debug("FPDS: querying {} contract IDs", len(contract_ids))
    with SyncFPDSAtomClient(shared_limiter=rate_limiter) as fpds:
        try:
            results = fpds.get_descriptions(contract_ids)
        except Exception as e:
            logger.debug("FPDS error: {}", e)
            results = {}
    logger.debug("FPDS: {}/{} descriptions found", len(results), len(contract_ids))
    return results


def _fallback_build_award_type_groups(
    ids: Iterable[str],
) -> list[tuple[list[str], str, list[str]]]:
    """Local fallback for award-type grouping when the centralized helper is unavailable."""
    piids: list[str] = []
    fains: list[str] = []
    unknown: list[str] = []
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
    groups: list[tuple[list[str], str, list[str]]] = []
    if piids:
        groups.append((piids, "contracts", ["A", "B", "C", "D"]))
    if fains:
        groups.append((fains, "assistance", ["02", "03", "04", "05"]))
    for uid in unknown:
        groups.append(([uid], "contracts", ["A", "B", "C", "D"]))
        groups.append(([uid], "assistance", ["02", "03", "04", "05"]))
    return groups


# Method-specific config for the contract-description query; tried in order.
_DESCRIPTION_METHODS = (
    (
        "search_awards",
        ["Award ID", "Description", "Awarding Agency", "Award Type"],
        "Description",
    ),
    (
        "search_transactions",
        ["Award ID", "Transaction Description", "Awarding Agency", "Award Type"],
        "Transaction Description",
    ),
)


def fetch_usaspending_contract_descriptions(
    awards: list[dict],
    *,
    rate_limiter: RateLimiter | None = None,
    fpds_rate_limiter: RateLimiter | None = None,
) -> dict[str, str]:
    """Fetch contract descriptions from USAspending (with FPDS fallback for PIIDs).

    Used as supplementary LLM context when solicitation topic data is unavailable.
    Returns a dict keyed by contract number; descriptions over 500 chars are
    truncated with an ellipsis.
    """
    try:
        from sbir_etl.enrichers.usaspending.client import build_award_type_groups
    except ImportError:
        build_award_type_groups = _fallback_build_award_type_groups  # type: ignore[assignment]

    raw_ids = [c for a in awards if (c := str(a.get("Contract", "")).strip())]
    if not raw_ids:
        return {}

    requests_to_make = build_award_type_groups(raw_ids)
    all_ids = list({aid for ids, _, _ in requests_to_make for aid in ids})
    logger.debug(
        "USAspending contract desc: {} IDs in {} groups",
        len(all_ids),
        len(requests_to_make),
    )

    results: dict[str, str] = {}
    failed_ids: set[str] = set()

    def _ingest(data: dict, desc_key: str) -> None:
        for r in data.get("results", []):
            aid = str(r.get("Award ID", "")).strip()
            desc = str(r.get(desc_key, "")).strip()
            if aid and desc and aid not in results:
                results[aid] = desc[:500] + "..." if len(desc) > 500 else desc

    usa = SyncUSAspendingClient()
    try:
        for ids, group_name, codes in requests_to_make:
            filters = {"award_ids": list(ids), "award_type_codes": codes}
            logger.debug(
                "USAspending contract desc: {} ({} IDs: {})",
                group_name,
                len(ids),
                ids[:3],
            )
            data: dict | None = None
            used_desc_key = "Description"
            for method, fields, desc_key in _DESCRIPTION_METHODS:
                try:
                    _wait(rate_limiter)
                    data = getattr(usa, method)(
                        filters=filters,
                        fields=fields,
                        limit=len(ids),
                        sort="Award ID",
                        order="desc",
                    )
                    logger.debug(
                        "USAspending {}/{}: {} results",
                        method,
                        group_name,
                        len(data.get("results", [])),
                    )
                    used_desc_key = desc_key
                    break
                except Exception as e:
                    logger.debug("USAspending {}/{} failed: {}", method, group_name, e)
            if data is None:
                failed_ids.update(ids)
                continue
            _ingest(data, used_desc_key)
    except Exception as e:
        failed_ids.update(cid for cid in all_ids if cid not in results)
        logger.warning("USAspending contract desc error: {}", e)
    finally:
        usa.close()

    # FPDS Atom Feed fallback for contract PIIDs (not FAINs).
    fpds_eligible = [
        cid
        for cid in failed_ids
        if cid not in results and not re.match(r"^DE-", cid, re.IGNORECASE)
    ]
    if fpds_eligible:
        logger.debug(
            "USAspending failed for {} IDs, {} eligible for FPDS fallback",
            len(failed_ids),
            len(fpds_eligible),
        )
        if fpds_results := fetch_fpds_descriptions(
            fpds_eligible,
            rate_limiter=fpds_rate_limiter or rate_limiter,
        ):
            results.update(fpds_results)
            logger.info(
                "FPDS fallback recovered {}/{} descriptions",
                len(fpds_results),
                len(fpds_eligible),
            )

    logger.debug(
        "Contract descriptions: {}/{} found (USAspending + FPDS)",
        len(results),
        len(all_ids),
    )
    return results
