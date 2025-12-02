#!/usr/bin/env python3
"""Extract recipient_lookup table from USAspending database dump.

Downloads directly from USAspending.gov, extracts only the recipient_lookup table,
and uploads as a parquet file to S3 with metadata for version tracking.

Usage:
    python extract_recipient_lookup.py --s3-bucket sbir-etl-production-data
    python extract_recipient_lookup.py --s3-bucket sbir-etl-production-data --from-s3
    python extract_recipient_lookup.py --check-only  # Just check if new data available
"""

import argparse
import io
import json
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

USASPENDING_DOWNLOAD_BASE = "https://files.usaspending.gov/database_download"

RECIPIENT_LOOKUP_COLUMNS = [
    "id", "recipient_hash", "legal_business_name", "duns", "uei",
    "parent_uei", "parent_duns", "parent_legal_business_name",
    "address_line_1", "address_line_2", "city", "state", "zip5", "zip4",
    "country_code", "congressional_district", "business_types_codes", "update_date",
]

RECIPIENT_LOOKUP_OID = "5419"


def get_latest_dump_info() -> dict:
    """Get info about the latest dump from USAspending by probing recent dates."""
    from datetime import timedelta

    # Try recent dates (USAspending typically releases on 6th of month)
    today = datetime.now(timezone.utc)
    dates_to_try = []

    # Check current month and 2 months back, trying 6th, 1st, 15th
    for months_back in range(3):
        check_date = today - timedelta(days=30 * months_back)
        for day in [6, 1, 15, 20]:
            try:
                test_date = check_date.replace(day=day)
                if test_date <= today:
                    dates_to_try.append(test_date.strftime("%Y%m%d"))
            except ValueError:
                pass

    # Remove duplicates and sort newest first
    dates_to_try = sorted(set(dates_to_try), reverse=True)

    for date_str in dates_to_try:
        filename = f"usaspending-db_{date_str}.zip"
        url = f"{USASPENDING_DOWNLOAD_BASE}/{filename}"

        try:
            head = requests.head(url, timeout=30, allow_redirects=True)
            if head.status_code == 200:
                return {
                    "filename": filename,
                    "url": url,
                    "source_date": date_str,
                    "last_modified": head.headers.get("Last-Modified"),
                    "content_length": int(head.headers.get("Content-Length", 0)),
                    "etag": head.headers.get("ETag", "").strip('"'),
                }
        except requests.RequestException:
            continue

    raise ValueError(f"Could not find USAspending dump file (tried dates: {dates_to_try[:5]}...)")


def get_current_metadata(s3_client, bucket: str, prefix: str) -> dict | None:
    """Get metadata from the most recent extraction."""
    try:
        # List all metadata files
        response = s3_client.list_objects_v2(Bucket=bucket, Prefix=f"{prefix}/")
        if "Contents" not in response:
            return None

        meta_files = [o["Key"] for o in response["Contents"] if o["Key"].endswith("_metadata.json")]
        if not meta_files:
            return None

        latest = sorted(meta_files)[-1]
        obj = s3_client.get_object(Bucket=bucket, Key=latest)
        return json.loads(obj["Body"].read().decode())
    except Exception:
        return None


def download_from_usaspending(dest_path: Path, url: str) -> None:
    """Download directly from USAspending.gov."""
    print(f"Downloading from {url}")
    subprocess.run(["wget", "-c", "-O", str(dest_path), url], check=True)
    print(f"Downloaded {dest_path.stat().st_size / (1024**3):.1f} GB")


def find_latest_s3_dump(s3_client, bucket: str) -> str | None:
    """Find the latest USAspending dump in S3."""
    prefix = "raw/usaspending/database/"
    response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
    if "Contents" not in response:
        return None
    dumps = [o for o in response["Contents"] if o["Key"].endswith(".zip") and "subset" not in o["Key"]]
    if not dumps:
        return None
    return max(dumps, key=lambda x: x["Size"])["Key"]


