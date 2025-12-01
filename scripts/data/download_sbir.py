#!/usr/bin/env python3
"""Download SBIR awards CSV from SBIR.gov to S3.

Usage:
    python scripts/data/download_sbir.py
    python scripts/data/download_sbir.py --s3-bucket my-bucket
"""

import argparse
import hashlib
import os
from datetime import datetime, UTC

import boto3
import requests

SBIR_AWARDS_URL = "https://data.www.sbir.gov/awarddatafiles/Award_All_Years.csv"


def download_sbir_awards(s3_bucket: str) -> dict:
    """Download SBIR awards CSV and upload to S3."""
    print(f"📥 Downloading SBIR awards from: {SBIR_AWARDS_URL}")

    s3 = boto3.client("s3")

    # Download file
    response = requests.get(SBIR_AWARDS_URL, stream=True, timeout=300)
    response.raise_for_status()

    content_length = int(response.headers.get("content-length", 0))
    print(f"📊 Size: {content_length / 1024 / 1024:.1f} MB")

    # Download and hash
    hasher = hashlib.sha256()
    chunks = []
    downloaded = 0

    for chunk in response.iter_content(chunk_size=1024 * 1024):  # 1MB chunks
        chunks.append(chunk)
        hasher.update(chunk)
        downloaded += len(chunk)
        if content_length:
            pct = downloaded / content_length * 100
            print(f"  {pct:.1f}% ({downloaded / 1024 / 1024:.1f} MB)", end="\r")

    print()
    data = b"".join(chunks)
    file_hash = hasher.hexdigest()

    # Check if file has changed
    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    s3_key = f"raw/awards/{date_str}/Award_All_Years.csv"

    # Check previous version
    try:
        existing = s3.list_objects_v2(
            Bucket=s3_bucket,
            Prefix="raw/awards/",
        )
        if existing.get("Contents"):
            latest = sorted(existing["Contents"], key=lambda x: x["LastModified"])[-1]
            latest_meta = s3.head_object(Bucket=s3_bucket, Key=latest["Key"])
            previous_hash = latest_meta.get("Metadata", {}).get("sha256", "")

            if previous_hash == file_hash:
                print(f"✅ No changes detected (hash matches {latest['Key']})")
                return {
                    "changed": False,
                    "s3_bucket": s3_bucket,
                    "s3_key": latest["Key"],
                    "sha256": file_hash,
                }
    except Exception as e:
        print(f"⚠️ Could not check previous version: {e}")

    # Upload to S3
    print(f"📤 Uploading to s3://{s3_bucket}/{s3_key}")
    s3.put_object(
        Bucket=s3_bucket,
        Key=s3_key,
        Body=data,
        ContentType="text/csv",
        Metadata={
            "source_url": SBIR_AWARDS_URL,
            "sha256": file_hash,
            "downloaded_at": datetime.now(UTC).isoformat(),
        },
    )

    print(f"✅ Uploaded: {len(data) / 1024 / 1024:.1f} MB")
    print(f"   SHA256: {file_hash[:16]}...")

    return {
        "changed": True,
        "s3_bucket": s3_bucket,
        "s3_key": s3_key,
        "size": len(data),
        "sha256": file_hash,
    }


def main():
    parser = argparse.ArgumentParser(description="Download SBIR awards to S3")
    parser.add_argument("--s3-bucket", default=os.environ.get("S3_BUCKET", "sbir-etl-production-data"))
    args = parser.parse_args()

    result = download_sbir_awards(args.s3_bucket)

    if result["changed"]:
        print(f"\n✅ New data uploaded: s3://{result['s3_bucket']}/{result['s3_key']}")
    else:
        print(f"\n✅ No changes - using existing: s3://{result['s3_bucket']}/{result['s3_key']}")


if __name__ == "__main__":
    main()
