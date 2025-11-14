"""Company categorization enricher module.

This module provides functionality to retrieve federal contract portfolios from
USAspending for SBIR companies to support categorization as Product/Service/Mixed firms.

Key Functions:
    - retrieve_company_contracts: Retrieve all federal contracts for a company (DuckDB)
    - retrieve_company_contracts_api: Retrieve all federal contracts for a company (API)
    - extract_sbir_phase: Extract SBIR phase from contract description
"""

import re
import time
from typing import Any

import httpx
import pandas as pd
from loguru import logger

from src.extractors.usaspending import DuckDBUSAspendingExtractor


def retrieve_company_contracts(
    extractor: DuckDBUSAspendingExtractor,
    uei: str | None = None,
    duns: str | None = None,
    cage: str | None = None,
    table_name: str = "usaspending_awards",
) -> pd.DataFrame:
    """Retrieve all federal contracts for a company from USAspending.

    Queries the USAspending database for all contracts associated with a company
    using their identifiers (UEI, DUNS, CAGE). Returns contracts with fields needed
    for company categorization.

    Args:
        extractor: DuckDB USAspending extractor instance
        uei: Company UEI (Unique Entity Identifier)
        duns: Company DUNS number
        cage: Company CAGE code
        table_name: USAspending table name (default: usaspending_awards)

    Returns:
        DataFrame with columns:
            - award_id: Contract/award identifier
            - psc: Product Service Code
            - contract_type: Type of contract pricing
            - pricing: Type of contract pricing
            - description: Award description
            - award_amount: Federal action obligation
            - recipient_uei: Recipient UEI
            - recipient_duns: Recipient DUNS
            - cage_code: CAGE code
            - sbir_phase: SBIR phase if detected (I, II, III)

    Examples:
        >>> extractor = DuckDBUSAspendingExtractor(":memory:")
        >>> contracts = retrieve_company_contracts(extractor, uei="ABC123DEF456")
        >>> len(contracts)
        15
    """
    # Validate at least one identifier is provided
    if not any([uei, duns, cage]):
        logger.warning("No company identifiers provided, returning empty DataFrame")
        return pd.DataFrame()

    # Build WHERE clause based on available identifiers
    where_clauses = []
    if uei:
        # USAspending may have various UEI column names
        where_clauses.append(f"recipient_uei = '{uei}'")
        where_clauses.append(f"awardee_or_recipient_uei = '{uei}'")
    if duns:
        where_clauses.append(f"recipient_duns = '{duns}'")
        where_clauses.append(f"awardee_or_recipient_uniqu = '{duns}'")
    if cage:
        where_clauses.append(f"cage_code = '{cage}'")
        where_clauses.append(f"vendor_doing_as_business_n = '{cage}'")

    # Combine clauses with OR (any identifier match)
    where_clause = " OR ".join(where_clauses)

    # Build query to extract relevant fields
    # Note: USAspending field names vary - using common variations
    query = f"""
    SELECT
        COALESCE(award_id_piid, piid, fain, uri, award_id) as award_id,
        product_or_service_code as psc,
        type_of_contract_pricing as contract_type,
        type_of_contract_pricing as pricing,
        award_description as description,
        CAST(federal_action_obligation as DOUBLE) as award_amount,
        recipient_uei,
        awardee_or_recipient_uei,
        COALESCE(recipient_duns, awardee_or_recipient_uniqu) as recipient_duns,
        cage_code,
        action_date,
        fiscal_year
    FROM {table_name}
    WHERE ({where_clause})
        AND federal_action_obligation IS NOT NULL
        AND federal_action_obligation != 0
    """

    try:
        conn = extractor.connect()
        logger.debug(f"Querying USAspending for company contracts (UEI={uei}, DUNS={duns}, CAGE={cage})")

        result = conn.execute(query).fetchdf()

        if result.empty:
            logger.info(
                f"No contracts found in USAspending for company "
                f"(UEI={uei}, DUNS={duns}, CAGE={cage})"
            )
            return pd.DataFrame()

        # Clean up and standardize the results
        # Combine recipient_uei and awardee_or_recipient_uei into single column
        if "recipient_uei" in result.columns and "awardee_or_recipient_uei" in result.columns:
            result["recipient_uei"] = result["recipient_uei"].fillna(
                result["awardee_or_recipient_uei"]
            )
            result = result.drop(columns=["awardee_or_recipient_uei"])

        # Extract SBIR phase from description
        result["sbir_phase"] = result["description"].apply(_extract_sbir_phase)

        # Drop any rows with invalid award_id
        result = result[result["award_id"].notna()]

        # Ensure numeric types
        result["award_amount"] = pd.to_numeric(result["award_amount"], errors="coerce")

        # Drop duplicates based on award_id
        result = result.drop_duplicates(subset=["award_id"])

        logger.info(
            f"Retrieved {len(result)} contracts for company "
            f"(UEI={uei}, DUNS={duns}, CAGE={cage})"
        )

        return result

    except Exception as e:
        logger.error(
            f"Failed to query USAspending for company "
            f"(UEI={uei}, DUNS={duns}, CAGE={cage}): {e}"
        )
        # Return empty DataFrame on error rather than raising
        return pd.DataFrame()


