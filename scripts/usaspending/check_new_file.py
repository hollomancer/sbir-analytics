#!/usr/bin/env python3
"""Check if a new USAspending database file is available.

This script checks the source URL to see if a new file is available by:
1. Making an HTTP HEAD request to check Last-Modified date
2. Comparing with the last downloaded file in S3
3. Checking Content-Length to detect file size changes

Usage:
    # Auto-discover latest available file (recommended)
    python check_new_file.py --database-type full --s3-bucket sbir-etl-production-data

    # Check specific date
    python check_new_file.py --database-type full --date 20251106

    # Check specific URL
    python check_new_file.py --source-url https://files.usaspending.gov/...
"""

import argparse
import os
import re
import sys
from datetime import datetime, timedelta, UTC
from urllib.request import Request, urlopen

import boto3

# USAspending database download base URL
USASPENDING_DB_BASE_URL = "https://files.usaspending.gov/database_download"

USASPENDING_DOWNLOADS = {
    "full": "{base}/usaspending-db_{date}.zip",
    "test": "{base}/usaspending-db-subset_{date}.zip",
}


def check_file_availability(
    source_url: str,
    s3_bucket: str = None,
    s3_key: str = None,
) -> dict:
    """Check if a new file is available at the source URL.

    Returns:
        dict with:
            - available: bool - whether file exists at source
            - last_modified: datetime - Last-Modified header from source
            - content_length: int - file size in bytes
            - is_new: bool - whether this is newer than S3 version
            - s3_last_modified: datetime - Last-Modified from S3 (if exists)
    """
    result = {
        "available": False,
        "last_modified": None,
        "content_length": None,
        "is_new": False,
        "s3_last_modified": None,
        "source_url": source_url,
    }

    # Make HEAD request to check file availability
    try:
        req = Request(source_url, method="HEAD")
        req.add_header("User-Agent", "SBIR-Analytics-Checker/1.0")
        req.add_header("Accept", "*/*")

        with urlopen(req, timeout=30) as response:
            if response.getcode() == 200:
                result["available"] = True

                # Get Last-Modified header
                last_modified_str = response.headers.get("Last-Modified")
                if last_modified_str:
                    from email.utils import parsedate_to_datetime

                    result["last_modified"] = parsedate_to_datetime(last_modified_str)

                # Get Content-Length
                content_length_str = response.headers.get("Content-Length")
                if content_length_str:
                    result["content_length"] = int(content_length_str)

            elif response.getcode() == 404:
                result["available"] = False
                result["error"] = "File not found (404)"
            else:
                result["available"] = False
                result["error"] = f"HTTP {response.getcode()}"

    except Exception as e:
        result["available"] = False
        result["error"] = str(e)
        return result

    # Compare with S3 if bucket and key provided
    if s3_bucket and s3_key:
        s3_client = boto3.client("s3")
        try:
            s3_obj = s3_client.head_object(Bucket=s3_bucket, Key=s3_key)
            s3_last_modified = s3_obj["LastModified"]
            result["s3_last_modified"] = s3_last_modified

            # Check if source file is newer
            if result["last_modified"]:
                result["is_new"] = result["last_modified"] > s3_last_modified
            else:
                # If no Last-Modified header, compare Content-Length
                s3_size = s3_obj.get("ContentLength")
                if result["content_length"] and s3_size:
                    result["is_new"] = result["content_length"] != s3_size

        except s3_client.exceptions.ClientError as e:
            # File doesn't exist in S3, so it's new
            if e.response["Error"]["Code"] == "404":
                result["is_new"] = True
            else:
                result["s3_error"] = str(e)

    return result


