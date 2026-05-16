"""SEC EDGAR enrichment logic for SBIR companies.

Resolves SBIR company names to SEC CIK numbers, extracts financial data
from XBRL filings, and detects M&A events from 8-K filings.
"""

from __future__ import annotations

import asyncio
import re
from datetime import date, datetime
from typing import Any

import pandas as pd
from loguru import logger
from rapidfuzz import fuzz

from ...models.sec_edgar import (
    CompanyEdgarProfile,
    EdgarFinancials,
    EdgarFormDFiling,
    EdgarMAEvent,
    MAAcquisitionType,
)
from .client import EdgarAPIClient


# XBRL concept lists per financial field; first match wins.
_FINANCIAL_CONCEPTS: dict[str, list[str]] = {
    "revenue": [
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
    ],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "total_assets": ["Assets"],
    "total_liabilities": ["Liabilities"],
    "rd_expense": [
        "ResearchAndDevelopmentExpense",
        "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
    ],
    "operating_income": ["OperatingIncomeLoss"],
    "cash_and_equivalents": ["CashAndCashEquivalentsAtCarryingValue", "Cash"],
}

# Fields required to consider a financials record useful (skip if all None).
_REQUIRED_FINANCIAL_FIELDS = ("revenue", "net_income", "total_assets", "rd_expense")


def _extract_latest_fact(
    facts: dict[str, Any],
    concept_names: list[str],
    *,
    taxonomy: str = "us-gaap",
) -> tuple[float | None, date | None]:
    """Extract the most recent 10-K/10-Q/20-F value for any of `concept_names`.

    Returns (value, period_end_date) or (None, None) if not found.
    """
    tax_facts = facts.get("facts", {}).get(taxonomy, {})
    for concept in concept_names:
        usd_entries = (tax_facts.get(concept) or {}).get("units", {}).get("USD", [])
        annual = [
            e
            for e in usd_entries
            if e.get("form") in ("10-K", "10-Q", "20-F") and e.get("val") is not None
        ]
        if not annual:
            continue
        annual.sort(key=lambda e: e.get("end", ""), reverse=True)
        latest = annual[0]
        try:
            period_end = date.fromisoformat(latest["end"])
        except (ValueError, KeyError):
            period_end = None
        return float(latest["val"]), period_end
    return None, None


def _extract_financials(cik: str, facts: dict[str, Any]) -> EdgarFinancials | None:
    """Extract standardized financials from EDGAR company facts."""
    values: dict[str, float | None] = {}
    dates: list[date] = []
    for field, concepts in _FINANCIAL_CONCEPTS.items():
        val, period_end = _extract_latest_fact(facts, concepts)
        values[field] = val
        if period_end:
            dates.append(period_end)

    if all(values[f] is None for f in _REQUIRED_FINANCIAL_FIELDS) or not dates:
        return None

    latest_date = max(dates)
    return EdgarFinancials(cik=cik, fiscal_year=latest_date.year, filing_date=latest_date, **values)


def _detect_ma_events(cik: str, filings: list[dict[str, Any]]) -> list[EdgarMAEvent]:
    """Detect M&A events from 8-K filings (Item 1.01 / Item 2.01)."""
    events = []
    for filing in filings:
        if filing.get("form_type") != "8-K":
            continue
        description = (filing.get("description") or "").lower()
        items_found: list[str] = []
        if "1.01" in description or "material" in description:
            items_found.append("1.01")
        if "2.01" in description or "acqui" in description or "merger" in description:
            items_found.append("2.01")
        if not items_found:
            continue

        if "acqui" in description:
            event_type = MAAcquisitionType.ACQUISITION
        elif "merger" in description:
            event_type = MAAcquisitionType.MERGER
        else:
            event_type = MAAcquisitionType.UNKNOWN

        try:
            filing_date = date.fromisoformat(filing["filing_date"])
        except (ValueError, KeyError, TypeError):
            continue

        events.append(
            EdgarMAEvent(
                cik=cik,
                filing_date=filing_date,
                accession_number=filing.get("accession_number", ""),
                event_type=event_type,
                items_reported=items_found,
                description=filing.get("description"),
            )
        )
    return events


# ---------------------------------------------------------------------------
# Mention classification (inbound M&A detection)
# ---------------------------------------------------------------------------

