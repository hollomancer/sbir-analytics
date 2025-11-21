#!/usr/bin/env python3
"""Standalone test for transaction endpoint - no dependencies required."""

import json
import urllib.error
import urllib.request


def test_transaction_endpoint(uei: str) -> None:
    """Test the spending_by_transaction endpoint with a UEI."""

    print("=" * 80)
    print("Transaction Endpoint Test (No Dependencies)")
    print("=" * 80)
    print(f"\nTesting with UEI: {uei}")
    print()

    # Build the API request
    url = "https://api.usaspending.gov/api/v2/search/spending_by_transaction/"

    payload = {
        "filters": {"award_type_codes": ["A", "B", "C", "D"], "recipient_search_text": [uei]},
        "fields": [
            "Award ID",
            "Recipient Name",
            "Transaction Amount",
            "Transaction Description",
            "Action Date",
            "PSC",
            "Recipient UEI",
            "Award Type",
        ],
        "sort": "Transaction Amount",
        "order": "desc",
        "page": 1,
        "limit": 5,  # Just get 5 for quick test
    }

    print("Request payload:")
    print(json.dumps(payload, indent=2))
    print()

    # Make the API request
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "SBIR-Analytics/1.0"},
            method="POST",
        )

        print(f"Sending POST request to: {url}")
        print()

        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.load(response)

        print("✓ API request successful!")
        print()

        # Analyze response
        results = data.get("results", [])
        page_metadata = data.get("page_metadata", {})

        print("Response summary:")
        print(f"  - Total results in response: {len(results)}")
        print(f"  - Has more pages: {page_metadata.get('hasNext', False)}")
        print()

        if not results:
            print("❌ No transactions found for this UEI")
            return

        # Check first result structure
        first_result = results[0]
        print("First transaction keys:")
        print(f"  {list(first_result.keys())}")
        print()

        # Check PSC coverage
        psc_count = sum(1 for r in results if r.get("PSC"))
        psc_coverage = (psc_count / len(results) * 100) if results else 0

        print(f"PSC Coverage: {psc_count}/{len(results)} ({psc_coverage:.1f}%)")
        print()

        # Show sample transactions
        print("Sample transactions:")
        print("-" * 80)
        for i, transaction in enumerate(results[:3], 1):
            award_id = transaction.get("Award ID", "N/A")
            psc = transaction.get("PSC", "(missing)")
            amount = transaction.get("Transaction Amount", 0)
            desc = transaction.get("Transaction Description", "N/A")[:60]

            print(f"\n{i}. Award ID: {award_id}")
            print(f"   PSC: {psc}")
            print(f"   Amount: ${float(amount):,.2f}" if amount else "   Amount: N/A")
            print(f"   Description: {desc}")

        print()
        print("=" * 80)

        if psc_coverage >= 80:
            print("✓ SUCCESS: Transaction endpoint returns PSC codes!")
        elif psc_coverage > 0:
            print(f"⚠ PARTIAL: {psc_coverage:.1f}% of transactions have PSC codes")
        else:
            print("❌ FAILURE: No PSC codes in transaction response")

        print("=" * 80)

        # Save full response for inspection
        with open("/tmp/transaction_response.json", "w") as f:
            json.dump(data, f, indent=2)
        print("\n✓ Full response saved to: /tmp/transaction_response.json")

    except urllib.error.HTTPError as e:
        print(f"❌ HTTP Error {e.code}: {e.reason}")
        print()
        error_body = e.read().decode("utf-8")
        print("Error response:")
        try:
            error_data = json.loads(error_body)
            print(json.dumps(error_data, indent=2))
        except Exception:
            print(error_body[:500])
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    import sys

    # Use command line arg or default UEI
    uei = sys.argv[1] if len(sys.argv) > 1 else "RMG1AZ1ZH8Q7"
    test_transaction_endpoint(uei)
