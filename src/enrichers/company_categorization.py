"""Company categorization enricher module.

This module provides functionality to retrieve federal contract portfolios from
USAspending for SBIR companies to support categorization as Product/Service/Mixed firms.

IMPORTANT: SBIR/STTR awards are excluded from categorization to focus on non-R&D federal
contract revenue that reflects the company's product vs service business model. However,
SBIR/STTR awards can be retrieved separately for reporting and debugging purposes.

The module supports fallback to company name-based search when UEI/DUNS identifiers are
missing or invalid, ensuring broader coverage for companies with incomplete metadata.

Key Functions:
    - retrieve_company_contracts: Retrieve non-SBIR federal contracts for categorization (DuckDB)
    - retrieve_company_contracts_api: Retrieve non-SBIR federal contracts for categorization (API, with name fallback)
    - retrieve_sbir_awards: Retrieve SBIR/STTR awards for reporting (DuckDB)
    - retrieve_sbir_awards_api: Retrieve SBIR/STTR awards for reporting (API, with name fallback)
    - extract_sbir_phase: Extract SBIR phase from contract description
"""

import re
import time
from typing import Any

import httpx
import pandas as pd
from loguru import logger

from src.extractors.usaspending import DuckDBUSAspendingExtractor


def _is_valid_identifier(value: str | None) -> bool:
    """Check if an identifier (UEI/DUNS/CAGE) is valid.

    Args:
        value: Identifier value to validate

    Returns:
        True if valid, False if None, NaN, empty, or invalid
    """
    if value is None:
        return False
    if isinstance(value, float) and pd.isna(value):
        return False
    if isinstance(value, str):
        # Check for string "nan", "none", empty, or whitespace
        cleaned = value.strip().lower()
        if cleaned in ("", "nan", "none", "null"):
            return False
    return True