# Filing types searched for inbound M&A signals, grouped by strength.
_MA_FILING_TYPES = "8-K,DEFM14A,PREM14A,SC TO-T,SC 14D9,425"
_ANNUAL_FILING_TYPES = "10-K,10-Q"
_OWNERSHIP_FILING_TYPES = "SC 13D,SC 13D/A,SC 13G,SC 13G/A"

# SIC code ranges that are almost always noise (REIT/mortgage filings).
_NOISE_SIC_RANGES = (range(6500, 6800), range(6150, 6200))

# 8-K item codes by signal strength.
_MA_ITEMS = {"1.01", "2.01"}  # definitive agreement, completion of acquisition
_FINANCIAL_ITEMS = {"2.02", "2.05"}  # results of operations, delisting
_DISCLOSURE_ITEMS = {"7.01", "8.01"}  # Reg FD, other events

# Form-type → mention classification (when no overriding items match).
_FORM_TYPE_LABELS: dict[str, str] = {
    "DEFM14A": "ma_proxy",
    "PREM14A": "ma_proxy",
    "SC TO-T": "ma_definitive",
    "SC 14D9": "ma_definitive",
    "SC 13D": "ownership_active",
    "SC 13D/A": "ownership_active",
    "SC 13G": "ownership_passive",
    "SC 13G/A": "ownership_passive",
}

_CORP_SUFFIX = re.compile(
    r",?\s*(Inc\.?|Corp\.?|LLC|Ltd\.?|Co\.?|L\.?P\.?|/DE|/NV|/MD|CORP|INC)$",
    re.IGNORECASE,
)

# Keyword regexes for surrounding-text context classification, ordered by priority.
_MENTION_CONTEXT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"acquir|acquisition|merger|merg(?:ed|ing)|purchased|buyout|"
            r"definitive agreement|business combination|tender offer|"
            r"takeover|bought|close[ds]? (?:the|its) (?:acquisition|purchase)",
            re.IGNORECASE,
        ),
        "acquisition",
    ),
    (
        re.compile(
            r"(?:subsidiary|subsidiaries|wholly[- ]owned|100\s*%|exhibit\s*21)",
            re.IGNORECASE,
        ),
        "subsidiary",
    ),
    (
        re.compile(
            r"invest(?:ed|ment|ing|or)|venture|equity stake|strategic partnership|"
            r"funding round|series [A-F]|capital raise|convertible note",
            re.IGNORECASE,
        ),
        "investment",
    ),
    (
        re.compile(
            r"contract|subcontract|awarded|teaming|supplier|vendor|"
            r"customer|partner(?:ship)?|teamed with|prime contractor",
            re.IGNORECASE,
        ),
        "contract",
    ),
    (
        re.compile(
            r"compet(?:itor|ition|e)|market participant|industry peer|"
            r"comparable|peer group|competitor",
            re.IGNORECASE,
        ),
        "competitor",
    ),
]


# Common English / generic terms used by noise scoring to detect ambiguous names.
_COMMON_ENGLISH_WORDS = frozenset(
    {
        "sediment",
        "informed",
        "ideas",
        "menara",
        "elkins",
        "bai",
        "nil",
        "merit",
        "quest",
        "delta",
        "alpha",
        "summit",
        "pioneer",
        "atlas",
        "nexus",
        "pulse",
        "prism",
        "forge",
        "apex",
        "core",
        "edge",
        "relay",
        "array",
        "signal",
        "matrix",
        "tensor",
        "vector",
        "orbit",
        "cipher",
        "helix",
        "locus",
        "verge",
        "haven",
        "arbor",
        "cadre",
    }
)

_GENERIC_NAME_WORDS = frozenset(
    {
        "advanced",
        "applied",
        "central",
        "digital",
        "first",
        "general",
        "global",
        "good",
        "health",
        "information",
        "integrated",
        "management",
        "material",
        "national",
        "new",
        "process",
        "quality",
        "research",
        "risk",
        "smith",
        "systems",
        "training",
        "development",
        "engineering",
        "computer",
        "methods",
        "programs",
        "services",
        "consulting",
        "park",
        "west",
        "east",
        "north",
        "south",
        "project",
        "transfer",
    }
)


