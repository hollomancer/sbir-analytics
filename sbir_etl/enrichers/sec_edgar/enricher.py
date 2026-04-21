"""SEC EDGAR enrichment logic for SBIR companies.

Resolves SBIR company names to SEC CIK numbers, extracts financial data
from XBRL filings, and detects M&A events from 8-K filings.
"""

from __future__ import annotations

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

# XBRL concept names for financial data extraction
_REVENUE_CONCEPTS = [
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "SalesRevenueNet",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
]
_NET_INCOME_CONCEPTS = [
    "NetIncomeLoss",
    "ProfitLoss",
]
_TOTAL_ASSETS_CONCEPTS = [
    "Assets",
]
_TOTAL_LIABILITIES_CONCEPTS = [
    "Liabilities",
]
_RD_EXPENSE_CONCEPTS = [
    "ResearchAndDevelopmentExpense",
    "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
]
_OPERATING_INCOME_CONCEPTS = [
    "OperatingIncomeLoss",
]
_CASH_CONCEPTS = [
    "CashAndCashEquivalentsAtCarryingValue",
    "Cash",
]


def _extract_latest_fact(
    facts: dict[str, Any],
    concept_names: list[str],
    *,
    taxonomy: str = "us-gaap",
) -> tuple[float | None, date | None]:
    """Extract the most recent value for a financial concept from XBRL facts.

    Tries each concept name in order and returns the first match with a
    10-K or 10-Q filing context.

    Returns:
        Tuple of (value, period_end_date) or (None, None) if not found.
        The date is the XBRL reporting period end date, not the SEC filing date.
    """
    tax_facts = facts.get("facts", {}).get(taxonomy, {})
    for concept in concept_names:
        concept_data = tax_facts.get(concept)
        if not concept_data:
            continue
        units = concept_data.get("units", {})
        # Financial values are in USD
        usd_entries = units.get("USD", [])
        if not usd_entries:
            continue
        # Filter to annual (10-K) or quarterly (10-Q) filings
        annual_entries = [
            e for e in usd_entries
            if e.get("form") in ("10-K", "10-Q", "20-F")
            and e.get("val") is not None
        ]
        if not annual_entries:
            continue
        # Sort by end date descending to get most recent
        annual_entries.sort(key=lambda e: e.get("end", ""), reverse=True)
        latest = annual_entries[0]
        try:
            period_end = date.fromisoformat(latest["end"])
        except (ValueError, KeyError):
            period_end = None
        return float(latest["val"]), period_end
    return None, None


def _extract_financials(
    cik: str, facts: dict[str, Any]
) -> EdgarFinancials | None:
    """Extract standardized financials from EDGAR company facts."""
    revenue, rev_date = _extract_latest_fact(facts, _REVENUE_CONCEPTS)
    net_income, ni_date = _extract_latest_fact(facts, _NET_INCOME_CONCEPTS)
    total_assets, ta_date = _extract_latest_fact(facts, _TOTAL_ASSETS_CONCEPTS)
    total_liabilities, tl_date = _extract_latest_fact(facts, _TOTAL_LIABILITIES_CONCEPTS)
    rd_expense, rd_date = _extract_latest_fact(facts, _RD_EXPENSE_CONCEPTS)
    operating_income, oi_date = _extract_latest_fact(facts, _OPERATING_INCOME_CONCEPTS)
    cash, cash_date = _extract_latest_fact(facts, _CASH_CONCEPTS)

    # If we couldn't extract anything useful, skip
    if all(v is None for v in [revenue, net_income, total_assets, rd_expense]):
        return None

    # Use the most recent period end date among all extracted values
    dates = [d for d in [rev_date, ni_date, ta_date, tl_date, rd_date, oi_date, cash_date] if d]
    latest_date = max(dates) if dates else None

    # Require a valid date to avoid creating records with sentinel fiscal_year=0
    if latest_date is None:
        return None

    return EdgarFinancials(
        cik=cik,
        fiscal_year=latest_date.year,
        revenue=revenue,
        net_income=net_income,
        total_assets=total_assets,
        total_liabilities=total_liabilities,
        rd_expense=rd_expense,
        operating_income=operating_income,
        cash_and_equivalents=cash,
        filing_date=latest_date,
    )


