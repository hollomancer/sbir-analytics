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

# Filer names matching these patterns are almost always noise (lease filings,
# mortgage pass-throughs, etc. that mention tenant/borrower company names).
_NOISE_FILER_KEYWORDS = re.compile(
    r"realty|reit|real estate|properties trust|mortgage|pass thr|"
    r"commercial mort|capital trust|property trust",
    re.IGNORECASE,
)


def _is_noise_filer(filer_name: str, target_name: str) -> bool:
    """Return True if this filer→target mention is likely noise.

    Catches:
    - REITs and real estate companies (Vornado, Mack-Cali) whose lease
      filings mention tenant companies
    - Name collisions where the target name is a substring of a different
      company name (e.g. "Fibertek" matching "Thermo Fibertek")
    """
    if _NOISE_FILER_KEYWORDS.search(filer_name):
        return True

    # Name collision: target name appears inside filer name as a component
    # of a longer, different company name.
    # e.g. "FIBERTEK" in "THERMO FIBERTEK INC" → different company.
    # But "MERCURY" in "MERCURY SYSTEMS" → same entity family, keep it.
    _SUFFIXES = re.compile(
        r",?\s*(Inc\.?|Corp\.?|LLC|Ltd\.?|Co\.?|L\.?P\.?|/DE|/NV|/MD|CORP|INC)$",
        re.IGNORECASE,
    )
    target_clean = _SUFFIXES.sub("", target_name).strip().upper()
    filer_clean = _SUFFIXES.sub("", filer_name).strip().upper()

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
    - REIT/real estate filers (lease noise)
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
        # Skip noise filers (REITs, name collisions)
        if _is_noise_filer(filer_name, company_name):
            continue

        filing_date_str = mention.get("file_date")
        if not filing_date_str:
            continue
        try:
            filing_date = date.fromisoformat(filing_date_str)
        except ValueError:
            continue

        form_type = mention.get("form_type", "")
        events.append(
            EdgarMAEvent(
                cik=mention.get("filer_cik", ""),
                filer_name=filer_name,
                filing_date=filing_date,
                accession_number=mention.get("accession_number", ""),
                event_type=MAAcquisitionType.ACQUISITION,
                items_reported=[form_type or "inbound_mention"],
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


async def _resolve_cik(
    client: EdgarAPIClient,
    company_name: str,
    *,
    high_threshold: int = 90,
    low_threshold: int = 75,
) -> dict[str, Any] | None:
    """Resolve a company name to a CIK using EDGAR full-text search.

    Uses fuzzy matching to compare SBIR company names against EDGAR entity names.

    Returns:
        Dict with cik, entity_name, match_score, match_method, ticker or None.
    """
    results = await client.search_companies(company_name, limit=10)
    if not results:
        return None

    best_match = None
    best_score = 0

    # Strip common corporate suffixes for better matching of short names
    _SUFFIXES = re.compile(
        r",?\s*(Inc\.?|Corp\.?|LLC|Ltd\.?|Co\.?|L\.?P\.?|/DE|/NV|/MD)$",
        re.IGNORECASE,
    )

    query_clean = _SUFFIXES.sub("", company_name).strip().upper()

    for result in results:
        entity_name = result.get("entity_name", "")
        if not entity_name:
            continue
        entity_clean = _SUFFIXES.sub("", entity_name).strip().upper()
        # Use the better of token_set_ratio (handles word reordering) and
        # ratio on cleaned names (handles short names like "IonQ" vs "IonQ, Inc.")
        score = max(
            fuzz.token_set_ratio(query_clean, entity_clean),
            fuzz.ratio(query_clean, entity_clean),
        )
        if score > best_score:
            best_score = score
            best_match = result

    if best_match and best_score >= low_threshold:
        return {
            "cik": best_match["cik"],
            "entity_name": best_match["entity_name"],
            "ticker": best_match.get("ticker"),
            "match_score": best_score / 100.0,  # Normalize to 0-1
            "match_method": "name_fuzzy_auto" if best_score >= high_threshold else "name_fuzzy_review",
        }

    return None


async def enrich_company(
    client: EdgarAPIClient,
    company_name: str,
    company_uei: str | None = None,
    *,
    search_inbound_ma: bool = True,
    search_form_d: bool = True,
) -> CompanyEdgarProfile:
    """Enrich a single company with SEC EDGAR data.

    Focuses on signals available for *all* companies (including private):
    1. Inbound M&A mentions — search for the company name in other public
       companies' 8-K filings (catches acquisitions of private targets)
    2. Form D filings — Regulation D private capital raises

    Args:
        client: EdgarAPIClient instance.
        company_name: SBIR company name.
        company_uei: Optional UEI for linking.
        search_inbound_ma: Whether to search for the company as an M&A target.
        search_form_d: Whether to search for Form D (Reg D) filings.

    Returns:
        CompanyEdgarProfile with whatever data could be resolved.
    """
    profile = CompanyEdgarProfile(
        company_name=company_name,
        company_uei=company_uei,
        enriched_at=datetime.now(),
    )

    # Inbound M&A detection — search for this company's name in other
    # public companies' 8-K filings.  Deduplicate by filer so we report
    # distinct acquirers, not duplicate filings from the same company.
    if search_inbound_ma:
        inbound_events = await _search_inbound_ma_mentions(client, company_name)
        # Deduplicate: keep the latest filing per filer
        by_filer: dict[str, EdgarMAEvent] = {}
        for e in inbound_events:
            key = e.filer_name or e.cik
            if key not in by_filer or e.filing_date > by_filer[key].filing_date:
                by_filer[key] = e
        deduped = list(by_filer.values())

        profile.inbound_ma_mention_count = len(deduped)
        if deduped:
            profile.inbound_ma_acquirers = [e.filer_name for e in deduped if e.filer_name]
            profile.inbound_ma_filing_types = sorted({
                ft for e in deduped for ft in e.items_reported if ft
            })
            profile.latest_inbound_ma_date = max(e.filing_date for e in deduped)

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
            if profile.inbound_ma_mention_count or profile.has_form_d:
                matched_count += 1

            if (len(profiles)) % 50 == 0:
                logger.info(
                    f"SEC EDGAR enrichment progress: {len(profiles)}/{total} "
                    f"({matched_count} public matches)"
                )

        # Count private company signals
        inbound_ma_count = sum(1 for p in profiles if p.get("inbound_ma_mention_count", 0) > 0)
        form_d_count = sum(1 for p in profiles if p.get("has_form_d", False))

        logger.info(
            f"SEC EDGAR enrichment complete: {matched_count}/{total} with signals "
            f"({matched_count / total * 100:.1f}%), "
            f"{inbound_ma_count} with inbound M&A mentions, "
            f"{form_d_count} with Form D filings"
        )

        # Build enrichment DataFrame and merge
        enrichment_df = pd.DataFrame(profiles)
        # Prefix enrichment columns to avoid collisions
        rename_map = {
            col: f"sec_{col}"
            for col in enrichment_df.columns
            if col not in (company_name_col, "company_name")
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