def retrieve_company_contracts_api(
    uei: str | None = None,
    duns: str | None = None,
    base_url: str = "https://api.usaspending.gov/api/v2",
    timeout: int = 30,
    page_size: int = 100,
    max_psc_lookups: int = 100,
) -> pd.DataFrame:
    """Retrieve all federal contracts for a company from USAspending API.

    Uses the /search/spending_by_transaction/ endpoint which returns transaction-level
    data including PSC codes directly in the response. This endpoint properly populates
    PSC codes without requiring additional API calls per award.

    Args:
        uei: Company UEI (Unique Entity Identifier)
        duns: Company DUNS number
        base_url: USAspending API base URL
        timeout: Request timeout in seconds
        page_size: Number of results per page
        max_psc_lookups: Unused (kept for API compatibility)

    Returns:
        DataFrame with columns:
            - award_id: Contract/award identifier
            - psc: Product Service Code
            - contract_type: Type of contract pricing
            - pricing: Type of contract pricing
            - description: Transaction description
            - award_amount: Transaction amount
            - recipient_uei: Recipient UEI
            - recipient_duns: Recipient DUNS
            - sbir_phase: SBIR phase if detected (I, II, III)

    Examples:
        >>> contracts = retrieve_company_contracts_api(uei="ABC123DEF456")
        >>> len(contracts)
        15
    """
    # Validate at least one identifier is provided
    if not any([uei, duns]):
        logger.warning("No company identifiers provided (UEI or DUNS), returning empty DataFrame")
        return pd.DataFrame()

    logger.info(f"Retrieving contracts from USAspending API using transaction endpoint (UEI={uei}, DUNS={duns})")

    # Build search filters using AdvancedFilterObject
    filters: dict[str, Any] = {
        "award_type_codes": ["A", "B", "C", "D"],  # Contract awards only
    }

    # Add recipient search - recipient_search_text searches across name, UEI, and DUNS
    recipient_search_terms = []
    if uei:
        recipient_search_terms.append(uei)
    if duns:
        recipient_search_terms.append(duns)

    if recipient_search_terms:
        filters["recipient_search_text"] = recipient_search_terms

    # Fields to retrieve from transaction endpoint
    # Using the exact field names from the API documentation
    fields = [
        "Award ID",              # Award identifier
        "Recipient Name",        # Company name
        "Transaction Amount",    # Amount for this transaction
        "Transaction Description",  # Description
        "Action Date",           # Transaction date
        "PSC",                   # Product/Service Code (the key field we need!)
        "Recipient UEI",         # Recipient UEI
        "Award Type",            # Contract type
        "internal_id",           # Internal award identifier
    ]

    all_transactions = []
    page = 1

    try:
        logger.info("Fetching transactions from spending_by_transaction endpoint")
        while True:
            # Build payload with ALL required fields per API contract
            payload = {
                "filters": filters,
                "fields": fields,
                "sort": "Transaction Amount",  # Required field per API docs
                "order": "desc",
                "page": page,
                "limit": page_size,
            }

            url = f"{base_url}/search/spending_by_transaction/"
            logger.debug(f"Fetching page {page} from spending_by_transaction endpoint")

            try:
                response = httpx.post(
                    url,
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "User-Agent": "SBIR-ETL/1.0",
                    },
                    timeout=timeout,
                )
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPError as e:
                logger.error(f"HTTP error fetching transactions from USAspending API: {e}")
                if page == 1:
                    return pd.DataFrame()
                break
            except Exception as e:
                logger.error(f"Error fetching transactions from USAspending API: {e}")
                if page == 1:
                    return pd.DataFrame()
                break

            results = data.get("results", [])
            if not results:
                logger.debug(f"No more results found (page {page})")
                break

            # Debug: Log structure of first result to understand response format
            if page == 1 and results:
                logger.debug(f"First transaction result keys: {list(results[0].keys())}")
                # Check if PSC is present in the response
                psc_value = results[0].get("PSC")
                logger.debug(f"First transaction PSC value: {psc_value}")

            # Process each transaction
            for transaction in results:
                # Extract PSC field - should be directly in the response as "PSC"
                psc_value = transaction.get("PSC")

                # Log if PSC is empty to help debugging
                if not psc_value or (isinstance(psc_value, str) and not psc_value.strip()):
                    logger.debug(
                        f"PSC field empty for transaction. "
                        f"Award ID: {transaction.get('Award ID')}, "
                        f"Available keys: {list(transaction.keys())}"
                    )

                processed_transaction = {
                    "award_id": transaction.get("Award ID") or transaction.get("internal_id"),
                    "psc": psc_value,
                    "contract_type": transaction.get("Award Type"),
                    "pricing": transaction.get("Award Type"),
                    "description": transaction.get("Transaction Description"),
                    "award_amount": transaction.get("Transaction Amount", 0),
                    "recipient_uei": transaction.get("Recipient UEI") or uei,
                    "recipient_duns": duns,
                    "action_date": transaction.get("Action Date"),
                    "award_type": transaction.get("Award Type"),
                }

                # Generate fallback ID if award_id is missing
                if not processed_transaction["award_id"]:
                    processed_transaction["award_id"] = f"UNKNOWN_{len(all_transactions)}"
                    logger.debug(
                        f"No award ID found in transaction response. Available keys: {list(transaction.keys())}"
                    )

                all_transactions.append(processed_transaction)

            # Check if there are more pages
            page_metadata = data.get("page_metadata", {})
            has_next = page_metadata.get("hasNext", False)
            total = page_metadata.get("total", 0)

            logger.debug(f"Retrieved {len(results)} transactions (page {page}), total available: {total}")

            if not has_next:
                logger.debug("No more pages available")
                break

            page += 1

        logger.info(f"Retrieved {len(all_transactions)} transactions from spending_by_transaction endpoint")

        if not all_transactions:
            logger.warning(f"No transactions found for company (UEI={uei}, DUNS={duns})")
            return pd.DataFrame()

        # Convert to DataFrame
        df = pd.DataFrame(all_transactions)

        # Check PSC coverage
        psc_count = (~df["psc"].isna()).sum()
        psc_coverage = (psc_count / len(df) * 100) if len(df) > 0 else 0
        logger.info(f"PSC code coverage: {psc_count}/{len(df)} ({psc_coverage:.1f}%)")

        # Extract SBIR phase from description
        df["sbir_phase"] = df["description"].apply(_extract_sbir_phase)

        # Ensure numeric types for award_amount
        df["award_amount"] = pd.to_numeric(df["award_amount"], errors="coerce")

        # Drop duplicates based on award_id
        initial_count = len(df)
        df = df.drop_duplicates(subset=["award_id"])
        if len(df) < initial_count:
            logger.debug(f"Removed {initial_count - len(df)} duplicate contracts")

        logger.info(f"Processed {len(df)} unique contracts")

        return df

    except Exception as e:
        import traceback
        logger.error(f"Failed to retrieve contracts from USAspending API: {e}")
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
        return pd.DataFrame()


