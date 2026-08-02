#!/usr/bin/env python3
"""Download the USAspending database dump to a local directory.

Writes locally by default. Passing --s3-bucket selects the legacy path that
streams to S3 via multipart upload; that path is retired once the AWS data
plane is gone.

Features (local path):
- Resume capability: HTTP Range requests continue a partial file
- Checkpoint tracking: progress saved to a sidecar next to the partial file
- Disk guard: fails fast when the volume cannot hold the dump

Usage:
    python download_database.py --database-type full --date 20251106
    python download_database.py --dest /Volumes/SSDmini/sbir-analytics/data/usaspending
    python download_database.py --source-url https://files.usaspending.gov/...

On failure, simply re-run the script to resume from the checkpoint.
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.exceptions import IncompleteRead, ProtocolError, ReadTimeoutError
from urllib3.util.retry import Retry

# Import file checking and discovery logic from check_new_file.py
from scripts.usaspending.check_new_file import check_file_availability, find_latest_available_file


# USAspending database download base URL
USASPENDING_DB_BASE_URL = "https://files.usaspending.gov/database_download"

USASPENDING_DOWNLOADS = {
    "full": "{base}/usaspending-db_{date}.zip",
    "test": "{base}/usaspending-db-subset_{date}.zip",
}

DEFAULT_DEST = "data/usaspending"


_S3_CLIENT = None


def _s3():
    """Cached S3 client. boto3 is only imported on the S3 mirror path."""
    global _S3_CLIENT
    if _S3_CLIENT is None:
        import boto3

        _S3_CLIENT = boto3.client("s3")
    return _S3_CLIENT


def get_checkpoint_s3_key(s3_key: str) -> str:
    """Get S3 key for checkpoint file."""
    # Store checkpoints in S3 under .checkpoints/ prefix
    return f".checkpoints/{s3_key}.checkpoint"


def load_checkpoint(s3_bucket: str, checkpoint_s3_key: str) -> dict | None:
    """Load download checkpoint from S3 if it exists."""
    try:
        response = _s3().get_object(Bucket=s3_bucket, Key=checkpoint_s3_key)
        checkpoint_data = json.loads(response["Body"].read().decode("utf-8"))
        print(f"Loaded checkpoint from s3://{s3_bucket}/{checkpoint_s3_key}")
        return checkpoint_data
    except _s3().exceptions.NoSuchKey:
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
        _s3().put_object(
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
        _s3().delete_object(Bucket=s3_bucket, Key=checkpoint_s3_key)
        print(f"Cleared checkpoint: s3://{s3_bucket}/{checkpoint_s3_key}")
    except Exception as e:
        print(f"Warning: Failed to clear checkpoint from S3: {e}")


def resolve_source_url(
    database_type: str = "full",
    date_str: str = None,
    source_url: str = None,
) -> str:
    """Resolve the dump URL, auto-discovering the latest file when no date is given."""
    if source_url:
        return source_url

    if database_type not in USASPENDING_DOWNLOADS:
        raise ValueError(
            f"Unknown database_type '{database_type}'. "
            f"Known types: {', '.join(USASPENDING_DOWNLOADS.keys())}"
        )

    if date_str:
        return USASPENDING_DOWNLOADS[database_type].format(
            base=USASPENDING_DB_BASE_URL, date=date_str
        )

    print("No date specified - searching for latest available file...")
    latest_file = find_latest_available_file(database_type=database_type, s3_bucket=None)
    if not latest_file:
        raise FileNotFoundError(
            f"No available {database_type} database file found in recent months.\n"
            f"Please specify a date with --date YYYYMMDD or check available files manually."
        )
    return latest_file["source_url"]


def get_checkpoint_path(dest_path: Path) -> Path:
    """Checkpoint sidecar for a local download, alongside the partial file."""
    return dest_path.with_suffix(dest_path.suffix + ".checkpoint")


def load_local_checkpoint(checkpoint_path: Path) -> dict | None:
    """Load a local download checkpoint, or None when absent or unreadable."""
    if not checkpoint_path.is_file():
        return None
    try:
        data = json.loads(checkpoint_path.read_text())
        print(f"Loaded checkpoint from {checkpoint_path}")
        return data
    except (OSError, json.JSONDecodeError) as e:
        print(f"Warning: Failed to load checkpoint {checkpoint_path}: {e}")
        return None


def save_local_checkpoint(
    checkpoint_path: Path, bytes_downloaded: int, source_url: str, total_bytes: int | None
) -> None:
    """Persist download progress next to the partial file."""
    try:
        checkpoint_path.write_text(
            json.dumps(
                {
                    "bytes_downloaded": bytes_downloaded,
                    "source_url": source_url,
                    "total_bytes": total_bytes,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
                indent=2,
            )
        )
    except OSError as e:
        print(f"Warning: Failed to save checkpoint {checkpoint_path}: {e}")


def clear_local_checkpoint(checkpoint_path: Path) -> None:
    """Remove the checkpoint after a verified complete download."""
    try:
        checkpoint_path.unlink(missing_ok=True)
    except OSError as e:
        print(f"Warning: Failed to clear checkpoint {checkpoint_path}: {e}")


def check_free_space(dest_dir: Path, required_bytes: int, multiplier: float = 1.5) -> None:
    """Raise before downloading if the volume cannot hold the dump.

    The dump is large and downloading onto a full SSD fails late and leaves a
    useless partial file, so this fails fast instead.
    """
    if not required_bytes:
        return
    usage = shutil.disk_usage(dest_dir)
    needed = int(required_bytes * multiplier)
    if usage.free < needed:
        raise OSError(
            f"Insufficient disk space at {dest_dir}: "
            f"{usage.free / 1024**3:.1f} GB free, need ~{needed / 1024**3:.1f} GB "
            f"({required_bytes / 1024**3:.1f} GB dump x {multiplier})"
        )
    print(
        f"Disk space OK: {usage.free / 1024**3:.1f} GB free, "
        f"need ~{needed / 1024**3:.1f} GB"
    )


def download_local(
    dest_dir: Path,
    database_type: str = "full",
    date_str: str = None,
    source_url: str = None,
    force_refresh: bool = False,
    chunk_size: int = 8 * 1024 * 1024,
) -> dict:
    """Download the USAspending dump to a local directory, resuming if interrupted.

    Uses HTTP Range requests to continue a partial file rather than restarting,
    with progress checkpointed to a sidecar so a killed run resumes cheaply.
    """
    source_url = resolve_source_url(database_type, date_str, source_url)
    filename = source_url.rsplit("/", 1)[-1]

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / filename
    checkpoint_path = get_checkpoint_path(dest_path)

    availability = check_file_availability(source_url)
    if not availability["available"]:
        raise FileNotFoundError(f"Source file not available: {source_url}")
    total_bytes = availability.get("content_length") or 0

    if dest_path.is_file() and not force_refresh:
        if total_bytes and dest_path.stat().st_size == total_bytes:
            print(f"Already downloaded: {dest_path} ({total_bytes / 1024**3:.1f} GB)")
            clear_local_checkpoint(checkpoint_path)
            return {
                "status": "skipped",
                "path": str(dest_path),
                "size": total_bytes,
                "source_url": source_url,
            }

    if force_refresh:
        dest_path.unlink(missing_ok=True)
        clear_local_checkpoint(checkpoint_path)

    resume_from = dest_path.stat().st_size if dest_path.is_file() else 0
    checkpoint = load_local_checkpoint(checkpoint_path)
    if checkpoint and checkpoint.get("source_url") != source_url:
        # Checkpoint belongs to a different dump; start over rather than splice.
        print("Checkpoint is for a different source URL - restarting download")
        dest_path.unlink(missing_ok=True)
        resume_from = 0

    check_free_space(dest_dir, max(total_bytes - resume_from, 0))

    headers = {}
    if resume_from:
        headers["Range"] = f"bytes={resume_from}-"
        print(f"Resuming from byte {resume_from:,} ({resume_from / 1024**3:.1f} GB)")

    session = requests.Session()
    session.mount(
        "https://",
        HTTPAdapter(
            max_retries=Retry(
                total=5, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504]
            )
        ),
    )

    print(f"Downloading {source_url}")
    print(f"   -> {dest_path}")
    start = time.time()
    downloaded = resume_from

    with session.get(source_url, headers=headers, stream=True, timeout=300) as response:
        response.raise_for_status()
        # A server ignoring Range returns 200 with the whole body; restart cleanly.
        if resume_from and response.status_code == 200:
            print("Server ignored Range request - restarting from byte 0")
            dest_path.unlink(missing_ok=True)
            resume_from = downloaded = 0

        mode = "ab" if resume_from else "wb"
        with open(dest_path, mode) as fh:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if not chunk:
                    continue
                fh.write(chunk)
                downloaded += len(chunk)
                save_local_checkpoint(checkpoint_path, downloaded, source_url, total_bytes)
                if total_bytes:
                    pct = downloaded / total_bytes * 100
                    print(
                        f"  {pct:.1f}% ({downloaded / 1024**3:.2f} / "
                        f"{total_bytes / 1024**3:.2f} GB)",
                        end="\r",
                    )
    print()

    actual = dest_path.stat().st_size
    if total_bytes and actual != total_bytes:
        raise OSError(
            f"Download incomplete: {actual:,} bytes on disk, expected {total_bytes:,}. "
            f"Re-run to resume from the checkpoint."
        )

    clear_local_checkpoint(checkpoint_path)
    elapsed = time.time() - start
    print(f"Downloaded {actual / 1024**3:.2f} GB in {elapsed / 60:.1f} min")

    return {
        "status": "success",
        "path": str(dest_path),
        "size": actual,
        "source_url": source_url,
        "download_time_seconds": elapsed,
    }


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
            _s3().head_object(Bucket=s3_bucket, Key=s3_key)
            print(f"File already exists in S3: s3://{s3_bucket}/{s3_key}")
            print("Skipping download. Use --force-refresh to override.")
            return {"status": "skipped", "s3_key": s3_key}
        except _s3().exceptions.ClientError:
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
                        _s3().list_parts(
                            Bucket=s3_bucket,
                            Key=s3_key,
                            UploadId=existing_upload_id,
                        )
                        upload_id = existing_upload_id
                        parts = existing_parts.copy()
                        part_number = len(existing_parts) + 1
                        print(f"✅ Reusing existing multipart upload: {upload_id}")
                    except _s3().exceptions.ClientError as e:
                        print(
                            f"⚠️ Existing multipart upload {existing_upload_id} not found: {e}"
                        )
                        print("Checkpoint is stale - clearing and starting fresh download from beginning")
                        # Clear stale checkpoint
                        clear_checkpoint(s3_bucket, checkpoint_s3_key)
                        # Reset to start from beginning
                        existing_upload_id = None
                        bytes_resume_from = 0
                        resume_mode = False
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
        multipart_upload = _s3().create_multipart_upload(
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
                                # Upload part (logging only on retry or error)
                                part_response = _s3().upload_part(
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
                        if total_size % (10 * 1024 * 1024 * 1024) < CHUNK_SIZE:  # Every 10GB
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

        _s3().complete_multipart_upload(
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
            _s3().abort_multipart_upload(
                Bucket=s3_bucket,
                Key=s3_key,
                UploadId=upload_id,
            )
        except Exception as abort_error:
            print(f"Error aborting multipart upload: {abort_error}")
        raise


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Download the USAspending database dump to a local directory"
    )
    parser.add_argument(
        "--dest",
        default=os.environ.get("USASPENDING_DUMP_DIR", DEFAULT_DEST),
        help=f"Directory to download the dump into (default: {DEFAULT_DEST})",
    )
    parser.add_argument(
        "--s3-bucket",
        default=os.environ.get("S3_BUCKET") or os.environ.get("SBIR_ANALYTICS_S3_BUCKET"),
        help="Use the legacy S3 multipart path instead of a local download",
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
        if args.s3_bucket:
            result = download_and_upload(
                s3_bucket=args.s3_bucket,
                database_type=args.database_type,
                date_str=args.date,
                source_url=args.source_url,
                force_refresh=args.force_refresh,
            )
        else:
            result = download_local(
                dest_dir=Path(args.dest),
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
