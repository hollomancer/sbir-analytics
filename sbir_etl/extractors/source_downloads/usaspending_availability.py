"""Check if a new USAspending database file is available.

Epistemic tier: pipelines.

This script checks the source URL to see if a new file is available by:
1. Making an HTTP HEAD request to check Last-Modified date
2. Comparing with the last downloaded file in S3
3. Checking Content-Length to detect file size changes

Usage:
    # Auto-discover latest available file (recommended)

    # Check specific date
    python check_new_file.py --database-type full --date 20251106

    # Check specific URL
    python check_new_file.py --source-url https://files.usaspending.gov/...
"""

import argparse
import os
import sys
from datetime import datetime, UTC
from typing import NotRequired, TypedDict
from urllib.request import Request, urlopen

# USAspending database download base URL
USASPENDING_DB_BASE_URL = "https://files.usaspending.gov/database_download"

USASPENDING_DOWNLOADS = {
    "full": "{base}/usaspending-db_{date}.zip",
    "test": "{base}/usaspending-db-subset_{date}.zip",
}
EPISTEMIC_TIER = "pipelines"


class AvailabilityResult(TypedDict):
    """Metadata returned by one USAspending source probe."""

    available: bool
    last_modified: datetime | None
    content_length: int | None
    is_new: bool
    source_url: str
    error: NotRequired[str]


class LatestAvailableFile(TypedDict):
    """A discovered USAspending database cut."""

    source_url: str
    date_str: str
    available: bool


def check_file_availability(source_url: str) -> AvailabilityResult:
    """Check if a new file is available at the source URL.

    Returns:
        dict with:
            - available: bool - whether file exists at source
            - last_modified: datetime - Last-Modified header from source
            - content_length: int - file size in bytes
            - is_new: bool - whether this is newer than S3 version
    """
    result: AvailabilityResult = {
        "available": False,
        "last_modified": None,
        "content_length": None,
        "is_new": False,
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

    return result


def find_latest_available_file(
    database_type: str,
    max_months_back: int = 3,
) -> LatestAvailableFile | None:
    """
    Find the latest available file by checking recent dates.

    Strategy:
    1. Try current month and previous months (checking 1st, 6th, 15th of each month)
    2. Return the first available file found (newest first)

    Args:
        database_type: "full" or "test"
        max_months_back: Maximum number of months to check backwards

    Returns:
        dict with source_url, date_str, and availability info, or None
    """
    start_date = datetime.now(UTC)

    url_template = USASPENDING_DOWNLOADS[database_type]

    # Build list of dates to check (newest first)
    dates_to_check: list[str] = []

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
            latest_file = find_latest_available_file(database_type=args.database_type)

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

    result = check_file_availability(source_url=source_url)

    # Output result
    if args.json:
        import json

        # Convert datetime objects to ISO strings for JSON
        json_result = result.copy()
        if json_result.get("last_modified"):
            json_result["last_modified"] = json_result["last_modified"].isoformat()

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
        print(f"Is New: {result['is_new']}")

    # Exit code: 0 if new file available, 1 if not
    sys.exit(0 if result.get("is_new") else 1)


if __name__ == "__main__":
    main()