def compute_mention_noise_score(
    company_name: str,
    mention_count: int,
    award_count: int,
) -> int:
    """Score how likely a company's filing mentions are noise (0 = clean).

    Two factors: name distinctiveness (short acronyms, single common words,
    or all-generic phrases match unrelated text) and mention-to-award ratio
    (many mentions but very few SBIR awards is suspicious). Recommended
    threshold: score ≥ 2 filters ~9% of mentions while preserving real signals.
    """
    words = re.findall(r"[A-Za-z]+", company_name)
    score = 0

    if len(words) == 1 and len(words[0]) <= 3:
        score += 3  # Short acronyms (LTI, MCA, BMS) match everywhere.
    elif len(words) == 1 and words[0].lower() in _COMMON_ENGLISH_WORDS:
        score += 3
    elif len(words) == 1:
        score += 1  # Single longer word — mildly suspicious.
    elif all(w.lower() in _GENERIC_NAME_WORDS for w in words if len(w) > 2):
        score += 2  # All words are generic business terms.

    if award_count > 0:
        ratio = mention_count / award_count
        if ratio > 5:
            score += 2
        elif ratio > 2:
            score += 1

    return score


async def _extract_mention_context(
    client: EdgarAPIClient,
    company_name: str,
    mention: dict,
    *,
    context_chars: int = 500,
) -> str | None:
    """Fetch the filing document and classify the mention by surrounding text."""
    doc_id = mention.get("doc_id", "")
    if not doc_id or ":" not in doc_id:
        return None
    accession, filename = doc_id.split(":", 1)
    cik = mention.get("filer_cik", "")
    if not cik:
        return None

    text = await client.fetch_filing_document(cik, accession, filename)
    if not text:
        return None

    match = re.search(re.escape(company_name), text, re.IGNORECASE)
    if not match:
        clean_name = _CORP_SUFFIX.sub("", company_name).strip()
        if len(clean_name) >= 5:
            match = re.search(re.escape(clean_name), text, re.IGNORECASE)
    if not match:
        return None

    start = max(0, match.start() - context_chars)
    end = min(len(text), match.end() + context_chars)
    window = text[start:end]

    for pattern, label in _MENTION_CONTEXT_PATTERNS:
        if pattern.search(window):
            return label
    return None


def _classify_mention(items: list[str], form_type: str) -> str:
    """Classify a filing mention by signal strength.

    Returns one of: 'ma_definitive', 'ma_proxy', 'ownership_active',
    'ownership_passive', 'financial_mention', 'disclosure', 'filing_mention'.
    """
    if label := _FORM_TYPE_LABELS.get(form_type):
        return label
    item_set = set(items)
    if item_set & _MA_ITEMS:
        return "ma_definitive"
    if item_set & _FINANCIAL_ITEMS:
        return "financial_mention"
    if item_set & _DISCLOSURE_ITEMS:
        return "disclosure"
    return "filing_mention"


def _is_noise(filer_name: str, target_name: str, sics: list[str]) -> bool:
    """Return True if a mention is likely noise (REIT/mortgage filer or name collision)."""
    for sic_str in sics:
        try:
            sic = int(sic_str)
        except (ValueError, TypeError):
            continue
        if any(sic in r for r in _NOISE_SIC_RANGES):
            return True

    target_clean = _CORP_SUFFIX.sub("", target_name).strip().upper()
    filer_clean = _CORP_SUFFIX.sub("", filer_name).strip().upper()
    return (
        target_clean in filer_clean
        and filer_clean != target_clean
        and len(filer_clean) > len(target_clean) + 3
    )


async def _search_filing_mentions_filtered(
    client: EdgarAPIClient,
    company_name: str,
    forms: str,
    *,
    name_match_threshold: int = 80,
    limit: int = 20,
) -> list[EdgarMAEvent]:
    """Search for mentions of a company in filings by other public companies.

    Filters self-filings (by fuzzy name match), REIT/mortgage filers (by SIC),
    and name-collision filers (target name is a substring of a different,
    longer filer name).
    """
    mentions = await client.search_filing_mentions(company_name, forms=forms, limit=limit)
    if not mentions:
        return []

    events: list[EdgarMAEvent] = []
    for mention in mentions:
        filer_name = mention.get("filer_name", "")
        if not filer_name:
            continue
        if fuzz.token_set_ratio(company_name.upper(), filer_name.upper()) >= name_match_threshold:
            continue  # self-filing
        if _is_noise(filer_name, company_name, mention.get("sics", [])):
            continue

        filing_date_str = mention.get("file_date")
        if not filing_date_str:
            continue
        try:
            filing_date = date.fromisoformat(filing_date_str)
        except ValueError:
            continue

        form_type = mention.get("form_type", "")
        mention_type = _classify_mention(mention.get("items", []), form_type)

        # Ambiguous mentions: one extra HTTP request to classify from surrounding text.
        if mention_type == "filing_mention":
            text_context = await _extract_mention_context(client, company_name, mention)
            if text_context:
                mention_type = text_context

        events.append(
            EdgarMAEvent(
                cik=mention.get("filer_cik", ""),
                filer_name=filer_name,
                filing_date=filing_date,
                accession_number=mention.get("accession_number", ""),
                event_type=MAAcquisitionType.ACQUISITION,
                mention_type=mention_type,
                description=mention.get("file_description"),
                is_target=True,
            )
        )
    return events


