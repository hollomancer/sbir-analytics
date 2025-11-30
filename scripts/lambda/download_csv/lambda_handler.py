"""Lambda function to download SBIR awards CSV and upload to S3."""

import os
import sys
from datetime import datetime, UTC
from typing import Any

# Add common module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from common.download_utils import create_standard_response, download_file, upload_to_s3

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
        csv_data, content_type = download_file(source_url, max_size_mb=500)

        # Count rows (approximate from bytes, or parse header)
        row_count = csv_data.count(b"\n") - 1  # Subtract header

        # Generate S3 key with date
        timestamp = datetime.now(UTC)
        date_str = timestamp.strftime("%Y-%m-%d")
        s3_key = f"raw/awards/{date_str}/award_data.csv"

        # Upload to S3
        file_hash = upload_to_s3(
            data=csv_data,
            s3_bucket=s3_bucket,
            s3_key=s3_key,
            content_type="text/csv",
            metadata={
                "source_url": source_url,
                "downloaded_at": timestamp.isoformat(),
            },
        )

        return create_standard_response(
            success=True,
            s3_bucket=s3_bucket,
            s3_key=s3_key,
            sha256=file_hash,
            file_size=len(csv_data),
            source_url=source_url,
            row_count=row_count,
        )

    except Exception as e:
        print(f"Error downloading CSV: {e}")
        return create_standard_response(success=False, error=str(e))
