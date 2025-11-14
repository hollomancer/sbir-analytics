"""Company categorization enricher module.

This module provides functionality to retrieve federal contract portfolios from
USAspending for SBIR companies to support categorization as Product/Service/Mixed firms.

Key Functions:
    - retrieve_company_contracts: Retrieve all federal contracts for a company
    - extract_sbir_phase: Extract SBIR phase from contract description
"""

import re

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