def _detect_ma_events(
    cik: str, filings: list[dict[str, Any]]
) -> list[EdgarMAEvent]:
    """Detect M&A events from 8-K filings.

    Looks for Item 1.01 (material definitive agreements) and
    Item 2.01 (completion of acquisition/disposition) in 8-K filings.
    """
    events = []
    for filing in filings:
        if filing.get("form_type") != "8-K":
            continue
        description = (filing.get("description") or "").lower()
        # Check if description mentions M&A-relevant items
        items_found = []
        if "1.01" in description or "material" in description:
            items_found.append("1.01")
        if "2.01" in description or "acqui" in description or "merger" in description:
            items_found.append("2.01")

        if not items_found:
            continue

        event_type = MAAcquisitionType.UNKNOWN
        if "acqui" in description:
            event_type = MAAcquisitionType.ACQUISITION
        elif "merger" in description:
            event_type = MAAcquisitionType.MERGER

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


# Filing types searched for inbound M&A signals, grouped by strength.
# Stronger types are definitively M&A-related; weaker types may be noise.
_MA_FILING_TYPES = "8-K,DEFM14A,PREM14A,SC TO-T,SC 14D9,425"
_ANNUAL_FILING_TYPES = "10-K,10-Q"
_OWNERSHIP_FILING_TYPES = "SC 13D,SC 13D/A,SC 13G,SC 13G/A"

# SIC code ranges that are almost always noise (their filings mention
# tenant/borrower company names in lease or mortgage documents).
_NOISE_SIC_RANGES = {
    range(6500, 6800),  # Real estate (REITs, property trusts)
    range(6150, 6200),  # Mortgage brokers and pass-throughs
}

# 8-K item codes that indicate M&A activity.
_MA_ITEMS = {"1.01", "2.01"}            # definitive agreement, completion of acquisition
_FINANCIAL_ITEMS = {"2.02", "2.05"}     # results of operations, delisting
_DISCLOSURE_ITEMS = {"7.01", "8.01"}    # Reg FD, other events

_CORP_SUFFIX = re.compile(
    r",?\s*(Inc\.?|Corp\.?|LLC|Ltd\.?|Co\.?|L\.?P\.?|/DE|/NV|/MD|CORP|INC)$",
    re.IGNORECASE,
)


# Keywords in surrounding text that indicate specific mention contexts.
_MA_KEYWORDS = re.compile(
    r"acquir|acquisition|merger|merg(?:ed|ing)|purchased|buyout|"
    r"definitive agreement|business combination|tender offer|"
    r"takeover|bought|close[ds]? (?:the|its) (?:acquisition|purchase)",
    re.IGNORECASE,
)
_SUBSIDIARY_KEYWORDS = re.compile(
    r"(?:subsidiary|subsidiaries|wholly[- ]owned|100\s*%|exhibit\s*21)",
    re.IGNORECASE,
)
_INVESTMENT_KEYWORDS = re.compile(
    r"invest(?:ed|ment|ing|or)|venture|equity stake|strategic partnership|"
    r"funding round|series [A-F]|capital raise|convertible note",
    re.IGNORECASE,
)
_CONTRACT_KEYWORDS = re.compile(
    r"contract|subcontract|awarded|teaming|supplier|vendor|"
    r"customer|partner(?:ship)?|teamed with|prime contractor",
    re.IGNORECASE,
)
_COMPETITOR_KEYWORDS = re.compile(
    r"compet(?:itor|ition|e)|market participant|industry peer|"
    r"comparable|peer group|competitor",
    re.IGNORECASE,
)


