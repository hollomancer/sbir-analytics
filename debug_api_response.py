#!/usr/bin/env python3
"""Debug script to inspect actual USAspending API response structure."""

import httpx
import json

api_url = "https://api.usaspending.gov/api/v2/search/spending_by_award/"

# Test with a known company
payload = {
    "filters": {
        "award_type_codes": ["A", "B", "C", "D"],
        "time_period": [
            {
                "start_date": "2020-10-01",
                "end_date": "2021-09-30",
            }
        ],
        "recipient_search_text": ["Physical Optics Corporation"],
    },
    "fields": [
        "Award ID",
        "Recipient Name",
        "Award Amount",
        "Description",
        "Product or Service Code",
        "product_or_service_code",
        "psc_code",
        "recipient_uei",
    ],
    "limit": 1,
    "page": 1,
}

print("=" * 80)
print("USAspending API Response Structure Inspector")
print("=" * 80)
print(f"\nRequesting fields: {payload['fields']}")
print(f"API URL: {api_url}\n")

try:
    with httpx.Client(timeout=30) as client:
        response = client.post(api_url, json=payload)
        response.raise_for_status()

        data = response.json()

        print(f"Response status: {response.status_code}")
        print(f"Response keys: {list(data.keys())}\n")

        if "results" in data and len(data["results"]) > 0:
            print("=" * 80)
            print("FIRST RESULT (full structure):")
            print("=" * 80)
            result = data["results"][0]
            print(json.dumps(result, indent=2))

            print("\n" + "=" * 80)
            print("KEY ANALYSIS:")
            print("=" * 80)

            # Check PSC field variations
            psc_checks = [
                "Product or Service Code",
                "product_or_service_code",
                "psc_code",
                "psc",
                "PSC",
            ]

            for field in psc_checks:
                value = result.get(field)
                print(f"  '{field}': {value} (type: {type(value).__name__})")

            # Check if it's nested
            print("\n  Checking for nested structures...")
            for key, value in result.items():
                if isinstance(value, dict):
                    print(f"  '{key}' is a dict with keys: {list(value.keys())}")
                    if "code" in value:
                        print(f"    → Contains 'code': {value.get('code')}")
        else:
            print("No results returned!")
            print(f"Response: {json.dumps(data, indent=2)}")

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
