#!/usr/bin/env python3
"""Stream-extract NAICS lookup from USAspending transaction_fpds.

Creates a deduplicated (UEI, NAICS) mapping from contract transactions.
Uses HTTP range requests to download the file, then DuckDB for memory-efficient processing.

Usage:
    python stream_extract_naics.py --s3-bucket <bucket>
    python stream_extract_naics.py --list-only
    python stream_extract_naics.py --local-output /tmp/naics_lookup.parquet
"""

import argparse
import sys
import tempfile
from datetime import datetime, timezone

import boto3
import duckdb

from usaspending_zip import HttpZipReader, find_latest_usaspending_url

# Column indices in transaction_fpds (5882.dat.gz)
NAICS_COL = 30  # naics_code (0-indexed: column31)
UEI_COL = 96    # awardee_or_recipient_uei (0-indexed: column97)
TRANSACTION_FPDS_FILE = "5882.dat.gz"


def extract_naics_with_duckdb(gz_path: str, output_path: str) -> int:
    """Use DuckDB to extract unique (UEI, NAICS) pairs from gzipped TSV."""
    print("\nProcessing with DuckDB...")

    conn = duckdb.connect(":memory:")

    query = f"""
        COPY (
            SELECT DISTINCT
                column{UEI_COL} AS uei,
                column{NAICS_COL} AS naics_code
            FROM read_csv('{gz_path}',
                delim = '\t',
                header = false,
                auto_detect = false,
                columns = {{'column{NAICS_COL}': 'VARCHAR', 'column{UEI_COL}': 'VARCHAR'}},
                null_padding = true,
                ignore_errors = true
            )
            WHERE length(column{UEI_COL}) = 12
              AND column{UEI_COL} ~ '^[A-Z0-9]{{12}}$'
              AND length(column{NAICS_COL}) = 6
              AND column{NAICS_COL} ~ '^[0-9]{{6}}$'
        ) TO '{output_path}' (FORMAT PARQUET, COMPRESSION SNAPPY)
    """

    conn.execute(query)
    count = conn.execute(f"SELECT COUNT(*) FROM '{output_path}'").fetchone()[0]
    conn.close()

    return count


def main():
    parser = argparse.ArgumentParser(description="Extract NAICS lookup from USAspending")
    parser.add_argument("--url", help="Direct URL to USAspending ZIP")
    parser.add_argument("--s3-bucket", help="S3 bucket for output and caching")
    parser.add_argument("--output-prefix", default="raw/usaspending/naics_lookup")
    parser.add_argument("--list-only", action="store_true", help="List files only")
    parser.add_argument("--local-output", help="Local output path (skip S3)")
    args = parser.parse_args()

    url = args.url or find_latest_usaspending_url()
    if not url:
        print("ERROR: Provide --url or could not find latest dump")
        sys.exit(1)

    # Setup S3 for caching if bucket provided
    s3 = boto3.client("s3") if args.s3_bucket else None

    print(f"Source: {url}")
    reader = HttpZipReader(url, s3_client=s3, cache_bucket=args.s3_bucket)
    print(f"ZIP size: {reader.size / (1024**3):.2f} GB")

    print("\nScanning ZIP...")
    files = reader.list_files()
    print(f"Found {len(files)} files")

    if args.list_only:
        print("\n=== Files (sorted by size) ===")
        for f in sorted(files, key=lambda x: -x["uncompressed_size"])[:20]:
            size_gb = f["uncompressed_size"] / (1024**3)
            print(f"  {f['filename']:20} {size_gb:8.2f} GB")
        return

    # Find transaction_fpds
    target = next((f for f in files if f["filename"] == TRANSACTION_FPDS_FILE), None)
    if not target:
        print(f"ERROR: Could not find {TRANSACTION_FPDS_FILE}")
        sys.exit(1)

    print(f"\nTarget: {target['filename']}")
    print(f"  Compressed: {target['compressed_size'] / (1024**3):.1f} GB")
    print(f"  Uncompressed: {target['uncompressed_size'] / (1024**3):.1f} GB")

    with tempfile.TemporaryDirectory() as tmpdir:
        gz_path = f"{tmpdir}/{TRANSACTION_FPDS_FILE}"
        output_path = args.local_output or f"{tmpdir}/naics_lookup.parquet"

        # Download
        print("\nDownloading...")
        reader.download_file(target, gz_path)

        # Process with DuckDB
        count = extract_naics_with_duckdb(gz_path, output_path)
        print(f"\nExtracted {count:,} unique (UEI, NAICS) pairs")

        # Upload to S3 if specified
        if args.s3_bucket and not args.local_output:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            s3_key = f"{args.output_prefix}/{date_str}/naics_lookup.parquet"
            s3.upload_file(output_path, args.s3_bucket, s3_key)
            print(f"Uploaded to s3://{args.s3_bucket}/{s3_key}")
        elif args.local_output:
            print(f"Saved to {args.local_output}")


if __name__ == "__main__":
    main()
