"""Lambda function to download PatentsView data and upload to S3."""

import hashlib
import os
from datetime import datetime, UTC
from typing import Any
from urllib.request import Request, urlopen

import boto3

s3_client = boto3.client("s3")

# PatentsView bulk download URLs
# PatentsView provides bulk data downloads via S3
# Documentation: https://patentsview.org/downloads/data-downloads
# Note: PatentsView may require using their API or website for downloads
# Direct S3 URLs may not be publicly accessible - use source_url parameter if needed

# Alternative download domains (CloudFront + direct S3 buckets)
PATENTSVIEW_BASE_URLS = [
    "https://download.patentsview.org/data",  # CloudFront front-door (no auth required)
    "https://data.patentsview.org/download",  # Direct HTTPS front-end
    "https://data.patentsview.org.s3.amazonaws.com/download",  # Alternate S3 alias
    "https://s3.amazonaws.com/data.patentsview.org/download",  # Legacy bucket
]

PATENTSVIEW_S3_BASE_V1 = PATENTSVIEW_BASE_URLS[-1]

# Mapping of table names to download filenames (all TSV.ZIP with g_ prefix)
PATENTSVIEW_TABLE_FILENAMES = {
    "patent": "g_patent.tsv.zip",
    "patents": "g_patent.tsv.zip",
    "assignee": "g_assignee_disambiguated.tsv.zip",
    "assignees": "g_assignee_disambiguated.tsv.zip",
    "assignee_disambiguated": "g_assignee_disambiguated.tsv.zip",
    "assignee_disambiguated_current": "g_assignee_disambiguated.tsv.zip",
    "inventor": "g_inventor_disambiguated.tsv.zip",
    "inventors": "g_inventor_disambiguated.tsv.zip",
    "location": "g_location_disambiguated.tsv.zip",
    "locations": "g_location_disambiguated.tsv.zip",
    "citation": "g_cpc_current.tsv.zip",
    "citations": "g_cpc_current.tsv.zip",
    "foreign_citation": "g_foreign_citation.tsv.zip",
    "foreign_citations": "g_foreign_citation.tsv.zip",
    "cpc": "g_cpc_current.tsv.zip",
    "cpcs": "g_cpc_current.tsv.zip",
    "cpc_current": "g_cpc_current.tsv.zip",
    "cpc_subsection": "g_cpc_subsection.tsv.zip",
    "nber": "g_nber.tsv.zip",
    "nber_subcategory": "g_nber.tsv.zip",
    "uspc": "g_uspc_current.tsv.zip",
    "uspcs": "g_uspc_current.tsv.zip",
    "lawyer": "g_lawyer.tsv.zip",
    "lawyers": "g_lawyer.tsv.zip",
    "gov_interest": "g_gov_interest.tsv.zip",
    "government_interest": "g_gov_interest.tsv.zip",
}

PATENTSVIEW_DOWNLOADS_PAGE = "https://patentsview.org/downloads/data-downloads"


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
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

        urls_to_try = []
        table_key = dataset_type.lower()

        # Construct URL if not provided
        if not source_url:
            if table_key in PATENTSVIEW_TABLE_FILENAMES:
                filename = PATENTSVIEW_TABLE_FILENAMES[table_key]
                urls_to_try = [f"{base}/{filename}" for base in PATENTSVIEW_BASE_URLS]
                source_url = urls_to_try[0]
                print(
                    f"Using PatentsView download filename '{filename}' for dataset '{dataset_type}'. "
                    f"First attempt: {source_url}"
                )
            else:
                known_types = sorted(
                    {k for k in PATENTSVIEW_TABLE_FILENAMES.keys() if not k.endswith("s")}
                )
                raise ValueError(
                    f"Unknown dataset_type '{dataset_type}' and no source_url provided. "
                    f"Known types: {', '.join(known_types)}. "
                    f"Or provide source_url directly. "
                    f"See {PATENTSVIEW_DOWNLOADS_PAGE} for more options."
                )
        else:
            urls_to_try = [source_url]
            if PATENTSVIEW_S3_BASE_V1 in source_url:
                # Try alternate formats for legacy S3 path
                legacy_suffix = source_url.split(PATENTSVIEW_S3_BASE_V1, maxsplit=1)[-1]
                for base in PATENTSVIEW_BASE_URLS[:-1]:
                    urls_to_try.append(f"{base}{legacy_suffix}")

        # Download data - try multiple URL formats if first fails
        print(f"Downloading PatentsView {dataset_type} from {source_url}")

        data = None
        content_type = ""
        last_error = None

        for url in urls_to_try:
            try:
                print(f"Attempting download from: {url}")
                req = Request(url)
                req.add_header(
                    "User-Agent", "SBIR-Analytics-Lambda/1.0 (https://github.com/sbir-analytics)"
                )
                req.add_header("Accept", "*/*")
                req.add_header("Accept-Encoding", "gzip, deflate")

                with urlopen(req, timeout=300) as response:
                    if response.getcode() == 200:
                        data = response.read()
                        content_type = response.headers.get("Content-Type", "") or ""
                        source_url = url  # Update to the URL that worked
                        print(f"Successfully downloaded from: {url}")
                        break
                    else:
                        print(f"HTTP {response.getcode()} from {url}")
            except Exception as e:
                last_error = e
                print(f"Error downloading from {url}: {e}")
                continue

        if data is None:
            error_msg = f"Failed to download from all attempted URLs. Last error: {last_error}"
            if "403" in str(last_error):
                error_msg += (
                    "\n\nNote: PatentsView S3 bucket may require authentication or use a different download mechanism. "
                    "Please check https://patentsview.org/downloads/data-downloads for the correct download method. "
                    "You may need to provide a source_url parameter with the actual download link."
                )
            raise Exception(error_msg)

        # Compute hash
        file_hash = hashlib.sha256(data).hexdigest()

        # Generate S3 key with date
        timestamp = datetime.now(UTC)
        date_str = timestamp.strftime("%Y-%m-%d")
        # Determine file extension from content type or URL hint
        lower_content_type = content_type.lower()
        lower_url = source_url.lower()
        if "zip" in lower_content_type or lower_url.endswith(".zip"):
            file_ext = ".zip"
        elif "csv" in lower_content_type or lower_url.endswith(".csv"):
            file_ext = ".csv"
        elif "json" in lower_content_type or lower_url.endswith(".json"):
            file_ext = ".json"
        elif (
            "tsv" in lower_content_type or "tab" in lower_content_type or lower_url.endswith(".tsv")
        ):
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
            ContentType=content_type
            or ("application/zip" if file_ext == ".zip" else "text/tab-separated-values"),
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
