#!/usr/bin/env python3
"""Download USPTO data files to S3.

Replaces the Lambda function with a script that runs on GitHub Actions.

Usage:
    python scripts/data/download_uspto.py --dataset patentsview --table patent
    python scripts/data/download_uspto.py --dataset assignments
    python scripts/data/download_uspto.py --dataset ai_patents
"""

import argparse
import hashlib
import os
import sys
from datetime import datetime, UTC

import boto3
import requests

# PatentsView configuration
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
USPTO_ASSIGNMENT_URL = "https://data.uspto.gov/ui/datasets/products/files/ECORSEXC/2023/csv.zip"

# USPTO AI Patent Dataset
USPTO_AI_PATENT_URL = "https://data.uspto.gov/ui/datasets/products/files/ECOPATAI/2023/ai_model_predictions.csv.zip"


def download_and_upload(source_url: str, s3_bucket: str, s3_key: str) -> dict:
    """Download file and stream to S3."""
    print(f"📥 Downloading: {source_url}")

    s3 = boto3.client("s3")

    # Stream download
    response = requests.get(source_url, stream=True, timeout=300)
    response.raise_for_status()

    content_length = int(response.headers.get("content-length", 0))
    print(f"📊 Size: {content_length / 1024 / 1024:.1f} MB")

    # Calculate hash while uploading
    hasher = hashlib.sha256()
    chunks = []
    downloaded = 0

    for chunk in response.iter_content(chunk_size=8 * 1024 * 1024):  # 8MB chunks
        chunks.append(chunk)
        hasher.update(chunk)
        downloaded += len(chunk)
        if content_length:
            pct = downloaded / content_length * 100
            print(f"  {pct:.1f}% ({downloaded / 1024 / 1024:.1f} MB)", end="\r")

    print()
    data = b"".join(chunks)
    file_hash = hasher.hexdigest()

    # Upload to S3
    print(f"📤 Uploading to s3://{s3_bucket}/{s3_key}")
    s3.put_object(
        Bucket=s3_bucket,
        Key=s3_key,
        Body=data,
        ContentType="application/zip",
        Metadata={
            "source_url": source_url,
            "sha256": file_hash,
            "downloaded_at": datetime.now(UTC).isoformat(),
        },
    )

    print(f"✅ Uploaded: {len(data) / 1024 / 1024:.1f} MB")
    print(f"   SHA256: {file_hash[:16]}...")

    return {
        "s3_bucket": s3_bucket,
        "s3_key": s3_key,
        "size": len(data),
        "sha256": file_hash,
    }


def main():
    parser = argparse.ArgumentParser(description="Download USPTO data to S3")
    parser.add_argument("--dataset", required=True, choices=["patentsview", "assignments", "ai_patents"])
    parser.add_argument("--table", help="PatentsView table name (for patentsview dataset)")
    parser.add_argument("--s3-bucket", default=os.environ.get("S3_BUCKET", "sbir-etl-production-data"))
    args = parser.parse_args()

    date_str = datetime.now(UTC).strftime("%Y-%m-%d")

    if args.dataset == "patentsview":
        table = args.table or "patent"
        if table not in PATENTSVIEW_TABLES:
            print(f"❌ Unknown table: {table}. Valid: {list(PATENTSVIEW_TABLES.keys())}")
            sys.exit(1)

        filename = PATENTSVIEW_TABLES[table]
        source_url = f"{PATENTSVIEW_BASE_URL}/{filename}"
        s3_key = f"raw/uspto/patentsview/{date_str}/{table}.zip"

    elif args.dataset == "assignments":
        source_url = USPTO_ASSIGNMENT_URL
        s3_key = f"raw/uspto/assignments/{date_str}/patent_assignments.zip"

    elif args.dataset == "ai_patents":
        source_url = USPTO_AI_PATENT_URL
        s3_key = f"raw/uspto/ai_patents/{date_str}/ai_patent_dataset.zip"

    try:
        result = download_and_upload(source_url, args.s3_bucket, s3_key)
        print(f"\n✅ Success: s3://{result['s3_bucket']}/{result['s3_key']}")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