def _fetch_award_details(award_id: str, base_url: str, timeout: int) -> dict[str, Any] | None:
    """Fetch detailed award information including PSC code.

    This is used as a fallback when the transaction endpoint doesn't return PSC codes.

    Args:
        award_id: Award identifier (PIID or generated_internal_id)
        base_url: USAspending API base URL
        timeout: Request timeout in seconds

    Returns:
        Award details dict with PSC code, or None if fetch fails
    """
    try:
        url = f"{base_url}/awards/{award_id}/"
        response = httpx.get(url, timeout=timeout)
        response.raise_for_status()
        award_data = response.json()

        # Debug: Log the structure of the response to understand where PSC is located
        if isinstance(award_data, dict):
            # Log top-level keys to help debug structure
            logger.debug(f"Award {award_id} response keys: {list(award_data.keys())}")

        # Extract PSC from the detailed award response
        # Per USAspending API docs, PSC is in latest_transaction_contract_data for contract awards
        psc = None
        if isinstance(award_data, dict):
            # Primary location: latest_transaction_contract_data (for contracts)
            latest_contract = award_data.get("latest_transaction_contract_data", {})
            if isinstance(latest_contract, dict):
                psc = latest_contract.get("product_or_service_code")

            # Fallback locations if not in primary location
            if not psc:
                psc = (
                    award_data.get("product_or_service_code")
                    or award_data.get("psc")
                    or award_data.get("latest_transaction", {}).get("product_or_service_code")
                    or award_data.get("contract_data", {}).get("product_or_service_code")
                    or award_data.get("base_transaction", {}).get("product_or_service_code")
                )

            # If still not found, log warning with available keys
            if not psc:
                logger.warning(
                    f"PSC not found for award {award_id}. "
                    f"Response has keys: {list(award_data.keys())[:10]}"
                )

        if psc:
            logger.debug(f"Retrieved PSC '{psc}' for award {award_id} from individual award endpoint")
            return {"psc": psc}

        return None

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            logger.debug(f"Award {award_id} not found in individual award endpoint (404)")
        else:
            logger.warning(f"HTTP error fetching award details for {award_id}: {e}")
        return None
    except Exception as e:
        logger.warning(f"Error fetching award details for {award_id}: {e}")
        return None


