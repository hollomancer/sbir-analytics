#!/usr/bin/env python3
"""Quick test of contract justification output."""

from test_categorization_validation import print_contract_justifications

# Create sample classified contracts
sample_contracts = [
    {
        "award_id": "AWARD001",
        "classification": "Product",
        "method": "psc_numeric",
        "confidence": 0.95,
        "psc": "5820",
        "contract_type": "FFP",
        "sbir_phase": "II",
        "award_amount": 500000,
        "description": "Development of advanced radar system prototype",
    },
    {
        "award_id": "AWARD002",
        "classification": "Service",
        "method": "contract_type",
        "confidence": 1.0,
        "psc": "R425",
        "contract_type": "CPFF",
        "sbir_phase": None,
        "award_amount": 300000,
        "description": "Engineering services for software development",
    },
    {
        "award_id": "AWARD003",
        "classification": "R&D",
        "method": "psc_rd",
        "confidence": 0.90,
        "psc": "A123",
        "contract_type": None,
        "sbir_phase": "I",
        "award_amount": 150000,
        "description": "Research and development of novel algorithms",
    },
    {
        "award_id": "AWARD004",
        "classification": "Product",
        "method": "description_inference",
        "confidence": 0.85,
        "psc": "R425",
        "contract_type": "FFP",
        "sbir_phase": None,
        "award_amount": 250000,
        "description": "Manufacturing and delivery of sensor hardware units",
    },
    {
        "award_id": "AWARD005",
        "classification": "Service",
        "method": "psc_alphabetic",
        "confidence": 0.90,
        "psc": "R699",
        "contract_type": None,
        "sbir_phase": None,
        "award_amount": 100000,
        "description": "Technical consulting services",
    },
]

print("\nTesting contract justification output...")
print("=" * 80)

print_contract_justifications(
    sample_contracts,
    company_name="Test Company, Inc.",
    show_top_n=5
)

print("✓ Test complete!")
