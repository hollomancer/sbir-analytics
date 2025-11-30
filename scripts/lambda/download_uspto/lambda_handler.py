"""Unified Lambda function to download USPTO data and upload to S3.

This function consolidates three previously separate functions:
- download-uspto-patentsview
- download-uspto-assignments
- download-uspto-ai-patents

It supports multiple dataset types via the 'dataset' parameter.
"""

import os
import sys
from datetime import datetime, UTC
from typing import Any

# Add common module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from common.download_utils import (
    create_standard_response,
    determine_file_extension,
    download_file,
    has_file_changed,
    stream_download_to_s3,
    try_multiple_urls,
    upload_to_s3,
)

# PatentsView configuration
PATENTSVIEW_BASE_URLS = [
    "https://download.patentsview.org/data",  # CloudFront front-door (no auth required)
    "https://data.patentsview.org/download",  # Direct HTTPS front-end
    "https://data.patentsview.org.s3.amazonaws.com/download",  # Alternate S3 alias
    "https://s3.amazonaws.com/data.patentsview.org/download",  # Legacy bucket
]

PATENTSVIEW_TABLE_FILENAMES = {
    "patent": "g_patent.tsv.zip",
    "patents": "g_patent.tsv.zip",
    "assignee": "g_assignee_disambiguated.tsv.zip",
    "assignees": "g_assignee_disambiguated.tsv.zip",
    "assignee_disambiguated": "g_assignee_disambiguated.tsv.zip",
    "inventor": "g_inventor_disambiguated.tsv.zip",
    "inventors": "g_inventor_disambiguated.tsv.zip",
    "location": "g_location_disambiguated.tsv.zip",
    "locations": "g_location_disambiguated.tsv.zip",
    "cpc": "g_cpc_current.tsv.zip",
    "cpcs": "g_cpc_current.tsv.zip",
    "cpc_current": "g_cpc_current.tsv.zip",
    "nber": "g_nber.tsv.zip",
    "uspc": "g_uspc_current.tsv.zip",
    "lawyer": "g_lawyer.tsv.zip",
    "lawyers": "g_lawyer.tsv.zip",
    "gov_interest": "g_gov_interest.tsv.zip",
}

# USPTO Assignment Dataset configuration
USPTO_ASSIGNMENT_BASE = "https://data.uspto.gov/ui/datasets/products/files/ECORSEXC/2023"
USPTO_ASSIGNMENT_URLS = {
    "csv": f"{USPTO_ASSIGNMENT_BASE}/csv.zip",  # 1.78 GB
    "dta": f"{USPTO_ASSIGNMENT_BASE}/dta.zip",  # 1.56 GB
}

# USPTO AI Patent Dataset configuration
USPTO_AI_PATENT_BASE = "https://data.uspto.gov/ui/datasets/products/files/ECOPATAI/2023"
USPTO_AI_PATENT_URLS = {
    "csv": f"{USPTO_AI_PATENT_BASE}/ai_model_predictions.csv.zip",  # 764 MB
    "dta": f"{USPTO_AI_PATENT_BASE}/ai_model_predictions.dta.zip",  # 649 MB
}

# Dataset configurations
DATASET_CONFIGS = {
    "patentsview": {
        "s3_prefix": "raw/uspto/patentsview",
        "min_size": 1_000_000,  # 1 MB minimum
        "use_streaming": False,  # PatentsView files are typically smaller
        "validate_zip": True,
    },
    "assignments": {
        "s3_prefix": "raw/uspto/assignments",
        "min_size": 100_000_000,  # 100 MB minimum (full dataset is ~1.5-1.8 GB)
        "use_streaming": True,
        "validate_zip": True,
    },
    "ai_patents": {
        "s3_prefix": "raw/uspto/ai_patents",
        "min_size": 100_000_000,  # 100 MB minimum (2023 dataset is ~650-760 MB)
        "use_streaming": True,
        "validate_zip": True,
    },
}


