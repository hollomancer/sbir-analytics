#!/usr/bin/env python3
"""Quick test of USAspending API integration."""

from loguru import logger

from src.enrichers.company_categorization import retrieve_company_contracts_api
from src.transformers.company_categorization import (
    aggregate_company_classification,
    classify_contract,
)

# Test with a known company UEI
# Using a well-known contractor as an example
TEST_UEI = "J1AENMB5K3L6"  # Example UEI

logger.info(f"Testing USAspending API integration with UEI: {TEST_UEI}")
logger.info("=" * 80)

# Retrieve contracts from API
logger.info("Step 1: Retrieving contracts from USAspending API...")
contracts_df = retrieve_company_contracts_api(uei=TEST_UEI, limit=50)

if contracts_df.empty:
    logger.warning("No contracts found - this may be expected if the UEI doesn't exist")
    logger.info("API integration is working (returned empty DataFrame successfully)")
else:
    logger.info(f"✓ Successfully retrieved {len(contracts_df)} contracts")
    logger.info(f"  Columns: {', '.join(contracts_df.columns)}")
    logger.info(f"  Total award amount: ${contracts_df['award_amount'].sum():,.2f}")

    # Show sample contracts
    logger.info("\nSample contracts:")
    for i, (_, contract) in enumerate(contracts_df.head(3).iterrows()):
        logger.info(f"  {i+1}. PSC={contract['psc']}, Amount=${contract['award_amount']:,.0f}")

    # Test classification
    logger.info("\nStep 2: Classifying contracts...")
    classified_contracts = []
    for _, contract in contracts_df.iterrows():
        contract_dict = contract.to_dict()
        classified = classify_contract(contract_dict)
        classified_contracts.append(classified.model_dump())

    # Count classifications
    product_count = sum(1 for c in classified_contracts if c["classification"] == "Product")
    service_count = sum(1 for c in classified_contracts if c["classification"] == "Service")
    rd_count = sum(1 for c in classified_contracts if c["classification"] == "R&D")

    logger.info(f"  Product: {product_count}, Service: {service_count}, R&D: {rd_count}")

    # Aggregate to company level
    logger.info("\nStep 3: Aggregating to company classification...")
    company_result = aggregate_company_classification(
        classified_contracts,
        company_uei=TEST_UEI,
        company_name="Test Company"
    )

    logger.info(f"  Classification: {company_result.classification}")
    logger.info(f"  Product %: {company_result.product_pct:.1f}%")
    logger.info(f"  Service %: {company_result.service_pct:.1f}%")
    logger.info(f"  Confidence: {company_result.confidence}")
    logger.info(f"  Awards: {company_result.award_count}")
    logger.info(f"  Total $: ${company_result.total_dollars:,.0f}")

logger.info("\n" + "=" * 80)
logger.info("✓ API INTEGRATION TEST COMPLETE")
logger.info("=" * 80)
