#!/usr/bin/env python3
"""Test restructured classification logic: PSC primary, pricing confirms."""

from src.transformers.company_categorization import classify_contract

print("=" * 80)
print("RESTRUCTURED CLASSIFICATION LOGIC TEST")
print("PSC = PRIMARY SIGNAL (the noun)")
print("Pricing = SECONDARY SIGNAL (confirms or creates ambiguity)")
print("=" * 80)

tests_passed = 0
tests_total = 0

def test(name, contract, expected_classification, expected_confidence_min, expected_confidence_max=None):
    global tests_passed, tests_total
    tests_total += 1

    result = classify_contract(contract)

    if expected_confidence_max is None:
        expected_confidence_max = expected_confidence_min

    classification_match = result.classification == expected_classification
    confidence_match = expected_confidence_min <= result.confidence <= expected_confidence_max

    status = "✓ PASS" if (classification_match and confidence_match) else "✗ FAIL"

    if classification_match and confidence_match:
        tests_passed += 1

    print(f"\n{tests_total}. {name}")
    print(f"   PSC: {contract.get('psc')} | Pricing: {contract.get('pricing')}")
    print(f"   → {result.classification} (confidence: {result.confidence:.2f}, method: {result.method})")
    print(f"   Expected: {expected_classification} ({expected_confidence_min:.2f}-{expected_confidence_max:.2f})")
    print(f"   {status}")

    if not classification_match:
        print(f"   ERROR: Expected {expected_classification}, got {result.classification}")
    if not confidence_match:
        print(f"   ERROR: Confidence {result.confidence:.2f} outside expected range")

    return result

print("\n" + "=" * 80)
print("HIGH AGREEMENT ZONES (High Confidence 0.90-0.95)")
print("=" * 80)

# Test 1: PSC numeric + FFP → Product (high agreement)
test("PSC numeric + FFP (high agreement)",
    {"award_id": "T1", "psc": "5820", "pricing": "FFP", "description": "Radio equipment"},
    "Product", 0.90, 0.95)

# Test 2: PSC R&D + CPFF → R&D (high agreement)
test("PSC R&D + CPFF (high agreement)",
    {"award_id": "T2", "psc": "A123", "pricing": "CPFF", "description": "Research services"},
    "R&D", 0.90, 0.95)

# Test 3: PSC service + CPFF → Service (high agreement)
test("PSC service + CPFF (high agreement)",
    {"award_id": "T3", "psc": "R425", "pricing": "CPFF", "description": "Engineering services"},
    "Service", 0.90, 0.95)

# Test 4: PSC service + T&M → Service (high agreement)
test("PSC service + T&M (high agreement)",
    {"award_id": "T4", "psc": "R425", "pricing": "T&M", "description": "Staff augmentation"},
    "Service", 0.90, 0.95)

print("\n" + "=" * 80)
print("LOW AGREEMENT ZONES (Lower Confidence 0.60-0.70)")
print("=" * 80)

# Test 5: PSC numeric + CPFF → Product but low confidence (unusual)
test("PSC numeric + CPFF (low agreement - unusual)",
    {"award_id": "T5", "psc": "5820", "pricing": "CPFF", "description": "Prototype development"},
    "Product", 0.60, 0.70)

# Test 6: PSC service + FFP → Service but low confidence (integrators)
test("PSC service + FFP (low agreement - integrators)",
    {"award_id": "T6", "psc": "R425", "pricing": "FFP", "description": "System integration"},
    "Service", 0.60, 0.70)

# Test 7: PSC numeric + T&M → Product but low confidence (unusual)
test("PSC numeric + T&M (low agreement - unusual)",
    {"award_id": "T7", "psc": "5820", "pricing": "T&M", "description": "Technical support"},
    "Product", 0.60, 0.70)

print("\n" + "=" * 80)
print("PSC PRIMARY: CPFF doesn't override numeric PSC")
print("=" * 80)

# Test 8: CRITICAL - PSC numeric + CPFF stays Product (PSC wins)
result8 = test("PSC numeric + CPFF → PRODUCT (not Service)",
    {"award_id": "T8", "psc": "5820", "pricing": "CPFF", "description": "Hardware development"},
    "Product", 0.60, 0.70)
print(f"   CRITICAL: PSC is primary - numeric PSC stays Product even with CPFF")

print("\n" + "=" * 80)
print("PSC D/E/F (IT/Telecom/Space) Handling")
print("=" * 80)

# Test 9: PSC D + FFP → Product
test("PSC D + FFP",
    {"award_id": "T9", "psc": "D302", "pricing": "FFP", "description": "Software delivery"},
    "Product", 0.75, 0.85)

# Test 10: PSC E + no pricing → Service
test("PSC E + no pricing",
    {"award_id": "T10", "psc": "E201", "pricing": None, "description": "Telecom services"},
    "Service", 0.70, 0.80)

print("\n" + "=" * 80)
print("Description Inference (FFP + Service PSC + Product Keywords)")
print("=" * 80)

# Test 11: Service PSC + FFP + product keywords → Product
test("Service PSC + FFP + 'hardware' → Product",
    {"award_id": "T11", "psc": "R425", "pricing": "FFP", "description": "Development of prototype hardware"},
    "Product", 0.70, 0.80)

# Test 12: Service PSC + FFP + no keywords → Service (low conf)
test("Service PSC + FFP + no keywords → Service",
    {"award_id": "T12", "psc": "R425", "pricing": "FFP", "description": "System integration services"},
    "Service", 0.60, 0.70)

print("\n" + "=" * 80)
print("SBIR Phase Adjustment")
print("=" * 80)

# Test 13: SBIR I + numeric PSC → Product
test("SBIR Phase I + numeric PSC → Product",
    {"award_id": "T13", "psc": "5820", "pricing": None, "sbir_phase": "I"},
    "Product", 0.85, 0.95)

# Test 14: SBIR I + alphabetic PSC → R&D
test("SBIR Phase I + alphabetic PSC → R&D",
    {"award_id": "T14", "psc": "R425", "pricing": None, "sbir_phase": "I"},
    "R&D", 0.80, 0.90)

print("\n" + "=" * 80)
print(f"RESULTS: {tests_passed}/{tests_total} tests passed")
print("=" * 80)

if tests_passed == tests_total:
    print("✓ ALL TESTS PASSED!")
    print("\nKey Principles Verified:")
    print("  1. PSC is the PRIMARY signal (the noun)")
    print("  2. Pricing CONFIRMS or creates ambiguity (the grammar)")
    print("  3. High agreement → high confidence (0.90-0.95)")
    print("  4. Low agreement → lower confidence (0.60-0.70)")
    print("  5. CPFF does NOT override numeric PSC")
else:
    print(f"✗ {tests_total - tests_passed} TEST(S) FAILED")
    exit(1)