def _extract_sbir_phase(description: str | None) -> str | None:
    """Extract SBIR phase from award description.

    Looks for patterns like "Phase I", "Phase II", "Phase III", "SBIR Phase 1", etc.

    Args:
        description: Award description text

    Returns:
        SBIR phase (I, II, III) or None if not detected

    Examples:
        >>> _extract_sbir_phase("SBIR Phase I Research")
        'I'
        >>> _extract_sbir_phase("Phase II Development")
        'II'
        >>> _extract_sbir_phase("Regular contract")
        None
    """
    if not description or not isinstance(description, str):
        return None

    # Normalize to uppercase for matching
    desc_upper = description.upper()

    # Pattern 1: "PHASE I", "PHASE II", "PHASE III"
    phase_patterns = [
        (r"\bPHASE\s*III\b", "III"),
        (r"\bPHASE\s*II\b", "II"),
        (r"\bPHASE\s*I\b", "I"),
        (r"\bPHASE\s*3\b", "III"),
        (r"\bPHASE\s*2\b", "II"),
        (r"\bPHASE\s*1\b", "I"),
    ]

    # Check SBIR/STTR patterns first
    if "SBIR" in desc_upper or "STTR" in desc_upper:
        for pattern, phase in phase_patterns:
            if re.search(pattern, desc_upper):
                return phase

    # Check general phase patterns
    for pattern, phase in phase_patterns:
        if re.search(pattern, desc_upper):
            # Only return if it looks like SBIR context
            # (avoid false positives from general "phase" mentions)
            if any(
                keyword in desc_upper
                for keyword in ["SBIR", "STTR", "SMALL BUSINESS", "INNOVATION", "RESEARCH"]
            ):
                return phase

    return None


def batch_retrieve_company_contracts(
    extractor: DuckDBUSAspendingExtractor,
    companies: pd.DataFrame,
    uei_col: str = "company_uei",
    duns_col: str = "company_duns",
    cage_col: str = "company_cage",
    batch_size: int = 100,
) -> dict[str, pd.DataFrame]:
    """Retrieve contracts for multiple companies in batches.

    Args:
        extractor: DuckDB USAspending extractor instance
        companies: DataFrame with company identifiers
        uei_col: Column name for UEI
        duns_col: Column name for DUNS
        cage_col: Column name for CAGE
        batch_size: Number of companies to process per batch

    Returns:
        Dictionary mapping company UEI to DataFrame of contracts

    Examples:
        >>> companies = pd.DataFrame({
        ...     "company_uei": ["ABC123", "DEF456"],
        ...     "company_duns": ["123456789", "987654321"]
        ... })
        >>> extractor = DuckDBUSAspendingExtractor(":memory:")
        >>> results = batch_retrieve_company_contracts(extractor, companies)
        >>> len(results)
        2
    """
    results = {}

    # Process companies in batches
    total_companies = len(companies)
    for i in range(0, total_companies, batch_size):
        batch = companies.iloc[i : i + batch_size]
        logger.info(
            f"Processing batch {i // batch_size + 1} "
            f"({i + 1}-{min(i + batch_size, total_companies)} of {total_companies})"
        )

        for _, company in batch.iterrows():
            uei = company.get(uei_col) if uei_col in company else None
            duns = company.get(duns_col) if duns_col in company else None
            cage = company.get(cage_col) if cage_col in company else None

            # Use UEI as primary key for results
            key = uei or duns or cage
            if not key:
                logger.warning("Company has no identifiers, skipping")
                continue

            contracts = retrieve_company_contracts(
                extractor, uei=uei, duns=duns, cage=cage
            )
            results[key] = contracts

    logger.info(f"Retrieved contracts for {len(results)} companies")
    return results
