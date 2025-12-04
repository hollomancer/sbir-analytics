#!/usr/bin/env python3
"""Download USPTO data files to S3.

Replaces the Lambda function with a script that runs on GitHub Actions.

Usage:
    python scripts/data/download_uspto.py --dataset patentsview --table patent
    python scripts/data/download_uspto.py --dataset assignments
    python scripts/data/download_uspto.py --dataset ai_patents

URLs verified: December 2024
- PatentsView: https://download.patentsview.org/data (bulk download endpoint)
- USPTO Assignments: 2023 is latest release (verified Dec 2024)
- USPTO AI Patents: 2023 is latest release (verified Dec 2024, updated Jan 8, 2025)
"""

import argparse
import hashlib
import os
import sys
import time
from datetime import datetime, UTC

import boto3
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# PatentsView configuration
# Verified: December 2024
# Source: https://download.patentsview.org/data
PATENTSVIEW_BASE_URL = "https://download.patentsview.org/data"
PATENTSVIEW_TABLES = {
    "patent": "g_patent.tsv.zip",
    "assignee": "g_assignee_disambiguated.tsv.zip",
    "inventor": "g_inventor_disambiguated.tsv.zip",
    "location": "g_location_disambiguated.tsv.zip",
    "cpc": "g_cpc_current.tsv.zip",
    "gov_interest": "g_gov_interest.tsv.zip",
}

# USPTO Assignment Dataset
# Verified: December 2024 - 2023 is latest release
# Source: https://www.uspto.gov/ip-policy/economic-research/research-datasets/patent-assignment-dataset
# Full dataset includes: assignment, assignor, assignee, documentid, assignment_conveyance, documentid_admin
USPTO_ASSIGNMENT_URL = "https://data.uspto.gov/ui/datasets/products/files/ECORSEXC/2023/csv.zip"

# USPTO AI Patent Dataset
# Verified: December 2024 - 2023 is latest release (updated Jan 8, 2025)
# Source: https://www.uspto.gov/ip-policy/economic-research/research-datasets/artificial-intelligence-patent-dataset
# Note: 2023 release uses CSV format (2020 release used TSV)
USPTO_AI_PATENT_URL = "https://data.uspto.gov/ui/datasets/products/files/ECOPATAI/2023/ai_model_predictions.csv.zip"

# User-Agent header for USPTO downloads
USER_AGENT = "SBIR-Analytics/1.0 (GitHub Actions; +https://github.com/your-org/sbir-analytics)"


def create_session_with_retries() -> requests.Session:
    """Create requests session with retry logic and exponential backoff."""
    session = requests.Session()

    # Configure retry strategy
    retry_strategy = Retry(
        total=3,  # Maximum 3 retry attempts
        backoff_factor=2,  # Exponential backoff: 2, 4, 8 seconds
        status_forcelist=[429, 500, 502, 503, 504],  # Retry on these HTTP status codes
        allowed_methods=["GET"],  # Only retry GET requests
    )

    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    # Set User-Agent header
    session.headers.update({"User-Agent": USER_AGENT})

    return session


