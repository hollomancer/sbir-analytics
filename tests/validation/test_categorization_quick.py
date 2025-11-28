#!/usr/bin/env python3
"""Quick test script for company categorization system.

Run this to verify the basic classification logic works correctly.
"""

from src.transformers.company_categorization import (
    aggregate_company_classification,
    classify_contract,
)


print("=" * 80)
print("Company Categorization - Quick Test")
print("=" * 80)

# Test 1: Contract Classification - Numeric PSC (Product)
print("\n1. Testing contract classification - Numeric PSC (Product)")
contract1 = {
    "award_id": "TEST001",
    "psc": "1234",
    "contract_type": "FFP",
    "pricing": "FFP",
    "description": "Hardware development",
    "award_amount": 100000,
}
result1 = classify_contract(contract1)
print(f"   PSC: {contract1['psc']}")
print(f"   Result: {result1.classification}")
print(f"   Method: {result1.method}")
print(f"   Confidence: {result1.confidence}")
assert result1.classification == "Product", "Expected Product classification"
print("   ✓ PASS")

# Test 2: Contract Classification - Alphabetic PSC (Service)
print("\n2. Testing contract classification - Alphabetic PSC (Service)")
contract2 = {
    "award_id": "TEST002",
    "psc": "R425",
    "contract_type": "FFP",
    "pricing": "FFP",
    "description": "Consulting services",
    "award_amount": 150000,
}
result2 = classify_contract(contract2)
print(f"   PSC: {contract2['psc']}")
print(f"   Result: {result2.classification}")
print(f"   Method: {result2.method}")
assert result2.classification == "Service", "Expected Service classification"
print("   ✓ PASS")

# Test 3: Contract Classification - R&D PSC
print("\n3. Testing contract classification - R&D PSC (starts with A)")
contract3 = {
    "award_id": "TEST003",
    "psc": "A123",
    "contract_type": "FFP",
    "pricing": "FFP",
    "description": "Basic research",
    "award_amount": 200000,
}
result3 = classify_contract(contract3)
print(f"   PSC: {contract3['psc']}")
print(f"   Result: {result3.classification}")
print(f"   Method: {result3.method}")
# Note: R&D PSC codes are treated as Service for Fixed Price contracts
assert result3.classification == "Service", "Expected Service classification (R&D PSC treated as Service for FFP)"
assert result3.method == "fixed_price_rd_psc_as_service", "Expected fixed_price_rd_psc_as_service method"
print("   ✓ PASS")

# Test 4: Contract Type Override - CPFF → Service
print("\n4. Testing contract type override - CPFF → Service")
contract4 = {
    "award_id": "TEST004",
    "psc": "1234",  # Numeric (would be Product)
    "contract_type": "CPFF",  # But CPFF overrides to Service
    "pricing": "CPFF",
    "description": "Development work",
    "award_amount": 250000,
}
result4 = classify_contract(contract4)
print(f"   PSC: {contract4['psc']} (numeric - normally Product)")
print(f"   Contract Type: {contract4['contract_type']}")
print(f"   Result: {result4.classification}")
print(f"   Method: {result4.method}")
assert result4.classification == "Service", "Expected Service due to CPFF override"
print("   ✓ PASS")

# Test 5: Description Inference - FFP with product keywords
print("\n5. Testing description inference - FFP with 'prototype'")
contract5 = {
    "award_id": "TEST005",
    "psc": "R425",  # Alphabetic (would be Service)
    "contract_type": "FFP",
    "pricing": "FFP",
    "description": "Development of a prototype device",
    "award_amount": 180000,
}
result5 = classify_contract(contract5)
print(f"   PSC: {contract5['psc']} (alphabetic - normally Service)")
print(f"   Description: '{contract5['description']}'")
print(f"   Result: {result5.classification}")
print(f"   Method: {result5.method}")
assert result5.classification == "Product", "Expected Product due to 'prototype' keyword"
print("   ✓ PASS")

# Test 6: SBIR Phase Adjustment - Phase I → R&D
print("\n6. Testing SBIR phase adjustment - Phase I → R&D")
contract6 = {
    "award_id": "TEST006",
    "psc": "R425",
    "contract_type": "FFP",
    "pricing": "FFP",
    "description": "SBIR Phase I research",
    "award_amount": 150000,
    "sbir_phase": "I",
}
result6 = classify_contract(contract6)
print(f"   PSC: {contract6['psc']}")
print(f"   SBIR Phase: {contract6['sbir_phase']}")
print(f"   Result: {result6.classification}")
print(f"   Method: {result6.method}")
assert result6.classification == "R&D", "Expected R&D for SBIR Phase I"
print("   ✓ PASS")

