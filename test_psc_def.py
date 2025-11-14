#!/usr/bin/env python3
"""Test PSC D/E/F handling and confidence levels."""

from src.transformers.company_categorization import classify_contract

print("=" * 80)
print("Testing PSC D/E/F (IT/Telecom/Space) Classification")
print("=" * 80)

# Test 1: PSC D + FFP → Product
test1 = {
    "award_id": "TEST_D_FFP",
    "psc": "D302",  # IT services
    "contract_type": None,
    "pricing": "FFP",
    "description": "Software development",
    "award_amount": 100000,
    "sbir_phase": None,
}
result1 = classify_contract(test1)
print(f"\n1. PSC D + FFP:")
print(f"   PSC: {test1['psc']} | Pricing: {test1['pricing']}")
print(f"   → Classification: {result1.classification}")
print(f"   → Method: {result1.method}")
print(f"   → Confidence: {result1.confidence}")
assert result1.classification == "Product", f"Expected Product, got {result1.classification}"
assert result1.method == "psc_def_ffp", f"Expected psc_def_ffp, got {result1.method}"
assert result1.confidence == 0.75, f"Expected 0.75 confidence, got {result1.confidence}"
print("   ✓ PASS")

# Test 2: PSC E + FFP → Product
test2 = {
    "award_id": "TEST_E_FFP",
    "psc": "E201",  # Telecom
    "contract_type": None,
    "pricing": "FFP",
    "description": "Network equipment",
    "award_amount": 200000,
    "sbir_phase": None,
}
result2 = classify_contract(test2)
print(f"\n2. PSC E + FFP:")
print(f"   PSC: {test2['psc']} | Pricing: {test2['pricing']}")
print(f"   → Classification: {result2.classification}")
print(f"   → Method: {result2.method}")
print(f"   → Confidence: {result2.confidence}")
assert result2.classification == "Product", f"Expected Product, got {result2.classification}"
assert result2.method == "psc_def_ffp", f"Expected psc_def_ffp, got {result2.method}"
assert result2.confidence == 0.75, f"Expected 0.75 confidence, got {result2.confidence}"
print("   ✓ PASS")

# Test 3: PSC F + FFP → Product
test3 = {
    "award_id": "TEST_F_FFP",
    "psc": "F999",  # Space systems
    "contract_type": None,
    "pricing": "FFP",
    "description": "Satellite components",
    "award_amount": 500000,
    "sbir_phase": None,
}
result3 = classify_contract(test3)
print(f"\n3. PSC F + FFP:")
print(f"   PSC: {test3['psc']} | Pricing: {test3['pricing']}")
print(f"   → Classification: {result3.classification}")
print(f"   → Method: {result3.method}")
print(f"   → Confidence: {result3.confidence}")
assert result3.classification == "Product", f"Expected Product, got {result3.classification}"
assert result3.method == "psc_def_ffp", f"Expected psc_def_ffp, got {result3.method}"
assert result3.confidence == 0.75, f"Expected 0.75 confidence, got {result3.confidence}"
print("   ✓ PASS")

# Test 4: PSC D + no pricing → Service
test4 = {
    "award_id": "TEST_D_NONE",
    "psc": "D302",
    "contract_type": None,
    "pricing": None,
    "description": "IT consulting",
    "award_amount": 150000,
    "sbir_phase": None,
}
result4 = classify_contract(test4)
print(f"\n4. PSC D + no pricing:")
print(f"   PSC: {test4['psc']} | Pricing: {test4['pricing']}")
print(f"   → Classification: {result4.classification}")
print(f"   → Method: {result4.method}")
print(f"   → Confidence: {result4.confidence}")
assert result4.classification == "Service", f"Expected Service, got {result4.classification}"
assert result4.method == "psc_def_service", f"Expected psc_def_service, got {result4.method}"
assert result4.confidence == 0.75, f"Expected 0.75 confidence, got {result4.confidence}"
print("   ✓ PASS")

