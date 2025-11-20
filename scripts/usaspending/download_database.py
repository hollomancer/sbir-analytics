#!/usr/bin/env python3
"""Standalone script to download USAspending database and upload to S3.

This script can run on EC2 or any machine with AWS credentials configured.
It downloads the database dump and streams it directly to S3 using multipart upload.

Usage:
    python download_database.py --database-type full --date 20251106
    python download_database.py --source-url https://files.usaspending.gov/...
"""

import argparse
import hashlib
import os
import sys
from datetime import datetime, timezone
from urllib.request import Request, urlopen

import boto3

# Import file checking and discovery logic from check_new_file.py
from scripts.usaspending.check_new_file import (
    check_file_availability,
    find_latest_available_file,
)

s3_client = boto3.client("s3")

# USAspending database download base URL
USASPENDING_DB_BASE_URL = "https://files.usaspending.gov/database_download"

USASPENDING_DOWNLOADS = {
    "full": "{base}/usaspending-db_{date}.zip",
    "test": "{base}/usaspending-db-subset_{date}.zip",
}


def download_and_upload(
    s3_bucket: str,
    database_type: str = "full",
    date_str: str = None,
    source_url: str = None,
    force_refresh: bool = False,
) -> dict:
    """Download USAspending database and upload to S3."""
    # Construct URL if not provided
    if not source_url:
        if database_type not in USASPENDING_DOWNLOADS:
            raise ValueError(
                f"Unknown database_type '{database_type}'. "
                f"Known types: {', '.join(USASPENDING_DOWNLOADS.keys())}"
            )

        if not date_str:
            # Auto-discover latest available file instead of using today's date
            print("No date specified - searching for latest available file...")
            latest_file = find_latest_available_file(
                database_type=database_type,
                s3_bucket=None,  # Don't need S3 for discovery, just finding source URL
            )
            
            if not latest_file:
                raise FileNotFoundError(
                    f"No available {database_type} database file found in recent months.\n"
                    f"Please specify a date with --date YYYYMMDD or check available files manually."
                )
            
            source_url = latest_file["source_url"]
            date_str = latest_file["date_str"]
            print(f"Found latest available file: {date_str}")
        else:
            url_template = USASPENDING_DOWNLOADS[database_type]
            source_url = url_template.format(base=USASPENDING_DB_BASE_URL, date=date_str)

    print(f"Checking if file exists: {source_url}")
    
    # Check if file exists before starting download (reuse check_new_file logic)
    file_check = check_file_availability(
        source_url=source_url,
        s3_bucket=None,  # Don't compare with S3 here, just check availability
        s3_key=None,
    )
    
    if not file_check.get("available"):
        error_msg = file_check.get("error", "File not found")
        raise FileNotFoundError(
            f"File not available at {source_url}: {error_msg}\n"
            f"Please check:\n"
            f"  1. The date is correct (files are typically released monthly)\n"
            f"  2. The database type is correct (test vs full)\n"
            f"  3. Try running without --date to auto-discover latest file\n"
            f"  4. Or use: python scripts/usaspending/check_new_file.py --database-type {database_type}"
        )
    
    # Display file info
    if file_check.get("content_length"):
        size_gb = file_check["content_length"] / 1024 / 1024 / 1024
        print(f"✅ File found: {file_check['content_length']:,} bytes ({size_gb:.2f} GB)")
    if file_check.get("last_modified"):
        print(f"   Last modified: {file_check['last_modified']}")
    
    print(f"Downloading USAspending database ({database_type}) from {source_url}")

    # Generate S3 key
    # Format: raw/usaspending/database/YYYY-MM-DD/usaspending-db_YYYYMMDD.zip
    # This matches the pattern expected by find_latest_usaspending_dump()
    timestamp = datetime.now(timezone.utc)
    s3_date_str = timestamp.strftime("%Y-%m-%d")
    filename = source_url.split("/")[-1]
    s3_key = f"raw/usaspending/database/{s3_date_str}/{filename}"

    # Check if file already exists
    if not force_refresh:
        try:
            s3_client.head_object(Bucket=s3_bucket, Key=s3_key)
            print(f"File already exists in S3: s3://{s3_bucket}/{s3_key}")
            print("Skipping download. Use --force-refresh to override.")
            return {"status": "skipped", "s3_key": s3_key}
        except s3_client.exceptions.ClientError:
            pass  # File doesn't exist, continue

    # Download and upload using multipart
    CHUNK_SIZE = 100 * 1024 * 1024  # 100 MB

    req = Request(source_url)
    req.add_header("User-Agent", "SBIR-Analytics-EC2/1.0")
    req.add_header("Accept", "*/*")

    multipart_upload = s3_client.create_multipart_upload(
        Bucket=s3_bucket,
        Key=s3_key,
        ContentType="application/zip",
        Metadata={
            "source_url": source_url,
            "downloaded_at": timestamp.isoformat(),
            "database_type": database_type,
        },
    )
    upload_id = multipart_upload["UploadId"]
    print(f"Initiated multipart upload: {upload_id}")

    try:
        parts = []
        part_number = 1
        total_size = 0
        hasher = hashlib.sha256()

        with urlopen(req, timeout=600) as response:
            if response.getcode() != 200:
                raise Exception(f"HTTP {response.getcode()} from {source_url}")

            while True:
                chunk = response.read(CHUNK_SIZE)
                if not chunk:
                    break

                hasher.update(chunk)
                total_size += len(chunk)

                print(f"Uploading part {part_number} ({len(chunk)} bytes)")
                part_response = s3_client.upload_part(
                    Bucket=s3_bucket,
                    Key=s3_key,
                    PartNumber=part_number,
                    UploadId=upload_id,
                    Body=chunk,
                )

                parts.append(
                    {
                        "ETag": part_response["ETag"],
                        "PartNumber": part_number,
                    }
                )

                part_number += 1

                if total_size > 10 * 1024 * 1024 * 1024:  # 10 GB
                    print(f"WARNING: Large file download in progress ({total_size / 1024 / 1024 / 1024:.2f} GB)")

        file_hash = hasher.hexdigest()
        print(
            f"Completing multipart upload. Total size: {total_size} bytes ({total_size / 1024 / 1024 / 1024:.2f} GB), SHA256: {file_hash}"
        )

        s3_client.complete_multipart_upload(
            Bucket=s3_bucket,
            Key=s3_key,
            UploadId=upload_id,
            MultipartUpload={"Parts": parts},
        )

        print(f"Successfully uploaded to s3://{s3_bucket}/{s3_key}")
        print(f"File size: {total_size} bytes ({total_size / 1024 / 1024 / 1024:.2f} GB)")
        print(f"SHA256: {file_hash}")

        return {
            "status": "success",
            "s3_bucket": s3_bucket,
            "s3_key": s3_key,
            "sha256": file_hash,
            "file_size": total_size,
            "source_url": source_url,
            "downloaded_at": timestamp.isoformat(),
            "database_type": database_type,
            "parts_count": len(parts),
        }

    except Exception as e:
        print(f"Error during multipart upload, aborting: {e}")
        try:
            s3_client.abort_multipart_upload(
                Bucket=s3_bucket,
                Key=s3_key,
                UploadId=upload_id,
            )
        except Exception as abort_error:
            print(f"Error aborting multipart upload: {abort_error}")
        raise


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Download USAspending database and upload to S3"
    )
    # Get default from environment or use default
    default_bucket = (
        os.environ.get("S3_BUCKET")
        or os.environ.get("SBIR_ETL__S3_BUCKET")
        or "sbir-etl-production-data"
    )
    
    parser.add_argument(
        "--s3-bucket",
        default=default_bucket,
        help=f"S3 bucket name (default: {default_bucket} from env or hardcoded)",
    )
    parser.add_argument(
        "--database-type",
        choices=["full", "test"],
        default=os.environ.get("DATABASE_TYPE", "full"),
        help="Database type to download (default: full)",
    )
    parser.add_argument(
        "--date",
        default=os.environ.get("DATE"),
        help="Date in YYYYMMDD format (default: current date)",
    )
    parser.add_argument(
        "--source-url",
        default=os.environ.get("SOURCE_URL"),
        help="Override source URL (optional)",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        default=os.environ.get("FORCE_REFRESH", "false").lower() == "true",
        help="Force refresh even if file already exists",
    )

    args = parser.parse_args()

    try:
        result = download_and_upload(
            s3_bucket=args.s3_bucket,
            database_type=args.database_type,
            date_str=args.date,
            source_url=args.source_url,
            force_refresh=args.force_refresh,
        )
        sys.exit(0 if result.get("status") in ["success", "skipped"] else 1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