async def _search_inbound_ma_mentions(
    client: EdgarAPIClient,
    company_name: str,
    *,
    name_match_threshold: int = 80,
) -> list[EdgarMAEvent]:
    """Concurrently search three tiers of filings for inbound M&A signals.

    Tiers: (1) strong M&A — 8-K/DEFM14A/PREM14A/SC TO-T/425;
    (2) annual/quarterly — 10-K/10-Q post-acquisition mentions;
    (3) ownership — SC 13D/13G (>5% stakes).
    """
    strong, annual, ownership = await asyncio.gather(
        _search_filing_mentions_filtered(
            client,
            company_name,
            _MA_FILING_TYPES,
            name_match_threshold=name_match_threshold,
            limit=20,
        ),
        _search_filing_mentions_filtered(
            client,
            company_name,
            _ANNUAL_FILING_TYPES,
            name_match_threshold=name_match_threshold,
            limit=10,
        ),
        _search_filing_mentions_filtered(
            client,
            company_name,
            _OWNERSHIP_FILING_TYPES,
            name_match_threshold=name_match_threshold,
            limit=10,
        ),
    )
    return strong + annual + ownership


async def _search_form_d_filings(
    client: EdgarAPIClient,
    company_name: str,
    *,
    match_threshold: int = 85,
) -> list[EdgarFormDFiling]:
    """Search for Form D (Regulation D) filings by a company.

    Only applies name fuzzy matching here. State, temporal, and person-based
    disambiguation are handled in the --form-d-xml pass.
    """
    results = await client.search_form_d_filings(company_name, limit=10)
    if not results:
        return []

    filings: list[EdgarFormDFiling] = []
    for result in results:
        entity_name = result.get("entity_name", "")
        if not entity_name:
            continue
        score = fuzz.token_set_ratio(company_name.upper(), entity_name.upper())
        if score < match_threshold:
            continue
        filing_date_str = result.get("file_date")
        if not filing_date_str:
            continue
        try:
            filing_date = date.fromisoformat(filing_date_str)
        except ValueError:
            continue
        filings.append(
            EdgarFormDFiling(
                cik=result.get("cik", ""),
                entity_name=entity_name,
                filing_date=filing_date,
                match_confidence=score / 100.0,
            )
        )
    return filings


# ---------------------------------------------------------------------------
# CIK resolution
# ---------------------------------------------------------------------------

# Words common to many company names; don't distinguish one company from another.
_GENERIC_WORDS = frozenset(
    {
        "TECHNOLOGIES",
        "TECHNOLOGY",
        "SYSTEMS",
        "SCIENCES",
        "RESEARCH",
        "ENGINEERING",
        "SOLUTIONS",
        "ANALYTICS",
        "DYNAMICS",
        "INDUSTRIES",
        "ASSOCIATES",
        "CONSULTING",
        "SERVICES",
        "GROUP",
        "INTERNATIONAL",
        "LABORATORIES",
        "INSTRUMENTS",
        "MATERIALS",
        "DEVICES",
        "APPLICATIONS",
        "ADVANCED",
        "APPLIED",
        "DIGITAL",
        "GENERAL",
        "NATIONAL",
        "AMERICAN",
        "GLOBAL",
        "INTEGRATED",
        "PRECISION",
        "SCIENTIFIC",
        "TECHNICAL",
        "INNOVATIONS",
        "CORPORATION",
        "COMPANY",
        "ENTERPRISES",
    }
)