def get_patentsview_urls(table_name: str) -> list[str]:
    """Get list of URLs to try for PatentsView dataset."""
    table_key = table_name.lower()

    if table_key not in PATENTSVIEW_TABLE_FILENAMES:
        known_types = sorted({k for k in PATENTSVIEW_TABLE_FILENAMES.keys() if not k.endswith("s")})
        raise ValueError(
            f"Unknown PatentsView table '{table_name}'. "
            f"Known types: {', '.join(known_types)}. "
            f"See https://patentsview.org/downloads/data-downloads"
        )

    filename = PATENTSVIEW_TABLE_FILENAMES[table_key]
    return [f"{base}/{filename}" for base in PATENTSVIEW_BASE_URLS]


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Download USPTO data and upload to S3.

    Supports change detection - will report whether file has changed
    compared to the most recent version in S3.

    Event structure:
    {
        "s3_bucket": "sbir-etl-production-data",  # Optional, can use S3_BUCKET env var
        "dataset": "patentsview",  # Required: "patentsview", "assignments", or "ai_patents"
        "source_url": "https://...",  # Optional, will use defaults if not provided
        "table_name": "patent",  # Optional, for PatentsView datasets
        "format": "csv",  # Optional, for assignments/ai_patents (csv or dta)
        "force_refresh": false  # Optional, skip change detection if true
    }

    Returns:
    {
        "statusCode": 200,
        "body": {
            "status": "success",
            "changed": true/false,  # Whether file has changed
            "s3_bucket": "...",
            "s3_key": "...",
            "sha256": "...",
            ...
        }
    }

    Examples:
        # Download PatentsView patent table
        {"dataset": "patentsview", "table_name": "patent"}

        # Download USPTO assignments in CSV format
        {"dataset": "assignments", "format": "csv"}

        # Download USPTO AI patents
        {"dataset": "ai_patents"}
    """
    try:
        # Get S3 bucket
        s3_bucket = event.get("s3_bucket") or os.environ.get("S3_BUCKET")
        if not s3_bucket:
            raise ValueError("S3_BUCKET not provided in event or environment")

        # Get dataset type
        dataset = event.get("dataset", "patentsview")
        if dataset not in DATASET_CONFIGS:
            raise ValueError(
                f"Unknown dataset '{dataset}'. "
                f"Valid options: {', '.join(DATASET_CONFIGS.keys())}"
            )

        config = DATASET_CONFIGS[dataset]
        source_url = event.get("source_url")
        force_refresh = event.get("force_refresh", False)
        urls_to_try = []

        # Determine source URLs based on dataset type
        if dataset == "patentsview":
            table_name = event.get("table_name") or event.get("dataset_type", "patent")

            if source_url:
                urls_to_try = [source_url]
            else:
                urls_to_try = get_patentsview_urls(table_name)
                source_url = urls_to_try[0]

            filename = table_name
            file_format = "tsv.zip"

        elif dataset == "assignments":
            file_format = event.get("format", "csv")
            if file_format not in USPTO_ASSIGNMENT_URLS:
                raise ValueError(
                    f"Unknown format '{file_format}'. Valid: csv, dta. "
                    f"See https://www.uspto.gov/ip-policy/economic-research/research-datasets/patent-assignment-dataset"
                )

            if not source_url:
                source_url = USPTO_ASSIGNMENT_URLS[file_format]
            urls_to_try = [source_url]
            filename = f"patent_assignments_{file_format}"

        elif dataset == "ai_patents":
            file_format = event.get("format", "csv")
            if file_format not in USPTO_AI_PATENT_URLS:
                raise ValueError(f"Unknown format '{file_format}'. Valid: csv, dta")

            if not source_url:
                source_url = USPTO_AI_PATENT_URLS[file_format]
            urls_to_try = [source_url]
            filename = "ai_patent_dataset"

        # Generate S3 key
        timestamp = datetime.now(UTC)
        date_str = timestamp.strftime("%Y-%m-%d")
        s3_key = f"{config['s3_prefix']}/{date_str}/{filename}.zip"

        # Prepare base metadata (SHA256 will be added after download)
        metadata = {
            "source_url": source_url,
            "downloaded_at": timestamp.isoformat(),
            "dataset": dataset,
        }

        # Note: For streaming downloads, SHA256 is computed during upload
        # and stored in S3 metadata by stream_download_to_s3()

        # Download and upload
        if config["use_streaming"]:
            # Use streaming upload for large files
            # Note: For streaming, we can't check before upload (file too large for memory)
            # Instead, we check after upload and report whether changed
            print(f"Using streaming download for {dataset}")

            def stream_func(url):
                return stream_download_to_s3(
                    source_url=url,
                    s3_bucket=s3_bucket,
                    s3_key=s3_key,
                    metadata=metadata,
                    min_size=config["min_size"],
                    validate_zip=config["validate_zip"],
                )

            (total_size, file_hash), successful_url = try_multiple_urls(urls_to_try, stream_func)
            source_url = successful_url

            # Check if changed after upload (for reporting purposes)
            # Note: File is already uploaded - we're just checking against previous versions
            changed = True
            if not force_refresh:
                changed, previous = has_file_changed(
                    current_hash=file_hash,
                    s3_bucket=s3_bucket,
                    s3_prefix=f"{config['s3_prefix']}/",
                    current_size=total_size,
                )
                print(f"Change detection (post-upload): changed={changed}")
            else:
                print("Force refresh enabled - skipping change detection")

        else:
            # Download to memory first for smaller files
            # Can check before upload and skip if unchanged
            print(f"Using in-memory download for {dataset}")

            def download_func(url):
                return download_file(url, max_size_mb=500)

            (data, content_type), successful_url = try_multiple_urls(urls_to_try, download_func)
            source_url = successful_url

            # Compute hash
            import hashlib

            file_hash = hashlib.sha256(data).hexdigest()

            # Check if changed before upload
            changed = True
            if not force_refresh:
                changed, previous = has_file_changed(
                    current_hash=file_hash,
                    s3_bucket=s3_bucket,
                    s3_prefix=f"{config['s3_prefix']}/",
                    current_size=len(data),
                )
                print(f"Change detection (pre-upload): changed={changed}")
            else:
                print("Force refresh enabled - skipping change detection")

            # Upload to S3 (always upload, even if unchanged)
            # Note: Downstream processes may need the file in a specific location
            file_hash = upload_to_s3(
                data=data,
                s3_bucket=s3_bucket,
                s3_key=s3_key,
                content_type=content_type or "application/zip",
                metadata={
                    **metadata,
                    "sha256": file_hash,
                },
            )
            total_size = len(data)

        print(f"Successfully processed {dataset}: {total_size / 1_000_000:.1f} MB")

        return create_standard_response(
            success=True,
            s3_bucket=s3_bucket,
            s3_key=s3_key,
            sha256=file_hash,
            file_size=total_size,
            source_url=source_url,
            dataset=dataset,
            changed=changed,  # Report whether file has changed
        )

    except Exception as e:
        print(f"Error downloading USPTO data: {e}")
        import traceback

        traceback.print_exc()
        return create_standard_response(success=False, error=str(e))
