#!/usr/bin/env python3
"""Quick test script to verify PSC code retrieval from USAspending API.

This script tests the fixed two-step approach:
1. Fetch awards using spending_by_award endpoint
2. Retrieve PSC codes from individual award endpoint

Run this to verify PSC codes are being successfully retrieved.
"""

import sys
from pathlib import Path


# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from loguru import logger

from src.enrichers.company_categorization import retrieve_company_contracts_api


# Configure logger for testing
logger.remove()
logger.add(sys.stderr, level="DEBUG")  # Enable DEBUG to see API response structure


def test_psc_retrieval():
    """Test PSC code retrieval with a known company."""

    print("=" * 80)
    print("PSC Code Retrieval Test")
    print("=" * 80)
    print()

    # Test with a small UEI (you can change this to test with a specific company)
    test_uei = input("Enter UEI to test (or press Enter for demo UEI): ").strip()

    if not test_uei:
        print("No UEI provided. Please provide a valid UEI to test.")
        print()
        print("Example UEIs you can try:")
        print("  - Any UEI from your database")
        print("  - A known SBIR recipient UEI")
        return

    print(f"\nTesting with UEI: {test_uei}")
    print("Fetching contracts (PSC fallback lookups limited internally)...")
    print()

    try:
        # Retrieve contracts with limited PSC lookups for quick testing
        contracts_df = retrieve_company_contracts_api(uei=test_uei)

        if contracts_df.empty:
            print("❌ No contracts found for this UEI")
            return

        print(f"✓ Retrieved {len(contracts_df)} contracts")
        print()

        # Check PSC code coverage
        total_contracts = len(contracts_df)
        contracts_with_psc = (~contracts_df["psc"].isna()).sum()
        psc_coverage = (contracts_with_psc / total_contracts * 100) if total_contracts > 0 else 0

        print(f"PSC Code Coverage: {contracts_with_psc}/{total_contracts} ({psc_coverage:.1f}%)")
        print()

        # Show sample of contracts with PSC codes
        if contracts_with_psc > 0:
            print("Sample contracts WITH PSC codes:")
            print("-" * 80)
            sample_with_psc = contracts_df[~contracts_df["psc"].isna()].head(5)
            for _, row in sample_with_psc.iterrows():
                award_id = row["award_id"]
                psc = row["psc"]
                amount = row["award_amount"]
                desc = (row["description"] or "N/A")[:60]
                print(f"  Award: {award_id}")
                print(f"    PSC: {psc}")
                print(f"    Amount: ${amount:,.0f}")
                print(f"    Description: {desc}")
                print()
        else:
            print("❌ No contracts have PSC codes!")
            print()

        # Show sample of contracts WITHOUT PSC codes
        contracts_without_psc = total_contracts - contracts_with_psc
        if contracts_without_psc > 0:
            print(f"WARNING: {contracts_without_psc} contracts are missing PSC codes")
            print("-" * 80)
            sample_without_psc = contracts_df[contracts_df["psc"].isna()].head(3)
            for _, row in sample_without_psc.iterrows():
                award_id = row["award_id"]
                amount = row["award_amount"]
                desc = (row["description"] or "N/A")[:60]
                print(f"  Award: {award_id}")
                print("    PSC: (missing)")
                print(f"    Amount: ${amount:,.0f}")
                print(f"    Description: {desc}")
                print()

        # Summary
        print("=" * 80)
        if psc_coverage >= 80:
            print("✓ TEST PASSED: PSC code retrieval is working well")
        elif psc_coverage >= 50:
            print("⚠ TEST WARNING: PSC codes partially retrieved")
            print("  Some awards may not have PSC data available")
        else:
            print("❌ TEST FAILED: Most contracts missing PSC codes")
            print("  The API may not be returning PSC data correctly")
        print("=" * 80)

    except Exception as e:
        print(f"❌ Error during test: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_psc_retrieval()