def _clean_company_name(name: str) -> str:
    """Iteratively strip corporate suffixes (handles 'QUALCOMM INC/DE')."""
    upper = name.strip().upper()
    for _ in range(3):
        cleaned = _CORP_SUFFIX.sub("", upper).strip()
        if cleaned == upper:
            break
        upper = cleaned
    return upper


def _distinctive_words(cleaned_name: str) -> set[str]:
    """Words in a cleaned name that aren't generic business terms."""
    return set(cleaned_name.split()) - _GENERIC_WORDS


async def _resolve_cik(
    client: EdgarAPIClient,
    company_name: str,
    *,
    threshold: int = 90,
) -> dict[str, Any] | None:
    """Resolve a company name to a CIK using three-layer filtering.

    1. Fuzzy score ≥ threshold on suffix-cleaned names
    2. Containment filter — reject if query is a substring of a longer entity
    3. Distinctive word overlap — at least one non-generic word in common
       (skipped for single-word names where the whole name IS distinctive)

    Returns dict(cik, entity_name, ticker, match_score, match_method) or None.
    """
    results = await client.search_companies(company_name, limit=10)
    if not results:
        return None

    query_clean = _clean_company_name(company_name)
    query_distinctive = _distinctive_words(query_clean)
    query_is_multiword = len(query_clean.split()) > 1

    best_match: dict[str, Any] | None = None
    best_score: float = 0

    for result in results:
        entity_name = result.get("entity_name", "")
        if not entity_name:
            continue
        entity_clean = _clean_company_name(entity_name)

        score = max(
            fuzz.token_set_ratio(query_clean, entity_clean),
            fuzz.ratio(query_clean, entity_clean),
        )
        if score < threshold:
            continue

        # Containment filter
        if (
            query_clean in entity_clean
            and entity_clean != query_clean
            and len(entity_clean) > len(query_clean) + 3
        ):
            continue

        # Distinctive-word overlap (multi-word queries only)
        if query_is_multiword:
            entity_distinctive = _distinctive_words(entity_clean)
            if (
                query_distinctive
                and entity_distinctive
                and not (query_distinctive & entity_distinctive)
            ):
                continue

        if score > best_score:
            best_score = score
            best_match = result

    if best_match is None:
        return None
    return {
        "cik": best_match["cik"],
        "entity_name": best_match["entity_name"],
        "ticker": best_match.get("ticker"),
        "match_score": best_score / 100.0,
        "match_method": "name_match",
    }


# ---------------------------------------------------------------------------
# Public enrichment entry points
# ---------------------------------------------------------------------------


async def enrich_company(
    client: EdgarAPIClient,
    company_name: str,
    company_uei: str | None = None,
    *,
    award_count: int = 0,
    resolve_cik: bool = True,
    fetch_financials: bool = True,
    search_inbound_ma: bool = True,
    search_form_d: bool = False,
) -> CompanyEdgarProfile:
    """Enrich a single SBIR company with SEC EDGAR data.

    Two signal types (Form D sourced separately via bulk index):
      1. CIK resolution — match to a public filer, then optionally pull
         XBRL financials (revenue, R&D, assets).
      2. Filing mentions — search for the company in other filers' filings
         (M&A, ownership, partnership signals).

    Form D is off by default — use `fetch_form_d_index.py` for bulk Form D
    matching from EDGAR quarterly index files instead of EFTS.
    """
    profile = CompanyEdgarProfile(
        company_name=company_name,
        company_uei=company_uei,
        enriched_at=datetime.now(),
    )

    # CIK resolution and XBRL financials.
    if resolve_cik:
        match = await _resolve_cik(client, company_name)
        if match:
            cik = match["cik"]
            profile.cik = cik
            profile.is_publicly_traded = True
            profile.match_confidence = match["match_score"]
            profile.match_method = match["match_method"]
            profile.ticker = match.get("ticker")
            if fetch_financials:
                facts = await client.get_company_facts(cik)
                if facts and (financials := _extract_financials(cik, facts)):
                    profile.latest_revenue = financials.revenue
                    profile.latest_rd_expense = financials.rd_expense
                    profile.latest_total_assets = financials.total_assets
                    profile.latest_net_income = financials.net_income
                    profile.financials_as_of = financials.filing_date
                    profile.sic_code = facts.get("sic")

    # Filing mentions; dedupe by filer keeping the latest filing.
    if search_inbound_ma:
        inbound_events = await _search_inbound_ma_mentions(client, company_name)
        by_filer: dict[str, EdgarMAEvent] = {}
        for e in inbound_events:
            key = e.filer_name or e.cik
            if key not in by_filer or e.filing_date > by_filer[key].filing_date:
                by_filer[key] = e
        deduped = list(by_filer.values())

        profile.mention_count = len(deduped)
        if deduped:
            profile.mention_filers = [e.filer_name for e in deduped if e.filer_name]
            profile.mention_types = sorted({e.mention_type for e in deduped if e.mention_type})
            profile.latest_mention_date = max(e.filing_date for e in deduped)

    # Form D (Reg D private capital raises).
    if search_form_d:
        form_d_filings = await _search_form_d_filings(client, company_name)
        profile.form_d_count = len(form_d_filings)
        if form_d_filings:
            profile.has_form_d = True
            profile.form_d_cik = form_d_filings[0].cik
            profile.latest_form_d_date = max(f.filing_date for f in form_d_filings)

    if profile.mention_count > 0:
        profile.mention_noise_score = compute_mention_noise_score(
            company_name, profile.mention_count, award_count
        )

    return profile


