"""Lambda function to download PatentsView data and upload to S3."""

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict
from urllib.request import urlopen, Request
import boto3

s3_client = boto3.client("s3")

# PatentsView bulk download URLs
# Note: These URLs may need to be updated based on actual PatentsView download page structure
PATENTSVIEW_BASE_URL = "https://patentsview.org/download/data-download-tables"
# Common PatentsView table names
PATENTSVIEW_TABLES = [
    "patent",
    "assignee",
    "inventor",
    "location",
    "cpc_subsection",
    "nber_subcategory",
    "uspc_mainclass",
]


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Download PatentsView data and upload to S3.
    
    Event structure:
    {
        "s3_bucket": "sbir-etl-production-data",
        "dataset_type": "patent",  # or "assignee", "inventor", etc.
        "table_name": "patent",  # Optional, defaults to dataset_type
        "source_url": "https://...",  # Optional, will construct if not provided
        "force_refresh": false
    }
    """
    try:
        s3_bucket = event.get("s3_bucket") or os.environ.get("S3_BUCKET")
        if not s3_bucket:
            raise ValueError("S3_BUCKET not provided in event or environment")

        dataset_type = event.get("dataset_type") or event.get("table_name", "patent")
        source_url = event.get("source_url")
        force_refresh = event.get("force_refresh", False)

        # Construct URL if not provided
        if not source_url:
            # PatentsView uses specific download endpoints - this is a placeholder
            # Actual URL structure may vary; update based on PatentsView API documentation
            source_url = f"{PATENTSVIEW_BASE_URL}?table={dataset_type}"

        # Download data
        print(f"Downloading PatentsView {dataset_type} from {source_url}")
        req = Request(source_url)
        req.add_header("User-Agent", "SBIR-ETL-Lambda/1.0")
        
        with urlopen(req, timeout=300) as response:
            data = response.read()

        # Compute hash
        file_hash = hashlib.sha256(data).hexdigest()

        # Generate S3 key with date
        timestamp = datetime.now(timezone.utc)
        date_str = timestamp.strftime("%Y-%m-%d")
        # Determine file extension from content type or default to .tsv (PatentsView uses TSV)
        content_type = response.headers.get("Content-Type", "")
        if "csv" in content_type.lower():
            file_ext = ".csv"
        elif "tsv" in content_type.lower() or "tab" in content_type.lower():
            file_ext = ".tsv"
        else:
            file_ext = ".tsv"  # Default for PatentsView
        
        s3_key = f"raw/uspto/patentsview/{date_str}/{dataset_type}{file_ext}"

        # Upload to S3
        print(f"Uploading to s3://{s3_bucket}/{s3_key}")
        s3_client.put_object(
            Bucket=s3_bucket,
            Key=s3_key,
            Body=data,
            ContentType=content_type or "text/tab-separated-values",
            Metadata={
                "sha256": file_hash,
                "source_url": source_url,
                "downloaded_at": timestamp.isoformat(),
                "dataset_type": dataset_type,
            },
        )

        return {
            "statusCode": 200,
            "body": {
                "status": "success",
                "s3_bucket": s3_bucket,
                "s3_key": s3_key,
                "sha256": file_hash,
                "file_size": len(data),
                "source_url": source_url,
                "downloaded_at": timestamp.isoformat(),
                "dataset_type": dataset_type,
            },
        }

    except Exception as e:
        print(f"Error downloading PatentsView data: {e}")
        import traceback
        traceback.print_exc()
        return {
            "statusCode": 500,
            "body": {
                "status": "error",
                "error": str(e),
            },
        }

