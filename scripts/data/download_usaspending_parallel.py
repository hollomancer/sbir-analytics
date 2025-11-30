#!/usr/bin/env python3
"""Parallel USAspending database download with S3 multipart upload.

Optimizations:
- Parallel chunk downloads (configurable concurrency)
- Direct streaming to S3 multipart upload
- Automatic retry and resume capability across runs
- Preserves upload state on failure for next run to resume
"""

import argparse
import asyncio
import sys
import time
from datetime import UTC, datetime

import aiohttp
import boto3

from scripts.data.parallel_download import DownloadChunk, download_chunk
from scripts.usaspending.check_new_file import find_latest_available_file


def get_all_uploaded_parts(s3_client, bucket: str, key: str, upload_id: str) -> dict:
    """Get all uploaded parts with pagination (handles >1000 parts)."""
    parts = {}
    part_marker = 0

    while True:
        response = s3_client.list_parts(
            Bucket=bucket,
            Key=key,
            UploadId=upload_id,
            PartNumberMarker=part_marker,
        )

        for part in response.get("Parts", []):
            parts[part["PartNumber"]] = {
                "ETag": part["ETag"],
                "PartNumber": part["PartNumber"],
            }

        if not response.get("IsTruncated", False):
            break
        part_marker = response.get("NextPartNumberMarker", 0)

    return parts


