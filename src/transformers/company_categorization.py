"""Company categorization transformer module.

This module implements the contract classification and company aggregation logic
for categorizing SBIR companies as Product, Service, or Mixed based on their
federal contract portfolios from USAspending.

The classification system operates at two levels:
1. Contract-level: Classify individual contracts using PSC codes, contract types,
   pricing, description keywords, and SBIR phase
2. Company-level: Aggregate contract classifications using dollar-weighted analysis

Key Functions:
    - classify_contract: Classify a single contract/award
    - aggregate_company_classification: Aggregate contract classifications to company level
"""

from loguru import logger

from src.models.categorization import CompanyClassification, ContractClassification


def classify_contract(contract: dict) -> ContractClassification:
    """Classify a single federal contract/award.

    Classification logic (in priority order):
    1. Contract type overrides: CPFF, Cost-Type, T&M → Service (highest priority)
    2. PSC-based: numeric → Product, A/B → R&D, alphabetic → Service
    3. Description inference: FFP with product keywords → Product
    4. SBIR phase adjustment: Phase I/II → R&D (unless numeric PSC)

    Args:
        contract: Dictionary with fields:
            - award_id (str): Contract identifier
            - psc (str): Product Service Code
            - contract_type (str): Contract type
            - pricing (str): Pricing type
            - description (str): Award description
            - award_amount (float): Award amount in USD
            - sbir_phase (str): SBIR phase if applicable

    Returns:
        ContractClassification: Classified contract with method and confidence

    Examples:
        >>> contract = {"award_id": "TEST001", "psc": "1234", "contract_type": "FFP",
        ...             "pricing": "FFP", "award_amount": 100000}
        >>> result = classify_contract(contract)
        >>> result.classification
        'Product'
        >>> result.method
        'psc_numeric'
    """
    # Extract fields with safe defaults
    award_id = contract.get("award_id", "")
    # Convert PSC to string if it's a number (handles numeric PSC codes stored as int)
    psc_raw = contract.get("psc", "")
    psc = str(psc_raw) if psc_raw else ""
    contract_type = contract.get("contract_type", "")
    pricing = contract.get("pricing", "")
    description = contract.get("description", "") or ""
    award_amount = contract.get("award_amount")
    sbir_phase = contract.get("sbir_phase")

    # --- Rule 1: Contract type overrides (highest priority) ---
    # CPFF, Cost-Type, or T&M pricing → Service
    if _is_service_contract_type(contract_type, pricing):
        return ContractClassification(
            award_id=award_id,
            classification="Service",
            method="contract_type",
            confidence=0.95,
            psc=psc or None,
            contract_type=contract_type or None,
            pricing=pricing or None,
            description=description or None,
            award_amount=award_amount,
            sbir_phase=sbir_phase,
        )

    # --- Rule 2: PSC-based classification ---
    if psc:
        psc_classification, psc_method, psc_confidence = _classify_by_psc(psc)

        # --- Rule 3: Description inference (only for FFP with non-R&D PSC) ---
        # FFP with product keywords can override alphabetic PSC → Product
        if pricing and pricing.upper() == "FFP" and psc_classification != "R&D":
            product_match = _check_product_keywords(description)
            if product_match:
                return ContractClassification(
                    award_id=award_id,
                    classification="Product",
                    method="description_inference",
                    confidence=0.85,
                    psc=psc,
                    contract_type=contract_type or None,
                    pricing=pricing,
                    description=description or None,
                    award_amount=award_amount,
                    sbir_phase=sbir_phase,
                )

        # --- Rule 4: SBIR phase adjustment ---
        if sbir_phase and sbir_phase in ("I", "II"):
            # Phase I/II with numeric PSC → keep Product
            if psc_classification == "Product":
                return ContractClassification(
                    award_id=award_id,
                    classification="Product",
                    method="sbir_numeric_psc",
                    confidence=0.90,
                    psc=psc,
                    contract_type=contract_type or None,
                    pricing=pricing or None,
                    description=description or None,
                    award_amount=award_amount,
                    sbir_phase=sbir_phase,
                )
            else:
                # Phase I/II with alphabetic PSC → R&D
                return ContractClassification(
                    award_id=award_id,
                    classification="R&D",
                    method="sbir_adjustment",
                    confidence=0.90,
                    psc=psc,
                    contract_type=contract_type or None,
                    pricing=pricing or None,
                    description=description or None,
                    award_amount=award_amount,
                    sbir_phase=sbir_phase,
                )

        # Return PSC-based classification
        return ContractClassification(
            award_id=award_id,
            classification=psc_classification,
            method=psc_method,
            confidence=psc_confidence,
            psc=psc,
            contract_type=contract_type or None,
            pricing=pricing or None,
            description=description or None,
            award_amount=award_amount,
            sbir_phase=sbir_phase,
        )

    # --- Default: Service (low confidence) ---
    logger.debug(f"Contract {award_id} has no PSC code, defaulting to Service")
    return ContractClassification(
        award_id=award_id,
        classification="Service",
        method="default",
        confidence=0.50,
        psc=None,
        contract_type=contract_type or None,
        pricing=pricing or None,
        description=description or None,
        award_amount=award_amount,
        sbir_phase=sbir_phase,
    )