def extract_recipient_lookup(zip_path: Path) -> pd.DataFrame:
    """Extract recipient_lookup table from USAspending ZIP."""
    print(f"Opening ZIP: {zip_path}")
    with zipfile.ZipFile(zip_path, "r") as zf:
        copy_files = [n for n in zf.namelist() if n.endswith(f".{RECIPIENT_LOOKUP_OID}.dat")]
        if not copy_files:
            raise ValueError(f"No recipient_lookup file (OID {RECIPIENT_LOOKUP_OID}) found")
        with zf.open(copy_files[0]) as f:
            df = pd.read_csv(f, sep="\t", header=None, names=RECIPIENT_LOOKUP_COLUMNS,
                           na_values=["\\N", ""], low_memory=False, dtype=str)
    print(f"Loaded {len(df):,} recipient records")
    return df


def upload_parquet(df: pd.DataFrame, s3_client, bucket: str, key: str) -> int:
    """Upload DataFrame as parquet to S3. Returns size in bytes."""
    table = pa.Table.from_pandas(df)
    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="snappy")
    size = buffer.tell()
    buffer.seek(0)
    s3_client.upload_fileobj(buffer, bucket, key)
    print(f"Uploaded {size / (1024*1024):.1f} MB to s3://{bucket}/{key}")
    return size


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--s3-bucket", help="S3 bucket for output")
    parser.add_argument("--from-s3", action="store_true", help="Use existing S3 dump")
    parser.add_argument("--check-only", action="store_true", help="Only check if new data available")
    parser.add_argument("--force", action="store_true", help="Force extraction even if data unchanged")
    parser.add_argument("--output-prefix", default="raw/usaspending/recipient_lookup")
    args = parser.parse_args()

    s3_client = boto3.client("s3") if args.s3_bucket else None

    # Get latest dump info from USAspending
    print("Checking USAspending.gov for latest dump...")
    source_info = get_latest_dump_info()
    print(f"Latest: {source_info['filename']} ({source_info['content_length']/(1024**3):.1f} GB)")

    # Check if we already have this version
    if s3_client and not args.force:
        current = get_current_metadata(s3_client, args.s3_bucket, args.output_prefix)
        if current and current.get("source_date") == source_info["source_date"]:
            print(f"Already have data from {source_info['source_date']} - skipping")
            if args.check_only:
                print("STATUS: UP_TO_DATE")
            sys.exit(0)

    if args.check_only:
        print(f"STATUS: NEW_DATA_AVAILABLE (source_date={source_info['source_date']})")
        sys.exit(0)

    if not args.s3_bucket:
        print("ERROR: --s3-bucket required for extraction")
        sys.exit(1)

    # Download and extract
    with tempfile.TemporaryDirectory() as tmpdir:
        local_zip = Path(tmpdir) / "usaspending.zip"

        if args.from_s3:
            source_key = find_latest_s3_dump(s3_client, args.s3_bucket)
            if not source_key:
                print("ERROR: No dump in S3, use direct download")
                sys.exit(1)
            print(f"Downloading from S3: {source_key}")
            s3_client.download_file(args.s3_bucket, source_key, str(local_zip))
        else:
            download_from_usaspending(local_zip, source_info["url"])

        df = extract_recipient_lookup(local_zip)

    # Upload parquet
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    parquet_key = f"{args.output_prefix}/{today}/recipient_lookup.parquet"
    parquet_size = upload_parquet(df, s3_client, args.s3_bucket, parquet_key)

    # Upload metadata for version tracking
    metadata = {
        "source_date": source_info["source_date"],
        "source_filename": source_info["filename"],
        "source_etag": source_info["etag"],
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "row_count": len(df),
        "parquet_key": parquet_key,
        "parquet_size_bytes": parquet_size,
    }
    meta_key = f"{args.output_prefix}/{today}/recipient_lookup_metadata.json"
    s3_client.put_object(Bucket=args.s3_bucket, Key=meta_key, Body=json.dumps(metadata, indent=2))
    print(f"Metadata: s3://{args.s3_bucket}/{meta_key}")

    print(f"SUCCESS: {len(df):,} recipients from {source_info['source_date']}")


if __name__ == "__main__":
    main()
