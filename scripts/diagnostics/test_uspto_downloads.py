#!/usr/bin/env python3
"""Test USPTO data download URLs to diagnose why Lambda downloads are failing."""

import hashlib
from urllib.request import Request, urlopen

URLS = {
    "Patent Assignments (full CSV)": "https://data.uspto.gov/ui/datasets/products/files/ECORSEXC/2023/csv.zip",
    "AI Patents (CSV)": "https://data.uspto.gov/ui/datasets/products/files/ECOPATAI/2023/ai_model_predictions.csv.zip",
}

EXPECTED_SIZES = {
    "Patent Assignments (full CSV)": 1_780_000_000,  # 1.78 GB
    "AI Patents (CSV)": 764_000_000,  # 764 MB
}


def test_url(name: str, url: str):
    """Test downloading from a URL and report diagnostics."""
    print(f"\n{'=' * 80}")
    print(f"Testing: {name}")
    print(f"URL: {url}")
    print(f"{'=' * 80}")

    try:
        req = Request(url)
        req.add_header("User-Agent", "SBIR-Analytics-Lambda/1.0")

        print("Sending request...")
        with urlopen(req, timeout=30) as response:
            # Get headers
            print(f"\nHTTP Status: {response.status}")
            print(f"Content-Type: {response.headers.get('Content-Type')}")
            print(f"Content-Length: {response.headers.get('Content-Length')}")

            # Read first 1KB to check for error pages
            first_kb = response.read(1024)
            print(f"\nFirst 100 bytes (hex): {first_kb[:100].hex()}")
            print(f"First 100 bytes (text): {first_kb[:100]}")

            # Check if it's a ZIP file
            if first_kb.startswith(b"PK\x03\x04"):
                print("✅ Valid ZIP file magic bytes detected")
            elif first_kb.startswith(b"<!DOCTYPE") or first_kb.startswith(b"<html"):
                print("❌ HTML content detected - likely an error page")
                print(f"HTML preview: {first_kb.decode('utf-8', errors='ignore')[:200]}")
                return
            else:
                print("⚠️  Unknown file format")

            # Download rest of file
            print("\nDownloading full file...")
            data = first_kb + response.read()
            file_size = len(data)

            print(f"Downloaded: {file_size:,} bytes ({file_size / 1_000_000:.2f} MB)")

            expected = EXPECTED_SIZES.get(name, 0)
            if expected > 0:
                if file_size < expected * 0.5:
                    print(
                        f"❌ File is suspiciously small (expected ~{expected / 1_000_000:.0f} MB)"
                    )
                else:
                    print(
                        f"✅ File size looks reasonable (expected ~{expected / 1_000_000:.0f} MB)"
                    )

            # Compute hash
            file_hash = hashlib.sha256(data).hexdigest()
            print(f"SHA256: {file_hash}")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    for name, url in URLS.items():
        test_url(name, url)

    print(f"\n{'=' * 80}")
    print("SUMMARY")
    print(f"{'=' * 80}")
    print("If both downloads show small file sizes (<100 MB), the issue is:")
    print("  1. USPTO data portal is down/misconfigured")
    print("  2. Files were moved to different URLs")
    print("  3. Access restrictions (IP blocking, rate limiting)")
    print("\nIf downloads work locally but fail in Lambda:")
    print("  1. Lambda IP addresses may be blocked")
    print("  2. Lambda timeout (15 min) may be too short")
    print("  3. Lambda memory (1024 MB) may be insufficient for 1.78 GB file")