def _is_service_contract_type(contract_type: str, pricing: str) -> bool:
    """Check if contract type or pricing indicates service work.

    Service indicators:
    - Contract type: CPFF, Cost-Type
    - Pricing: T&M (Time and Materials)

    Args:
        contract_type: Contract type string
        pricing: Pricing type string

    Returns:
        True if contract type indicates service work
    """
    if not contract_type and not pricing:
        return False

    # Normalize to uppercase for comparison
    ct = contract_type.upper() if contract_type else ""
    pr = pricing.upper() if pricing else ""

    # Check for service-indicating contract types
    service_types = {"CPFF", "COST-TYPE", "COST TYPE"}
    if any(st in ct for st in service_types):
        return True

    # Check for T&M pricing
    if "T&M" in pr or "T & M" in pr or "TIME AND MATERIALS" in pr or "TIME & MATERIALS" in pr:
        return True

    return False


def _classify_by_psc(psc: str) -> tuple[str, str, float]:
    """Classify contract based on PSC (Product Service Code).

    PSC classification rules:
    - Numeric PSC (e.g., "1234") → Product
    - PSC starting with A or B → R&D
    - Other alphabetic PSC → Service

    Args:
        psc: Product Service Code

    Returns:
        Tuple of (classification, method, confidence)
    """
    if not psc:
        return ("Service", "default", 0.50)

<<<<<<< HEAD
    # Ensure PSC is a string (handles cases where numeric PSC might be passed as int)
    psc_str = str(psc) if psc else ""
    if not psc_str:
=======
    # Handle edge case where PSC might be a dict instead of string
    if isinstance(psc, dict):
        # Try to extract the code from the dict
        psc = psc.get("code") or psc.get("psc_code") or psc.get("psc") or ""
        if not psc:
            return ("Service", "default", 0.50)

    # Ensure PSC is a string
    if not isinstance(psc, str):
>>>>>>> claude/fix-psc-codes-issue-01Pg9ogB15qXtSpxJW43oab7
        return ("Service", "default", 0.50)

    # Get first character of PSC
    first_char = psc_str[0].upper()

    # Numeric PSC → Product
    if first_char.isdigit():
        return ("Product", "psc_numeric", 0.90)

    # PSC starting with A or B → R&D
    if first_char in ("A", "B"):
        return ("R&D", "psc_rd", 0.90)

    # Other alphabetic PSC → Service
    return ("Service", "psc_alphabetic", 0.90)


def _check_product_keywords(description: str) -> bool:
    """Check if description contains product-indicating keywords.

    Product keywords:
    - prototype
    - hardware
    - device

    Args:
        description: Award description text

    Returns:
        True if description contains product keywords
    """
    if not description:
        return False

    # Normalize to lowercase for comparison
    desc_lower = description.lower()

    # Check for product keywords
    product_keywords = ["prototype", "hardware", "device"]
    return any(keyword in desc_lower for keyword in product_keywords)


