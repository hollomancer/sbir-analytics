"""Lambda function to download USPTO Patent Assignment Dataset and upload to S3."""

import hashlib
import os
from datetime import datetime, timezone
from typing import Any, Dict
from urllib.request import Request, urlopen

import boto3

s3_client = boto3.client("s3")

# USPTO Patent Assignment Dataset URLs
# Research datasets page: https://www.uspto.gov/ip-policy/economic-research/research-datasets/patent-assignment-dataset
# Legacy page: https://www.uspto.gov/learning-and-resources/fee-schedules/patent-assignment-data
#
# Direct download URLs (2024 release - latest as of 2025)
USPTO_ASSIGNMENT_BASE = "https://data.uspto.gov/ui/datasets/products/files/ECORSEXC/2023"
USPTO_ASSIGNMENT_DEFAULT_URLS = {
    "csv": f"{USPTO_ASSIGNMENT_BASE}/csv.zip",
    "dta": f"{USPTO_ASSIGNMENT_BASE}/dta.zip",
    # Parquet format may not be available - CSV and DTA are the standard formats
}

USPTO_ASSIGNMENT_DATASET_PAGE = "https://www.uspto.gov/ip-policy/economic-research/research-datasets/patent-assignment-dataset"
USPTO_ASSIGNMENT_LEGACY_PAGE = "https://www.uspto.gov/learning-and-resources/fee-schedules/patent-assignment-data"


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Download USPTO Patent Assignment Dataset and upload to S3.
    
    Event structure:
    {
        "s3_bucket": "sbir-etl-production-data",
        "source_url": "https://...",  # Optional, defaults to USPTO
        "format": "csv",  # or "dta", "parquet" - defaults to csv
        "force_refresh": false
    }
    """
    try:
        s3_bucket = event.get("s3_bucket") or os.environ.get("S3_BUCKET")
        if not s3_bucket:
            raise ValueError("S3_BUCKET not provided in event or environment")

        source_url = event.get("source_url")
        file_format = event.get("format", "csv")
        force_refresh = event.get("force_refresh", False)

        # Construct URL if not provided
        if not source_url:
            # Use default URL based on format (2023 release)
            if file_format in USPTO_ASSIGNMENT_DEFAULT_URLS:
                source_url = USPTO_ASSIGNMENT_DEFAULT_URLS[file_format]
                print(f"Using default USPTO Patent Assignment URL ({file_format} format): {source_url}")
                print(f"Note: This is the 2023 release. Check {USPTO_ASSIGNMENT_DATASET_PAGE} for newer releases.")
            else:
                # Unknown format - try to construct URL or provide helpful error
                if file_format == "parquet":
                    raise ValueError(
                        f"Parquet format is not available for USPTO Patent Assignment Dataset. "
                        f"Available formats: csv, dta. "
                        f"See {USPTO_ASSIGNMENT_DATASET_PAGE} for available formats."
                    )
                else:
                    raise ValueError(
                        f"Unknown format '{file_format}'. Available formats: csv, dta. "
                        f"Or provide source_url directly. "
                        f"See {USPTO_ASSIGNMENT_DATASET_PAGE} for more information."
                    )

        # Download data
        print(f"Downloading USPTO Patent Assignment data ({file_format}) from {source_url}")
        req = Request(source_url)
        req.add_header("User-Agent", "SBIR-ETL-Lambda/1.0")
        
        with urlopen(req, timeout=600) as response:  # Longer timeout for large files
            data = response.read()

        # Compute hash
        file_hash = hashlib.sha256(data).hexdigest()

        # Generate S3 key with date
        timestamp = datetime.now(timezone.utc)
        date_str = timestamp.strftime("%Y-%m-%d")
        file_ext = file_format if file_format.startswith(".") else f".{file_format}"
        s3_key = f"raw/uspto/assignments/{date_str}/patent_assignments{file_ext}"

        # Determine content type
        content_type_map = {
            "csv": "text/csv",
            "dta": "application/x-stata",
            "parquet": "application/parquet",
        }
        content_type = content_type_map.get(file_format, "application/octet-stream")

        # Upload to S3
        print(f"Uploading to s3://{s3_bucket}/{s3_key}")
        s3_client.put_object(
            Bucket=s3_bucket,
            Key=s3_key,
            Body=data,
            ContentType=content_type,
            Metadata={
                "sha256": file_hash,
                "source_url": source_url,
                "downloaded_at": timestamp.isoformat(),
                "format": file_format,
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
                "format": file_format,
            },
        }

    except Exception as e:
        print(f"Error downloading USPTO Assignment data: {e}")
        import traceback
        traceback.print_exc()
        return {
            "statusCode": 500,
            "body": {
                "status": "error",
                "error": str(e),
            },
        }
