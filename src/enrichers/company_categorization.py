"""Company categorization enricher module.

This module provides functionality to retrieve federal contract portfolios from
USAspending for SBIR companies to support categorization as Product/Service/Mixed firms.

Key Functions:
    - retrieve_company_contracts_api: Retrieve contracts via USAspending API (recommended)
    - retrieve_company_contracts_db: Retrieve contracts from DuckDB (legacy)
    - extract_sbir_phase: Extract SBIR phase from contract description
"""

import re
import time
from typing import Any

import httpx
import pandas as pd
from loguru import logger


def retrieve_company_contracts_api(
    uei: str | None = None,
    duns: str | None = None,
    limit: int = 1000,
    timeout: int = 30,
) -> pd.DataFrame:
    """Retrieve all federal contracts for a company from USAspending API.

    Uses the USAspending.gov public API to retrieve contract data. This is the
    recommended method as it doesn't require a local database.

    Note: API has a max limit of 100 results per request. This function automatically
    paginates to retrieve up to the specified limit.

    Args:
        uei: Company UEI (Unique Entity Identifier)
        duns: Company DUNS number (legacy identifier)
        limit: Maximum number of contracts to retrieve (default: 1000)
        timeout: Request timeout in seconds (default: 30)

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
        45
        >>> contracts['psc'].value_counts()
    """
    # Validate at least one identifier is provided
    if not any([uei, duns]):
        logger.warning("No company identifiers provided, returning empty DataFrame")
        return pd.DataFrame()

    logger.info(f"Retrieving contracts from USAspending API (UEI={uei}, DUNS={duns})")

    # Build API request
    api_url = "https://api.usaspending.gov/api/v2/search/spending_by_award/"

    # Build filters based on available identifiers
    filters = {
        "award_type_codes": ["A", "B", "C", "D"],  # Contract types
        # Use broad time period to capture all available contracts
        # USAspending.gov data goes back to ~2008
        "time_period": [
            {
                "start_date": "2008-10-01",  # Start of FY2009
                "end_date": "2025-09-30",    # End of FY2025
            }
        ],
    }

    if uei:
        filters["recipient_search_text"] = [uei]
    elif duns:
        filters["recipient_search_text"] = [duns]

    # API has max limit of 100 per request
    page_size = 100
    all_records = []
    page = 1
    total_retrieved = 0

    try:
        with httpx.Client(timeout=timeout) as client:
            while total_retrieved < limit:
                # Build request payload for this page
                payload = {
                    "filters": filters,
                    "fields": [
                        "Award ID",
                        "Recipient Name",
                        "Award Amount",
                        "Description",
                        "awarding_agency_name",
                        "Start Date",
                        "End Date",
                        "Product or Service Code",
                        "recipient_uei",
                        "recipient_duns",
                    ],
                    "limit": min(page_size, limit - total_retrieved),
                    "page": page,
                    "sort": "Award Amount",
                    "order": "desc",
                }

                # Make API request
                response = client.post(api_url, json=payload)
                response.raise_for_status()

                data = response.json()
                results = data.get("results", [])

                if not results:
                    # No more results
                    break

                # Convert results to records
                for idx, result in enumerate(results):
                    # Extract PSC code - handle nested structure
                    # USAspending often returns: product_or_service_code.code
                    psc_field = result.get("Product or Service Code", "")

                    if isinstance(psc_field, dict):
                        # Nested: {"code": "5820", "description": "..."}
                        psc = psc_field.get("code", "")
                        if idx == 0 and page == 1:
                            logger.debug(f"PSC returned as nested dict: {psc_field}")
                    elif isinstance(psc_field, str):
                        # Flat string
                        psc = psc_field
                        if idx == 0 and page == 1:
                            logger.debug(f"PSC returned as flat string: '{psc_field}'")
                    else:
                        # Try alternative field names
                        if idx == 0 and page == 1:
                            logger.warning(f"PSC field empty/unexpected type, trying alternatives. Available keys: {list(result.keys())}")
                        psc = result.get("product_or_service_code", "")
                        if isinstance(psc, dict):
                            psc = psc.get("code", "")

                    # Clean PSC code
                    psc = str(psc).strip() if psc else ""

                    # Debug: log if PSC is empty for first contract
                    if idx == 0 and page == 1 and not psc:
                        logger.error(f"CRITICAL: PSC is empty after parsing! Raw response keys: {list(result.keys())}")

                    # Parse contract type/pricing from description (best effort)
                    description = result.get("Description", "") or ""
                    contract_type, pricing = _infer_contract_type_from_description(description)

                    # Extract SBIR phase
                    sbir_phase = _extract_sbir_phase(description)

                    record = {
                        "award_id": result.get("Award ID", ""),
                        "psc": psc,
                        "contract_type": contract_type,
                        "pricing": pricing,
                        "description": description,
                        "award_amount": float(result.get("Award Amount", 0) or 0),
                        "recipient_uei": result.get("recipient_uei", uei),
                        "recipient_duns": result.get("recipient_duns", duns),
                        "sbir_phase": sbir_phase,
                    }
                    all_records.append(record)

                total_retrieved += len(results)
                page += 1

                # If we got fewer results than page_size, we've reached the end
                if len(results) < page_size:
                    break

                # Small delay between requests to be respectful to API
                if total_retrieved < limit:
                    time.sleep(0.1)

        if not all_records:
            logger.info(f"No contracts found in USAspending API for company (UEI={uei}, DUNS={duns})")
            return pd.DataFrame()

        logger.info(f"Retrieved {len(all_records)} contracts from USAspending API across {page - 1} page(s)")

        # Convert to DataFrame
        df = pd.DataFrame(all_records)

        # Drop duplicates based on award_id
        df = df.drop_duplicates(subset=["award_id"])

        logger.info(f"Processed {len(df)} unique contracts")
        return df

    except httpx.TimeoutException:
        logger.error(
            f"USAspending API request timed out after {timeout}s "
            f"for company (UEI={uei}, DUNS={duns})"
        )
        return pd.DataFrame()

    except httpx.HTTPStatusError as e:
        logger.error(
            f"USAspending API returned error {e.response.status_code} "
            f"for company (UEI={uei}, DUNS={duns}): {e.response.text}"
        )
        return pd.DataFrame()

    except Exception as e:
        logger.error(
            f"Failed to query USAspending API for company "
            f"(UEI={uei}, DUNS={duns}): {e}"
        )
        return pd.DataFrame()