def download_and_upload(source_url: str, s3_bucket: str, s3_key: str) -> dict:
    """Download file and stream to S3 with retry logic and progress tracking.

    Args:
        source_url: URL to download from
        s3_bucket: S3 bucket name
        s3_key: S3 object key

    Returns:
        dict with s3_bucket, s3_key, size, and sha256

    Raises:
        requests.exceptions.RequestException: On download failure after retries
        boto3.exceptions.S3UploadFailedError: On S3 upload failure
    """
    print(f"📥 Downloading: {source_url}")
    print(f"   User-Agent: {USER_AGENT}")

    s3 = boto3.client("s3")
    session = create_session_with_retries()

    try:
        # Stream download with retry logic
        response = session.get(source_url, stream=True, timeout=300)
        response.raise_for_status()

        content_length = int(response.headers.get("content-length", 0))
        print(f"📊 Size: {content_length / 1024 / 1024:.1f} MB")

        # Calculate hash while downloading
        hasher = hashlib.sha256()
        chunks = []
        downloaded = 0
        start_time = time.time()

        for chunk in response.iter_content(chunk_size=8 * 1024 * 1024):  # 8MB chunks
            if chunk:  # Filter out keep-alive chunks
                chunks.append(chunk)
                hasher.update(chunk)
                downloaded += len(chunk)

                if content_length:
                    pct = downloaded / content_length * 100
                    elapsed = time.time() - start_time
                    speed = downloaded / elapsed / 1024 / 1024 if elapsed > 0 else 0
                    print(f"  {pct:.1f}% ({downloaded / 1024 / 1024:.1f} MB) - {speed:.1f} MB/s", end="\r")

        print()  # New line after progress
        data = b"".join(chunks)
        file_hash = hasher.hexdigest()

        elapsed = time.time() - start_time
        print(f"⏱️  Download completed in {elapsed:.1f}s")

        # Upload to S3
        print(f"📤 Uploading to s3://{s3_bucket}/{s3_key}")
        upload_start = time.time()

        s3.put_object(
            Bucket=s3_bucket,
            Key=s3_key,
            Body=data,
            ContentType="application/zip",
            Metadata={
                "source_url": source_url,
                "sha256": file_hash,
                "downloaded_at": datetime.now(UTC).isoformat(),
                "user_agent": USER_AGENT,
            },
        )

        upload_elapsed = time.time() - upload_start
        print(f"✅ Uploaded: {len(data) / 1024 / 1024:.1f} MB in {upload_elapsed:.1f}s")
        print(f"   SHA256: {file_hash[:16]}...")

        return {
            "s3_bucket": s3_bucket,
            "s3_key": s3_key,
            "size": len(data),
            "sha256": file_hash,
            "download_time_seconds": elapsed,
            "upload_time_seconds": upload_elapsed,
        }

    except requests.exceptions.RequestException as e:
        print(f"❌ Download failed after retries: {e}")
        raise
    except Exception as e:
        print(f"❌ Upload failed: {e}")
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Download USPTO data to S3",
        epilog="""
Examples:
  python scripts/data/download_uspto.py --dataset patentsview --table patent
  python scripts/data/download_uspto.py --dataset assignments
  python scripts/data/download_uspto.py --dataset ai_patents
  python scripts/data/download_uspto.py --dataset patentsview --table assignee --s3-bucket my-bucket
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dataset",
        required=True,
        choices=["patentsview", "assignments", "ai_patents"],
        help="Dataset to download",
    )
    parser.add_argument(
        "--table",
        help="PatentsView table name (for patentsview dataset). Valid: %(choices)s",
        choices=list(PATENTSVIEW_TABLES.keys()),
    )
    parser.add_argument(
        "--s3-bucket",
        default=os.environ.get("S3_BUCKET", "sbir-etl-production-data"),
        help="S3 bucket name (default: %(default)s)",
    )
    args = parser.parse_args()

    date_str = datetime.now(UTC).strftime("%Y-%m-%d")

    print(f"🚀 USPTO Data Download")
    print(f"   Dataset: {args.dataset}")
    print(f"   Date: {date_str}")
    print(f"   S3 Bucket: {args.s3_bucket}")
    print()

    try:
        if args.dataset == "patentsview":
            table = args.table or "patent"
            if table not in PATENTSVIEW_TABLES:
                print(f"❌ Unknown table: {table}")
                print(f"   Valid tables: {', '.join(PATENTSVIEW_TABLES.keys())}")
                sys.exit(1)

            filename = PATENTSVIEW_TABLES[table]
            source_url = f"{PATENTSVIEW_BASE_URL}/{filename}"
            s3_key = f"raw/uspto/patentsview/{date_str}/{table}.zip"
            print(f"   Table: {table}")

        elif args.dataset == "assignments":
            source_url = USPTO_ASSIGNMENT_URL
            s3_key = f"raw/uspto/assignments/{date_str}/patent_assignments.zip"
            print(f"   Format: CSV (2023 release)")

        elif args.dataset == "ai_patents":
            source_url = USPTO_AI_PATENT_URL
            s3_key = f"raw/uspto/ai_patents/{date_str}/ai_patent_dataset.zip"
            print(f"   Format: CSV (2023 release, updated Jan 8, 2025)")

        print()
        result = download_and_upload(source_url, args.s3_bucket, s3_key)

        print()
        print("=" * 60)
        print("✅ Download Complete")
        print("=" * 60)
        print(f"S3 Location: s3://{result['s3_bucket']}/{result['s3_key']}")
        print(f"File Size: {result['size'] / 1024 / 1024:.1f} MB")
        print(f"SHA256: {result['sha256']}")
        print(f"Download Time: {result['download_time_seconds']:.1f}s")
        print(f"Upload Time: {result['upload_time_seconds']:.1f}s")
        print("=" * 60)

    except requests.exceptions.Timeout as e:
        print()
        print("=" * 60)
        print("❌ Download Timeout")
        print("=" * 60)
        print(f"Error: Request timed out after 300 seconds")
        print(f"URL: {source_url}")
        print(f"Suggestion: Check network connectivity or try again later")
        print("=" * 60)
        sys.exit(1)

    except requests.exceptions.HTTPError as e:
        print()
        print("=" * 60)
        print("❌ HTTP Error")
        print("=" * 60)
        print(f"Status Code: {e.response.status_code}")
        print(f"URL: {source_url}")
        print(f"Error: {e}")
        print(f"Suggestion: Verify URL is correct and accessible")
        print("=" * 60)
        sys.exit(1)

    except requests.exceptions.RequestException as e:
        print()
        print("=" * 60)
        print("❌ Network Error")
        print("=" * 60)
        print(f"Error: {e}")
        print(f"URL: {source_url}")
        print(f"Suggestion: Check network connectivity and try again")
        print("=" * 60)
        sys.exit(1)

    except Exception as e:
        print()
        print("=" * 60)
        print("❌ Unexpected Error")
        print("=" * 60)
        print(f"Error: {e}")
        print(f"Type: {type(e).__name__}")
        import traceback
        print(f"Traceback:")
        traceback.print_exc()
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