def find_latest_file_in_s3(s3_bucket: str, database_type: str) -> dict:
    """Find the most recent file in S3 for a given database type.

    Returns:
        dict with s3_key, last_modified, and date_str of the latest file, or None
    """
    s3_client = boto3.client("s3")
    prefix = "raw/usaspending/database/"

    try:
        # List all files in the database directory
        paginator = s3_client.get_paginator("list_objects_v2")
        latest_file = None
        latest_date = None
        latest_date_str = None

        for page in paginator.paginate(Bucket=s3_bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                # Check if this matches the database type
                if database_type == "full" and "usaspending-db_" in key:
                    # Extract date from filename: usaspending-db_YYYYMMDD.zip
                    match = re.search(r"usaspending-db_(\d{8})\.zip", key)
                    if match:
                        file_date_str = match.group(1)
                        if latest_date is None or obj["LastModified"] > latest_date:
                            latest_file = key
                            latest_date = obj["LastModified"]
                            latest_date_str = file_date_str
                elif database_type == "test" and "usaspending-db-subset_" in key:
                    # Extract date from filename: usaspending-db-subset_YYYYMMDD.zip
                    match = re.search(r"usaspending-db-subset_(\d{8})\.zip", key)
                    if match:
                        file_date_str = match.group(1)
                        if latest_date is None or obj["LastModified"] > latest_date:
                            latest_file = key
                            latest_date = obj["LastModified"]
                            latest_date_str = file_date_str

        if latest_file:
            return {
                "s3_key": latest_file,
                "last_modified": latest_date,
                "date_str": latest_date_str,
            }
        return None

    except Exception as e:
        print(f"Error finding latest file in S3: {e}", file=sys.stderr)
        return None


def find_latest_available_file(
    database_type: str,
    s3_bucket: str = None,
    max_months_back: int = 3,
) -> dict:
    """
    Find the latest available file by checking recent dates.

    Strategy:
    1. Check S3 for latest file date (if available) - start from there
    2. Try current month and previous months (checking 1st, 6th, 15th of each month)
    3. Return the first available file found (newest first)

    Args:
        database_type: "full" or "test"
        s3_bucket: S3 bucket to check for existing files
        max_months_back: Maximum number of months to check backwards

    Returns:
        dict with source_url, date_str, and availability info, or None
    """
    # Get starting date - use S3 latest date if available, otherwise current date
    start_date = datetime.now(UTC)
    if s3_bucket:
        latest_s3 = find_latest_file_in_s3(s3_bucket, database_type)
        if latest_s3 and latest_s3.get("date_str"):
            # Start from S3 date and check forward (in case newer file available)
            try:
                s3_date = datetime.strptime(latest_s3["date_str"], "%Y%m%d")
                s3_date = s3_date.replace(tzinfo=UTC)
                # Check from S3 date forward, then backwards
                start_date = max(start_date, s3_date + timedelta(days=1))
            except (ValueError, TypeError):
                pass

    url_template = USASPENDING_DOWNLOADS[database_type]

    # Build list of dates to check (newest first)
    dates_to_check = []

    # Start from current date and go backwards
    current = start_date
    for _ in range(max_months_back + 1):
        # Try common release dates: 6th (typical), 1st, 15th
        for day in [6, 1, 15]:
            try:
                test_date = current.replace(day=day)
                dates_to_check.append(test_date.strftime("%Y%m%d"))
            except ValueError:
                # Invalid day for this month (e.g., Feb 30)
                continue

        # Move to previous month
        if current.month == 1:
            current = current.replace(year=current.year - 1, month=12)
        else:
            current = current.replace(month=current.month - 1)

    # Remove duplicates and sort (newest first)
    dates_to_check = sorted(set(dates_to_check), reverse=True)

    # Check each date
    for test_date_str in dates_to_check:
        source_url = url_template.format(base=USASPENDING_DB_BASE_URL, date=test_date_str)

        # Quick check if file exists
        try:
            req = Request(source_url, method="HEAD")
            req.add_header("User-Agent", "SBIR-Analytics-Checker/1.0")
            req.add_header("Accept", "*/*")

            with urlopen(req, timeout=10) as response:
                if response.getcode() == 200:
                    # Found an available file
                    return {
                        "source_url": source_url,
                        "date_str": test_date_str,
                        "available": True,
                    }
        except Exception:
            # File doesn't exist at this date, try next
            continue

    # No file found
    return None


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Check if a new USAspending database file is available"
    )
    parser.add_argument(
        "--s3-bucket",
        default=os.environ.get("S3_BUCKET", "sbir-etl-production-data"),
        help="S3 bucket name",
    )
    parser.add_argument(
        "--database-type",
        choices=["full", "test"],
        default=os.environ.get("DATABASE_TYPE", "full"),
        help="Database type to check",
    )
    parser.add_argument(
        "--date",
        default=os.environ.get("DATE"),
        help="Date in YYYYMMDD format (optional - auto-discovers latest if not provided)",
    )
    parser.add_argument(
        "--source-url",
        default=os.environ.get("SOURCE_URL"),
        help="Override source URL (optional)",
    )
    parser.add_argument(
        "--compare-with-s3",
        action="store_true",
        default=True,
        help="Compare with existing S3 files (default: True)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output result as JSON",
    )

    args = parser.parse_args()

    # Construct URL if not provided
    if not args.source_url:
        if args.date:
            # Use explicit date if provided
            date_str = args.date
            url_template = USASPENDING_DOWNLOADS[args.database_type]
            source_url = url_template.format(base=USASPENDING_DB_BASE_URL, date=date_str)
        else:
            # Auto-discover latest available file
            print("No date specified - searching for latest available file...", file=sys.stderr)
            latest_file = find_latest_available_file(
                database_type=args.database_type,
                s3_bucket=args.s3_bucket if args.compare_with_s3 else None,
            )

            if not latest_file:
                error_msg = (
                    f"No available {args.database_type} database file found in recent months"
                )
                if args.json:
                    import json

                    print(
                        json.dumps(
                            {
                                "available": False,
                                "error": error_msg,
                                "database_type": args.database_type,
                            },
                            indent=2,
                        )
                    )
                else:
                    print(f"Error: {error_msg}")
                sys.exit(1)

            source_url = latest_file["source_url"]
            date_str = latest_file["date_str"]
            if not args.json:
                print(f"Found latest available file: {date_str}", file=sys.stderr)
    else:
        source_url = args.source_url
        date_str = None

    # Find latest S3 file if comparing
    s3_key = None
    if args.compare_with_s3:
        latest_s3 = find_latest_file_in_s3(args.s3_bucket, args.database_type)
        if latest_s3:
            s3_key = latest_s3["s3_key"]

    # Check file availability
    result = check_file_availability(
        source_url=source_url,
        s3_bucket=args.s3_bucket if args.compare_with_s3 else None,
        s3_key=s3_key,
    )

    # Output result
    if args.json:
        import json

        # Convert datetime objects to ISO strings for JSON
        json_result = result.copy()
        if json_result.get("last_modified"):
            json_result["last_modified"] = json_result["last_modified"].isoformat()
        if json_result.get("s3_last_modified"):
            json_result["s3_last_modified"] = json_result["s3_last_modified"].isoformat()

        print(json.dumps(json_result, indent=2))
    else:
        print(f"Source URL: {source_url}")
        print(f"Available: {result['available']}")
        if result.get("error"):
            print(f"Error: {result['error']}")
        if result.get("last_modified"):
            print(f"Last Modified: {result['last_modified']}")
        if result.get("content_length"):
            size_gb = result["content_length"] / 1024 / 1024 / 1024
            print(f"Size: {result['content_length']:,} bytes ({size_gb:.2f} GB)")
        if result.get("s3_last_modified"):
            print(f"S3 Last Modified: {result['s3_last_modified']}")
        print(f"Is New: {result['is_new']}")

    # Exit code: 0 if new file available, 1 if not
    sys.exit(0 if result.get("is_new") else 1)


if __name__ == "__main__":
    main()
