#!/usr/bin/env python3
"""Extract recipient_lookup table from USAspending database dump.

Downloads directly from USAspending.gov, extracts only the recipient_lookup table,
and uploads as a parquet file to S3.

Usage:
    python extract_recipient_lookup.py --s3-bucket sbir-etl-production-data
    python extract_recipient_lookup.py --s3-bucket sbir-etl-production-data --from-s3  # Use existing S3 dump
"""

import argparse
import io
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import boto3
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import requests

USASPENDING_DOWNLOAD_URL = "https://files.usaspending.gov/database_download/"

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


def get_latest_dump_filename() -> str:
    """Get the latest dump filename from USAspending."""
    # USAspending publishes dumps with date in filename
    # Check their listing page or use known pattern
    response = requests.get(USASPENDING_DOWNLOAD_URL, timeout=30)
    response.raise_for_status()

    # Parse for latest usaspending-db_YYYYMMDD.zip
    import re
    matches = re.findall(r'usaspending-db_(\d{8})\.zip', response.text)
    if not matches:
        raise ValueError("Could not find USAspending dump files")

    latest_date = sorted(matches)[-1]
    return f"usaspending-db_{latest_date}.zip"


def download_from_usaspending(dest_path: Path) -> None:
    """Download directly from USAspending.gov using wget for resume support."""
    filename = get_latest_dump_filename()
    url = f"{USASPENDING_DOWNLOAD_URL}{filename}"

    print(f"Downloading from {url}")
    print(f"Destination: {dest_path}")

    # Use wget for better resume support on large files
    result = subprocess.run(
        ["wget", "-c", "-O", str(dest_path), url],
        check=True,
    )

    print(f"Downloaded {dest_path.stat().st_size / (1024**3):.1f} GB")


def find_latest_s3_dump(s3_client, bucket: str) -> str | None:
    """Find the latest USAspending dump in S3."""
    prefix = "raw/usaspending/database/"
    response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)

    if "Contents" not in response:
        return None

    # Find most recent full dump (largest file)
    dumps = [
        obj for obj in response["Contents"]
        if obj["Key"].endswith(".zip") and "subset" not in obj["Key"]
    ]

    if not dumps:
        return None

    # Get the largest one (full dump vs partial)
    largest = max(dumps, key=lambda x: x["Size"])
    return largest["Key"]


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
            df = pd.read_csv(
                f,
                sep="\t",
                header=None,
                names=RECIPIENT_LOOKUP_COLUMNS,
                na_values=["\\N", ""],
                low_memory=False,
                dtype=str,
            )

    print(f"Loaded {len(df):,} recipient records")
    return df


def upload_parquet(df: pd.DataFrame, s3_client, bucket: str, key: str) -> None:
    """Upload DataFrame as parquet to S3."""
    print(f"Converting to parquet and uploading to s3://{bucket}/{key}")

    table = pa.Table.from_pandas(df)
    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="snappy")
    buffer.seek(0)

    s3_client.upload_fileobj(buffer, bucket, key)
    size_mb = buffer.tell() / (1024 * 1024)
    print(f"Uploaded {size_mb:.1f} MB to s3://{bucket}/{key}")


def main():
    parser = argparse.ArgumentParser(description="Extract recipient_lookup from USAspending dump")
    parser.add_argument("--s3-bucket", required=True, help="S3 bucket for output")
    parser.add_argument("--from-s3", action="store_true", help="Use existing dump from S3 instead of downloading fresh")
    parser.add_argument("--output-prefix", default="raw/usaspending/recipient_lookup", help="S3 prefix for output")
    args = parser.parse_args()

    s3_client = boto3.client("s3")

    with tempfile.TemporaryDirectory() as tmpdir:
        local_zip = Path(tmpdir) / "usaspending.zip"

        if args.from_s3:
            # Download from S3
            source_key = find_latest_s3_dump(s3_client, args.s3_bucket)
            if not source_key:
                print("ERROR: No USAspending dump found in S3")
                sys.exit(1)
            print(f"Downloading from S3: s3://{args.s3_bucket}/{source_key}")
            s3_client.download_file(args.s3_bucket, source_key, str(local_zip))
        else:
            # Download directly from USAspending.gov
            download_from_usaspending(local_zip)

        # Extract recipient_lookup
        df = extract_recipient_lookup(local_zip)

    # Generate output key with date
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    output_key = f"{args.output_prefix}/{today}/recipient_lookup.parquet"

    upload_parquet(df, s3_client, args.s3_bucket, output_key)

    print(f"SUCCESS: Extracted {len(df):,} recipients to s3://{args.s3_bucket}/{output_key}")


if __name__ == "__main__":
    main()
