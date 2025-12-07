#!/usr/bin/env python3
"""Standalone script to download USAspending database and upload to S3.

This script can run on EC2 or any machine with AWS credentials configured.
It downloads the database dump and streams it directly to S3 using multipart upload.

Features:
- Resume capability: Automatically resumes from last checkpoint if download fails
- HTTP Range requests: Uses Range headers to download only missing bytes
- Checkpoint tracking: Saves progress after each chunk for reliable recovery (stored in S3)
- Multipart upload: Streams directly to S3 in chunks without local storage

Usage:
    python download_database.py --database-type full --date 20251106
    python download_database.py --source-url https://files.usaspending.gov/...

On failure, simply re-run the script to resume from the checkpoint.
Checkpoints are stored in S3 under .checkpoints/ prefix for persistence across container restarts.
"""

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import boto3
import requests
from requests.adapters import HTTPAdapter
from urllib3.exceptions import IncompleteRead, ProtocolError, ReadTimeoutError
from urllib3.util.retry import Retry

# Import file checking and discovery logic from check_new_file.py
from scripts.usaspending.check_new_file import check_file_availability, find_latest_available_file


s3_client = boto3.client("s3")

# USAspending database download base URL
USASPENDING_DB_BASE_URL = "https://files.usaspending.gov/database_download"

USASPENDING_DOWNLOADS = {
    "full": "{base}/usaspending-db_{date}.zip",
    "test": "{base}/usaspending-db-subset_{date}.zip",
}


def get_checkpoint_s3_key(s3_key: str) -> str:
    """Get S3 key for checkpoint file."""
    # Store checkpoints in S3 under .checkpoints/ prefix
    return f".checkpoints/{s3_key}.checkpoint"


def load_checkpoint(s3_bucket: str, checkpoint_s3_key: str) -> dict | None:
    """Load download checkpoint from S3 if it exists."""
    try:
        response = s3_client.get_object(Bucket=s3_bucket, Key=checkpoint_s3_key)
        checkpoint_data = json.loads(response["Body"].read().decode("utf-8"))
        print(f"Loaded checkpoint from s3://{s3_bucket}/{checkpoint_s3_key}")
        return checkpoint_data
    except s3_client.exceptions.NoSuchKey:
        return None
    except Exception as e:
        print(f"Warning: Failed to load checkpoint from S3: {e}")
        return None


