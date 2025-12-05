#!/usr/bin/env python3
"""Stream-extract recipient_lookup from USAspending ZIP.

Uses HTTP range requests to download only the needed file,
then DuckDB for memory-efficient processing.

Usage:
    python stream_extract_recipient.py --s3-bucket sbir-etl-production-data
    python stream_extract_recipient.py --url <url> --s3-bucket <bucket>
    python stream_extract_recipient.py --list-only
"""

import argparse
import gzip
import io
import json
import sys
import tempfile
from datetime import datetime, timezone

import boto3
import duckdb

from usaspending_zip import HttpZipReader, find_latest_usaspending_url

# Expected columns for recipient_lookup table (20 columns)
RECIPIENT_LOOKUP_COLUMNS = [
    "id", "recipient_hash", "legal_business_name", "duns", "address_line_1",
    "address_line_2", "business_types_codes", "city", "congressional_district",
    "country_code", "parent_duns", "parent_legal_business_name", "state",
    "zip4", "zip5", "alternate_names", "source", "update_date", "uei", "parent_uei",
]


def find_recipient_lookup_file(reader: HttpZipReader, files: list[dict]) -> dict | None:
    """Auto-detect the recipient_lookup file by sampling candidates."""
    print("Auto-detecting recipient_lookup file...")
    candidates = [
        f for f in files
        if f["filename"].endswith(".dat.gz")
        and 100 * 1024**2 < f["uncompressed_size"] < 3 * 1024**3
    ]
    print(f"  Checking {len(candidates)} candidate files...")

    for f in sorted(candidates, key=lambda x: x["uncompressed_size"]):
        try:
            sample = reader.sample_file(f)
            gz = gzip.GzipFile(fileobj=io.BytesIO(sample))
            decompressed = gz.read(5000)
            first_line = decompressed.decode("utf-8", errors="replace").split("\n")[0]
            cols = first_line.split("\t")
            # recipient_lookup: ~20 columns, col[1] is UUID, col[2] is name
            if 18 <= len(cols) <= 22:
                col1 = cols[1] if len(cols) > 1 else ""
                col2 = cols[2] if len(cols) > 2 else ""
                if len(col1) == 36 and col1.count("-") == 4 and any(c.isalpha() for c in col2):
                    print(f"  Found: {f['filename']} ({f['uncompressed_size']/(1024**2):.0f} MB, {len(cols)} cols)")
                    return f
        except Exception:
            continue
    return None


def process_with_duckdb(gz_path: str, output_path: str) -> int:
    """Use DuckDB to read gzipped TSV and export to parquet."""
    print("\nProcessing with DuckDB...")

    # Build column definitions: {'column0': 'VARCHAR', 'column1': 'VARCHAR', ...}
    col_defs = ", ".join([f"'column{i}': 'VARCHAR'" for i in range(len(RECIPIENT_LOOKUP_COLUMNS))])
    col_aliases = ", ".join([f"column{i} AS {name}" for i, name in enumerate(RECIPIENT_LOOKUP_COLUMNS)])

    conn = duckdb.connect(":memory:")

    query = f"""
        COPY (
            SELECT {col_aliases}
            FROM read_csv('{gz_path}',
                delim = '\t',
                header = false,
                auto_detect = false,
                columns = {{{col_defs}}},
                null_padding = true,
                ignore_errors = true,
                nullstr = '\\N'
            )
        ) TO '{output_path}' (FORMAT PARQUET, COMPRESSION SNAPPY)
    """

    conn.execute(query)
    count = conn.execute(f"SELECT COUNT(*) FROM '{output_path}'").fetchone()[0]
    conn.close()

    return count


def main():
    parser = argparse.ArgumentParser(description="Extract recipient_lookup from USAspending")
    parser.add_argument("--url", help="Direct URL to USAspending ZIP")
    parser.add_argument("--s3-bucket", help="S3 bucket for input/output and caching")
    parser.add_argument("--output-prefix", default="raw/usaspending/recipient_lookup")
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
            size_mb = f["uncompressed_size"] / (1024**2)
            print(f"  {f['filename']:20} {size_mb:8.1f} MB")
        return

    # Find recipient_lookup
    target = find_recipient_lookup_file(reader, files)
    if not target:
        print("ERROR: Could not find recipient_lookup file")
        sys.exit(1)

    print(f"\nTarget: {target['filename']}")
    print(f"  Compressed: {target['compressed_size'] / (1024**2):.1f} MB")
    print(f"  Uncompressed: {target['uncompressed_size'] / (1024**2):.1f} MB")

    with tempfile.TemporaryDirectory() as tmpdir:
        gz_path = f"{tmpdir}/recipient_lookup.dat.gz"
        output_path = args.local_output or f"{tmpdir}/recipient_lookup.parquet"

        # Download
        reader.download_file(target, gz_path)

        # Process with DuckDB
        count = process_with_duckdb(gz_path, output_path)
        print(f"\nExtracted {count:,} recipients")

        # Upload to S3 if specified
        if s3 and args.s3_bucket and not args.local_output:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            parquet_key = f"{args.output_prefix}/{today}/recipient_lookup.parquet"
            print(f"\nUploading to s3://{args.s3_bucket}/{parquet_key}")
            s3.upload_file(output_path, args.s3_bucket, parquet_key)

            # Save metadata
            metadata = {
                "source": args.url or url,
                "extracted_at": datetime.now(timezone.utc).isoformat(),
                "row_count": count,
                "parquet_key": parquet_key,
            }
            meta_key = f"{args.output_prefix}/{today}/recipient_lookup_metadata.json"
            s3.put_object(Bucket=args.s3_bucket, Key=meta_key, Body=json.dumps(metadata, indent=2))
            print(f"SUCCESS: Extracted {count:,} recipients to S3")
        elif args.local_output:
            print(f"Saved to {args.local_output}")


if __name__ == "__main__":
    main()
