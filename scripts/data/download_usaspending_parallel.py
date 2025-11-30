#!/usr/bin/env python3
"""Parallel USAspending database download with S3 multipart upload.

Optimizations:
- Parallel chunk downloads (10 concurrent)
- Direct streaming to S3 multipart upload
- Automatic retry and resume capability
- 2-3x faster than sequential download
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


async def parallel_download_to_s3(
    source_url: str,
    s3_bucket: str,
    s3_key: str,
    chunk_size: int = 50 * 1024 * 1024,  # 50 MB
    max_concurrent: int = 10,
) -> dict:
    """Download file in parallel and upload to S3."""
    overall_start = time.time()
    s3_client = boto3.client("s3")

    # Get file size
    print("=" * 80)
    print("📥 USAspending Database Download")
    print("=" * 80)

    async with aiohttp.ClientSession() as session:
        async with session.head(source_url) as response:
            file_size = int(response.headers.get("Content-Length", 0))
            if file_size == 0:
                raise ValueError("Cannot determine file size")

    file_size_gb = file_size / 1024 / 1024 / 1024
    print(f"📊 File size: {file_size_gb:.2f} GB ({file_size:,} bytes)")
    print(f"🔗 Source: {source_url}")

    # Check for existing multipart upload
    existing_uploads = s3_client.list_multipart_uploads(Bucket=s3_bucket, Prefix=s3_key)
    upload_id = None
    existing_parts = {}

    for upload in existing_uploads.get("Uploads", []):
        if upload["Key"] == s3_key:
            upload_id = upload["UploadId"]
            print(f"🔄 Found existing upload: {upload_id}")

            # List already uploaded parts
            parts_response = s3_client.list_parts(Bucket=s3_bucket, Key=s3_key, UploadId=upload_id)
            for part in parts_response.get("Parts", []):
                existing_parts[part["PartNumber"]] = {
                    "ETag": part["ETag"],
                    "PartNumber": part["PartNumber"],
                }
            print(f"✅ Found {len(existing_parts)} already uploaded parts")
            break

    # Create new multipart upload if none exists
    if not upload_id:
        multipart = s3_client.create_multipart_upload(
            Bucket=s3_bucket,
            Key=s3_key,
            ContentType="application/zip",
        )
        upload_id = multipart["UploadId"]
        print(f"🆕 Created new upload: {upload_id}")

    print(f"📦 S3 destination: s3://{s3_bucket}/{s3_key}")
    print(f"🆔 Upload ID: {upload_id}")

    try:
        # Create chunks
        chunks = []
        for i in range(0, file_size, chunk_size):
            end = min(i + chunk_size - 1, file_size - 1)
            chunks.append(DownloadChunk(chunk_id=len(chunks), start_byte=i, end_byte=end))

        chunk_size_mb = chunk_size / 1024 / 1024
        print(f"📦 Split into {len(chunks)} chunks of ~{chunk_size_mb:.0f} MB each")
        print(f"⚡ Max concurrent downloads: {max_concurrent}")

        if existing_parts:
            print(f"⏭️  Skipping {len(existing_parts)} already uploaded parts")
        print()

        # Download and upload chunks concurrently
        semaphore = asyncio.Semaphore(max_concurrent)
        parts = list(existing_parts.values())  # Start with existing parts
        completed_parts = len(existing_parts)
        bytes_transferred = sum(chunk_size for _ in existing_parts)
        download_start = time.time()

        async def download_and_upload(chunk: DownloadChunk) -> dict:
            nonlocal completed_parts, bytes_transferred

            # Skip if already uploaded
            part_number = chunk.chunk_id + 1
            if part_number in existing_parts:
                return existing_parts[part_number]

            async with semaphore:
                chunk_start = time.time()
                async with aiohttp.ClientSession() as session:
                    downloaded = await download_chunk(session, source_url, chunk)

                    # Upload to S3
                    part_response = s3_client.upload_part(
                        Bucket=s3_bucket,
                        Key=s3_key,
                        PartNumber=chunk.chunk_id + 1,
                        UploadId=upload_id,
                        Body=downloaded.data,
                    )

                    completed_parts += 1
                    chunk_bytes = len(downloaded.data)
                    bytes_transferred += chunk_bytes

                    # Calculate progress and speed
                    progress_pct = (completed_parts / len(chunks)) * 100
                    elapsed = time.time() - download_start
                    speed_mbps = (bytes_transferred / elapsed / 1024 / 1024) if elapsed > 0 else 0
                    eta_seconds = (
                        ((file_size - bytes_transferred) / (bytes_transferred / elapsed))
                        if elapsed > 0 and bytes_transferred > 0
                        else 0
                    )

                    chunk_time = time.time() - chunk_start
                    chunk_mb = chunk_bytes / 1024 / 1024

                    print(
                        f"✅ Part {completed_parts:3d}/{len(chunks)} ({progress_pct:5.1f}%) | "
                        f"{chunk_mb:6.1f} MB in {chunk_time:5.1f}s | "
                        f"Speed: {speed_mbps:6.1f} MB/s | "
                        f"ETA: {eta_seconds / 60:5.1f}m"
                    )

                    return {
                        "ETag": part_response["ETag"],
                        "PartNumber": chunk.chunk_id + 1,
                    }

        print("🚀 Starting parallel download and upload...")
        parts = await asyncio.gather(*[download_and_upload(chunk) for chunk in chunks])
        download_time = time.time() - download_start

        print()
        print("🔄 Completing multipart upload...")

        # Complete multipart upload
        complete_start = time.time()
        s3_client.complete_multipart_upload(
            Bucket=s3_bucket,
            Key=s3_key,
            UploadId=upload_id,
            MultipartUpload={"Parts": sorted(parts, key=lambda p: p["PartNumber"])},
        )
        complete_time = time.time() - complete_start
        total_time = time.time() - overall_start

        # Print summary
        print()
        print("=" * 80)
        print("✨ DOWNLOAD COMPLETE")
        print("=" * 80)
        print(f"📊 Total size: {file_size_gb:.2f} GB ({file_size:,} bytes)")
        print(f"📦 Total parts: {len(chunks)}")
        print(f"⏱️  Download time: {download_time:.1f}s ({download_time / 60:.1f}m)")
        print(f"⏱️  Completion time: {complete_time:.1f}s")
        print(f"⏱️  Total time: {total_time:.1f}s ({total_time / 60:.1f}m)")
        print(f"⚡ Average speed: {file_size / download_time / 1024 / 1024:.1f} MB/s")
        print(f"📍 S3 location: s3://{s3_bucket}/{s3_key}")
        print("=" * 80)

        return {
            "status": "success",
            "s3_bucket": s3_bucket,
            "s3_key": s3_key,
            "file_size": file_size,
            "file_size_gb": round(file_size_gb, 2),
            "chunks": len(chunks),
            "download_time_seconds": round(download_time, 1),
            "total_time_seconds": round(total_time, 1),
            "average_speed_mbps": round(file_size / download_time / 1024 / 1024, 1),
        }

    except Exception as e:
        print()
        print("=" * 80)
        print("❌ ERROR DURING DOWNLOAD")
        print("=" * 80)
        print(f"Error: {e}")
        print(f"Upload ID: {upload_id}")
        print(f"Completed parts: {completed_parts}/{len(chunks)}")
        print(f"Bytes transferred: {bytes_transferred / 1024 / 1024 / 1024:.2f} GB")
        print("Aborting multipart upload...")
        print("=" * 80)
        s3_client.abort_multipart_upload(Bucket=s3_bucket, Key=s3_key, UploadId=upload_id)
        raise


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Parallel USAspending database download")
    parser.add_argument("--s3-bucket", required=True, help="S3 bucket name")
    parser.add_argument("--database-type", choices=["full", "test"], default="full")
    parser.add_argument("--date", help="Date in YYYYMMDD format (auto-detect if not provided)")
    parser.add_argument("--source-url", help="Override source URL")
    parser.add_argument("--max-concurrent", type=int, default=10, help="Max concurrent downloads")

    args = parser.parse_args()

    # Find latest file if not specified
    if not args.source_url:
        print("🔍 Finding latest available file...")
        print(f"   Database type: {args.database_type}")
        print("   Checking last 3 months of releases...")

        try:
            latest = find_latest_available_file(database_type=args.database_type, s3_bucket=None)
            if not latest:
                print("❌ No available file found")
                print("   Checked dates: 1st, 6th, and 15th of each month")
                print("   Base URL: https://files.usaspending.gov/database_download/")
                print("   Pattern: usaspending-db_YYYYMMDD.zip")
                sys.exit(1)
            source_url = latest["source_url"]
            date_str = latest["date_str"]
            print(f"✅ Found file dated {date_str}")
            print(f"   URL: {source_url}")
        except Exception as e:
            print(f"❌ Error finding file: {e}")
            import traceback

            traceback.print_exc()
            sys.exit(1)
    else:
        source_url = args.source_url
        date_str = args.date or "unknown"

    # Generate S3 key
    s3_date = datetime.now(UTC).strftime("%Y-%m-%d")
    filename = source_url.split("/")[-1]
    s3_key = f"raw/usaspending/database/{s3_date}/{filename}"

    # Run parallel download
    try:
        asyncio.run(
            parallel_download_to_s3(
                source_url=source_url,
                s3_bucket=args.s3_bucket,
                s3_key=s3_key,
                max_concurrent=args.max_concurrent,
            )
        )
        print()
        print("✅ All operations completed successfully!")
        sys.exit(0)
    except Exception as e:
        print()
        print(f"❌ Fatal error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