async def _extract_mention_context(
    client: EdgarAPIClient,
    company_name: str,
    mention: dict,
    *,
    context_chars: int = 500,
) -> str | None:
    """Fetch the filing document and classify the mention context.

    Returns a context label: 'acquisition', 'subsidiary', 'investment',
    'contract', 'competitor', or None if context can't be determined.
    """
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

    # Find the company name and extract surrounding context
    pattern = re.compile(re.escape(company_name), re.IGNORECASE)
    match = pattern.search(text)
    if not match:
        # Try without corporate suffixes
        clean_name = _CORP_SUFFIX.sub("", company_name).strip()
        if len(clean_name) >= 5:
            match = re.search(re.escape(clean_name), text, re.IGNORECASE)
    if not match:
        return None

    start = max(0, match.start() - context_chars)
    end = min(len(text), match.end() + context_chars)
    window = text[start:end]

    # Classify based on keywords in the context window
    if _MA_KEYWORDS.search(window):
        return "acquisition"
    if _SUBSIDIARY_KEYWORDS.search(window):
        return "subsidiary"
    if _INVESTMENT_KEYWORDS.search(window):
        return "investment"
    if _CONTRACT_KEYWORDS.search(window):
        return "contract"
    if _COMPETITOR_KEYWORDS.search(window):
        return "competitor"
    return None


def _classify_mention(items: list[str], form_type: str) -> str:
    """Classify a filing mention by signal strength.

    Returns one of: 'ma_definitive', 'ma_proxy', 'ownership_active',
    'ownership_passive', 'financial_mention', 'disclosure', 'filing_mention'.
    """
    item_set = set(items)

    if form_type in ("DEFM14A", "PREM14A"):
        return "ma_proxy"
    if form_type in ("SC TO-T", "SC 14D9"):
        return "ma_definitive"
    if form_type in ("SC 13D", "SC 13D/A"):
        return "ownership_active"
    if form_type in ("SC 13G", "SC 13G/A"):
        return "ownership_passive"
    if item_set & _MA_ITEMS:
        return "ma_definitive"
    if item_set & _FINANCIAL_ITEMS:
        return "financial_mention"
    if item_set & _DISCLOSURE_ITEMS:
        return "disclosure"
    return "filing_mention"


def _is_noise(
    filer_name: str, target_name: str, sics: list[str],
) -> bool:
    """Return True if this mention is likely noise.

    Catches:
    - Real estate / mortgage filers (by SIC code)
    - Name collisions where target is a substring of a different company
    """
    # SIC-based filter: real estate, mortgage pass-throughs
    for sic_str in sics:
        try:
            sic = int(sic_str)
        except (ValueError, TypeError):
            continue
        if any(sic in r for r in _NOISE_SIC_RANGES):
            return True

    # Name collision: target appears as a component of the filer's longer name
    target_clean = _CORP_SUFFIX.sub("", target_name).strip().upper()
    filer_clean = _CORP_SUFFIX.sub("", filer_name).strip().upper()
    if (
        target_clean in filer_clean
        and filer_clean != target_clean
        and len(filer_clean) > len(target_clean) + 3
    ):
        return True

    return False


