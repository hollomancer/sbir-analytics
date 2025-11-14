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

    Classification Framework:
    PSC is the PRIMARY signal (the noun - what is bought)
    Pricing is the SECONDARY signal (the grammar - how risk is priced)

    Together they form agreement zones:
    - High agreement → high confidence (0.90-0.95)
    - Low agreement → lower confidence (0.60-0.70)

    Agreement Zones:
    1. PSC numeric + FFP → Product (~90% probability)
    2. PSC R&D/Service + CPFF/Cost → R&D/Service (~95% probability)
    3. PSC Service + FFP → Ambiguous (integrators/IT shops)
    4. PSC numeric + CPFF → Unusual (prototype development)

    Args:
        contract: Dictionary with fields:
            - award_id (str): Contract identifier
            - psc (str): Product Service Code (PRIMARY)
            - contract_type (str): Contract type
            - pricing (str): Pricing type (SECONDARY)
            - description (str): Award description
            - award_amount (float): Award amount in USD
            - sbir_phase (str): SBIR phase if applicable

    Returns:
        ContractClassification: Classified contract with method and confidence
    """
    # Extract fields with safe defaults
    award_id = contract.get("award_id", "")
    psc = contract.get("psc", "")
    contract_type = contract.get("contract_type", "")
    pricing = contract.get("pricing", "")
    description = contract.get("description", "") or ""
    award_amount = contract.get("award_amount")
    sbir_phase = contract.get("sbir_phase")

    # --- STEP 1: PSC Classification (PRIMARY SIGNAL) ---
    if not psc:
        # No PSC → default to Service with low confidence
        logger.debug(f"Contract {award_id} has no PSC code, defaulting to Service")
        return ContractClassification(
            award_id=award_id,
            classification="Service",
            method="default_no_psc",
            confidence=0.50,
            psc=None,
            contract_type=contract_type or None,
            pricing=pricing or None,
            description=description or None,
            award_amount=award_amount,
            sbir_phase=sbir_phase,
        )

    # Get PSC-based classification (primary signal)
    psc_classification, psc_method, base_confidence = _classify_by_psc(psc)
    first_char = psc[0].upper()

    # --- STEP 2: PSC D/E/F Special Handling (IT/Telecom/Space) ---
    if first_char in ("D", "E", "F"):
        return _classify_psc_def(
            award_id, psc, pricing, contract_type, description, award_amount, sbir_phase
        )

    # --- STEP 3: Pricing Agreement Check (SECONDARY SIGNAL) ---
    # Pricing confirms or creates ambiguity
    final_confidence = base_confidence
    method = psc_method

    if pricing:
        pricing_upper = pricing.upper()

        # Cost-based pricing (CPFF, CPIF, CPAF, Cost-Type)
        if any(cost_type in pricing_upper for cost_type in ["CPFF", "CPIF", "CPAF", "COST"]):
            if psc_classification in ["Service", "R&D"]:
                # HIGH AGREEMENT: Service/R&D PSC + Cost pricing
                # "PSC = R&D + Type = CPFF → ~95% probability of labor/R&D"
                final_confidence = 0.95
                method = f"{psc_method}_cost_confirmed"
            else:
                # LOW AGREEMENT: Product PSC + Cost pricing (unusual)
                # Could be prototype development, R&D phase
                final_confidence = 0.65
                method = f"{psc_method}_cost_conflict"

        # Fixed-price (FFP)
        elif "FFP" in pricing_upper:
            if psc_classification == "Product":
                # HIGH AGREEMENT: Product PSC + FFP
                # "PSC = numeric + Type = FFP → ~90% probability of products/material"
                final_confidence = 0.95
                method = f"{psc_method}_ffp_confirmed"
            elif psc_classification in ["Service", "R&D"]:
                # LOW AGREEMENT: Service PSC + FFP (ambiguous - integrators)
                # "PSC = services + Type = FFP → ambiguous; integrators and IT shops live here"
                # Check for product keywords to resolve ambiguity
                if _check_product_keywords(description):
                    # Description suggests product despite service PSC
                    return ContractClassification(
                        award_id=award_id,
                        classification="Product",
                        method="description_inference_ffp",
                        confidence=0.75,
                        psc=psc,
                        contract_type=contract_type or None,
                        pricing=pricing,
                        description=description or None,
                        award_amount=award_amount,
                        sbir_phase=sbir_phase,
                    )
                # No product keywords → stay with service classification but lower confidence
                final_confidence = 0.65
                method = f"{psc_method}_ffp_ambiguous"

        # Time & Materials (T&M)
        elif "T&M" in pricing_upper or "TIME" in pricing_upper:
            if psc_classification in ["Service", "R&D"]:
                # HIGH AGREEMENT: Service/R&D PSC + T&M
                # "T&M → staff augmentation"
                final_confidence = 0.95
                method = f"{psc_method}_tm_confirmed"
            else:
                # LOW AGREEMENT: Product PSC + T&M (unusual)
                final_confidence = 0.65
                method = f"{psc_method}_tm_conflict"

    # --- STEP 4: SBIR Phase Adjustment ---
    if sbir_phase and sbir_phase in ("I", "II"):
        # Phase I/II are typically R&D
        if psc_classification == "Product":
            # Numeric PSC with SBIR I/II → keep as Product (prototype development)
            method = "sbir_numeric_psc"
            final_confidence = 0.90
        else:
            # Alphabetic PSC with SBIR I/II → R&D
            psc_classification = "R&D"
            method = "sbir_rd_adjustment"
            final_confidence = 0.85

    # --- STEP 5: Return Final Classification ---
    return ContractClassification(
        award_id=award_id,
        classification=psc_classification,
        method=method,
        confidence=final_confidence,
        psc=psc,
        contract_type=contract_type or None,
        pricing=pricing or None,
        description=description or None,
        award_amount=award_amount,
        sbir_phase=sbir_phase,
    )


def _classify_psc_def(
    award_id: str,
    psc: str,
    pricing: str,
    contract_type: str,
    description: str,
    award_amount: float,
    sbir_phase: str | None,
) -> ContractClassification:
    """Handle PSC D/E/F (IT, telecom, space) classification.

    These PSCs are ambiguous and require pricing to resolve.
    """
    pricing_upper = pricing.upper() if pricing else ""

    # FFP suggests fixed deliverable → Product
    if "FFP" in pricing_upper:
        return ContractClassification(
            award_id=award_id,
            classification="Product",
            method="psc_def_ffp",
            confidence=0.80,  # Moderate-high for IT/telecom product
            psc=psc,
            contract_type=contract_type or None,
            pricing=pricing,
            description=description or None,
            award_amount=award_amount,
            sbir_phase=sbir_phase,
        )

    # Cost/T&M or no pricing → Service (IT/telecom default)
    return ContractClassification(
        award_id=award_id,
        classification="Service",
        method="psc_def_service",
        confidence=0.75,  # Moderate confidence for IT/telecom service
        psc=psc,
        contract_type=contract_type or None,
        pricing=pricing or None,
        description=description or None,
        award_amount=award_amount,
        sbir_phase=sbir_phase,
    )


def _classify_by_psc(psc: str) -> tuple[str, str, float]:
    """Classify contract based on PSC (Product Service Code).

    PSC classification rules:
    - Numeric PSC (e.g., "1234") → Product (high confidence)
    - PSC starting with A or B → R&D (moderate confidence)
    - PSC starting with D/E/F → Handled separately (IT/telecom/space)
    - Other alphabetic PSC → Service (moderate confidence)

    Confidence levels:
    - High (0.95): Numeric PSCs - strong product indicator
    - Moderate (0.75): Alphabetic PSCs - less definitive

    Args:
        psc: Product Service Code

    Returns:
        Tuple of (classification, method, confidence)
    """
    if not psc:
        return ("Service", "default", 0.50)

    # Get first character of PSC
    first_char = psc[0].upper()

    # Numeric PSC → Product (high confidence)
    if first_char.isdigit():
        return ("Product", "psc_numeric", 0.95)

    # PSC starting with A or B → R&D (moderate confidence)
    if first_char in ("A", "B"):
        return ("R&D", "psc_rd", 0.75)

    # PSC D/E/F handled separately in main classification logic
    # Other alphabetic PSC → Service (moderate confidence)
    return ("Service", "psc_alphabetic", 0.75)


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
            psc_families.add(c.psc[0].upper())

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
