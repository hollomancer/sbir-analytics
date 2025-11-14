#!/usr/bin/env python3
"""Test basic USAspending API access."""

import httpx
import json

# Test different endpoints to see which ones work
endpoints = [
    ("GET", "https://api.usaspending.gov/api/v2/autocomplete/awarding_agency/DoD/"),
    ("POST", "https://api.usaspending.gov/api/v2/search/spending_by_award/", {
        "filters": {
            "award_type_codes": ["A"],
            "time_period": [{"start_date": "2020-10-01", "end_date": "2021-09-30"}],
        },
        "fields": ["Award ID", "Award Amount"],
        "limit": 1,
    }),
]

for method, url, *payload_args in endpoints:
    print(f"\nTesting {method} {url}")
    print("=" * 80)

    try:
        with httpx.Client(timeout=30) as client:
            if method == "GET":
                response = client.get(url)
            else:
                payload = payload_args[0] if payload_args else {}
                print(f"Payload: {json.dumps(payload, indent=2)}")
                response = client.post(url, json=payload)

            print(f"Status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print(f"Success! Response keys: {list(data.keys())}")
                if 'results' in data:
                    print(f"Results count: {len(data['results'])}")
            else:
                print(f"Error: {response.text[:200]}")

    except Exception as e:
        print(f"Exception: {e}")

print("\n" + "=" * 80)
print("Test complete")
