"""Lambda function to download USPTO AI Patent Dataset and upload to S3."""

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict
from urllib.request import urlopen, Request
import boto3

s3_client = boto3.client("s3")

# USPTO AI Patent Dataset URL
# Note: Update with actual download URL from USPTO research datasets page
USPTO_AI_PATENT_BASE_URL = "https://www.uspto.gov/ip-policy/economic-research/research-datasets"


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Download USPTO AI Patent Dataset and upload to S3.
    
    Event structure:
    {
        "s3_bucket": "sbir-etl-production-data",
        "source_url": "https://...",  # Optional
        "force_refresh": false
    }
    """
    try:
        s3_bucket = event.get("s3_bucket") or os.environ.get("S3_BUCKET")
        if not s3_bucket:
            raise ValueError("S3_BUCKET not provided in event or environment")

        source_url = event.get("source_url")
        force_refresh = event.get("force_refresh", False)

        # Construct URL if not provided
        # Note: This is a placeholder; update with actual AI Patent Dataset download URL
        if not source_url:
            # The AI Patent Dataset may be available as a direct download link
            # Update this URL based on the actual USPTO research datasets page
            source_url = f"{USPTO_AI_PATENT_BASE_URL}/artificial-intelligence-patent-dataset"

        # Download data
        print(f"Downloading USPTO AI Patent Dataset from {source_url}")
        req = Request(source_url)
        req.add_header("User-Agent", "SBIR-ETL-Lambda/1.0")
        
        with urlopen(req, timeout=600) as response:  # Longer timeout for large files
            data = response.read()

        # Compute hash
        file_hash = hashlib.sha256(data).hexdigest()

        # Generate S3 key with date
        timestamp = datetime.now(timezone.utc)
        date_str = timestamp.strftime("%Y-%m-%d")
        
        # Determine file extension from content type or URL
        content_type = response.headers.get("Content-Type", "")
        if "csv" in content_type.lower() or source_url.endswith(".csv"):
            file_ext = ".csv"
        elif "json" in content_type.lower() or source_url.endswith(".json"):
            file_ext = ".json"
        elif "zip" in content_type.lower() or source_url.endswith(".zip"):
            file_ext = ".zip"
        else:
            file_ext = ".csv"  # Default
        
        s3_key = f"raw/uspto/ai_patents/{date_str}/ai_patent_dataset{file_ext}"

        # Upload to S3
        print(f"Uploading to s3://{s3_bucket}/{s3_key}")
        s3_client.put_object(
            Bucket=s3_bucket,
            Key=s3_key,
            Body=data,
            ContentType=content_type or "application/octet-stream",
            Metadata={
                "sha256": file_hash,
                "source_url": source_url,
                "downloaded_at": timestamp.isoformat(),
                "dataset": "ai_patents",
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
            },
        }

    except Exception as e:
        print(f"Error downloading USPTO AI Patent data: {e}")
        import traceback
        traceback.print_exc()
        return {
            "statusCode": 500,
            "body": {
                "status": "error",
                "error": str(e),
            },
        }

