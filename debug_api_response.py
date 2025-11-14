#!/usr/bin/env python3
"""Debug script to inspect USAspending API response structure."""

import httpx
import json

# Test with one of the award IDs from the previous test
award_id = "N0017306C2049"
base_url = "https://api.usaspending.gov/api/v2"

print(f"Fetching award details for: {award_id}")
print(f"URL: {base_url}/awards/{award_id}/")
print()

try:
    response = httpx.get(
        f"{base_url}/awards/{award_id}/",
        timeout=30,
        headers={"User-Agent": "SBIR-ETL/1.0"}
    )
    response.raise_for_status()
    award_data = response.json()

    print("=" * 80)
    print("API Response Structure")
    print("=" * 80)

    # Print top-level keys
    print("\nTop-level keys:")
    for key in sorted(award_data.keys()):
        value = award_data[key]
        value_type = type(value).__name__
        print(f"  - {key}: {value_type}")

    # Check specific keys that might contain PSC
    print("\n" + "=" * 80)
    print("Checking for PSC fields...")
    print("=" * 80)

    psc_fields = [
        "product_or_service_code",
        "psc",
        "PSC",
        "product_service_code",
    ]

    for field in psc_fields:
        if field in award_data:
            print(f"✓ Found '{field}': {award_data[field]}")
        else:
            print(f"✗ '{field}' not found")

    # Check nested structures
    print("\n" + "=" * 80)
    print("Checking nested structures for PSC...")
    print("=" * 80)

    nested_paths = [
        ("latest_transaction", "product_or_service_code"),
        ("contract_data", "product_or_service_code"),
        ("base_transaction", "product_or_service_code"),
        ("latest_transaction", "contract_data", "product_or_service_code"),
    ]

    for path in nested_paths:
        current = award_data
        path_str = " -> ".join(path)
        try:
            for key in path:
                if isinstance(current, dict) and key in current:
                    current = current[key]
                else:
                    current = None
                    break

            if current is not None:
                print(f"✓ Found at '{path_str}': {current}")
            else:
                print(f"✗ '{path_str}' not found")
        except Exception as e:
            print(f"✗ Error checking '{path_str}': {e}")

    # Show latest_transaction structure if it exists
    if "latest_transaction" in award_data and isinstance(award_data["latest_transaction"], dict):
        print("\n" + "=" * 80)
        print("latest_transaction keys:")
        print("=" * 80)
        for key in sorted(award_data["latest_transaction"].keys()):
            value = award_data["latest_transaction"][key]
            value_type = type(value).__name__
            # Show first few characters if string, length if list, etc.
            preview = ""
            if isinstance(value, str):
                preview = f" = '{value[:50]}...'" if len(value) > 50 else f" = '{value}'"
            elif isinstance(value, (list, dict)):
                preview = f" ({len(value)} items)"
            print(f"  - {key}: {value_type}{preview}")

    # Show contract_data structure if it exists
    if "contract_data" in award_data and isinstance(award_data["contract_data"], dict):
        print("\n" + "=" * 80)
        print("contract_data keys:")
        print("=" * 80)
        for key in sorted(award_data["contract_data"].keys()):
            value = award_data["contract_data"][key]
            value_type = type(value).__name__
            preview = ""
            if isinstance(value, str):
                preview = f" = '{value[:50]}...'" if len(value) > 50 else f" = '{value}'"
            elif isinstance(value, (list, dict)):
                preview = f" ({len(value)} items)"
            print(f"  - {key}: {value_type}{preview}")

    # Save full response to file for inspection
    output_file = "debug_api_response.json"
    with open(output_file, "w") as f:
        json.dump(award_data, f, indent=2)
    print(f"\n✓ Full response saved to: {output_file}")

except httpx.HTTPStatusError as e:
    print(f"❌ HTTP Error: {e}")
    print(f"   Status: {e.response.status_code}")
    print(f"   Response: {e.response.text[:500]}")
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
