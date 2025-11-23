"""Lambda function to download SBIR awards CSV and upload to S3."""

import hashlib
import os
from datetime import datetime, UTC
from typing import Any
from urllib.request import urlopen

import boto3

s3_client = boto3.client("s3")

DEFAULT_SOURCE_URL = "https://data.www.sbir.gov/mod_awarddatapublic/award_data.csv"


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Download CSV from SBIR.gov and upload to S3.

    Event structure:
    {
        "s3_bucket": "sbir-etl-production-data",
        "source_url": "https://...",  # Optional, defaults to SBIR.gov
        "force_refresh": false
    }
    """
    try:
        s3_bucket = event.get("s3_bucket") or os.environ.get("S3_BUCKET")
        if not s3_bucket:
            raise ValueError("S3_BUCKET not provided in event or environment")

        source_url = event.get("source_url") or DEFAULT_SOURCE_URL

        # Download CSV
        print(f"Downloading CSV from {source_url}")
        with urlopen(source_url) as response:
            csv_data = response.read()

        # Compute hash
        file_hash = hashlib.sha256(csv_data).hexdigest()

        # Count rows (approximate from bytes, or parse header)
        row_count = csv_data.count(b"\n") - 1  # Subtract header
        file_size = len(csv_data)

        # Generate S3 key with date
        timestamp = datetime.now(UTC)
        date_str = timestamp.strftime("%Y-%m-%d")
        s3_key = f"raw/awards/{date_str}/award_data.csv"

        # Upload to S3
        print(f"Uploading to s3://{s3_bucket}/{s3_key}")
        s3_client.put_object(
            Bucket=s3_bucket,
            Key=s3_key,
            Body=csv_data,
            ContentType="text/csv",
            Metadata={
                "sha256": file_hash,
                "source_url": source_url,
                "downloaded_at": timestamp.isoformat(),
            },
        )

        return {
            "statusCode": 200,
            "body": {
                "status": "success",
                "s3_bucket": s3_bucket,
                "s3_key": s3_key,
                "sha256": file_hash,
                "file_size": file_size,
                "row_count": row_count,
                "source_url": source_url,
                "downloaded_at": timestamp.isoformat(),
            },
        }

    except Exception as e:
        print(f"Error downloading CSV: {e}")
        return {
            "statusCode": 500,
            "body": {
                "status": "error",
                "error": str(e),
            },
        }