def aggregate_company_classification(
    contracts: list[dict],
    company_uei: str,
    company_name: str = "",
) -> CompanyClassification:
    """Aggregate contract classifications to company level.

    Aggregation logic:
    1. Calculate dollar-weighted percentages for Product vs Service/R&D
    2. Apply 60% threshold for Product-leaning or Service-leaning
    3. Apply Mixed classification if neither threshold met
    4. Apply override rules (e.g., >6 PSC families → Mixed)
    5. Assign confidence level based on number of awards

    Args:
        contracts: List of classified contracts (as dicts or ContractClassification objects)
        company_uei: Company UEI identifier
        company_name: Company name (optional)

    Returns:
        CompanyClassification: Aggregated company classification

    Examples:
        >>> contracts = [
        ...     {"classification": "Product", "award_amount": 100000, "psc": "1234"},
        ...     {"classification": "Service", "award_amount": 200000, "psc": "R425"}
        ... ]
        >>> result = aggregate_company_classification(contracts, "TEST123UEI000", "Test Company")
        >>> result.classification
        'Service-leaning'
        >>> result.product_pct
        33.33
    """
    # Handle edge case: insufficient data
    if len(contracts) < 2:
        logger.warning(f"Company {company_uei} has fewer than 2 contracts, classifying as Uncertain")
        return CompanyClassification(
            company_uei=company_uei,
            company_name=company_name or "Unknown",
            classification="Uncertain",
            product_pct=0.0,
            service_pct=0.0,
            confidence="Low",
            award_count=len(contracts),
            psc_family_count=0,
            total_dollars=0.0,
            product_dollars=0.0,
            service_rd_dollars=0.0,
            override_reason="insufficient_awards",
            contracts=[],
        )

    # Convert dicts to ContractClassification objects if needed
    classified_contracts = []
    for c in contracts:
        if isinstance(c, ContractClassification):
            classified_contracts.append(c)
        elif isinstance(c, dict):
            # If dict has classification already, keep it
            if "classification" in c and "award_id" in c:
                classified_contracts.append(
                    ContractClassification(
                        award_id=c.get("award_id", ""),
                        classification=c["classification"],
                        method=c.get("method", "unknown"),
                        confidence=c.get("confidence", 0.5),
                        psc=c.get("psc"),
                        contract_type=c.get("contract_type"),
                        pricing=c.get("pricing"),
                        description=c.get("description"),
                        award_amount=c.get("award_amount"),
                        sbir_phase=c.get("sbir_phase"),
                    )
                )
            else:
                # Classify the contract first
                classified = classify_contract(c)
                classified_contracts.append(classified)

    # Calculate dollar-weighted percentages
    total_dollars = sum(c.award_amount or 0.0 for c in classified_contracts)
    product_dollars = sum(
        c.award_amount or 0.0
        for c in classified_contracts
        if c.classification == "Product"
    )
    service_rd_dollars = sum(
        c.award_amount or 0.0
        for c in classified_contracts
        if c.classification in ("Service", "R&D")
    )

    # Calculate percentages
    if total_dollars > 0:
        product_pct = (product_dollars / total_dollars) * 100
        service_pct = (service_rd_dollars / total_dollars) * 100
    else:
        product_pct = 0.0
        service_pct = 0.0

    # Count PSC families
    psc_families = set()
    for c in classified_contracts:
        if c.psc:
            # Ensure PSC is string (defensive programming)
            psc_str = str(c.psc) if c.psc else ""
            if psc_str:
                psc_families.add(psc_str[0].upper())

    # Apply override rules and determine classification
    override_reason = None

    # Override 1: Too many PSC families (integrator/diverse portfolio)
    if len(psc_families) > 6:
        classification = "Mixed"
        override_reason = "high_psc_diversity"
        logger.info(
            f"Company {company_uei} has {len(psc_families)} PSC families, "
            f"overriding to Mixed classification"
        )
    # Standard classification based on thresholds
    elif product_pct >= 60:
        classification = "Product-leaning"
    elif service_pct >= 60:
        classification = "Service-leaning"
    else:
        classification = "Mixed"

    # Determine confidence level based on number of awards
    if len(classified_contracts) <= 2:
        confidence = "Low"
    elif len(classified_contracts) <= 5:
        confidence = "Medium"
    else:
        confidence = "High"

    logger.info(
        f"Classified company {company_uei} as {classification} "
        f"({len(classified_contracts)} awards, {confidence} confidence)"
    )

    return CompanyClassification(
        company_uei=company_uei,
        company_name=company_name or "Unknown",
        classification=classification,
        product_pct=round(product_pct, 2),
        service_pct=round(service_pct, 2),
        confidence=confidence,
        award_count=len(classified_contracts),
        psc_family_count=len(psc_families),
        total_dollars=total_dollars,
        product_dollars=product_dollars,
        service_rd_dollars=service_rd_dollars,
        override_reason=override_reason,
        contracts=classified_contracts,
    )