# Test 5: PSC D + CPFF → Service (contract type override)
test5 = {
    "award_id": "TEST_D_CPFF",
    "psc": "D302",
    "contract_type": "CPFF",
    "pricing": "CPFF",
    "description": "Software engineering services",
    "award_amount": 300000,
    "sbir_phase": None,
}
result5 = classify_contract(test5)
print(f"\n5. PSC D + CPFF (contract type override):")
print(f"   PSC: {test5['psc']} | Type: {test5['contract_type']}")
print(f"   → Classification: {result5.classification}")
print(f"   → Method: {result5.method}")
print(f"   → Confidence: {result5.confidence}")
assert result5.classification == "Service", f"Expected Service, got {result5.classification}"
assert result5.method == "contract_type", f"Expected contract_type, got {result5.method}"
assert result5.confidence == 0.95, f"Expected 0.95 confidence, got {result5.confidence}"
print("   ✓ PASS (contract type override beats PSC D/E/F)")

print("\n" + "=" * 80)
print("Testing Confidence Levels: High for Numeric, Moderate for Alphabetic")
print("=" * 80)

# Test 6: Numeric PSC → High confidence (0.95)
test6 = {
    "award_id": "TEST_NUMERIC",
    "psc": "5820",
    "contract_type": None,
    "pricing": None,
    "description": "Hardware",
    "award_amount": 100000,
    "sbir_phase": None,
}
result6 = classify_contract(test6)
print(f"\n6. Numeric PSC (high confidence):")
print(f"   PSC: {test6['psc']}")
print(f"   → Classification: {result6.classification}")
print(f"   → Confidence: {result6.confidence}")
assert result6.classification == "Product", f"Expected Product, got {result6.classification}"
assert result6.confidence == 0.95, f"Expected 0.95 confidence, got {result6.confidence}"
print("   ✓ PASS (high confidence for numeric PSC)")

# Test 7: Alphabetic PSC (non-D/E/F) → Moderate confidence (0.75)
test7 = {
    "award_id": "TEST_ALPHA",
    "psc": "R425",
    "contract_type": None,
    "pricing": None,
    "description": "Research services",
    "award_amount": 100000,
    "sbir_phase": None,
}
result7 = classify_contract(test7)
print(f"\n7. Alphabetic PSC (moderate confidence):")
print(f"   PSC: {test7['psc']}")
print(f"   → Classification: {result7.classification}")
print(f"   → Confidence: {result7.confidence}")
assert result7.classification == "Service", f"Expected Service, got {result7.classification}"
assert result7.confidence == 0.75, f"Expected 0.75 confidence, got {result7.confidence}"
print("   ✓ PASS (moderate confidence for alphabetic PSC)")

# Test 8: PSC A/B (R&D) → Moderate confidence (0.75)
test8 = {
    "award_id": "TEST_RD",
    "psc": "A123",
    "contract_type": None,
    "pricing": None,
    "description": "Basic research",
    "award_amount": 100000,
    "sbir_phase": None,
}
result8 = classify_contract(test8)
print(f"\n8. PSC A/B R&D (moderate confidence):")
print(f"   PSC: {test8['psc']}")
print(f"   → Classification: {result8.classification}")
print(f"   → Confidence: {result8.confidence}")
assert result8.classification == "R&D", f"Expected R&D, got {result8.classification}"
assert result8.confidence == 0.75, f"Expected 0.75 confidence, got {result8.confidence}"
print("   ✓ PASS (moderate confidence for R&D PSC)")

print("\n" + "=" * 80)
print("✓ ALL TESTS PASSED!")
print("=" * 80)
print("\nSummary:")
print("  - PSC D/E/F + FFP → Product (0.75 confidence)")
print("  - PSC D/E/F + no pricing → Service (0.75 confidence)")
print("  - PSC D/E/F + CPFF → Service via contract type override (0.95 confidence)")
print("  - Numeric PSC → High confidence (0.95)")
print("  - Alphabetic PSC → Moderate confidence (0.75)")
