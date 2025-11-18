"""Company categorization enricher module.

This module provides functionality to retrieve federal contract portfolios from
USAspending for SBIR companies to support categorization as Product/Service/Mixed firms.

IMPORTANT: SBIR/STTR awards are excluded from categorization to focus on non-R&D federal
contract revenue that reflects the company's product vs service business model. However,
SBIR/STTR awards can be retrieved separately for reporting and debugging purposes.

The module supports intelligent fallback strategies when UEI/DUNS identifiers are missing:
1. First: Try exact UEI/DUNS match
2. Second: Use USAspending autocomplete API for fuzzy name matching
3. Third: Fall back to direct name-based search

This multi-tier approach significantly improves coverage for companies with incomplete
metadata or name variations (e.g., "Advanced Technologies/Laboratories Intl" vs
"ADVANCED TECHNOLOGIES AND LABORATORIES (ATL) INTERNATIONAL, INC.").

Key Functions:
    - retrieve_company_contracts: Retrieve non-SBIR federal contracts for categorization (DuckDB)
    - retrieve_company_contracts_api: Retrieve non-SBIR federal contracts (API, with fuzzy matching)
    - retrieve_sbir_awards: Retrieve SBIR/STTR awards for reporting (DuckDB)
    - retrieve_sbir_awards_api: Retrieve SBIR/STTR awards for reporting (API, with fuzzy matching)
    - extract_sbir_phase: Extract SBIR phase from contract description
"""

import re
import threading
from typing import Any

import pandas as pd
from loguru import logger

from src.config.loader import get_config
from src.enrichers.usaspending import (
    USAspendingAPIClient,
    USAspendingAPIError,
    USAspendingRateLimitError,
)
from src.extractors.usaspending import DuckDBUSAspendingExtractor
from src.utils.async_tools import run_sync
from src.utils.usaspending_cache import USAspendingCache


_api_client: USAspendingAPIClient | None = None
_api_client_lock = threading.Lock()
PSC_DETAIL_LOOKUP_LIMIT = 50


def _get_usaspending_client() -> USAspendingAPIClient:
    """Get or initialize a shared USAspending API client."""
    global _api_client
    if _api_client is None:
        with _api_client_lock:
            if _api_client is None:
                _api_client = USAspendingAPIClient()
                logger.debug("Initialized shared USAspendingAPIClient for company categorization")
    return _api_client


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