# Test 7: Company Aggregation - Product-leaning
print("\n7. Testing company aggregation - Product-leaning (>60%)")
contracts_product = [
    {"award_id": "C1", "classification": "Product", "award_amount": 300000, "psc": "1234"},
    {"award_id": "C2", "classification": "Product", "award_amount": 200000, "psc": "5678"},
    {"award_id": "C3", "classification": "Service", "award_amount": 100000, "psc": "R425"},
]
company_result1 = aggregate_company_classification(
    contracts_product, "TEST123UEI000", "Test Company 1"
)
print(f"   Total Dollars: ${company_result1.total_dollars:,.0f}")
print(f"   Product Dollars: ${company_result1.product_dollars:,.0f}")
print(f"   Product %: {company_result1.product_pct:.1f}%")
print(f"   Classification: {company_result1.classification}")
print(f"   Confidence: {company_result1.confidence}")
assert company_result1.classification == "Product-leaning", "Expected Product-leaning"
assert company_result1.product_pct >= 51, "Expected >=51% product"
print("   ✓ PASS")

# Test 8: Company Aggregation - Service-leaning
print("\n8. Testing company aggregation - Service-leaning (>=51%)")
contracts_service = [
    {"award_id": "C1", "classification": "Service", "award_amount": 300000, "psc": "R425"},
    {"award_id": "C2", "classification": "R&D", "award_amount": 200000, "psc": "A123"},
    {"award_id": "C3", "classification": "Product", "award_amount": 100000, "psc": "1234"},
]
company_result2 = aggregate_company_classification(
    contracts_service, "TEST456UEI000", "Test Company 2"
)
print(f"   Total Dollars: ${company_result2.total_dollars:,.0f}")
print(f"   Service/R&D Dollars: ${company_result2.service_rd_dollars:,.0f}")
print(f"   Service %: {company_result2.service_pct:.1f}%")
print(f"   Classification: {company_result2.classification}")
print(f"   Confidence: {company_result2.confidence}")
assert company_result2.classification == "Service-leaning", "Expected Service-leaning"
assert company_result2.service_pct >= 51, "Expected >=51% service"
print("   ✓ PASS")

# Test 9: Company Aggregation - Mixed
print("\n9. Testing company aggregation - Mixed (neither >=51%)")
contracts_mixed = [
    {"award_id": "C1", "classification": "Product", "award_amount": 250000, "psc": "1234"},
    {"award_id": "C2", "classification": "Service", "award_amount": 250000, "psc": "R425"},
]
company_result3 = aggregate_company_classification(
    contracts_mixed, "TEST789UEI000", "Test Company 3"
)
print(f"   Product %: {company_result3.product_pct:.1f}%")
print(f"   Service %: {company_result3.service_pct:.1f}%")
print(f"   Classification: {company_result3.classification}")
assert company_result3.classification == "Mixed", "Expected Mixed classification"
print("   ✓ PASS")

# Test 10: Company Aggregation - Uncertain (insufficient awards)
print("\n10. Testing company aggregation - Uncertain (<2 awards)")
contracts_few = [
    {"award_id": "C1", "classification": "Product", "award_amount": 100000, "psc": "1234"},
]
company_result4 = aggregate_company_classification(contracts_few, "TEST000UEI000", "Test Company 4")
print(f"   Award Count: {company_result4.award_count}")
print(f"   Classification: {company_result4.classification}")
print(f"   Confidence: {company_result4.confidence}")
print(f"   Override Reason: {company_result4.override_reason}")
assert company_result4.classification == "Uncertain", "Expected Uncertain for <2 awards"
assert company_result4.confidence == "Low", "Expected Low confidence"
print("   ✓ PASS")

# Test 11: Confidence Levels
print("\n11. Testing confidence level assignment")
# Low confidence (<=2 awards)
low_conf = [
    {"award_id": "C1", "classification": "Product", "award_amount": 100000, "psc": "1234"},
    {"award_id": "C2", "classification": "Product", "award_amount": 100000, "psc": "5678"},
]
result_low = aggregate_company_classification(low_conf, "LOW001", "Low Conf Co")
print(f"   Low Confidence ({result_low.award_count} awards): {result_low.confidence}")
assert result_low.confidence == "Low", "Expected Low confidence"

# Medium confidence (2-5 awards)
medium_conf = low_conf + [
    {"award_id": "C3", "classification": "Product", "award_amount": 100000, "psc": "9012"},
]
result_medium = aggregate_company_classification(medium_conf, "MED001", "Medium Conf Co")
print(f"   Medium Confidence ({result_medium.award_count} awards): {result_medium.confidence}")
assert result_medium.confidence == "Medium", "Expected Medium confidence"

# High confidence (>5 awards)
high_conf = medium_conf + [
    {"award_id": "C4", "classification": "Product", "award_amount": 100000, "psc": "3456"},
    {"award_id": "C5", "classification": "Product", "award_amount": 100000, "psc": "7890"},
    {"award_id": "C6", "classification": "Product", "award_amount": 100000, "psc": "2345"},
]
result_high = aggregate_company_classification(high_conf, "HIGH001", "High Conf Co")
print(f"   High Confidence ({result_high.award_count} awards): {result_high.confidence}")
assert result_high.confidence == "High", "Expected High confidence"
print("   ✓ PASS")

print("\n" + "=" * 80)
print("✓ ALL TESTS PASSED!")
print("=" * 80)
print("\nThe company categorization system is working correctly.")
print("Next steps:")
print("  1. Run integration tests with real USAspending data")
print("  2. Execute the Dagster asset: enriched_sbir_companies_with_categorization")
print("  3. Validate against high-volume SBIR companies dataset")