def save_checkpoint(
    s3_bucket: str,
    checkpoint_s3_key: str,
    bytes_downloaded: int,
    parts: list[dict],
    upload_id: str,
    s3_key: str,
    source_url: str,
) -> None:
    """Save download checkpoint to S3."""
    try:
        checkpoint_data = {
            "bytes_downloaded": bytes_downloaded,
            "parts": parts,
            "upload_id": upload_id,
            "s3_bucket": s3_bucket,
            "s3_key": s3_key,
            "source_url": source_url,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        s3_client.put_object(
            Bucket=s3_bucket,
            Key=checkpoint_s3_key,
            Body=json.dumps(checkpoint_data, indent=2).encode("utf-8"),
            ContentType="application/json",
        )
    except Exception as e:
        print(f"Warning: Failed to save checkpoint to S3: {e}")


def clear_checkpoint(s3_bucket: str, checkpoint_s3_key: str) -> None:
    """Clear checkpoint file from S3 after successful completion."""
    try:
        s3_client.delete_object(Bucket=s3_bucket, Key=checkpoint_s3_key)
        print(f"Cleared checkpoint: s3://{s3_bucket}/{checkpoint_s3_key}")
    except Exception as e:
        print(f"Warning: Failed to clear checkpoint from S3: {e}")


def download_and_upload(
    s3_bucket: str,
    database_type: str = "full",
    date_str: str = None,
    source_url: str = None,
    force_refresh: bool = False,
) -> dict:
    """Download USAspending database and upload to S3."""
    # Construct URL if not provided
    if not source_url:
        if database_type not in USASPENDING_DOWNLOADS:
            raise ValueError(
                f"Unknown database_type '{database_type}'. "
                f"Known types: {', '.join(USASPENDING_DOWNLOADS.keys())}"
            )

        if not date_str:
            # Auto-discover latest available file instead of using today's date
            print("No date specified - searching for latest available file...")
            latest_file = find_latest_available_file(
                database_type=database_type,
                s3_bucket=None,  # Don't need S3 for discovery, just finding source URL
            )

            if not latest_file:
                raise FileNotFoundError(
                    f"No available {database_type} database file found in recent months.\n"
                    f"Please specify a date with --date YYYYMMDD or check available files manually."
                )

            source_url = latest_file["source_url"]
            date_str = latest_file["date_str"]
            print(f"Found latest available file: {date_str}")
        else:
            url_template = USASPENDING_DOWNLOADS[database_type]
            source_url = url_template.format(base=USASPENDING_DB_BASE_URL, date=date_str)

    print(f"Checking if file exists: {source_url}")

    # Check if file exists before starting download (reuse check_new_file logic)
    file_check = check_file_availability(
        source_url=source_url,
        s3_bucket=None,  # Don't compare with S3 here, just check availability
        s3_key=None,
    )

    if not file_check.get("available"):
        error_msg = file_check.get("error", "File not found")
        raise FileNotFoundError(
            f"File not available at {source_url}: {error_msg}\n"
            f"Please check:\n"
            f"  1. The date is correct (files are typically released monthly)\n"
            f"  2. The database type is correct (test vs full)\n"
            f"  3. Try running without --date to auto-discover latest file\n"
            f"  4. Or use: python scripts/usaspending/check_new_file.py --database-type {database_type}"
        )

    # Display file info
    if file_check.get("content_length"):
        size_gb = file_check["content_length"] / 1024 / 1024 / 1024
        print(f"✅ File found: {file_check['content_length']:,} bytes ({size_gb:.2f} GB)")
    if file_check.get("last_modified"):
        print(f"   Last modified: {file_check['last_modified']}")

    print(f"Downloading USAspending database ({database_type}) from {source_url}")

    # Generate S3 key
    # Format: raw/usaspending/database/YYYY-MM-DD/usaspending-db_YYYYMMDD.zip
    # This matches the pattern expected by find_latest_usaspending_dump()
    timestamp = datetime.now(UTC)
    s3_date_str = timestamp.strftime("%Y-%m-%d")
    filename = source_url.split("/")[-1]
    s3_key = f"raw/usaspending/database/{s3_date_str}/{filename}"

    # Check if file already exists
    if not force_refresh:
        try:
            s3_client.head_object(Bucket=s3_bucket, Key=s3_key)
            print(f"File already exists in S3: s3://{s3_bucket}/{s3_key}")
            print("Skipping download. Use --force-refresh to override.")
            return {"status": "skipped", "s3_key": s3_key}
        except s3_client.exceptions.ClientError:
            pass  # File doesn't exist, continue

    # Check for existing checkpoint to resume download
    checkpoint_s3_key = get_checkpoint_s3_key(s3_key)
    checkpoint = load_checkpoint(s3_bucket, checkpoint_s3_key)

    bytes_resume_from = 0
    existing_parts = []
    existing_upload_id = None
    resume_mode = False

    if checkpoint and not force_refresh:
        checkpoint_url = checkpoint.get("source_url")
        if checkpoint_url == source_url:
            bytes_resume_from = checkpoint.get("bytes_downloaded", 0)
            existing_parts = checkpoint.get("parts", [])
            existing_upload_id = checkpoint.get("upload_id")
            resume_mode = bytes_resume_from > 0

            if resume_mode:
                print("Resuming download from checkpoint:")
                print(
                    f"  Bytes already downloaded: {bytes_resume_from:,} ({bytes_resume_from / 1024 / 1024 / 1024:.2f} GB)"
                )
                print(f"  Parts already uploaded: {len(existing_parts)}")
                print(f"  Upload ID: {existing_upload_id}")

                # Verify multipart upload still exists
                if existing_upload_id:
                    try:
                        s3_client.list_parts(
                            Bucket=s3_bucket,
                            Key=s3_key,
                            UploadId=existing_upload_id,
                        )
                        upload_id = existing_upload_id
                        parts = existing_parts.copy()
                        part_number = len(existing_parts) + 1
                        print(f"Reusing existing multipart upload: {upload_id}")
                    except s3_client.exceptions.ClientError:
                        print(
                            f"Warning: Existing multipart upload {existing_upload_id} not found. Starting fresh."
                        )
                        existing_upload_id = None
                        parts = []
                        part_number = 1
                else:
                    parts = []
                    part_number = 1
            else:
                # Checkpoint exists but no progress, start fresh
                parts = []
                part_number = 1
        else:
            print("Warning: Checkpoint exists for different URL. Starting fresh download.")
            print(f"  Checkpoint URL: {checkpoint_url}")
            print(f"  Current URL: {source_url}")
            parts = []
            part_number = 1
    else:
        parts = []
        part_number = 1

    # Download and upload using multipart
    # Small chunk size for unstable connections (GitHub Actions runners)
    CHUNK_SIZE = 5 * 1024 * 1024  # 5 MB (reduced for GitHub Actions network stability)

    # Configure retry strategy for urllib3
    # Retry on connection errors, timeouts, and 5xx errors
    retry_strategy = Retry(
        total=5,  # Total number of retries
        backoff_factor=2,  # Exponential backoff: 0s, 2s, 4s, 8s, 16s
        status_forcelist=[500, 502, 503, 504],  # Retry on these HTTP status codes
        allowed_methods=["GET", "HEAD"],
        raise_on_status=False,  # Let requests handle status code errors
    )

    # Create session with retry adapter
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    # Use requests for better streaming and error handling
    # Disable automatic decompression to avoid IncompleteRead issues with compressed streams
    headers = {
        "User-Agent": "SBIR-Analytics-EC2/1.0",
        "Accept": "*/*",
        "Accept-Encoding": "identity",  # Disable compression to avoid stream issues
    }

    # Add Range header if resuming
    if resume_mode:
        # HTTP Range: bytes=START-END (END can be omitted to get rest of file)
        headers["Range"] = f"bytes={bytes_resume_from}-"
        print(f"Using Range request to resume from byte {bytes_resume_from:,}")

    # Create new multipart upload if not resuming with existing one
    if not resume_mode or not existing_upload_id:
        multipart_upload = s3_client.create_multipart_upload(
            Bucket=s3_bucket,
            Key=s3_key,
            ContentType="application/zip",
            Metadata={
                "source_url": source_url,
                "downloaded_at": timestamp.isoformat(),
                "database_type": database_type,
            },
        )
        upload_id = multipart_upload["UploadId"]
        print(f"Initiated multipart upload: {upload_id}")
    else:
        # Already set above when verifying existing upload
        pass

    try:
        # Initialize counters
        # Note: total_size tracks total bytes downloaded (including resume point)
        # total_bytes_new tracks new bytes downloaded in this session only
        # bytes_resume_from is the offset we're resuming from
        total_size = bytes_resume_from  # Start from resume point
        total_bytes_new = 0  # Track new bytes downloaded in this session (starts at 0)

        # Hash computation: Only hash if not resuming, or hash will be incomplete
        # On resume, we'll skip hash computation since we don't have the beginning bytes
        hasher = None if resume_mode else hashlib.sha256()
        if resume_mode:
            print("Note: Hash computation skipped on resume (would require full file)")

        # Top-level retry for streaming download errors
        # urllib3 Retry handles HTTP connection errors, but streaming errors
        # (like broken pipes during iter_content) need explicit retry
        # Increased retries for large file downloads with unstable connections
        max_download_retries = 20  # Increased for GitHub Actions
        download_retry_delay = 10  # Initial delay in seconds

        for download_attempt in range(max_download_retries):
            try:
                # Use session with retry adapter for streaming download
                # The urllib3 Retry adapter will handle connection errors automatically
                # Timeout: (connect timeout, read timeout)
                # Reduced read timeout to fail fast on stalls and retry sooner
                with session.get(
                    source_url,
                    stream=True,
                    headers=headers,
                    timeout=(30, 300),  # (connect 30s, read 5min) - fail fast on stalls
                ) as response:
                    # Handle partial content response (206) when resuming
                    if response.status_code == 206:
                        print("Received 206 Partial Content - resuming download")
                    elif response.status_code == 200:
                        if resume_mode:
                            print(
                                "Warning: Server returned 200 instead of 206. Starting from beginning."
                            )
                            # Reset resume mode since server doesn't support Range
                            resume_mode = False
                            bytes_resume_from = 0
                            total_size = 0
                            headers.pop("Range", None)  # Remove Range header
                    else:
                        response.raise_for_status()  # Raise HTTPError for bad responses

                    # Stream download in chunks with chunk-level retry for S3 uploads
                    # decode_unicode=False ensures we handle binary data correctly
                    for chunk in response.iter_content(chunk_size=CHUNK_SIZE, decode_unicode=False):
                        if not chunk:
                            continue  # Skip empty chunks but continue

                        # Hash chunk only if not resuming (we don't have beginning bytes for hash)
                        if hasher is not None:
                            hasher.update(chunk)

                        chunk_size_bytes = len(chunk)
                        total_size += chunk_size_bytes
                        total_bytes_new += chunk_size_bytes

                        # Retry chunk upload to S3 if it fails (with exponential backoff)
                        chunk_uploaded = False
                        max_chunk_retries = 5
                        for chunk_attempt in range(max_chunk_retries):
                            try:
                                print(f"Uploading part {part_number} ({chunk_size_bytes:,} bytes)")
                                part_response = s3_client.upload_part(
                                    Bucket=s3_bucket,
                                    Key=s3_key,
                                    PartNumber=part_number,
                                    UploadId=upload_id,
                                    Body=chunk,
                                )

                                parts.append(
                                    {
                                        "ETag": part_response["ETag"],
                                        "PartNumber": part_number,
                                    }
                                )

                                part_number += 1
                                chunk_uploaded = True

                                # Save checkpoint after successful chunk upload
                                save_checkpoint(
                                    s3_bucket,
                                    checkpoint_s3_key,
                                    total_size,
                                    parts,
                                    upload_id,
                                    s3_key,
                                    source_url,
                                )

                                break  # Success, move to next chunk

                            except Exception as chunk_error:
                                if chunk_attempt < max_chunk_retries - 1:
                                    wait_time = (
                                        2**chunk_attempt
                                    )  # Exponential backoff: 1s, 2s, 4s, 8s
                                    print(
                                        f"Warning: Failed to upload part {part_number} "
                                        f"(attempt {chunk_attempt + 1}/{max_chunk_retries}): {chunk_error}"
                                    )
                                    print(f"Retrying upload in {wait_time}s...")
                                    time.sleep(wait_time)
                                    # Retry the upload with the same chunk data
                                else:
                                    print(
                                        f"Error: Failed to upload part {part_number} after {max_chunk_retries} attempts"
                                    )
                                    raise  # Re-raise if all chunk retries exhausted

                        if not chunk_uploaded:
                            raise Exception(
                                f"Failed to upload part {part_number} after all retries"
                            )

                        # Progress indicator for large files
                        if total_size % (1024 * 1024 * 1024) < CHUNK_SIZE:  # Every ~1GB
                            print(
                                f"Progress: {total_size / 1024 / 1024 / 1024:.2f} GB total ({total_bytes_new / 1024 / 1024 / 1024:.2f} GB new)"
                            )

                # Download completed successfully - break out of retry loop
                break

            except (
                requests.exceptions.ChunkedEncodingError,
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
                requests.exceptions.RequestException,
                ProtocolError,
                ReadTimeoutError,
                IncompleteRead,
                ConnectionResetError,
                BrokenPipeError,
                TimeoutError,
            ) as e:
                # Save checkpoint before retrying so we can resume later
                if len(parts) > 0 and total_size > 0:
                    try:
                        save_checkpoint(
                            s3_bucket,
                            checkpoint_s3_key,
                            total_size,
                            parts,
                            upload_id,
                            s3_key,
                            source_url,
                        )
                        print(f"Saved checkpoint: {total_size:,} bytes, {len(parts)} parts")
                    except Exception as checkpoint_error:
                        print(f"Warning: Failed to save checkpoint: {checkpoint_error}")

                # These errors can occur during streaming, especially for large files
                if download_attempt < max_download_retries - 1:
                    wait_time = download_retry_delay * (
                        2**download_attempt
                    )  # Exponential backoff: 15s, 30s, 60s, ...
                    print(
                        f"Warning: Download streaming error (attempt {download_attempt + 1}/{max_download_retries}): {e}"
                    )
                    print(
                        f"Checkpoint saved. Will resume from byte {total_size:,} on next attempt."
                    )
                    print(f"Retrying download in {wait_time}s...")
                    time.sleep(wait_time)

                    # Reload checkpoint to get latest state before retry
                    updated_checkpoint = load_checkpoint(s3_bucket, checkpoint_s3_key)
                    if updated_checkpoint:
                        bytes_resume_from = updated_checkpoint.get("bytes_downloaded", total_size)
                        existing_parts = updated_checkpoint.get("parts", parts)
                        existing_upload_id = updated_checkpoint.get("upload_id", upload_id)

                        # Update state from checkpoint
                        parts = existing_parts.copy()
                        upload_id = existing_upload_id
                        part_number = len(parts) + 1
                        total_size = bytes_resume_from
                        total_bytes_new = 0  # Reset for new session from this point
                        resume_mode = bytes_resume_from > 0

                        # Update headers for resume
                        if bytes_resume_from > 0:
                            headers["Range"] = f"bytes={bytes_resume_from}-"
                            print(
                                f"Reloaded checkpoint: resuming from byte {bytes_resume_from:,} with {len(parts)} parts"
                            )
                        else:
                            headers.pop("Range", None)

                        # Reset hasher if resuming (can't hash partial file)
                        hasher = None if resume_mode else hashlib.sha256()

                    # Continue with existing parts and upload_id (don't abort/reset)
                    # The next iteration will use the saved checkpoint state
                else:
                    print(f"Error: Download failed after {max_download_retries} attempts")
                    print(
                        f"Progress saved in checkpoint: {total_size:,} bytes ({total_size / 1024 / 1024 / 1024:.2f} GB)"
                    )
                    print("Run the script again to resume from checkpoint.")
                    raise  # Re-raise if all download retries exhausted

        # Download completed successfully
        # Compute hash if available (only if we downloaded from beginning)
        file_hash = None
        if hasher is not None:
            file_hash = hasher.hexdigest()
            print(
                f"Completing multipart upload. Total size: {total_size} bytes ({total_size / 1024 / 1024 / 1024:.2f} GB), SHA256: {file_hash}"
            )
        else:
            print(
                f"Completing multipart upload. Total size: {total_size} bytes ({total_size / 1024 / 1024 / 1024:.2f} GB)"
            )
            print("Note: Hash not computed (download was resumed from checkpoint)")

        s3_client.complete_multipart_upload(
            Bucket=s3_bucket,
            Key=s3_key,
            UploadId=upload_id,
            MultipartUpload={"Parts": parts},
        )

        print(f"Successfully uploaded to s3://{s3_bucket}/{s3_key}")
        print(f"File size: {total_size} bytes ({total_size / 1024 / 1024 / 1024:.2f} GB)")
        if file_hash:
            print(f"SHA256: {file_hash}")

        # Clear checkpoint on successful completion
        clear_checkpoint(s3_bucket, checkpoint_s3_key)

        return {
            "status": "success",
            "s3_bucket": s3_bucket,
            "s3_key": s3_key,
            "sha256": file_hash,  # May be None if resumed
            "file_size": total_size,
            "source_url": source_url,
            "downloaded_at": timestamp.isoformat(),
            "database_type": database_type,
            "parts_count": len(parts),
            "resumed": resume_mode,
        }

    except Exception as e:
        print(f"Error during multipart upload, aborting: {e}")
        try:
            s3_client.abort_multipart_upload(
                Bucket=s3_bucket,
                Key=s3_key,
                UploadId=upload_id,
            )
        except Exception as abort_error:
            print(f"Error aborting multipart upload: {abort_error}")
        raise


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Download USAspending database and upload to S3")
    # Get default from environment or use default
    default_bucket = (
        os.environ.get("S3_BUCKET")
        or os.environ.get("SBIR_ANALYTICS_S3_BUCKET")
        or "sbir-etl-production-data"
    )

    parser.add_argument(
        "--s3-bucket",
        default=default_bucket,
        help=f"S3 bucket name (default: {default_bucket} from env or hardcoded)",
    )
    parser.add_argument(
        "--database-type",
        choices=["full", "test"],
        default=os.environ.get("DATABASE_TYPE", "full"),
        help="Database type to download (default: full)",
    )
    parser.add_argument(
        "--date",
        default=os.environ.get("DATE"),
        help="Date in YYYYMMDD format (default: current date)",
    )
    parser.add_argument(
        "--source-url",
        default=os.environ.get("SOURCE_URL"),
        help="Override source URL (optional)",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        default=os.environ.get("FORCE_REFRESH", "false").lower() == "true",
        help="Force refresh even if file already exists",
    )

    args = parser.parse_args()

    try:
        result = download_and_upload(
            s3_bucket=args.s3_bucket,
            database_type=args.database_type,
            date_str=args.date,
            source_url=args.source_url,
            force_refresh=args.force_refresh,
        )
        sys.exit(0 if result.get("status") in ["success", "skipped"] else 1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
