#!/usr/bin/env python3
"""Extract both recipient_lookup and NAICS from USAspending dump in one pass.

Designed for AWS Batch with sufficient disk space.
Provides detailed progress reporting for CloudWatch logs.
"""

import argparse
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

import boto3

from usaspending_zip import HttpZipReader, find_latest_usaspending_url


def log_disk_usage(tmpdir: str):
    """Log current disk usage."""
    result = subprocess.run(["df", "-h", tmpdir], capture_output=True, text=True)
    print(f"\n📊 Disk Usage:\n{result.stdout}")


def extract_both_files(url: str, s3_bucket: str):
    """Extract both recipient_lookup and NAICS in one pass."""
    print("=" * 80)
    print(f"🚀 USAspending Extraction Job")
    print(f"Source: {url}")
    print(f"Target: s3://{s3_bucket}/")
    print("=" * 80)

    s3 = boto3.client("s3")
    reader = HttpZipReader(url, s3_client=s3, cache_bucket=s3_bucket)

    print(f"\n📦 ZIP Archive Size: {reader.size / (1024**3):.2f} GB")

    print("\n🔍 Scanning ZIP contents...")
    files = reader.list_files()
    print(f"Found {len(files)} files in archive")

    # Find target files
    recipient_file = next((f for f in files if f["filename"] == "5881.dat.gz"), None)
    naics_file = next((f for f in files if f["filename"] == "5882.dat.gz"), None)

    if not recipient_file or not naics_file:
        print("❌ ERROR: Could not find required files (5881.dat.gz, 5882.dat.gz)")
        sys.exit(1)

    print(f"\n📋 Files to extract:")
    print(f"  recipient_lookup (5881.dat.gz): {recipient_file['compressed_size'] / (1024**3):.2f} GB compressed")
    print(f"  NAICS (5882.dat.gz): {naics_file['compressed_size'] / (1024**3):.2f} GB compressed")

    with tempfile.TemporaryDirectory() as tmpdir:
        log_disk_usage(tmpdir)

        # Extract recipient_lookup
        print("\n" + "=" * 80)
        print("📥 STEP 1: Extracting recipient_lookup")
        print("=" * 80)

        recipient_gz = f"{tmpdir}/5881.dat.gz"
        recipient_parquet = f"{tmpdir}/recipient_lookup.parquet"

        print(f"Downloading 5881.dat.gz...")
        reader.download_file(recipient_file, recipient_gz)
        print(f"✅ Download complete")
        log_disk_usage(tmpdir)

        print(f"\nProcessing with DuckDB...")
        from stream_extract_recipient import process_with_duckdb as extract_recipients_with_duckdb
        count = extract_recipients_with_duckdb(recipient_gz, recipient_parquet)
        print(f"✅ Extracted {count:,} recipients")

        # Upload to S3
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        s3_key = f"raw/usaspending/recipient_lookup/{date_str}/recipient_lookup.parquet"
        print(f"\n📤 Uploading to S3: {s3_key}")
        s3.upload_file(recipient_parquet, s3_bucket, s3_key)
        print(f"✅ Upload complete")

        # Clean up recipient files
        import os
        os.remove(recipient_gz)
        os.remove(recipient_parquet)
        print(f"\n🧹 Cleaned up recipient files")
        log_disk_usage(tmpdir)

        # Extract NAICS
        print("\n" + "=" * 80)
        print("📥 STEP 2: Extracting NAICS lookup")
        print("=" * 80)

        naics_gz = f"{tmpdir}/5882.dat.gz"
        naics_parquet = f"{tmpdir}/naics_lookup.parquet"

        print(f"Downloading 5882.dat.gz...")
        reader.download_file(naics_file, naics_gz)
        print(f"✅ Download complete")
        log_disk_usage(tmpdir)

        print(f"\nProcessing with DuckDB...")
        from stream_extract_naics import extract_naics_with_duckdb
        count = extract_naics_with_duckdb(naics_gz, naics_parquet)
        print(f"✅ Extracted {count:,} unique (UEI, NAICS) pairs")

        # Upload to S3
        s3_key = f"raw/usaspending/naics_lookup/{date_str}/naics_lookup.parquet"
        print(f"\n📤 Uploading to S3: {s3_key}")
        s3.upload_file(naics_parquet, s3_bucket, s3_key)
        print(f"✅ Upload complete")

        log_disk_usage(tmpdir)

    print("\n" + "=" * 80)
    print("✅ EXTRACTION COMPLETE")
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="Extract USAspending data (Batch job)")
    parser.add_argument("--url", help="Direct URL to USAspending ZIP")
    parser.add_argument("--s3-bucket", required=True, help="S3 bucket for output")
    args = parser.parse_args()

    url = args.url or find_latest_usaspending_url()
    if not url:
        print("❌ ERROR: Could not find USAspending dump URL")
        sys.exit(1)

    try:
        extract_both_files(url, args.s3_bucket)
    except Exception as e:
        print(f"\n❌ ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
