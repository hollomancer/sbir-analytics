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
# PatentsView provides bulk data downloads via S3
# Documentation: https://patentsview.org/downloads/data-downloads
# Direct S3 download URLs for bulk data tables
PATENTSVIEW_S3_BASE = "https://s3.amazonaws.com/data.patentsview.org/download"

# Mapping of table names to S3 download URLs
PATENTSVIEW_DOWNLOAD_URLS = {
    "patent": f"{PATENTSVIEW_S3_BASE}/patents.zip",
    "patents": f"{PATENTSVIEW_S3_BASE}/patents.zip",
    "assignee": f"{PATENTSVIEW_S3_BASE}/assignees.zip",
    "assignees": f"{PATENTSVIEW_S3_BASE}/assignees.zip",
    "inventor": f"{PATENTSVIEW_S3_BASE}/inventors.zip",
    "inventors": f"{PATENTSVIEW_S3_BASE}/inventors.zip",
    "location": f"{PATENTSVIEW_S3_BASE}/locations.zip",
    "locations": f"{PATENTSVIEW_S3_BASE}/locations.zip",
    "citation": f"{PATENTSVIEW_S3_BASE}/citations.zip",
    "citations": f"{PATENTSVIEW_S3_BASE}/citations.zip",
    "cpc": f"{PATENTSVIEW_S3_BASE}/cpcs.zip",
    "cpcs": f"{PATENTSVIEW_S3_BASE}/cpcs.zip",
    "nber": f"{PATENTSVIEW_S3_BASE}/nber_subcategories.zip",
    "nber_subcategory": f"{PATENTSVIEW_S3_BASE}/nber_subcategories.zip",
    "uspc": f"{PATENTSVIEW_S3_BASE}/uspcs.zip",
    "uspcs": f"{PATENTSVIEW_S3_BASE}/uspcs.zip",
    "foreign_citation": f"{PATENTSVIEW_S3_BASE}/foreign_citations.zip",
    "foreign_citations": f"{PATENTSVIEW_S3_BASE}/foreign_citations.zip",
    "lawyer": f"{PATENTSVIEW_S3_BASE}/lawyers.zip",
    "lawyers": f"{PATENTSVIEW_S3_BASE}/lawyers.zip",
}

PATENTSVIEW_DOWNLOADS_PAGE = "https://patentsview.org/downloads/data-downloads"


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
            # Try to construct URL from known table mappings
            table_key = dataset_type.lower()
            if table_key in PATENTSVIEW_DOWNLOAD_URLS:
                source_url = PATENTSVIEW_DOWNLOAD_URLS[table_key]
                print(f"Using default PatentsView URL for '{dataset_type}': {source_url}")
            else:
                raise ValueError(
                    f"Unknown dataset_type '{dataset_type}' and no source_url provided. "
                    f"Known types: {', '.join(sorted(set(k for k in PATENTSVIEW_DOWNLOAD_URLS.keys() if not k.endswith('s'))))}. "
                    f"Or provide source_url directly. "
                    f"See {PATENTSVIEW_DOWNLOADS_PAGE} for more options."
                )

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

