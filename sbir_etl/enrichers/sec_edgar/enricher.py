"""SEC EDGAR enrichment logic for SBIR companies.

Resolves SBIR company names to SEC CIK numbers, extracts financial data
from XBRL filings, and detects M&A events from 8-K filings.
"""

from __future__ import annotations

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


async def _search_inbound_ma_mentions(
    client: EdgarAPIClient,
    company_name: str,
    *,
    name_match_threshold: int = 80,
) -> list[EdgarMAEvent]:
    """Search for mentions of a company as an M&A target in public filings.

    Uses EFTS full-text search to find the company name inside 8-K filings
    filed by *other* public companies. This catches acquisitions where the
    SBIR company is the private target being acquired.

    Args:
        client: EdgarAPIClient instance.
        company_name: SBIR company name to search for.
        name_match_threshold: Minimum fuzzy score to accept a mention.

    Returns:
        List of EdgarMAEvent where is_target=True.
    """
    mentions = await client.search_filing_mentions(
        company_name, forms="8-K", limit=20
    )
    if not mentions:
        return []

    events = []
    for mention in mentions:
        # Verify the filer is not the same company (would be outbound, not inbound)
        filer_name = mention.get("filer_name", "")
        if not filer_name:
            continue
        similarity = fuzz.token_set_ratio(company_name.upper(), filer_name.upper())
        if similarity >= name_match_threshold:
            # This is the company's own filing, skip
            continue

        filing_date_str = mention.get("file_date")
        if not filing_date_str:
            continue
        try:
            filing_date = date.fromisoformat(filing_date_str)
        except ValueError:
            continue

        events.append(
            EdgarMAEvent(
                cik=mention.get("filer_cik", ""),
                filer_name=filer_name,
                filing_date=filing_date,
                accession_number=mention.get("accession_number", ""),
                event_type=MAAcquisitionType.ACQUISITION,
                items_reported=["inbound_mention"],
                description=mention.get("file_description"),
                is_target=True,
            )
        )
    return events


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

    for result in results:
        entity_name = result.get("entity_name", "")
        if not entity_name:
            continue
        score = fuzz.token_set_ratio(company_name.upper(), entity_name.upper())
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
    high_threshold: int = 90,
    low_threshold: int = 75,
    fetch_financials: bool = True,
    fetch_filings: bool = True,
    search_inbound_ma: bool = True,
    search_form_d: bool = True,
) -> CompanyEdgarProfile:
    """Enrich a single company with SEC EDGAR data.

    Steps:
    1. Resolve company name → CIK via EFTS search (public company match)
    2. If public: fetch XBRL financials via companyfacts API
    3. If public: fetch recent filings and detect outbound M&A from 8-Ks
    4. Search for inbound M&A mentions (private company as target in public 8-Ks)
    5. Search for Form D filings (private capital raises under Reg D)

    Steps 4 and 5 work for *all* companies, including private ones that
    have no CIK as a public registrant. This is the primary way to get
    EDGAR signals for the ~85-95% of SBIR companies that are private.

    Args:
        client: EdgarAPIClient instance.
        company_name: SBIR company name.
        company_uei: Optional UEI for linking.
        high_threshold: Fuzzy score threshold for auto-accept (0-100).
        low_threshold: Fuzzy score threshold for inclusion (0-100).
        fetch_financials: Whether to pull XBRL financial data.
        fetch_filings: Whether to pull filing history and detect M&A.
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

    # Step 1: CIK resolution (public company match)
    match = await _resolve_cik(
        client, company_name,
        high_threshold=high_threshold,
        low_threshold=low_threshold,
    )

    if match:
        cik = match["cik"]
        profile.cik = cik
        profile.is_publicly_traded = True
        profile.match_confidence = match["match_score"]
        profile.match_method = match["match_method"]
        profile.ticker = match.get("ticker")

        # Step 2: XBRL financials (public companies only)
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

        # Step 3: Filing history and outbound M&A detection (public companies only)
        if fetch_filings:
            filings = await client.get_recent_filings(
                cik, filing_types=["8-K", "10-K", "10-Q"]
            )
            profile.total_filings = len(filings)
            if filings:
                dates = [f.get("filing_date") for f in filings if f.get("filing_date")]
                if dates:
                    try:
                        profile.latest_filing_date = date.fromisoformat(max(dates))
                    except ValueError:
                        pass

                ma_events = _detect_ma_events(cik, filings)
                profile.ma_event_count = len(ma_events)
                if ma_events:
                    profile.latest_ma_event_date = max(e.filing_date for e in ma_events)
    else:
        logger.debug(f"No public EDGAR match for '{company_name}', checking private signals")

    # Step 4: Inbound M&A detection (works for all companies, especially private)
    # Search for this company's name mentioned inside other companies' 8-K filings
    if search_inbound_ma:
        inbound_events = await _search_inbound_ma_mentions(client, company_name)
        profile.inbound_ma_mention_count = len(inbound_events)
        if inbound_events:
            profile.inbound_ma_acquirers = list({
                e.filer_name for e in inbound_events if e.filer_name
            })
            profile.latest_inbound_ma_date = max(e.filing_date for e in inbound_events)

    # Step 5: Form D search (private capital raises)
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
    high_threshold: int = 90,
    low_threshold: int = 75,
    fetch_financials: bool = True,
    fetch_filings: bool = True,
    search_inbound_ma: bool = True,
    search_form_d: bool = True,
) -> pd.DataFrame:
    """Enrich a DataFrame of SBIR companies with SEC EDGAR data.

    Iterates over unique companies, resolves each to EDGAR, and merges
    enrichment columns back into the DataFrame. Works for both public
    and private companies:
    - Public: CIK match → financials, filings, outbound M&A
    - All: EFTS text search → inbound M&A mentions in public 8-K filings
    - All: Form D search → private capital raises under Reg D

    Args:
        companies_df: DataFrame with company records.
        client: Optional pre-configured EdgarAPIClient.
        company_name_col: Column name for company names.
        company_uei_col: Column name for UEI identifiers.
        high_threshold: Fuzzy score for auto-accept (0-100).
        low_threshold: Fuzzy score for inclusion (0-100).
        fetch_financials: Whether to pull XBRL financials.
        fetch_filings: Whether to pull filing history.
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
                high_threshold=high_threshold,
                low_threshold=low_threshold,
                fetch_financials=fetch_financials,
                fetch_filings=fetch_filings,
                search_inbound_ma=search_inbound_ma,
                search_form_d=search_form_d,
            )
            profiles.append(profile.model_dump())
            if profile.is_publicly_traded:
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
            f"SEC EDGAR enrichment complete: {matched_count}/{total} public matches "
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