def _normalize_company_name_for_search(company_name: str) -> list[str]:
    """Generate normalized variations of a company name for fuzzy matching.

    Creates multiple search variations to improve matching success rate when company
    names differ in punctuation, abbreviations, or formatting.

    Args:
        company_name: Original company name

    Returns:
        List of name variations to try, ordered from most to least specific

    Examples:
        >>> variations = _normalize_company_name_for_search("Advanced Technologies/Laboratories Intl")
        >>> variations
        ['Advanced Technologies/Laboratories Intl',
         'Advanced Technologies Laboratories International',
         'Advanced Technologies AND Laboratories International',
         'Advanced Technologies Laboratories']
    """
    if not company_name or not isinstance(company_name, str):
        return []

    # Common abbreviation expansions
    abbreviations = {
        r'\bIntl\.?\b': 'International',
        r'\bInt\'l\.?\b': 'International',
        r'\bInc\.?\b': 'Incorporated',
        r'\bCo\.?\b': 'Company',
        r'\bCorp\.?\b': 'Corporation',
        r'\bLtd\.?\b': 'Limited',
        r'\bLLC\.?\b': 'Limited Liability Company',
        r'\bLLP\.?\b': 'Limited Liability Partnership',
        r'\bL\.?L\.?C\.?\b': 'Limited Liability Company',
        r'\bL\.?P\.?\b': 'Limited Partnership',
        r'\bTech\.?\b': 'Technology',
        r'\bMfg\.?\b': 'Manufacturing',
        r'\bSys\.?\b': 'Systems',
        r'\bSvcs\.?\b': 'Services',
        r'\bMgmt\.?\b': 'Management',
        r'\bDev\.?\b': 'Development',
    }

    # Punctuation that often differs between sources
    punctuation_variants = {
        '/': ['AND', ' ', ''],  # "/" can be "AND", space, or removed
        '&': ['AND', 'and'],
        ',': ['', ' '],
        '-': [' ', ''],
    }

    variations = []

    # Variation 1: Original name (most specific)
    variations.append(company_name.strip())

    # Variation 2: Expand abbreviations only
    expanded = company_name
    for abbrev_pattern, expansion in abbreviations.items():
        expanded = re.sub(abbrev_pattern, expansion, expanded, flags=re.IGNORECASE)
    if expanded != company_name:
        variations.append(expanded.strip())

    # Variation 3: Expand abbreviations + normalize punctuation
    normalized = expanded
    for punct, replacements in punctuation_variants.items():
        if punct in normalized:
            # Try the first replacement (usually most semantic)
            replacement = f" {replacements[0]} " if replacements else ' '
            normalized = normalized.replace(punct, replacement)

    # Clean up multiple spaces
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    if normalized not in variations:
        variations.append(normalized)

    # Variation 4: Remove common legal suffixes entirely for broader matching
    # This helps match "ABC Inc" with "ABC Incorporated" or just "ABC"
    suffixes_to_remove = [
        r',?\s*(Inc\.?|Incorporated|LLC|L\.L\.C\.?|Ltd\.?|Limited|Corp\.?|Corporation|Company|Co\.?)$',
        r',?\s*\([^)]+\)$',  # Remove parenthetical expressions at end (e.g., "(ATL)")
    ]

    base_name = normalized
    for suffix_pattern in suffixes_to_remove:
        base_name = re.sub(suffix_pattern, '', base_name, flags=re.IGNORECASE)
    base_name = base_name.strip().rstrip(',').strip()

    if base_name and base_name not in variations and len(base_name) >= 10:
        variations.append(base_name)

    # Variation 5: Keep only the first 3-5 significant words (removes qualifiers)
    # This is the broadest/least specific search
    words = base_name.split()
    significant_words = [w for w in words if len(w) > 2]  # Skip very short words
    if len(significant_words) >= 3:
        core_name = ' '.join(significant_words[:5])
        if core_name not in variations and len(core_name) >= 10:
            variations.append(core_name)

    # Variation 6: Generate uppercase variations (USAspending often uses uppercase)
    # Add uppercase versions of key variations
    uppercase_variations = []
    for variation in variations[:3]:  # Only uppercase the first few most specific variations
        upper = variation.upper().strip()
        if upper != variation and len(upper) >= 5:  # Only add if different from original
            uppercase_variations.append(upper)
    
    # Add uppercase variations after the original variations but before the base name
    variations = variations[:3] + uppercase_variations + variations[3:]

    # Remove duplicates while preserving order
    # Prefer uppercase versions when there are case differences
    seen = {}  # Map lowercase -> actual variation (prefer uppercase)
    for variation in variations:
        if len(variation) < 5:
            continue
        normalized_check = variation.lower().strip()
        if normalized_check not in seen:
            seen[normalized_check] = variation
        else:
            # If we already have this variation, prefer uppercase version
            existing = seen[normalized_check]
            if variation.isupper() and not existing.isupper():
                seen[normalized_check] = variation
    
    # Convert back to list, preserving original order for first occurrence of each
    unique_variations = []
    seen_order = set()
    for variation in variations:
        normalized_check = variation.lower().strip()
        if normalized_check not in seen_order:
            unique_variations.append(seen[normalized_check])
            seen_order.add(normalized_check)

    return unique_variations