def _infer_contract_type_from_description(description: str) -> tuple[str | None, str | None]:
    """Infer contract type and pricing from description text.

    Args:
        description: Contract description

    Returns:
        Tuple of (contract_type, pricing)
    """
    if not description:
        return (None, None)

    desc_upper = description.upper()

    # Detect contract types
    contract_type = None
    pricing = None

    if "CPFF" in desc_upper or "COST PLUS FIXED FEE" in desc_upper:
        contract_type = "CPFF"
        pricing = "CPFF"
    elif "FFP" in desc_upper or "FIRM FIXED PRICE" in desc_upper:
        contract_type = "FFP"
        pricing = "FFP"
    elif "T&M" in desc_upper or "TIME AND MATERIAL" in desc_upper:
        contract_type = "T&M"
        pricing = "T&M"
    elif "COST TYPE" in desc_upper or "COST-TYPE" in desc_upper:
        contract_type = "Cost-Type"
        pricing = "Cost"

    return (contract_type, pricing)


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


def retrieve_company_contracts(
    uei: str | None = None,
    duns: str | None = None,
    use_api: bool = True,
    **kwargs: Any,
) -> pd.DataFrame:
    """Retrieve all federal contracts for a company.

    Convenience wrapper that uses API by default but can fall back to DuckDB.

    Args:
        uei: Company UEI (Unique Entity Identifier)
        duns: Company DUNS number
        use_api: Use USAspending API (default: True). If False, requires DuckDB extractor
        **kwargs: Additional arguments passed to underlying retrieval function

    Returns:
        DataFrame with contract data

    Examples:
        >>> # Use API (recommended)
        >>> contracts = retrieve_company_contracts(uei="ABC123DEF456")

        >>> # Use DuckDB (requires extractor in kwargs)
        >>> from src.extractors.usaspending import DuckDBUSAspendingExtractor
        >>> extractor = DuckDBUSAspendingExtractor("data/sbir.duckdb")
        >>> contracts = retrieve_company_contracts(
        ...     uei="ABC123", use_api=False, extractor=extractor
        ... )
    """
    if use_api:
        return retrieve_company_contracts_api(
            uei=uei,
            duns=duns,
            limit=kwargs.get("limit", 1000),
            timeout=kwargs.get("timeout", 30),
        )
    else:
        # Legacy DuckDB method
        extractor = kwargs.get("extractor")
        if not extractor:
            raise ValueError("extractor required when use_api=False")

        from src.extractors.usaspending import DuckDBUSAspendingExtractor

        return retrieve_company_contracts_db(
            extractor=extractor,
            uei=uei,
            duns=duns,
            cage=kwargs.get("cage"),
            table_name=kwargs.get("table_name", "usaspending_awards"),
        )


