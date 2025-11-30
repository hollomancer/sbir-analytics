"""Lambda function to check if a new USAspending database file is available.

This function can be triggered periodically (e.g., daily) to check for new files
and trigger the download workflow if a new file is detected.
"""

import os
from datetime import datetime, timedelta, UTC
from typing import Any

import boto3
from email.utils import parsedate_to_datetime
from urllib.request import Request, urlopen

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
    """Check if a new file is available at the source URL."""
    result = {
        "available": False,
        "last_modified": None,
        "content_length": None,
        "is_new": False,
        "s3_last_modified": None,
        "source_url": source_url,
    }

    try:
        req = Request(source_url, method="HEAD")
        req.add_header("User-Agent", "SBIR-Analytics-Checker/1.0")
        req.add_header("Accept", "*/*")

        with urlopen(req, timeout=30) as response:
            if response.getcode() == 200:
                result["available"] = True
                last_modified_str = response.headers.get("Last-Modified")
                if last_modified_str:
                    result["last_modified"] = parsedate_to_datetime(last_modified_str)
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

    if s3_bucket and s3_key:
        s3_client = boto3.client("s3")
        try:
            s3_obj = s3_client.head_object(Bucket=s3_bucket, Key=s3_key)
            s3_last_modified = s3_obj["LastModified"]
            result["s3_last_modified"] = s3_last_modified
            if result["last_modified"]:
                result["is_new"] = result["last_modified"] > s3_last_modified
            else:
                s3_size = s3_obj.get("ContentLength")
                if result["content_length"] and s3_size:
                    result["is_new"] = result["content_length"] != s3_size
        except s3_client.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "404":
                result["is_new"] = True
            else:
                result["s3_error"] = str(e)

    return result


def find_latest_file_in_s3(s3_bucket: str, database_type: str) -> dict:
    """Find the most recent file in S3 for a given database type."""
    s3_client = boto3.client("s3")
    prefix = "raw/usaspending/database/"

    try:
        paginator = s3_client.get_paginator("list_objects_v2")
        latest_file = None
        latest_date = None

        for page in paginator.paginate(Bucket=s3_bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if database_type == "full" and "usaspending-db_" in key:
                    if latest_date is None or obj["LastModified"] > latest_date:
                        latest_file = key
                        latest_date = obj["LastModified"]
                elif database_type == "test" and "usaspending-db-subset_" in key:
                    if latest_date is None or obj["LastModified"] > latest_date:
                        latest_file = key
                        latest_date = obj["LastModified"]

        if latest_file:
            return {"s3_key": latest_file, "last_modified": latest_date}
        return None
    except Exception as e:
        print(f"Error finding latest file in S3: {e}")
        return None


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Check if a new USAspending database file is available.

    Event structure:
    {
        "database_type": "full",  # or "test"
        "date": "20251106",  # YYYYMMDD format, optional (defaults to current date)
        "source_url": "https://...",  # Optional, will construct if not provided
        "s3_bucket": "sbir-etl-production-data",  # Optional, from env if not provided
        "trigger_download": false  # If true, triggers download Lambda/Step Functions
    }

    Returns:
    {
        "statusCode": 200,
        "body": {
            "available": true,
            "is_new": true,
            "last_modified": "2025-11-06T00:00:00Z",
            "content_length": 233661229756,
            "should_download": true,
            "source_url": "https://...",
            "triggered_download": false  # Only if trigger_download=true
        }
    }
    """
    try:
        s3_bucket = event.get("s3_bucket") or os.environ.get(
            "S3_BUCKET", "sbir-etl-production-data"
        )
        database_type = event.get("database_type", "full")
        date_str = event.get("date")
        source_url = event.get("source_url")
        trigger_download = event.get("trigger_download", False)

        # Construct URL if not provided
        if not source_url:
            if not date_str:
                # Search for most recent available file (check last 30 days)
                from datetime import timedelta
                now = datetime.now(UTC)
                url_template = USASPENDING_DOWNLOADS[database_type]

                for days_back in range(30):
                    check_date = now - timedelta(days=days_back)
                    candidate_date_str = check_date.strftime("%Y%m%d")
                    candidate_url = url_template.format(base=USASPENDING_DB_BASE_URL, date=candidate_date_str)

                    # Quick HEAD check
                    try:
                        req = Request(candidate_url, method="HEAD")
                        req.add_header("User-Agent", "SBIR-Analytics-Checker/1.0")
                        with urlopen(req, timeout=10) as response:
                            if response.getcode() == 200:
                                date_str = candidate_date_str
                                source_url = candidate_url
                                print(f"Found available file dated {date_str}")
                                break
                    except:
                        continue

                if not source_url:
                    # Fallback to today's date if nothing found
                    date_str = now.strftime("%Y%m%d")
                    source_url = url_template.format(base=USASPENDING_DB_BASE_URL, date=date_str)
            else:
                url_template = USASPENDING_DOWNLOADS[database_type]
                source_url = url_template.format(base=USASPENDING_DB_BASE_URL, date=date_str)

        print(f"Checking for new USAspending database file: {source_url}")

        # Find latest S3 file for comparison
        latest_s3 = find_latest_file_in_s3(s3_bucket, database_type)
        s3_key = latest_s3["s3_key"] if latest_s3 else None

        # Check file availability
        result = check_file_availability(
            source_url=source_url,
            s3_bucket=s3_bucket,
            s3_key=s3_key,
        )

        should_download = result.get("is_new", False) or not latest_s3
        triggered_download = False

        # Trigger download if requested and file is new
        if trigger_download and should_download:
            # Option 1: Invoke download Lambda function
            lambda_client = boto3.client("lambda")
            download_function_name = "sbir-analytics-download-usaspending-database"

            try:
                lambda_client.invoke(
                    FunctionName=download_function_name,
                    InvocationType="Event",  # Async invocation
                    Payload=bytes(
                        f'{{"database_type": "{database_type}", "date": "{date_str}", "s3_bucket": "{s3_bucket}"}}',
                        "utf-8",
                    ),
                )
                triggered_download = True
                print(f"Triggered download Lambda: {download_function_name}")
            except Exception as e:
                print(f"Error triggering download Lambda: {e}")
                result["trigger_error"] = str(e)

        # Prepare response
        response_body = {
            "available": result.get("available", False),
            "is_new": result.get("is_new", False),
            "should_download": should_download,
            "source_url": source_url,
            "triggered_download": triggered_download,
        }

        if result.get("last_modified"):
            response_body["last_modified"] = result["last_modified"].isoformat()
        if result.get("content_length"):
            response_body["content_length"] = result["content_length"]
            response_body["size_gb"] = round(result["content_length"] / 1024 / 1024 / 1024, 2)
        if result.get("s3_last_modified"):
            response_body["s3_last_modified"] = result["s3_last_modified"].isoformat()
        if result.get("error"):
            response_body["error"] = result["error"]

        return {
            "statusCode": 200,
            "body": response_body,
        }

    except Exception as e:
        print(f"Error checking USAspending file: {e}")
        import traceback

        traceback.print_exc()
        return {
            "statusCode": 500,
            "body": {
                "status": "error",
                "error": str(e),
                "database_type": event.get("database_type"),
            },
        }
