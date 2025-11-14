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
) -> pd.DataFrame:
    """Retrieve all federal contracts for a company from USAspending API.

    Uses a hybrid approach for maximum accuracy:
    1. Primary: Queries /search/spending_by_transaction/ endpoint for bulk retrieval
    2. Fallback: For contracts with missing PSC codes, queries /awards/{award_id}/
       endpoint individually (limited to 20 contracts to manage API load)

    The transaction endpoint is used first because the award search endpoint doesn't
    populate PSC codes. For any remaining contracts with missing PSC codes, individual
    award lookups are performed to fill in the gaps.

    Note: May return multiple transactions per award. Duplicates are removed based on
    award_id before returning.

    Args:
        uei: Company UEI (Unique Entity Identifier)
        duns: Company DUNS number
        base_url: USAspending API base URL
        timeout: Request timeout in seconds
        page_size: Number of results per page

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

    logger.info(f"Retrieving contracts from USAspending API (UEI={uei}, DUNS={duns})")

    # Build search filters for the API
    filters: dict[str, Any] = {
        "award_type_codes": ["A", "B", "C", "D"],  # Contract awards
    }

    # Add recipient search
    recipient_ids = []
    if uei:
        recipient_ids.append(uei)
    if duns:
        recipient_ids.append(duns)

    if recipient_ids:
        filters["recipient_search_text"] = recipient_ids

    # Fields to retrieve from API
    fields = [
        "Award ID",
        "Recipient Name",
        "Award Amount",
        "Description",
        "Start Date",
        "End Date",
        "Product or Service Code",
        "Contract Award Type",
        "awarding_agency_name",
        "recipient_uei",
        "recipient_duns",
    ]

    all_contracts = []
    page = 1

    try:
        while True:
            # Build POST request payload
            payload = {
                "filters": filters,
                "fields": fields,
                "page": page,
                "limit": page_size,
                "sort": "Award Amount",
                "order": "desc",
            }

            # Make API request
            # NOTE: Using spending_by_transaction instead of spending_by_award because
            # the award endpoint doesn't populate PSC codes in the response
            url = f"{base_url}/search/spending_by_transaction/"
            logger.debug(f"Fetching page {page} from USAspending API (transactions)")

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
                logger.error(f"HTTP error fetching contracts from USAspending API: {e}")
                if page == 1:
                    return pd.DataFrame()
                break
            except Exception as e:
                logger.error(f"Error fetching contracts from USAspending API: {e}")
                if page == 1:
                    return pd.DataFrame()
                break

            results = data.get("results", [])
            if not results:
                logger.debug(f"No more results found (page {page})")
                break

            # Process each contract
            for contract in results:
                # Extract PSC field - the API returns it as "Product or Service Code"
                psc_value = contract.get("Product or Service Code")

                # Log if PSC is empty to help debugging
                if not psc_value or (isinstance(psc_value, str) and not psc_value.strip()):
                    logger.warning(
                        f"PSC field empty/unexpected type, trying alternatives. "
                        f"Available keys: {list(contract.keys())}"
                    )
                    # Try alternative field names
                    psc_value = (
                        contract.get("product_or_service_code") or
                        contract.get("psc") or
                        contract.get("Product or Service Code") or
                        contract.get("PSC")
                    )

                    if not psc_value:
                        logger.error(
                            f"CRITICAL: PSC is empty after parsing! "
                            f"Raw response keys: {list(contract.keys())}"
                        )

                processed_contract = {
                    "award_id": contract.get("Award ID") or contract.get("internal_id"),
                    "psc": psc_value,
                    "contract_type": contract.get("Contract Award Type"),
                    "pricing": contract.get("Contract Award Type"),
                    "description": contract.get("Description"),
                    "award_amount": contract.get("Award Amount", 0),
                    "recipient_uei": contract.get("recipient_uei") or uei,
                    "recipient_duns": contract.get("recipient_duns") or duns,
                    "start_date": contract.get("Start Date"),
                    "end_date": contract.get("End Date"),
                    "awarding_agency": contract.get("awarding_agency_name"),
                }

                # Generate internal ID if award_id is missing
                if not processed_contract["award_id"]:
                    processed_contract["award_id"] = contract.get("generated_internal_id", f"UNKNOWN_{len(all_contracts)}")

                all_contracts.append(processed_contract)

            # Check if there are more pages
            page_metadata = data.get("page_metadata", {})
            has_next = page_metadata.get("hasNext", False)
            total = page_metadata.get("total", 0)

            logger.debug(f"Retrieved {len(results)} contracts (page {page}), total available: {total}")

            if not has_next:
                logger.debug("No more pages available")
                break

            page += 1

        logger.info(f"Retrieved {len(all_contracts)} contracts from USAspending API across {page} page(s)")

        if not all_contracts:
            logger.warning(f"No contracts found for company (UEI={uei}, DUNS={duns})")
            return pd.DataFrame()

        # Convert to DataFrame
        df = pd.DataFrame(all_contracts)

        # Fallback: Fetch PSC codes from individual award endpoint for contracts with missing PSC
        missing_psc_mask = df["psc"].isna() | (df["psc"] == "")
        missing_psc_count = missing_psc_mask.sum()

        if missing_psc_count > 0:
            logger.info(
                f"Attempting to retrieve PSC codes for {missing_psc_count} contracts "
                f"with missing PSC using individual award endpoint"
            )

            # Limit fallback calls to avoid excessive API requests (max 20)
            max_fallback_calls = min(20, missing_psc_count)
            missing_psc_df = df[missing_psc_mask].head(max_fallback_calls)

            for idx, row in missing_psc_df.iterrows():
                award_id = row["award_id"]
                if not award_id or award_id.startswith("UNKNOWN_"):
                    continue

                # Add small delay to respect rate limits (120 per minute = ~0.5s per request)
                time.sleep(0.5)

                award_details = _fetch_award_details(award_id, base_url, timeout)
                if award_details and award_details.get("psc"):
                    df.at[idx, "psc"] = award_details["psc"]

            retrieved_psc_count = (~(df["psc"].isna() | (df["psc"] == ""))).sum() - (
                len(df) - missing_psc_count
            )
            if retrieved_psc_count > 0:
                logger.info(
                    f"Successfully retrieved {retrieved_psc_count} PSC codes "
                    f"from individual award endpoint"
                )
            else:
                logger.warning("No PSC codes could be retrieved from individual award endpoint")

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
        logger.error(f"Failed to retrieve contracts from USAspending API: {e}")
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

        # Extract PSC from the detailed award response
        # The individual award endpoint has different structure
        psc = None
        if isinstance(award_data, dict):
            # Try various paths where PSC might be located
            psc = (
                award_data.get("product_or_service_code")
                or award_data.get("psc")
                or award_data.get("latest_transaction", {}).get("product_or_service_code")
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