def retrieve_company_contracts_db(
    extractor: Any,
    uei: str | None = None,
    duns: str | None = None,
    cage: str | None = None,
    table_name: str = "usaspending_awards",
) -> pd.DataFrame:
    """Retrieve all federal contracts for a company from DuckDB (legacy method).

    Queries the USAspending database for all contracts associated with a company
    using their identifiers (UEI, DUNS, CAGE). Returns contracts with fields needed
    for company categorization.

    Note: Requires USAspending database to be loaded in DuckDB. Consider using
    retrieve_company_contracts_api() instead.

    Args:
        extractor: DuckDB USAspending extractor instance
        uei: Company UEI (Unique Entity Identifier)
        duns: Company DUNS number
        cage: Company CAGE code
        table_name: USAspending table name (default: usaspending_awards)

    Returns:
        DataFrame with contract data

    Examples:
        >>> extractor = DuckDBUSAspendingExtractor(":memory:")
        >>> contracts = retrieve_company_contracts_db(extractor, uei="ABC123DEF456")
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
        logger.debug(f"Querying USAspending DB for company contracts (UEI={uei}, DUNS={duns}, CAGE={cage})")

        result = conn.execute(query).fetchdf()

        if result.empty:
            logger.info(
                f"No contracts found in USAspending DB for company "
                f"(UEI={uei}, DUNS={duns}, CAGE={cage})"
            )
            return pd.DataFrame()

        # Clean up and standardize the results
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
            f"Failed to query USAspending DB for company "
            f"(UEI={uei}, DUNS={duns}, CAGE={cage}): {e}"
        )
        return pd.DataFrame()


def batch_retrieve_company_contracts(
    companies: pd.DataFrame,
    uei_col: str = "company_uei",
    duns_col: str = "company_duns",
    use_api: bool = True,
    batch_size: int = 100,
    rate_limit_delay: float = 0.1,
) -> dict[str, pd.DataFrame]:
    """Retrieve contracts for multiple companies in batches.

    Args:
        companies: DataFrame with company identifiers
        uei_col: Column name for UEI
        duns_col: Column name for DUNS
        use_api: Use USAspending API (default: True)
        batch_size: Number of companies to process per batch
        rate_limit_delay: Delay between API requests in seconds (default: 0.1)

    Returns:
        Dictionary mapping company UEI to DataFrame of contracts

    Examples:
        >>> companies = pd.DataFrame({
        ...     "company_uei": ["ABC123", "DEF456"],
        ...     "company_duns": ["123456789", "987654321"]
        ... })
        >>> results = batch_retrieve_company_contracts(companies)
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

            # Use UEI as primary key for results
            key = uei or duns
            if not key:
                logger.warning("Company has no identifiers, skipping")
                continue

            contracts = retrieve_company_contracts(uei=uei, duns=duns, use_api=use_api)
            results[key] = contracts

            # Rate limiting for API requests
            if use_api and rate_limit_delay > 0:
                time.sleep(rate_limit_delay)

    logger.info(f"Retrieved contracts for {len(results)} companies")
    return results
