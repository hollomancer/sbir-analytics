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
    EdgarMAEvent,
    MAAcquisitionType,
)
from .client import EdgarAPIClient

# 8-K items that indicate M&A activity
_MA_8K_ITEMS = {"1.01", "2.01"}

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
        Tuple of (value, filing_date) or (None, None) if not found.
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
            filing_date = date.fromisoformat(latest["end"])
        except (ValueError, KeyError):
            filing_date = None
        return float(latest["val"]), filing_date
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

    # Use the most recent date among all extracted values
    dates = [d for d in [rev_date, ni_date, ta_date, tl_date, rd_date, oi_date, cash_date] if d]
    latest_date = max(dates) if dates else None

    return EdgarFinancials(
        cik=cik,
        fiscal_year=latest_date.year if latest_date else 0,
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
) -> CompanyEdgarProfile:
    """Enrich a single company with SEC EDGAR data.

    Steps:
    1. Resolve company name → CIK via EFTS search
    2. Fetch XBRL financials via companyfacts API
    3. Fetch recent filings and detect M&A events from 8-Ks

    Args:
        client: EdgarAPIClient instance.
        company_name: SBIR company name.
        company_uei: Optional UEI for linking.
        high_threshold: Fuzzy score threshold for auto-accept (0-100).
        low_threshold: Fuzzy score threshold for inclusion (0-100).
        fetch_financials: Whether to pull XBRL financial data.
        fetch_filings: Whether to pull filing history and detect M&A.

    Returns:
        CompanyEdgarProfile with whatever data could be resolved.
    """
    profile = CompanyEdgarProfile(
        company_name=company_name,
        company_uei=company_uei,
        enriched_at=datetime.now(),
    )

    # Step 1: CIK resolution
    match = await _resolve_cik(
        client, company_name,
        high_threshold=high_threshold,
        low_threshold=low_threshold,
    )
    if not match:
        logger.debug(f"No EDGAR match for '{company_name}'")
        return profile

    cik = match["cik"]
    profile.cik = cik
    profile.is_publicly_traded = True
    profile.match_confidence = match["match_score"]
    profile.match_method = match["match_method"]
    profile.ticker = match.get("ticker")

    # Step 2: XBRL financials
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

    # Step 3: Filing history and M&A detection
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
) -> pd.DataFrame:
    """Enrich a DataFrame of SBIR companies with SEC EDGAR data.

    Iterates over unique companies, resolves each to EDGAR, and merges
    enrichment columns back into the DataFrame.

    Args:
        companies_df: DataFrame with company records.
        client: Optional pre-configured EdgarAPIClient.
        company_name_col: Column name for company names.
        company_uei_col: Column name for UEI identifiers.
        high_threshold: Fuzzy score for auto-accept (0-100).
        low_threshold: Fuzzy score for inclusion (0-100).
        fetch_financials: Whether to pull XBRL financials.
        fetch_filings: Whether to pull filing history.

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
        if company_uei_col in companies_df.columns:
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
            )
            profiles.append(profile.model_dump())
            if profile.is_publicly_traded:
                matched_count += 1

            if (len(profiles)) % 50 == 0:
                logger.info(
                    f"SEC EDGAR enrichment progress: {len(profiles)}/{total} "
                    f"({matched_count} matched)"
                )

        logger.info(
            f"SEC EDGAR enrichment complete: {matched_count}/{total} companies matched "
            f"({matched_count / total * 100:.1f}%)"
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
