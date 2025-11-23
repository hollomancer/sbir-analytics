"""Lambda function to download USPTO AI Patent Dataset and upload to S3."""

import hashlib
import os
from datetime import datetime, UTC
from typing import Any
from urllib.request import Request, urlopen

import boto3

s3_client = boto3.client("s3")

# USPTO AI Patent Dataset URLs
# Research datasets page: https://www.uspto.gov/ip-policy/economic-research/research-datasets/artificial-intelligence-patent-dataset
# Developer portal: https://developer.uspto.gov/product/artificial-intelligence-patent-dataset-stata-dta-and-ms-excel-csv
#
# Direct download URLs (latest 2023 release)
USPTO_AI_PATENT_BASE = "https://data.uspto.gov/ui/datasets/products/files/ECOPATAI/2023"
USPTO_AI_PATENT_DEFAULT_URLS = {
    "csv": f"{USPTO_AI_PATENT_BASE}/ai_model_predictions.csv.zip",
    "dta": f"{USPTO_AI_PATENT_BASE}/ai_model_predictions.dta.zip",
    # Note: TSV format is available in 2020 release only
}

USPTO_AI_PATENT_DATASET_PAGE = "https://www.uspto.gov/ip-policy/economic-research/research-datasets/artificial-intelligence-patent-dataset"
USPTO_AI_PATENT_DEVELOPER_PORTAL = "https://developer.uspto.gov/product/artificial-intelligence-patent-dataset-stata-dta-and-ms-excel-csv"


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
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

        # Construct URL if not provided
        if not source_url:
            # Use default CSV format URL (2023 release)
            source_url = USPTO_AI_PATENT_DEFAULT_URLS.get("csv")
            print(f"Using default USPTO AI Patent Dataset URL (CSV format): {source_url}")
            print(f"Note: Other formats available at {USPTO_AI_PATENT_DATASET_PAGE}")

        # Download data
        print(f"Downloading USPTO AI Patent Dataset from {source_url}")
        req = Request(source_url)
        req.add_header("User-Agent", "SBIR-Analytics-Lambda/1.0")

        with urlopen(req, timeout=600) as response:  # Longer timeout for large files
            data = response.read()
            content_type = response.headers.get("Content-Type", "") or ""

        # Compute hash
        file_hash = hashlib.sha256(data).hexdigest()

        # Generate S3 key with date
        timestamp = datetime.now(UTC)
        date_str = timestamp.strftime("%Y-%m-%d")

        # Determine file extension from content type or URL
        lower_content_type = content_type.lower()
        lower_url = source_url.lower()
        if "zip" in lower_content_type or lower_url.endswith(".zip"):
            file_ext = ".zip"
        elif "csv" in lower_content_type or lower_url.endswith(".csv"):
            file_ext = ".csv"
        elif "json" in lower_content_type or lower_url.endswith(".json"):
            file_ext = ".json"
        else:
            file_ext = ".csv"  # Default

        s3_key = f"raw/uspto/ai_patents/{date_str}/ai_patent_dataset{file_ext}"

        # Upload to S3
        print(f"Uploading to s3://{s3_bucket}/{s3_key}")
        s3_client.put_object(
            Bucket=s3_bucket,
            Key=s3_key,
            Body=data,
            ContentType=content_type
            or ("application/zip" if file_ext == ".zip" else "application/octet-stream"),
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
