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

from typing import Union

from loguru import logger

from src.models.categorization import CompanyClassification, ContractClassification


def classify_contract(contract: dict) -> ContractClassification:
    """Classify a single federal contract/award.

    Classification logic (in priority order):
    1. Cost Reimbursement Contracts (CPFF, CPIF, CPAF, CPOF, Cost-Type) → Service-based
    2. Labor Hours Contracts (T&M, LH) → Service-based
    3. Fixed Price Contracts (FFP, FPIF, FPEPA) → Product-based (when PSC/keywords support it)
    4. PSC-based: numeric → Product, A/B → R&D, alphabetic → Service
    5. Description inference: product keywords → Product
    6. SBIR phase adjustment: Phase I/II → R&D (unless numeric PSC)

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
    psc = contract.get("psc", "")
    contract_type = contract.get("contract_type", "")
    pricing = contract.get("pricing", "")
    description = contract.get("description", "") or ""
    award_amount = contract.get("award_amount")
    sbir_phase = contract.get("sbir_phase")

    # --- Rule 1: Contract type overrides (highest priority) ---
    # Cost Reimbursement Contracts → Service-based
    # Labor Hours Contracts → Service-based
    if _is_service_contract_type(contract_type, pricing):
        return ContractClassification(
            award_id=award_id,
            classification="Service",
            method="contract_type_service",
            confidence=0.95,
            psc=psc or None,
            contract_type=contract_type or None,
            pricing=pricing or None,
            description=description or None,
            award_amount=award_amount,
            sbir_phase=sbir_phase,
        )

    # --- Rule 2: Fixed Price Contracts → Product-based (when PSC supports it) ---
    # Fixed Price contracts are product-based if they have numeric PSC or product keywords
    if _is_fixed_price_contract_type(contract_type, pricing):
        # Check if PSC indicates product
        if psc:
            psc_classification, psc_method, psc_confidence = _classify_by_psc(psc)
            # Fixed Price + numeric PSC → Product
            if psc_classification == "Product":
                return ContractClassification(
                    award_id=award_id,
                    classification="Product",
                    method="fixed_price_numeric_psc",
                    confidence=0.95,
                    psc=psc,
                    contract_type=contract_type or None,
                    pricing=pricing or None,
                    description=description or None,
                    award_amount=award_amount,
                    sbir_phase=sbir_phase,
                )
            # Fixed Price + R&D PSC → R&D
            if psc_classification == "R&D":
                return ContractClassification(
                    award_id=award_id,
                    classification="R&D",
                    method="fixed_price_rd_psc",
                    confidence=0.90,
                    psc=psc,
                    contract_type=contract_type or None,
                    pricing=pricing or None,
                    description=description or None,
                    award_amount=award_amount,
                    sbir_phase=sbir_phase,
                )
        
        # Fixed Price + product keywords → Product
        product_match = _check_product_keywords(description)
        if product_match:
            return ContractClassification(
                award_id=award_id,
                classification="Product",
                method="fixed_price_product_keywords",
                confidence=0.90,
                psc=psc or None,
                contract_type=contract_type or None,
                pricing=pricing or None,
                description=description or None,
                award_amount=award_amount,
                sbir_phase=sbir_phase,
            )
        
        # Fixed Price without clear product indicators → default to Product (but lower confidence)
        # This reflects that Fixed Price contracts are typically product-based
        return ContractClassification(
            award_id=award_id,
            classification="Product",
            method="fixed_price_default",
            confidence=0.75,
            psc=psc or None,
            contract_type=contract_type or None,
            pricing=pricing or None,
            description=description or None,
            award_amount=award_amount,
            sbir_phase=sbir_phase,
        )

    # --- Rule 3: PSC-based classification ---
    if psc:
        psc_classification, psc_method, psc_confidence = _classify_by_psc(psc)

        # --- Rule 4: Description inference (only for non-R&D PSC) ---
        # Product keywords can override alphabetic PSC → Product
        if psc_classification != "R&D":
            product_match = _check_product_keywords(description)
            if product_match:
                return ContractClassification(
                    award_id=award_id,
                    classification="Product",
                    method="description_inference",
                    confidence=0.85,
                    psc=psc,
                    contract_type=contract_type or None,
                    pricing=pricing or None,
                    description=description or None,
                    award_amount=award_amount,
                    sbir_phase=sbir_phase,
                )

        # --- Rule 5: SBIR phase adjustment ---
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


def is_cost_based_contract(contract_type: str, pricing: str) -> bool:
    """Check if contract type or pricing indicates cost-based contract.

    Cost-based contracts:
    - Cost Reimbursement Contracts: CPFF, CPIF, CPAF, CPOF, Cost-Type, Cost Plus

    Args:
        contract_type: Contract type string
        pricing: Pricing type string

    Returns:
        True if contract type indicates cost-based contract
    """
    if not contract_type and not pricing:
        return False

    # Normalize to uppercase for comparison
    ct = contract_type.upper() if contract_type else ""
    pr = pricing.upper() if pricing else ""

    # Cost Reimbursement Contracts
    cost_reimbursement_types = {
        "CPFF",  # Cost Plus Fixed Fee
        "CPIF",  # Cost Plus Incentive Fee
        "CPAF",  # Cost Plus Award Fee
        "CPOF",  # Cost Plus Other Fee
        "COST-TYPE",
        "COST TYPE",
        "COST PLUS",
        "COST+",
    }
    if any(crt in ct for crt in cost_reimbursement_types):
        return True
    if any(crt in pr for crt in cost_reimbursement_types):
        return True

    return False


def is_service_based_contract(contract_type: str, pricing: str) -> bool:
    """Check if contract type or pricing indicates service-based contract.

    Service-based contracts:
    - Labor Hours Contracts: T&M (Time and Materials), LH (Labor Hours)

    Args:
        contract_type: Contract type string
        pricing: Pricing type string

    Returns:
        True if contract type indicates service-based contract
    """
    if not contract_type and not pricing:
        return False

    # Normalize to uppercase for comparison
    ct = contract_type.upper() if contract_type else ""
    pr = pricing.upper() if pricing else ""

    # Labor Hours Contracts
    labor_hours_types = {
        "T&M",
        "T & M",
        "TIME AND MATERIALS",
        "TIME & MATERIALS",
        "LH",
        "LABOR HOURS",
        "LABOR-HOURS",
    }
    if any(lht in ct for lht in labor_hours_types):
        return True
    if any(lht in pr for lht in labor_hours_types):
        return True

    return False


def _is_service_contract_type(contract_type: str, pricing: str) -> bool:
    """Check if contract type or pricing indicates service work.

    Service-based contracts:
    - Cost Reimbursement Contracts: CPFF, CPIF, CPAF, CPOF, Cost-Type, Cost Plus
    - Labor Hours Contracts: T&M (Time and Materials), LH (Labor Hours)

    Args:
        contract_type: Contract type string
        pricing: Pricing type string

    Returns:
        True if contract type indicates service work
    """
    return is_cost_based_contract(contract_type, pricing) or is_service_based_contract(contract_type, pricing)


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

    # Handle edge case where PSC might be a dict instead of string
    if isinstance(psc, dict):
        # Try to extract the code from the dict
        psc = psc.get("code") or psc.get("psc_code") or psc.get("psc") or ""
        if not psc:
            return ("Service", "default", 0.50)

    # Ensure PSC is a string
    if not isinstance(psc, str):
        return ("Service", "default", 0.50)

    # Get first character of PSC
    first_char = psc[0].upper()

    # Numeric PSC → Product
    if first_char.isdigit():
        return ("Product", "psc_numeric", 0.90)

    # PSC starting with A or B → R&D
    if first_char in ("A", "B"):
        return ("R&D", "psc_rd", 0.90)

    # Other alphabetic PSC → Service
    return ("Service", "psc_alphabetic", 0.90)


def _is_fixed_price_contract_type(contract_type: str, pricing: str) -> bool:
    """Check if contract type or pricing indicates fixed price contract.

    Fixed Price Contracts → Product-based (when combined with numeric PSC or product keywords)

    Fixed Price contract types:
    - FFP (Firm Fixed Price)
    - FPIF (Fixed Price Incentive Firm)
    - FPEPA (Fixed Price with Economic Price Adjustment)
    - FPI (Fixed Price Incentive)
    - FP (Fixed Price)

    Args:
        contract_type: Contract type string
        pricing: Pricing type string

    Returns:
        True if contract type indicates fixed price contract
    """
    if not contract_type and not pricing:
        return False

    # Normalize to uppercase for comparison
    ct = contract_type.upper() if contract_type else ""
    pr = pricing.upper() if pricing else ""

    # Fixed Price Contracts → Product-based
    fixed_price_types = {
        "FFP",  # Firm Fixed Price
        "FPIF",  # Fixed Price Incentive Firm
        "FPEPA",  # Fixed Price with Economic Price Adjustment
        "FPI",  # Fixed Price Incentive
        "FP",  # Fixed Price
        "FIXED PRICE",
        "FIRM FIXED PRICE",
    }
    if any(fpt in ct for fpt in fixed_price_types):
        return True
    if any(fpt in pr for fpt in fixed_price_types):
        return True

    return False


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
    contracts: list[Union[dict, ContractClassification]],
    company_uei: str | None = None,
    company_name: str = "",
) -> CompanyClassification:
    """Aggregate contract classifications to company level.

    Aggregation logic:
    1. Calculate dollar-weighted percentages for Product, Service, and R&D separately
    2. Apply 51% threshold for Product-leaning, Service-leaning, or R&D-leaning
    3. Apply Mixed classification if no category reaches threshold
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
        logger.warning(f"Company {company_uei or company_name or 'Unknown'} has fewer than 2 contracts, classifying as Uncertain")
        return CompanyClassification(
            company_uei=company_uei,
            company_name=company_name or "Unknown",
            classification="Uncertain",
            product_pct=0.0,
            service_pct=0.0,
            rd_pct=0.0,
            confidence="Low",
            award_count=len(contracts),
            psc_family_count=0,
            total_dollars=0.0,
            product_dollars=0.0,
            service_dollars=0.0,
            rd_dollars=0.0,
            override_reason="insufficient_awards",
            contracts=[],
        )

    # Convert dicts to ContractClassification objects if needed
    classified_contracts: list[ContractClassification] = []
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

    # Calculate dollar-weighted percentages (separate R&D from Service)
    total_dollars = sum(c.award_amount or 0.0 for c in classified_contracts)
    product_dollars = sum(
        c.award_amount or 0.0
        for c in classified_contracts
        if c.classification == "Product"
    )
    service_dollars = sum(
        c.award_amount or 0.0
        for c in classified_contracts
        if c.classification == "Service"
    )
    rd_dollars = sum(
        c.award_amount or 0.0
        for c in classified_contracts
        if c.classification == "R&D"
    )

    # Calculate percentages
    if total_dollars > 0:
        product_pct = (product_dollars / total_dollars) * 100
        service_pct = (service_dollars / total_dollars) * 100
        rd_pct = (rd_dollars / total_dollars) * 100
    else:
        product_pct = 0.0
        service_pct = 0.0
        rd_pct = 0.0

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
            f"Company {company_uei or company_name or 'Unknown'} has {len(psc_families)} PSC families, "
            f"overriding to Mixed classification"
        )
    # Standard classification based on thresholds (three categories)
    elif product_pct >= 51:
        classification = "Product-leaning"
    elif service_pct >= 51:
        classification = "Service-leaning"
    elif rd_pct >= 51:
        classification = "R&D-leaning"
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
        f"Classified company {company_uei or company_name or 'Unknown'} as {classification} "
        f"({len(classified_contracts)} awards, {confidence} confidence) - "
        f"Product: {product_pct:.1f}%, Service: {service_pct:.1f}%, R&D: {rd_pct:.1f}%"
    )

    return CompanyClassification(
        company_uei=company_uei,
        company_name=company_name or "Unknown",
        classification=classification,
        product_pct=round(product_pct, 2),
        service_pct=round(service_pct, 2),
        rd_pct=round(rd_pct, 2),
        confidence=confidence,
        award_count=len(classified_contracts),
        psc_family_count=len(psc_families),
        total_dollars=total_dollars,
        product_dollars=product_dollars,
        service_dollars=service_dollars,
        rd_dollars=rd_dollars,
        override_reason=override_reason,
        contracts=classified_contracts,
    )
