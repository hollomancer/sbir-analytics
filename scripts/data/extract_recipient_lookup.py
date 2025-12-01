#!/usr/bin/env python3
"""Extract recipient_lookup table from USAspending database dump.

Downloads the full USAspending ZIP, extracts only the recipient_lookup table,
and uploads as a parquet file to S3.

Usage:
    python extract_recipient_lookup.py --s3-bucket sbir-etl-production-data
"""

import argparse
import io
import os
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import boto3
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# recipient_lookup table schema
RECIPIENT_LOOKUP_COLUMNS = [
    "id",
    "recipient_hash",
    "legal_business_name",
    "duns",
    "uei",
    "parent_uei",
    "parent_duns",
    "parent_legal_business_name",
    "address_line_1",
    "address_line_2",
    "city",
    "state",
    "zip5",
    "zip4",
    "country_code",
    "congressional_district",
    "business_types_codes",
    "update_date",
]

# OID for recipient_lookup in USAspending COPY dump
RECIPIENT_LOOKUP_OID = "5419"


def find_latest_dump(s3_client, bucket: str) -> str | None:
    """Find the latest USAspending dump in S3."""
    prefix = "raw/usaspending/database/"
    response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)

    if "Contents" not in response:
        return None

    # Find most recent full dump
    dumps = [
        obj["Key"]
        for obj in response["Contents"]
        if obj["Key"].endswith(".zip") and "subset" not in obj["Key"]
    ]

    if not dumps:
        return None

    return sorted(dumps)[-1]


def extract_recipient_lookup(zip_path: Path) -> pd.DataFrame:
    """Extract recipient_lookup table from USAspending ZIP."""
    print(f"Opening ZIP: {zip_path}")

    with zipfile.ZipFile(zip_path, "r") as zf:
        # Find the recipient_lookup COPY file (OID 5419)
        copy_files = [n for n in zf.namelist() if n.endswith(f".{RECIPIENT_LOOKUP_OID}.dat")]

        if not copy_files:
            raise ValueError(f"No recipient_lookup file (OID {RECIPIENT_LOOKUP_OID}) found in ZIP")

        copy_file = copy_files[0]
        print(f"Found recipient_lookup: {copy_file}")

        # Read the COPY format file
        with zf.open(copy_file) as f:
            # PostgreSQL COPY format: tab-separated, \N for NULL
            df = pd.read_csv(
                f,
                sep="\t",
                header=None,
                names=RECIPIENT_LOOKUP_COLUMNS,
                na_values=["\\N", ""],
                low_memory=False,
                dtype=str,  # Read all as string initially
            )

    print(f"Loaded {len(df):,} recipient records")
    return df


def upload_parquet(df: pd.DataFrame, s3_client, bucket: str, key: str) -> None:
    """Upload DataFrame as parquet to S3."""
    print(f"Converting to parquet and uploading to s3://{bucket}/{key}")

    # Convert to parquet in memory
    table = pa.Table.from_pandas(df)
    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="snappy")
    buffer.seek(0)

    # Upload
    s3_client.upload_fileobj(buffer, bucket, key)
    size_mb = buffer.tell() / (1024 * 1024)
    print(f"Uploaded {size_mb:.1f} MB to s3://{bucket}/{key}")


def main():
    parser = argparse.ArgumentParser(description="Extract recipient_lookup from USAspending dump")
    parser.add_argument("--s3-bucket", required=True, help="S3 bucket name")
    parser.add_argument("--source-key", help="Specific S3 key for source ZIP (auto-detect if not provided)")
    parser.add_argument("--output-prefix", default="raw/usaspending/recipient_lookup", help="S3 prefix for output")
    args = parser.parse_args()

    s3_client = boto3.client("s3")

    # Find source dump
    if args.source_key:
        source_key = args.source_key
    else:
        source_key = find_latest_dump(s3_client, args.s3_bucket)
        if not source_key:
            print("ERROR: No USAspending dump found in S3")
            sys.exit(1)

    print(f"Source: s3://{args.s3_bucket}/{source_key}")

    # Download to temp file (streaming would be better but ZIP requires random access)
    with tempfile.TemporaryDirectory() as tmpdir:
        local_zip = Path(tmpdir) / "usaspending.zip"
        print(f"Downloading to {local_zip}...")

        s3_client.download_file(args.s3_bucket, source_key, str(local_zip))
        print(f"Downloaded {local_zip.stat().st_size / (1024**3):.1f} GB")

        # Extract recipient_lookup
        df = extract_recipient_lookup(local_zip)

    # Generate output key with date
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    output_key = f"{args.output_prefix}/{today}/recipient_lookup.parquet"

    # Upload
    upload_parquet(df, s3_client, args.s3_bucket, output_key)

    print(f"SUCCESS: Extracted {len(df):,} recipients to s3://{args.s3_bucket}/{output_key}")


if __name__ == "__main__":
    main()