async def _search_filing_mentions_filtered(
    client: EdgarAPIClient,
    company_name: str,
    forms: str,
    *,
    name_match_threshold: int = 80,
    limit: int = 20,
) -> list[EdgarMAEvent]:
    """Search for mentions of a company in filings by other public companies.

    Filters:
    - Self-filings (filer IS the searched company)
    - Real estate / mortgage filers (by SIC code)
    - Name collisions (target name is substring of a different company)
    """
    mentions = await client.search_filing_mentions(
        company_name, forms=forms, limit=limit
    )
    if not mentions:
        return []

    events = []
    for mention in mentions:
        filer_name = mention.get("filer_name", "")
        if not filer_name:
            continue
        # Skip self-filings
        similarity = fuzz.token_set_ratio(company_name.upper(), filer_name.upper())
        if similarity >= name_match_threshold:
            continue
        # Skip noise (REITs by SIC, name collisions)
        sics = mention.get("sics", [])
        if _is_noise(filer_name, company_name, sics):
            continue

        filing_date_str = mention.get("file_date")
        if not filing_date_str:
            continue
        try:
            filing_date = date.fromisoformat(filing_date_str)
        except ValueError:
            continue

        form_type = mention.get("form_type", "")
        items = mention.get("items", [])
        mention_type = _classify_mention(items, form_type)

        # For ambiguous mentions, try to fetch the filing and classify
        # from surrounding text.  This costs one HTTP request per mention.
        if mention_type == "filing_mention":
            text_context = await _extract_mention_context(
                client, company_name, mention
            )
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
    """Search for M&A-related mentions across strong and weak filing types.

    Searches three tiers of filings:
    1. Strong M&A signals: 8-K, DEFM14A, PREM14A, SC TO-T, 425
    2. Annual/quarterly reports: 10-K, 10-Q (post-acquisition mentions)
    3. Ownership filings: SC 13D/13G (>5% stakes, pre-acquisition signal)

    Returns:
        Combined list of EdgarMAEvent from all tiers.
    """
    # Run all three searches concurrently
    import asyncio
    strong, annual, ownership = await asyncio.gather(
        _search_filing_mentions_filtered(
            client, company_name, _MA_FILING_TYPES,
            name_match_threshold=name_match_threshold, limit=20,
        ),
        _search_filing_mentions_filtered(
            client, company_name, _ANNUAL_FILING_TYPES,
            name_match_threshold=name_match_threshold, limit=10,
        ),
        _search_filing_mentions_filtered(
            client, company_name, _OWNERSHIP_FILING_TYPES,
            name_match_threshold=name_match_threshold, limit=10,
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

    Private companies raising capital under Reg D must file Form D.
    This identifies SBIR companies that raised venture/angel capital.

    Args:
        client: EdgarAPIClient instance.
        company_name: Company name to search for.
        match_threshold: Minimum fuzzy score for name match.

    Returns:
        List of EdgarFormDFiling records.
    """
    results = await client.search_form_d_filings(company_name, limit=10)
    if not results:
        return []

    filings = []
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


# Words that appear in many company names but don't distinguish one company
# from another.  Used by CIK resolution to require at least one distinctive
# word overlap between query and candidate.
_GENERIC_WORDS = frozenset({
    "TECHNOLOGIES", "TECHNOLOGY", "SYSTEMS", "SCIENCES", "RESEARCH",
    "ENGINEERING", "SOLUTIONS", "ANALYTICS", "DYNAMICS", "INDUSTRIES",
    "ASSOCIATES", "CONSULTING", "SERVICES", "GROUP", "INTERNATIONAL",
    "LABORATORIES", "INSTRUMENTS", "MATERIALS", "DEVICES", "APPLICATIONS",
    "ADVANCED", "APPLIED", "DIGITAL", "GENERAL", "NATIONAL", "AMERICAN",
    "GLOBAL", "INTEGRATED", "PRECISION", "SCIENTIFIC", "TECHNICAL",
    "INNOVATIONS", "CORPORATION", "COMPANY", "ENTERPRISES",
})


def _clean_company_name(name: str) -> str:
    """Strip corporate suffixes for matching.  Applied iteratively to handle
    nested suffixes like 'QUALCOMM INC/DE'."""
    upper = name.strip().upper()
    for _ in range(3):  # Max 3 passes
        cleaned = _CORP_SUFFIX.sub("", upper).strip()
        if cleaned == upper:
            break
        upper = cleaned
    return upper


def _distinctive_words(cleaned_name: str) -> set[str]:
    """Return the words in a cleaned name that aren't generic."""
    return set(cleaned_name.split()) - _GENERIC_WORDS


async def _resolve_cik(
    client: EdgarAPIClient,
    company_name: str,
    *,
    threshold: int = 90,
) -> dict[str, Any] | None:
    """Resolve a company name to a CIK using EDGAR full-text search.

    Uses three-layer filtering to minimize false positives:
    1. Fuzzy score threshold (≥90% after suffix stripping)
    2. Containment filter (reject if query is a substring of a longer,
       different entity name — e.g. "Fibertek" in "Thermo Fibertek")
    3. Distinctive word overlap (require at least one non-generic word
       in common — rejects "Impact Technologies" → "BK Technologies")

    Returns:
        Dict with cik, entity_name, match_score, match_method, ticker or None.
    """
    results = await client.search_companies(company_name, limit=10)
    if not results:
        return None

    query_clean = _clean_company_name(company_name)
    query_distinctive = _distinctive_words(query_clean)

    best_match = None
    best_score = 0

    for result in results:
        entity_name = result.get("entity_name", "")
        if not entity_name:
            continue
        entity_clean = _clean_company_name(entity_name)

        # Layer 1: fuzzy score on cleaned names
        score = max(
            fuzz.token_set_ratio(query_clean, entity_clean),
            fuzz.ratio(query_clean, entity_clean),
        )
        if score < threshold:
            continue

        # Layer 2: containment filter — reject if query name is embedded
        # inside a longer, different company name
        if (
            query_clean in entity_clean
            and entity_clean != query_clean
            and len(entity_clean) > len(query_clean) + 3
        ):
            continue

        # Layer 3: distinctive word overlap — at least one non-generic word
        # must be shared.  Skip this check for single-word names (e.g. "Qualcomm")
        # where the whole name IS the distinctive word.
        if len(query_clean.split()) > 1:
            entity_distinctive = _distinctive_words(entity_clean)
            if query_distinctive and entity_distinctive:
                if not (query_distinctive & entity_distinctive):
                    continue

        if score > best_score:
            best_score = score
            best_match = result

    if best_match:
        return {
            "cik": best_match["cik"],
            "entity_name": best_match["entity_name"],
            "ticker": best_match.get("ticker"),
            "match_score": best_score / 100.0,
            "match_method": "name_match",
        }

    return None


async def enrich_company(
    client: EdgarAPIClient,
    company_name: str,
    company_uei: str | None = None,
    *,
    resolve_cik: bool = True,
    fetch_financials: bool = True,
    search_inbound_ma: bool = True,
    search_form_d: bool = True,
) -> CompanyEdgarProfile:
    """Enrich a single company with SEC EDGAR data.

    Three signal types:
    1. CIK resolution — match company name to a public SEC filer, then
       optionally pull XBRL financials (revenue, R&D, assets)
    2. Filing mentions — search for the company name in other public
       companies' filings (M&A, ownership, partnership signals)
    3. Form D filings — Regulation D private capital raises

    Args:
        client: EdgarAPIClient instance.
        company_name: SBIR company name.
        company_uei: Optional UEI for linking.
        resolve_cik: Whether to attempt CIK resolution (public company match).
        fetch_financials: Whether to pull XBRL financials for CIK matches.
        search_inbound_ma: Whether to search for the company in other filings.
        search_form_d: Whether to search for Form D (Reg D) filings.

    Returns:
        CompanyEdgarProfile with whatever data could be resolved.
    """
    profile = CompanyEdgarProfile(
        company_name=company_name,
        company_uei=company_uei,
        enriched_at=datetime.now(),
    )

    # CIK resolution — match to a public SEC filer using 3-layer filtering
    if resolve_cik:
        match = await _resolve_cik(client, company_name)
        if match:
            cik = match["cik"]
            profile.cik = cik
            profile.is_publicly_traded = True
            profile.match_confidence = match["match_score"]
            profile.match_method = match["match_method"]
            profile.ticker = match.get("ticker")

            # Pull XBRL financials for matched public companies
            if fetch_financials:
                facts = await client.get_company_facts(cik)
                if facts:
                    financials = _extract_financials(cik, facts)
                    if financials:
                        profile.latest_revenue = financials.revenue
                        profile.latest_rd_expense = financials.rd_expense
                        profile.latest_total_assets = financials.total_assets
                        profile.latest_net_income = financials.net_income
                        profile.financials_as_of = financials.filing_date
                        profile.sic_code = facts.get("sic")

    # SEC filing mentions — search for this company's name in other public
    # companies' filings.  Deduplicate by filer so we report distinct
    # mentioning companies, not duplicate filings from the same filer.
    if search_inbound_ma:
        inbound_events = await _search_inbound_ma_mentions(client, company_name)
        # Deduplicate: keep the strongest-classified filing per filer
        by_filer: dict[str, EdgarMAEvent] = {}
        for e in inbound_events:
            key = e.filer_name or e.cik
            if key not in by_filer or e.filing_date > by_filer[key].filing_date:
                by_filer[key] = e
        deduped = list(by_filer.values())

        profile.mention_count = len(deduped)
        if deduped:
            profile.mention_filers = [e.filer_name for e in deduped if e.filer_name]
            profile.mention_types = sorted({
                e.mention_type for e in deduped if e.mention_type
            })
            profile.latest_mention_date = max(e.filing_date for e in deduped)

    # Form D search — private capital raises under Regulation D
    if search_form_d:
        form_d_filings = await _search_form_d_filings(client, company_name)
        profile.form_d_count = len(form_d_filings)
        if form_d_filings:
            profile.has_form_d = True
            profile.form_d_cik = form_d_filings[0].cik
            profile.latest_form_d_date = max(f.filing_date for f in form_d_filings)

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

    Iterates over unique companies and merges enrichment columns back.
    Focuses on signals available for all companies (including private):
    - EFTS text search → inbound M&A mentions in public 8-K filings
    - Form D search → private capital raises under Reg D

    Args:
        companies_df: DataFrame with company records.
        client: Optional pre-configured EdgarAPIClient.
        company_name_col: Column name for company names.
        company_uei_col: Column name for UEI identifiers.
        search_inbound_ma: Search for company as M&A target in public filings.
        search_form_d: Search for Form D (Reg D) filings.

    Returns:
        DataFrame with SEC EDGAR enrichment columns added.
    """
    if companies_df.empty:
        logger.warning("Empty DataFrame passed to SEC EDGAR enrichment")
        return companies_df

    own_client = False
    if client is None:
        client = EdgarAPIClient()
        own_client = True

    try:
        # De-duplicate by company name to minimize API calls
        unique_companies = companies_df[[company_name_col]].drop_duplicates()
        has_uei = (
            company_uei_col in companies_df.columns
            and company_uei_col != company_name_col
        )
        if has_uei:
            # Get first UEI per company for linking
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

        for idx, row in unique_companies.iterrows():
            name = row[company_name_col]
            uei = uei_lookup.get(name)

            profile = await enrich_company(
                client,
                name,
                company_uei=uei,
                search_inbound_ma=search_inbound_ma,
                search_form_d=search_form_d,
            )
            profiles.append(profile.model_dump())
            if profile.mention_count or profile.has_form_d:
                matched_count += 1

            if (len(profiles)) % 50 == 0:
                logger.info(
                    f"SEC EDGAR enrichment progress: {len(profiles)}/{total} "
                    f"({matched_count} public matches)"
                )

        # Count private company signals
        inbound_ma_count = sum(1 for p in profiles if p.get("mention_count", 0) > 0)
        form_d_count = sum(1 for p in profiles if p.get("has_form_d", False))

        logger.info(
            f"SEC EDGAR enrichment complete: {matched_count}/{total} with signals "
            f"({matched_count / total * 100:.1f}%), "
            f"{inbound_ma_count} with SEC filing mentions, "
            f"{form_d_count} with Form D filings"
        )

        # Build enrichment DataFrame and merge
        enrichment_df = pd.DataFrame(profiles)
        # Prefix enrichment columns to avoid collisions
        rename_map = {
            col: f"sec_{col}"
            for col in enrichment_df.columns
            if col not in (company_name_col, "company_name")
            and not col.startswith("sec_")
        }
        enrichment_df = enrichment_df.rename(columns=rename_map)

        # Merge on company name
        result = companies_df.merge(
            enrichment_df,
            left_on=company_name_col,
            right_on="company_name",
            how="left",
            suffixes=("", "_edgar"),
        )

        # Drop the duplicate company_name column from enrichment if it exists
        if "company_name_edgar" in result.columns:
            result = result.drop(columns=["company_name_edgar"])
        if "company_name" in result.columns and company_name_col != "company_name":
            result = result.drop(columns=["company_name"])

        return result

    finally:
        if own_client:
            await client.aclose()