async def parallel_download_to_s3(
    source_url: str,
    s3_bucket: str,
    s3_key: str,
    chunk_size: int = 50 * 1024 * 1024,  # 50 MB
    max_concurrent: int = 10,
) -> dict:
    """Download file in parallel and upload to S3 with resume support."""
    overall_start = time.time()
    s3_client = boto3.client("s3")

    print("=" * 80)
    print("📥 USAspending Database Download (with resume support)")
    print("=" * 80)

    # Get file size
    async with aiohttp.ClientSession() as session:
        async with session.head(source_url) as response:
            file_size = int(response.headers.get("Content-Length", 0))
            if file_size == 0:
                raise ValueError("Cannot determine file size")

    file_size_gb = file_size / 1024 / 1024 / 1024
    print(f"📊 File size: {file_size_gb:.2f} GB ({file_size:,} bytes)")
    print(f"🔗 Source: {source_url}")
    print(f"📦 S3 destination: s3://{s3_bucket}/{s3_key}")

    # Find existing multipart upload for this exact key
    existing_uploads = s3_client.list_multipart_uploads(Bucket=s3_bucket, Prefix=s3_key)
    upload_id = None
    existing_parts = {}

    for upload in existing_uploads.get("Uploads", []):
        if upload["Key"] == s3_key:
            upload_id = upload["UploadId"]
            print(f"🔄 Resuming existing upload: {upload_id[:20]}...")
            existing_parts = get_all_uploaded_parts(s3_client, s3_bucket, s3_key, upload_id)
            print(f"✅ Found {len(existing_parts)} already uploaded parts")
            break

    if not upload_id:
        multipart = s3_client.create_multipart_upload(
            Bucket=s3_bucket, Key=s3_key, ContentType="application/zip"
        )
        upload_id = multipart["UploadId"]
        print(f"🆕 Created new upload: {upload_id[:20]}...")

    # Calculate chunks
    chunks = []
    for i in range(0, file_size, chunk_size):
        end = min(i + chunk_size - 1, file_size - 1)
        chunks.append(DownloadChunk(chunk_id=len(chunks), start_byte=i, end_byte=end))

    total_chunks = len(chunks)
    remaining_chunks = [c for c in chunks if (c.chunk_id + 1) not in existing_parts]

    print(f"📦 Total chunks: {total_chunks} (~{chunk_size / 1024 / 1024:.0f} MB each)")
    print(f"⏭️  Already uploaded: {len(existing_parts)}")
    print(f"📥 Remaining: {len(remaining_chunks)}")
    print(f"⚡ Concurrency: {max_concurrent}")
    print()

    if not remaining_chunks:
        print("✅ All parts already uploaded, completing upload...")
        all_parts = list(existing_parts.values())
    else:
        # Download remaining chunks
        semaphore = asyncio.Semaphore(max_concurrent)
        completed = len(existing_parts)
        bytes_done = len(existing_parts) * chunk_size
        download_start = time.time()
        new_parts = []

        async def download_and_upload(chunk: DownloadChunk) -> dict:
            nonlocal completed, bytes_done

            async with semaphore:
                part_num = chunk.chunk_id + 1
                chunk_start = time.time()

                async with aiohttp.ClientSession() as sess:
                    downloaded = await download_chunk(sess, source_url, chunk)

                    part_response = s3_client.upload_part(
                        Bucket=s3_bucket,
                        Key=s3_key,
                        PartNumber=part_num,
                        UploadId=upload_id,
                        Body=downloaded.data,
                    )

                    completed += 1
                    chunk_bytes = len(downloaded.data)
                    bytes_done += chunk_bytes

                    elapsed = time.time() - download_start
                    speed = bytes_done / elapsed / 1024 / 1024 if elapsed > 0 else 0
                    pct = completed / total_chunks * 100
                    eta = (file_size - bytes_done) / (bytes_done / elapsed) / 60 if bytes_done > 0 else 0

                    print(
                        f"✅ Part {completed:4d}/{total_chunks} ({pct:5.1f}%) | "
                        f"{chunk_bytes / 1024 / 1024:5.1f} MB in {time.time() - chunk_start:4.1f}s | "
                        f"{speed:5.1f} MB/s | ETA: {eta:5.1f}m"
                    )

                    return {"ETag": part_response["ETag"], "PartNumber": part_num}

        print("🚀 Starting download...")
        try:
            new_parts = await asyncio.gather(*[download_and_upload(c) for c in remaining_chunks])
        except Exception as e:
            # Don't abort - preserve progress for next run
            print()
            print("=" * 80)
            print("⚠️  DOWNLOAD INTERRUPTED - Progress saved for resume")
            print("=" * 80)
            print(f"Error: {e}")
            print(f"Upload ID: {upload_id}")
            print(f"Parts completed: {completed}/{total_chunks}")
            print(f"Progress: {bytes_done / 1024 / 1024 / 1024:.2f} GB")
            print("Run again to resume from this point.")
            print("=" * 80)
            raise

        all_parts = list(existing_parts.values()) + new_parts

    # Complete upload
    print()
    print("🔄 Completing multipart upload...")
    s3_client.complete_multipart_upload(
        Bucket=s3_bucket,
        Key=s3_key,
        UploadId=upload_id,
        MultipartUpload={"Parts": sorted(all_parts, key=lambda p: p["PartNumber"])},
    )

    total_time = time.time() - overall_start
    print()
    print("=" * 80)
    print("✨ DOWNLOAD COMPLETE")
    print("=" * 80)
    print(f"📊 Total size: {file_size_gb:.2f} GB")
    print(f"📦 Total parts: {total_chunks}")
    print(f"⏱️  Total time: {total_time / 60:.1f} minutes")
    print(f"📍 S3: s3://{s3_bucket}/{s3_key}")
    print("=" * 80)

    return {"status": "success", "s3_bucket": s3_bucket, "s3_key": s3_key, "file_size": file_size}


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Parallel USAspending database download")
    parser.add_argument("--s3-bucket", required=True, help="S3 bucket name")
    parser.add_argument("--database-type", choices=["full", "test"], default="full")
    parser.add_argument("--source-url", help="Override source URL")
    parser.add_argument("--s3-key", help="Override S3 key (for resume)")
    parser.add_argument("--max-concurrent", type=int, default=3, help="Max concurrent downloads")

    args = parser.parse_args()

    # Find latest file
    if not args.source_url:
        print("🔍 Finding latest available file...")
        try:
            latest = find_latest_available_file(database_type=args.database_type, s3_bucket=None)
            if not latest:
                print("❌ No available file found")
                sys.exit(1)
            source_url = latest["source_url"]
            print(f"✅ Found: {source_url}")
        except Exception as e:
            print(f"❌ Error: {e}")
            sys.exit(1)
    else:
        source_url = args.source_url

    # Use consistent S3 key based on source filename (not today's date)
    # This ensures resume works across runs
    filename = source_url.split("/")[-1]
    if args.s3_key:
        s3_key = args.s3_key
    else:
        # Extract date from filename (usaspending-db_20251106.zip -> 2025-11-06)
        import re

        match = re.search(r"(\d{4})(\d{2})(\d{2})", filename)
        if match:
            file_date = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
        else:
            file_date = datetime.now(UTC).strftime("%Y-%m-%d")
        s3_key = f"raw/usaspending/database/{file_date}/{filename}"

    print(f"📦 S3 key: {s3_key}")

    try:
        asyncio.run(
            parallel_download_to_s3(
                source_url=source_url,
                s3_bucket=args.s3_bucket,
                s3_key=s3_key,
                max_concurrent=args.max_concurrent,
            )
        )
        sys.exit(0)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