def _fuzzy_match_recipient(company_name: str) -> dict[str, Any] | None:
    """Use USAspending autocomplete API to find the best recipient match for a company name.

    Tries multiple normalized variations of the company name to improve matching success
    rate when names differ in punctuation, abbreviations, or formatting.

    Args:
        company_name: Company name to search for

    Returns:
        Dictionary with matched recipient info (uei, name, etc.) or None if no match
    """
    if not company_name or not isinstance(company_name, str):
        return None

    # Generate normalized variations of the company name
    name_variations = _normalize_company_name_for_search(company_name)

    if not name_variations:
        logger.debug(f"Could not generate name variations for: {company_name}")
        return None

    logger.debug(f"Generated {len(name_variations)} name variations for '{company_name}': {name_variations}")

    # Track the best candidate match (in case we don't find one with UEI/DUNS)
    best_candidate = None

    # Try each variation until we find a match
    client = _get_usaspending_client()

    for idx, search_name in enumerate(name_variations, 1):
        try:
            data = run_sync(client.autocomplete_recipient(search_name, limit=5))

            results = data.get("results", [])
            if not results:
                logger.debug(
                    f"No autocomplete matches for variation {idx}/{len(name_variations)}: '{search_name}'"
                )
                continue  # Try next variation

            # Get the best match (first result)
            best_match = results[0]
            matched_name = best_match.get("legal_business_name", "")
            matched_uei = best_match.get("uei")
            matched_duns = best_match.get("duns")

            # If we found a match with valid UEI/DUNS, use it immediately
            if _is_valid_identifier(matched_uei) or _is_valid_identifier(matched_duns):
                # Log which variation succeeded
                if idx == 1:
                    logger.info(
                        f"Autocomplete matched '{company_name}' → '{matched_name}' (UEI: {matched_uei})"
                    )
                else:
                    logger.info(
                        f"Autocomplete matched '{company_name}' using variation '{search_name}' "
                        f"→ '{matched_name}' (UEI: {matched_uei})"
                    )
                return {
                    "uei": matched_uei,
                    "name": matched_name,
                    "duns": matched_duns,
                }
            
            # If match has valid name but no UEI/DUNS, keep it as a candidate but continue searching
            # We'll use the first match with a valid name if no better match is found
            if _is_valid_identifier(matched_name) and not _is_valid_identifier(matched_uei) and not _is_valid_identifier(matched_duns):
                if best_candidate is None:
                    best_candidate = {
                        "uei": matched_uei,
                        "name": matched_name,
                        "duns": matched_duns,
                    }
                logger.debug(
                    f"Found match with name '{matched_name}' but no UEI/DUNS, continuing search..."
                )
                # Continue to try more variations to find one with UEI/DUNS
                continue
            
            # If match has empty name and no UEI/DUNS, it's not useful - continue searching
            if not _is_valid_identifier(matched_name) and not _is_valid_identifier(matched_uei) and not _is_valid_identifier(matched_duns):
                logger.debug(
                    f"Found match with empty name and no UEI/DUNS for variation '{search_name}', continuing search..."
                )
                continue
            
            # If we have a valid name match (even without UEI/DUNS), return it
            # This will be used for direct name search
            if idx == 1:
                logger.info(
                    f"Autocomplete matched '{company_name}' → '{matched_name}' (UEI: {matched_uei})"
                )
            else:
                logger.info(
                    f"Autocomplete matched '{company_name}' using variation '{search_name}' "
                    f"→ '{matched_name}' (UEI: {matched_uei})"
                )
            return {
                "uei": matched_uei,
                "name": matched_name,
                "duns": matched_duns,
            }

        except USAspendingRateLimitError as e:
            logger.warning(
                f"Rate limit exceeded during autocomplete for '{search_name}', stopping search: {e}"
            )
            break
        except USAspendingAPIError as e:
            logger.debug(f"Autocomplete error for variation '{search_name}': {e}")
            continue

    # If we found a candidate with valid name but no UEI/DUNS, return it
    # This will be used for direct name search
    if best_candidate:
        logger.info(
            f"Autocomplete found match with name '{best_candidate['name']}' but no UEI/DUNS, "
            f"will use matched name for direct search"
        )
        return best_candidate

    # No matches found with any variation
    logger.debug(f"No autocomplete matches found for '{company_name}' after trying {len(name_variations)} variations")
    return None


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
    page_size: int = 100,  # API maximum limit is 100
) -> pd.DataFrame:
    """Retrieve all federal contracts for a company from USAspending API (excluding SBIR/STTR).

    Uses the /search/spending_by_transaction/ endpoint which returns transaction-level
    data including PSC codes directly in the response. SBIR/STTR awards are excluded to
    focus on non-R&D federal contract revenue. This endpoint properly populates
    PSC codes without requiring additional API calls per award.

    Implements intelligent fallback strategy when UEI/DUNS are missing:
    1. First: Use UEI/DUNS if valid
    2. Second: Use autocomplete API for fuzzy name matching to find UEI/DUNS
    3. Third: Fall back to direct name-based search

    When PSC codes are missing from the transaction endpoint, a small number of
    detailed award lookups are performed automatically (see PSC_DETAIL_LOOKUP_LIMIT).

    Args:
        uei: Company UEI (Unique Entity Identifier)
        duns: Company DUNS number
        company_name: Company name (used as fallback when UEI/DUNS are invalid)
        page_size: Number of results per page

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

    # Initialize cache
    try:
        config = get_config()
        cache_config = config.enrichment_refresh.usaspending.cache
        cache = USAspendingCache(
            cache_dir=cache_config.cache_dir,
            enabled=cache_config.enabled,
            ttl_hours=cache_config.ttl_hours,
        )
    except Exception as e:
        logger.debug(f"Could not initialize cache, proceeding without caching: {e}")
        cache = USAspendingCache(enabled=False)

    client = _get_usaspending_client()

    # Check cache first (non-SBIR contracts)
    cached_result = cache.get(uei=uei, duns=duns, company_name=company_name, cache_type="contracts")
    if cached_result is not None:
        logger.debug(f"Returning cached result for company (UEI={uei}, DUNS={duns}, name={company_name})")
        return cached_result

    # Try autocomplete fuzzy matching if we don't have valid identifiers but have a name
    fuzzy_matched = False
    matched_name = None
    if not (valid_uei or valid_duns) and valid_name and company_name:
        logger.info(f"Attempting fuzzy match via autocomplete for: {company_name}")
        match_result = _fuzzy_match_recipient(company_name)

        if match_result:
            # Use the matched identifiers instead of the original name
            matched_uei = match_result.get("uei")
            matched_duns = match_result.get("duns")
            matched_name = match_result.get("name")

            if _is_valid_identifier(matched_uei):
                uei = matched_uei
                valid_uei = True
                fuzzy_matched = True
            if _is_valid_identifier(matched_duns):
                duns = matched_duns
                valid_duns = True
                fuzzy_matched = True
            
            # If autocomplete matched but didn't return UEI/DUNS, use the matched name for search
            # The matched name is what USAspending recognizes and is more likely to work
            if not (valid_uei or valid_duns) and matched_name and _is_valid_identifier(matched_name):
                logger.info(f"Autocomplete matched name '{matched_name}' but no UEI/DUNS found, using matched name for search")
                company_name = matched_name
                fuzzy_matched = True

    # Determine search strategy
    if valid_uei or valid_duns:
        if fuzzy_matched:
            logger.info(f"Using fuzzy-matched identifiers (UEI={uei if valid_uei else 'N/A'}, DUNS={duns if valid_duns else 'N/A'})")
        else:
            logger.info(f"Retrieving contracts from USAspending API using identifiers (UEI={uei if valid_uei else 'N/A'}, DUNS={duns if valid_duns else 'N/A'})")
    else:
        if fuzzy_matched and matched_name:
            logger.info(f"Falling back to direct name search using autocomplete-matched name: {company_name}")
        else:
            logger.info(f"Falling back to direct name search for: {company_name}")

    # Build search filters using AdvancedFilterObject
    filters: dict[str, Any] = {
        "award_type_codes": ["A", "B", "C", "D"],  # Contract awards only
    }

    # Add recipient search - recipient_search_text searches across name, UEI, and DUNS
    # API requires an array format - include all available identifiers for better matching
    recipient_search_terms = []
    if valid_uei:
        recipient_search_terms.append(uei)
        logger.debug(f"Adding UEI to recipient_search_text: {uei}")
    if valid_duns:
        recipient_search_terms.append(duns)
        logger.debug(f"Adding DUNS to recipient_search_text: {duns}")
    # Include company name if available (helps when UEI/DUNS don't match correctly)
    if valid_name:
        # Use matched name from autocomplete if available, otherwise use original
        name_to_search = matched_name if (matched_name and _is_valid_identifier(matched_name)) else company_name
        recipient_search_terms.append(name_to_search)
        logger.debug(f"Adding company name to recipient_search_text: {name_to_search}")

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
        "Awarding Agency",       # Awarding agency name
        "Awarding Sub Agency",   # Awarding sub-agency name
        "internal_id",           # Internal award identifier
    ]

    all_transactions: list[dict[str, Any]] = []
    psc_detail_lookups = 0
    page = 1
    max_pages = 1000  # Safety limit to prevent infinite loops

    try:
        logger.info("Fetching transactions from spending_by_transaction endpoint")
        while page <= max_pages:
            logger.debug(
                f"Fetching page {page} from spending_by_transaction endpoint (company: {uei or company_name or 'Unknown'})"
            )
            try:
                data = run_sync(
                    client.search_transactions(
                        filters=filters,
                        fields=fields,
                        page=page,
                        limit=page_size,
                        sort="Transaction Amount",
                        order="desc",
                    )
                )
            except USAspendingRateLimitError as e:
                logger.error(f"Rate limit exceeded for page {page}, stopping pagination: {e}")
                if page == 1:
                    return pd.DataFrame()
                break
            except USAspendingAPIError as e:
                logger.error(f"API error fetching transactions (page {page}): {e}")
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
                # Check if agency fields are present
                awarding_agency = results[0].get("Awarding Agency")
                awarding_sub_agency = results[0].get("Awarding Sub Agency")
                logger.debug(f"First transaction Awarding Agency: {awarding_agency}, Awarding Sub Agency: {awarding_sub_agency}")

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
                    "awarding_agency": transaction.get("Awarding Agency"),
                    "awarding_sub_agency": transaction.get("Awarding Sub Agency"),
                }

                # Generate fallback ID if award_id is missing
                if not processed_transaction["award_id"]:
                    processed_transaction["award_id"] = f"UNKNOWN_{len(all_transactions)}"
                    logger.debug(
                        f"No award ID found in transaction response. Available keys: {list(transaction.keys())}"
                    )

                if (
                    (not psc_value or (isinstance(psc_value, str) and not psc_value.strip()))
                    and psc_detail_lookups < PSC_DETAIL_LOOKUP_LIMIT
                ):
                    fallback_details = _fetch_award_details(processed_transaction["award_id"])
                    if fallback_details and fallback_details.get("psc"):
                        processed_transaction["psc"] = fallback_details["psc"]
                        psc_detail_lookups += 1

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
            
            # Safety check: if we've retrieved a very large number of transactions, log warning
            if len(all_transactions) > 100000:
                logger.warning(
                    f"Retrieved {len(all_transactions)} transactions for company {uei or company_name or 'Unknown'}, "
                    f"stopping pagination at page {page} to prevent excessive data retrieval"
                )
                break
        
        if page > max_pages:
            logger.warning(
                f"Reached maximum page limit ({max_pages}) for company {uei or company_name or 'Unknown'}, "
                f"stopping pagination. Retrieved {len(all_transactions)} transactions so far."
            )

        logger.info(f"Retrieved {len(all_transactions)} transactions from spending_by_transaction endpoint")

        # If no results with UEI/DUNS and we have a company name, try name-based search as fallback
        if not all_transactions and (valid_uei or valid_duns) and valid_name:
            logger.info(
                f"No transactions found with UEI/DUNS, trying fallback search by company name: {company_name}"
            )
            # Try searching by company name - use name variations for better matching
            name_filters = {
                "award_type_codes": ["A", "B", "C", "D"],
            }
            
            # Generate name variations for better matching
            # API requires array format - include multiple variations for better matching
            name_variations = _normalize_company_name_for_search(company_name) if company_name else []
            # Use up to 3 most specific variations
            name_search_terms: list[str] = []
            for variation in name_variations[:3]:
                if variation and len(variation) >= 10:
                    name_search_terms.append(variation)
                    if len(name_search_terms) >= 3:
                        break
            if not name_search_terms and company_name:
                name_search_terms = [company_name]
            
            name_filters["recipient_search_text"] = name_search_terms
            logger.debug(f"Trying name search with variations: {name_search_terms}")
            
            # Try pagination with name search
            name_page = 1
            name_max_pages = 1000  # Safety limit
            name_transactions: list[dict[str, Any]] = []
            try:
                while name_page <= name_max_pages:
                    try:
                        name_data = run_sync(
                            client.search_transactions(
                                filters=name_filters,
                                fields=fields,
                                page=name_page,
                                limit=page_size,
                                sort="Transaction Amount",
                                order="desc",
                            )
                        )
                    except (USAspendingRateLimitError, USAspendingAPIError) as e:
                        logger.debug(f"Name-based fallback search error on page {name_page}: {e}")
                        break

                    name_results = name_data.get("results", [])

                    if not name_results:
                        break
                    
                    # Process name-based results
                    for transaction in name_results:
                        psc_raw = transaction.get("PSC")
                        if isinstance(psc_raw, dict):
                            psc_value = psc_raw.get("code") or psc_raw.get("psc_code") or psc_raw.get("psc")
                        elif isinstance(psc_raw, str):
                            psc_value = psc_raw
                        else:
                            psc_value = None
                        
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
                            "awarding_agency": transaction.get("Awarding Agency"),
                            "awarding_sub_agency": transaction.get("Awarding Sub Agency"),
                        }
                        
                        if not processed_transaction["award_id"]:
                            processed_transaction["award_id"] = f"UNKNOWN_{len(name_transactions)}"
                        
                        if (
                            (not psc_value or (isinstance(psc_value, str) and not psc_value.strip()))
                            and psc_detail_lookups < PSC_DETAIL_LOOKUP_LIMIT
                        ):
                            fallback_details = _fetch_award_details(processed_transaction["award_id"])
                            if fallback_details and fallback_details.get("psc"):
                                processed_transaction["psc"] = fallback_details["psc"]
                                psc_detail_lookups += 1
                        
                        name_transactions.append(processed_transaction)
                    
                    # Check for more pages
                    page_metadata = name_data.get("page_metadata", {})
                    has_next = page_metadata.get("hasNext", False)
                    if not has_next:
                        break
                    name_page += 1
                    
                    # Safety check: prevent excessive data retrieval
                    if len(name_transactions) > 100000:
                        logger.warning(
                            f"Retrieved {len(name_transactions)} transactions via name search for company {company_name}, "
                            f"stopping pagination at page {name_page}"
                        )
                        break
                
                if name_page > name_max_pages:
                    logger.warning(
                        f"Reached maximum page limit ({name_max_pages}) for name search of {company_name}, "
                        f"stopping pagination. Retrieved {len(name_transactions)} transactions so far."
                    )
                
                if name_transactions:
                    logger.info(
                        f"Found {len(name_transactions)} transactions using company name search. "
                        f"UEI {uei} may not be correctly linked in USAspending for {company_name}"
                    )
                    # Use name-based results instead
                    all_transactions = name_transactions
                else:
                    logger.warning(
                        f"Name-based fallback search also found no transactions for {company_name}"
                    )
            except Exception as e:
                logger.debug(f"Name-based fallback search failed: {e}")

        if not all_transactions:
            logger.warning(f"No transactions found for company (UEI={uei}, DUNS={duns}, name={company_name})")
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

        # Cache the result (non-SBIR contracts)
        cache.set(df, uei=uei, duns=duns, company_name=company_name, cache_type="contracts")

        return df

    except Exception as e:
        import traceback
        logger.error(f"Failed to retrieve contracts from USAspending API: {e}")
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
        return pd.DataFrame()


def _fetch_award_details(award_id: str) -> dict[str, Any] | None:
    """Fetch detailed award information including PSC code as a fallback."""
    try:
        client = _get_usaspending_client()
        award_data = run_sync(client.fetch_award_details(award_id))

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

    except USAspendingRateLimitError as e:
        logger.warning(f"Rate limit exceeded fetching award details for {award_id}: {e}")
        return None
    except USAspendingAPIError as e:
        logger.warning(f"API error fetching award details for {award_id}: {e}")
        return None
    except Exception as e:
        logger.warning(f"Unexpected error fetching award details for {award_id}: {e}")
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
    page_size: int = 100,  # API maximum limit is 100
) -> pd.DataFrame:
    """Retrieve ONLY SBIR/STTR awards for a company from USAspending API (for reporting).

    This function retrieves SBIR/STTR awards separately for debugging and reporting
    purposes. These awards are NOT used in the categorization logic.

    Implements intelligent fallback strategy when UEI/DUNS are missing:
    1. First: Use UEI/DUNS if valid
    2. Second: Use autocomplete API for fuzzy name matching to find UEI/DUNS
    3. Third: Fall back to direct name-based search

    Args:
        uei: Company UEI (Unique Entity Identifier)
        duns: Company DUNS number
        company_name: Company name (used as fallback when UEI/DUNS are invalid)
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

    # Initialize cache
    try:
        config = get_config()
        cache_config = config.enrichment_refresh.usaspending.cache
        cache = USAspendingCache(
            cache_dir=cache_config.cache_dir,
            enabled=cache_config.enabled,
            ttl_hours=cache_config.ttl_hours,
        )
    except Exception as e:
        logger.debug(f"Could not initialize cache, proceeding without caching: {e}")
        cache = USAspendingCache(enabled=False)

    client = _get_usaspending_client()

    # Check cache first (SBIR awards only)
    cached_result = cache.get(uei=uei, duns=duns, company_name=company_name, cache_type="sbir")
    if cached_result is not None:
        logger.debug(f"Returning cached SBIR awards result for company (UEI={uei}, DUNS={duns}, name={company_name})")
        return cached_result

    # Try autocomplete fuzzy matching if we don't have valid identifiers but have a name
    fuzzy_matched = False
    if not (valid_uei or valid_duns) and valid_name and company_name:
        logger.debug(f"Attempting fuzzy match via autocomplete for SBIR awards: {company_name}")
        match_result = _fuzzy_match_recipient(company_name)

        if match_result:
            matched_uei = match_result.get("uei")
            matched_duns = match_result.get("duns")

            if _is_valid_identifier(matched_uei):
                uei = matched_uei
                valid_uei = True
                fuzzy_matched = True
            if _is_valid_identifier(matched_duns):
                duns = matched_duns
                valid_duns = True
                fuzzy_matched = True

    if valid_uei or valid_duns:
        if fuzzy_matched:
            logger.debug(f"Using fuzzy-matched identifiers for SBIR (UEI={uei if valid_uei else 'N/A'}, DUNS={duns if valid_duns else 'N/A'})")
        else:
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

    all_transactions: list[dict[str, Any]] = []
    page = 1
    max_pages = 1000  # Safety limit to prevent infinite loops

    try:
        while page <= max_pages:
            try:
                data = run_sync(
                    client.search_transactions(
                        filters=filters,
                        fields=fields,
                        page=page,
                        limit=page_size,
                        sort="Transaction Amount",
                        order="desc",
                    )
                )
            except USAspendingRateLimitError as e:
                logger.error(f"Rate limit exceeded for SBIR awards page {page}, stopping pagination: {e}")
                if page == 1:
                    return pd.DataFrame()
                break
            except USAspendingAPIError as e:
                logger.error(f"API error fetching SBIR awards page {page}: {e}")
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
            
            # Safety check: prevent excessive data retrieval
            if len(all_transactions) > 100000:
                logger.warning(
                    f"Retrieved {len(all_transactions)} SBIR transactions for company {uei or company_name or 'Unknown'}, "
                    f"stopping pagination at page {page}"
                )
                break
        
        if page > max_pages:
            logger.warning(
                f"Reached maximum page limit ({max_pages}) for SBIR awards for company {uei or company_name or 'Unknown'}, "
                f"stopping pagination. Retrieved {len(all_transactions)} transactions so far."
            )

        if not all_transactions:
            logger.debug(f"No SBIR/STTR awards found via API (UEI={uei}, DUNS={duns})")
            return pd.DataFrame()

        df = pd.DataFrame(all_transactions)
        df["award_amount"] = pd.to_numeric(df["award_amount"], errors="coerce")
        df = df.drop_duplicates(subset=["award_id"])

        logger.debug(f"Retrieved {len(df)} SBIR/STTR awards via API")
        
        # Cache the result (SBIR awards only)
        cache.set(df, uei=uei, duns=duns, company_name=company_name, cache_type="sbir")
        
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