async def enrich_companies_with_edgar(
    companies_df: pd.DataFrame,
    client: EdgarAPIClient | None = None,
    *,
    company_name_col: str = "company_name",
    company_uei_col: str = "uei",
    search_inbound_ma: bool = True,
    search_form_d: bool = True,
) -> pd.DataFrame:
    """Enrich a DataFrame of SBIR companies with SEC EDGAR data.

    Iterates unique company names (one EDGAR call set per name), then merges
    the enrichment columns back onto every input row.
    """
    if companies_df.empty:
        logger.warning("Empty DataFrame passed to SEC EDGAR enrichment")
        return companies_df

    own_client = client is None
    if client is None:
        client = EdgarAPIClient()

    try:
        unique_companies = companies_df[[company_name_col]].drop_duplicates()
        if company_uei_col in companies_df.columns and company_uei_col != company_name_col:
            uei_lookup = (
                companies_df[[company_name_col, company_uei_col]]
                .drop_duplicates(subset=[company_name_col])
                .set_index(company_name_col)[company_uei_col]
                .to_dict()
            )
        else:
            uei_lookup = {}

        total = len(unique_companies)
        logger.info(f"Enriching {total} unique companies with SEC EDGAR data")

        profiles: list[dict[str, Any]] = []
        matched_count = 0
        for _, row in unique_companies.iterrows():
            name = row[company_name_col]
            profile = await enrich_company(
                client,
                name,
                company_uei=uei_lookup.get(name),
                search_inbound_ma=search_inbound_ma,
                search_form_d=search_form_d,
            )
            profiles.append(profile.model_dump())
            if profile.mention_count or profile.has_form_d:
                matched_count += 1
            if len(profiles) % 50 == 0:
                logger.info(
                    f"SEC EDGAR enrichment progress: {len(profiles)}/{total} "
                    f"({matched_count} public matches)"
                )

        inbound_ma_count = sum(1 for p in profiles if p.get("mention_count", 0) > 0)
        form_d_count = sum(1 for p in profiles if p.get("has_form_d", False))
        logger.info(
            f"SEC EDGAR enrichment complete: {matched_count}/{total} with signals "
            f"({matched_count / total * 100:.1f}%), "
            f"{inbound_ma_count} with SEC filing mentions, "
            f"{form_d_count} with Form D filings"
        )

        enrichment_df = pd.DataFrame(profiles)
        rename_map = {
            col: f"sec_{col}"
            for col in enrichment_df.columns
            if col not in (company_name_col, "company_name") and not col.startswith("sec_")
        }
        enrichment_df = enrichment_df.rename(columns=rename_map)
        result = companies_df.merge(
            enrichment_df,
            left_on=company_name_col,
            right_on="company_name",
            how="left",
            suffixes=("", "_edgar"),
        )
        if "company_name_edgar" in result.columns:
            result = result.drop(columns=["company_name_edgar"])
        if "company_name" in result.columns and company_name_col != "company_name":
            result = result.drop(columns=["company_name"])
        return result
    finally:
        if own_client:
            await client.aclose()