def retrieve_company_contracts(
    extractor: DuckDBUSAspendingExtractor,
    uei: str | None = None,
    duns: str | None = None,
    cage: str | None = None,
    table_name: str = "usaspending_awards",
) -> pd.DataFrame:
    """Retrieve all federal contracts for a company from USAspending (excluding SBIR/STTR).

    Queries the USAspending database for all contracts associated with a company
    using their identifiers (UEI, DUNS, CAGE). SBIR/STTR awards are excluded to focus
    on non-R&D federal contract revenue. Returns contracts with fields needed
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
    # IMPORTANT: Exclude SBIR/STTR awards to focus on other federal contract revenue
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
        AND (
            award_description IS NULL
            OR (
                UPPER(award_description) NOT LIKE '%SBIR%'
                AND UPPER(award_description) NOT LIKE '%STTR%'
                AND UPPER(award_description) NOT LIKE '%SMALL BUSINESS INNOVATION%'
                AND UPPER(award_description) NOT LIKE '%SMALL BUSINESS TECH%'
            )
        )
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
    company_name: str | None = None,
    base_url: str = "https://api.usaspending.gov/api/v2",
    timeout: int = 30,
    page_size: int = 100,
    max_psc_lookups: int = 100,
) -> pd.DataFrame:
    """Retrieve all federal contracts for a company from USAspending API (excluding SBIR/STTR).

    Uses the /search/spending_by_transaction/ endpoint which returns transaction-level
    data including PSC codes directly in the response. SBIR/STTR awards are excluded to
    focus on non-R&D federal contract revenue. This endpoint properly populates
    PSC codes without requiring additional API calls per award.

    Falls back to company name search if UEI/DUNS are missing or invalid.

    Args:
        uei: Company UEI (Unique Entity Identifier)
        duns: Company DUNS number
        company_name: Company name (used as fallback when UEI/DUNS are invalid)
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
    # Validate identifiers
    valid_uei = _is_valid_identifier(uei)
    valid_duns = _is_valid_identifier(duns)
    valid_name = _is_valid_identifier(company_name)

    # Check if we have at least one valid identifier
    if not any([valid_uei, valid_duns, valid_name]):
        logger.warning("No valid company identifiers provided (UEI, DUNS, or name), returning empty DataFrame")
        return pd.DataFrame()

    # Determine search strategy
    if valid_uei or valid_duns:
        logger.info(f"Retrieving contracts from USAspending API using identifiers (UEI={uei if valid_uei else 'N/A'}, DUNS={duns if valid_duns else 'N/A'})")
    else:
        logger.info(f"Falling back to name-based search for: {company_name}")

    # Build search filters using AdvancedFilterObject
    filters: dict[str, Any] = {
        "award_type_codes": ["A", "B", "C", "D"],  # Contract awards only
    }

    # Add recipient search - recipient_search_text searches across name, UEI, and DUNS
    recipient_search_terms = []
    if valid_uei:
        recipient_search_terms.append(uei)
    if valid_duns:
        recipient_search_terms.append(duns)
    if not recipient_search_terms and valid_name:
        # Fallback to company name if no valid identifiers
        recipient_search_terms.append(company_name)

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
                # Extract PSC field - API might return it as a dict or string
                psc_raw = transaction.get("PSC")

                # PSC might be a dict/object or a string - extract the code
                if isinstance(psc_raw, dict):
                    # If PSC is a dict, try to extract the code from common keys
                    psc_value = psc_raw.get("code") or psc_raw.get("psc_code") or psc_raw.get("psc")
                    if page == 1 and psc_raw:
                        logger.debug(f"PSC is a dict with keys: {list(psc_raw.keys())}, extracted: {psc_value}")
                elif isinstance(psc_raw, str):
                    psc_value = psc_raw
                else:
                    psc_value = None
                    if psc_raw is not None:
                        logger.debug(f"PSC has unexpected type: {type(psc_raw)}, value: {psc_raw}")

                # Log if PSC is empty to help debugging
                if not psc_value or (isinstance(psc_value, str) and not psc_value.strip()):
                    logger.debug(
                        f"PSC field empty for transaction. "
                        f"Award ID: {transaction.get('Award ID')}, "
                        f"PSC raw value: {psc_raw}"
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

        # Filter out SBIR/STTR awards to focus on other federal contract revenue
        initial_count = len(df)
        if initial_count > 0:
            df = df[
                df["description"].isna()
                | ~df["description"].str.upper().str.contains(
                    "SBIR|STTR|SMALL BUSINESS INNOVATION|SMALL BUSINESS TECH", regex=True, na=False
                )
            ]
            sbir_filtered = initial_count - len(df)
            if sbir_filtered > 0:
                logger.info(f"Filtered out {sbir_filtered} SBIR/STTR contracts ({sbir_filtered/initial_count*100:.1f}%)")

        if df.empty:
            logger.warning(f"No non-SBIR/STTR contracts found for company (UEI={uei}, DUNS={duns})")
            return pd.DataFrame()

        # Check PSC coverage
        psc_count = (~df["psc"].isna()).sum()
        psc_coverage = (psc_count / len(df) * 100) if len(df) > 0 else 0
        logger.info(f"PSC code coverage: {psc_count}/{len(df)} ({psc_coverage:.1f}%)")

        # Extract SBIR phase from description (should be minimal after filtering)
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


def retrieve_sbir_awards(
    extractor: DuckDBUSAspendingExtractor,
    uei: str | None = None,
    duns: str | None = None,
    cage: str | None = None,
    table_name: str = "usaspending_awards",
) -> pd.DataFrame:
    """Retrieve ONLY SBIR/STTR awards for a company from USAspending (for reporting).

    This function retrieves SBIR/STTR awards separately for debugging and reporting
    purposes. These awards are NOT used in the categorization logic.

    Args:
        extractor: DuckDB USAspending extractor instance
        uei: Company UEI (Unique Entity Identifier)
        duns: Company DUNS number
        cage: Company CAGE code
        table_name: USAspending table name (default: usaspending_awards)

    Returns:
        DataFrame with SBIR/STTR awards only
    """
    # Validate at least one identifier is provided
    if not any([uei, duns, cage]):
        logger.warning("No company identifiers provided, returning empty DataFrame")
        return pd.DataFrame()

    # Build WHERE clause based on available identifiers
    where_clauses = []
    if uei:
        where_clauses.append(f"recipient_uei = '{uei}'")
        where_clauses.append(f"awardee_or_recipient_uei = '{uei}'")
    if duns:
        where_clauses.append(f"recipient_duns = '{duns}'")
        where_clauses.append(f"awardee_or_recipient_uniqu = '{duns}'")
    if cage:
        where_clauses.append(f"cage_code = '{cage}'")
        where_clauses.append(f"vendor_doing_as_business_n = '{cage}'")

    where_clause = " OR ".join(where_clauses)

    # Query to retrieve ONLY SBIR/STTR awards
    query = f"""
    SELECT
        COALESCE(award_id_piid, piid, fain, uri, award_id) as award_id,
        award_description as description,
        CAST(federal_action_obligation as DOUBLE) as award_amount,
        action_date,
        fiscal_year
    FROM {table_name}
    WHERE ({where_clause})
        AND federal_action_obligation IS NOT NULL
        AND federal_action_obligation != 0
        AND (
            UPPER(award_description) LIKE '%SBIR%'
            OR UPPER(award_description) LIKE '%STTR%'
            OR UPPER(award_description) LIKE '%SMALL BUSINESS INNOVATION%'
            OR UPPER(award_description) LIKE '%SMALL BUSINESS TECH%'
        )
    """

    try:
        conn = extractor.connect()
        logger.debug(f"Querying USAspending for SBIR/STTR awards (UEI={uei}, DUNS={duns}, CAGE={cage})")

        result = conn.execute(query).fetchdf()

        if result.empty:
            logger.debug(f"No SBIR/STTR awards found in USAspending (UEI={uei}, DUNS={duns}, CAGE={cage})")
            return pd.DataFrame()

        # Drop any rows with invalid award_id
        result = result[result["award_id"].notna()]

        # Ensure numeric types
        result["award_amount"] = pd.to_numeric(result["award_amount"], errors="coerce")

        # Drop duplicates based on award_id
        result = result.drop_duplicates(subset=["award_id"])

        logger.debug(f"Retrieved {len(result)} SBIR/STTR awards (UEI={uei}, DUNS={duns}, CAGE={cage})")

        return result

    except Exception as e:
        logger.error(f"Failed to query SBIR/STTR awards: {e}")
        return pd.DataFrame()


def retrieve_sbir_awards_api(
    uei: str | None = None,
    duns: str | None = None,
    company_name: str | None = None,
    base_url: str = "https://api.usaspending.gov/api/v2",
    timeout: int = 30,
    page_size: int = 100,
) -> pd.DataFrame:
    """Retrieve ONLY SBIR/STTR awards for a company from USAspending API (for reporting).

    This function retrieves SBIR/STTR awards separately for debugging and reporting
    purposes. These awards are NOT used in the categorization logic.

    Falls back to company name search if UEI/DUNS are missing or invalid.

    Args:
        uei: Company UEI (Unique Entity Identifier)
        duns: Company DUNS number
        company_name: Company name (used as fallback when UEI/DUNS are invalid)
        base_url: USAspending API base URL
        timeout: Request timeout in seconds
        page_size: Number of results per page

    Returns:
        DataFrame with SBIR/STTR awards only
    """
    # Validate identifiers
    valid_uei = _is_valid_identifier(uei)
    valid_duns = _is_valid_identifier(duns)
    valid_name = _is_valid_identifier(company_name)

    if not any([valid_uei, valid_duns, valid_name]):
        logger.warning("No valid company identifiers provided (UEI, DUNS, or name), returning empty DataFrame")
        return pd.DataFrame()

    if valid_uei or valid_duns:
        logger.debug(f"Retrieving SBIR/STTR awards from USAspending API (UEI={uei if valid_uei else 'N/A'}, DUNS={duns if valid_duns else 'N/A'})")
    else:
        logger.debug(f"Retrieving SBIR/STTR awards from USAspending API using name: {company_name}")

    # Build search filters
    filters: dict[str, Any] = {
        "award_type_codes": ["A", "B", "C", "D"],
    }

    recipient_search_terms = []
    if valid_uei:
        recipient_search_terms.append(uei)
    if valid_duns:
        recipient_search_terms.append(duns)
    if not recipient_search_terms and valid_name:
        recipient_search_terms.append(company_name)

    if recipient_search_terms:
        filters["recipient_search_text"] = recipient_search_terms

    fields = [
        "Award ID",
        "Transaction Amount",
        "Transaction Description",
        "Action Date",
        "internal_id",
    ]

    all_transactions = []
    page = 1

    try:
        while True:
            payload = {
                "filters": filters,
                "fields": fields,
                "sort": "Transaction Amount",
                "order": "desc",
                "page": page,
                "limit": page_size,
            }

            url = f"{base_url}/search/spending_by_transaction/"

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
                logger.error(f"HTTP error fetching SBIR awards from API: {e}")
                if page == 1:
                    return pd.DataFrame()
                break

            results = data.get("results", [])
            if not results:
                break

            for transaction in results:
                description = transaction.get("Transaction Description", "")
                # Only include SBIR/STTR transactions
                if description and any(
                    keyword in description.upper()
                    for keyword in ["SBIR", "STTR", "SMALL BUSINESS INNOVATION", "SMALL BUSINESS TECH"]
                ):
                    all_transactions.append(
                        {
                            "award_id": transaction.get("Award ID") or transaction.get("internal_id"),
                            "description": description,
                            "award_amount": transaction.get("Transaction Amount", 0),
                            "action_date": transaction.get("Action Date"),
                        }
                    )

            page_metadata = data.get("page_metadata", {})
            has_next = page_metadata.get("hasNext", False)

            if not has_next:
                break

            page += 1

        if not all_transactions:
            logger.debug(f"No SBIR/STTR awards found via API (UEI={uei}, DUNS={duns})")
            return pd.DataFrame()

        df = pd.DataFrame(all_transactions)
        df["award_amount"] = pd.to_numeric(df["award_amount"], errors="coerce")
        df = df.drop_duplicates(subset=["award_id"])

        logger.debug(f"Retrieved {len(df)} SBIR/STTR awards via API")
        return df

    except Exception as e:
        logger.error(f"Failed to retrieve SBIR awards from API: {e}")
        return pd.DataFrame()


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
