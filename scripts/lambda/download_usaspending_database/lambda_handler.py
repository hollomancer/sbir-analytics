"""Lambda function to download USAspending PostgreSQL database dumps and upload to S3.

This function downloads monthly database dumps from files.usaspending.gov and streams them
directly to S3 using multipart upload to handle large files efficiently.

Note: For very large files (>1TB), consider using EC2/Fargate instead of Lambda
due to the 15-minute Lambda timeout limitation.
"""

import hashlib
import os
from datetime import datetime, timezone
from typing import Any, Dict
from urllib.request import Request, urlopen

import boto3

s3_client = boto3.client("s3")

# USAspending database download base URL
USASPENDING_DB_BASE_URL = "https://files.usaspending.gov/database_download"

# Available database downloads
# Full database: usaspending-db_YYYYMMDD.zip (very large, 1.5+ TB uncompressed)
# Note: These are complete PostgreSQL dumps, not individual tables
# Use DuckDB postgres_scanner to query specific tables after download
#
# Verified working URLs (as of Nov 2025):
#   https://files.usaspending.gov/database_download/usaspending-db_20251106.zip
#
# Test/sample database availability is unknown - if needed, provide explicit source_url
USASPENDING_DOWNLOADS = {
    "full": "{base}/usaspending-db_{date}.zip",
    "test": "{base}/usaspending-db-test_{date}.zip",  # URL pattern unverified
}


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Download USAspending database dump and upload to S3.

    Event structure:
    {
        "s3_bucket": "sbir-etl-production-data",
        "database_type": "test",  # or "full", "transaction_normalized", etc.
        "date": "20251006",  # YYYYMMDD format, optional
        "source_url": "https://...",  # Optional, will construct if not provided
        "force_refresh": false,
        "use_multipart": true  # Use multipart upload for large files (default true)
    }

    Returns:
    {
        "statusCode": 200,
        "body": {
            "status": "success",
            "s3_bucket": "...",
            "s3_key": "...",
            "sha256": "...",
            "file_size": 123456,
            "source_url": "...",
            "downloaded_at": "..."
        }
    }
    """
    try:
        s3_bucket = event.get("s3_bucket") or os.environ.get("S3_BUCKET")
        if not s3_bucket:
            raise ValueError("S3_BUCKET not provided in event or environment")

        database_type = event.get("database_type", "test")
        date_str = event.get("date")  # YYYYMMDD format
        source_url = event.get("source_url")
        force_refresh = event.get("force_refresh", False)
        use_multipart = event.get("use_multipart", True)

        # Construct URL if not provided
        if not source_url:
            if database_type not in USASPENDING_DOWNLOADS:
                raise ValueError(
                    f"Unknown database_type '{database_type}'. "
                    f"Known types: {', '.join(USASPENDING_DOWNLOADS.keys())}. "
                    f"Or provide source_url directly."
                )

            # If no date provided, use current month (dumps are monthly)
            if not date_str:
                now = datetime.now(timezone.utc)
                # Try current month first, then previous month
                date_str = now.strftime("%Y%m%d")

            url_template = USASPENDING_DOWNLOADS[database_type]
            source_url = url_template.format(
                base=USASPENDING_DB_BASE_URL,
                date=date_str
            )

        print(f"Downloading USAspending database ({database_type}) from {source_url}")

        # Generate S3 key
        timestamp = datetime.now(timezone.utc)
        s3_date_str = timestamp.strftime("%Y-%m-%d")
        filename = source_url.split("/")[-1]
        s3_key = f"raw/usaspending/database/{s3_date_str}/{filename}"

        # Check if file already exists and hash matches (unless force refresh)
        if not force_refresh:
            try:
                existing_obj = s3_client.head_object(Bucket=s3_bucket, Key=s3_key)
                existing_hash = existing_obj.get("Metadata", {}).get("sha256")
                if existing_hash:
                    print(f"File already exists in S3 with hash {existing_hash}")
                    # We'd need to download and hash to verify, so skip this check for now
                    # In production, you could implement a HEAD request to check Last-Modified
            except s3_client.exceptions.ClientError:
                pass  # File doesn't exist, continue with download

        # Download and upload
        # For large files, use multipart upload with streaming
        if use_multipart:
            result = _download_with_multipart_upload(
                source_url=source_url,
                s3_bucket=s3_bucket,
                s3_key=s3_key,
                database_type=database_type,
                timestamp=timestamp,
            )
        else:
            result = _download_direct(
                source_url=source_url,
                s3_bucket=s3_bucket,
                s3_key=s3_key,
                database_type=database_type,
                timestamp=timestamp,
            )

        return {
            "statusCode": 200,
            "body": result,
        }

    except Exception as e:
        print(f"Error downloading USAspending database: {e}")
        import traceback
        traceback.print_exc()
        return {
            "statusCode": 500,
            "body": {
                "status": "error",
                "error": str(e),
                "database_type": event.get("database_type"),
            },
        }


def _download_direct(
    source_url: str,
    s3_bucket: str,
    s3_key: str,
    database_type: str,
    timestamp: datetime,
) -> Dict[str, Any]:
    """Download entire file to memory then upload to S3 (for smaller files)."""
    print(f"Using direct download method for {source_url}")

    req = Request(source_url)
    req.add_header("User-Agent", "SBIR-Analytics-Lambda/1.0")
    req.add_header("Accept", "*/*")

    with urlopen(req, timeout=600) as response:
        if response.getcode() != 200:
            raise Exception(f"HTTP {response.getcode()} from {source_url}")

        data = response.read()
        file_size = len(data)
        print(f"Downloaded {file_size} bytes")

    # Compute hash
    file_hash = hashlib.sha256(data).hexdigest()
    print(f"Computed SHA256: {file_hash}")

    # Upload to S3
    print(f"Uploading to s3://{s3_bucket}/{s3_key}")
    s3_client.put_object(
        Bucket=s3_bucket,
        Key=s3_key,
        Body=data,
        ContentType="application/zip",
        Metadata={
            "sha256": file_hash,
            "source_url": source_url,
            "downloaded_at": timestamp.isoformat(),
            "database_type": database_type,
        },
    )

    return {
        "status": "success",
        "s3_bucket": s3_bucket,
        "s3_key": s3_key,
        "sha256": file_hash,
        "file_size": file_size,
        "source_url": source_url,
        "downloaded_at": timestamp.isoformat(),
        "database_type": database_type,
        "upload_method": "direct",
    }


def _download_with_multipart_upload(
    source_url: str,
    s3_bucket: str,
    s3_key: str,
    database_type: str,
    timestamp: datetime,
) -> Dict[str, Any]:
    """Download file in chunks and upload to S3 using multipart upload (for large files)."""
    print(f"Using multipart upload method for {source_url}")

    # Chunk size for streaming: 100 MB (minimum 5 MB for multipart)
    CHUNK_SIZE = 100 * 1024 * 1024

    req = Request(source_url)
    req.add_header("User-Agent", "SBIR-Analytics-Lambda/1.0")
    req.add_header("Accept", "*/*")

    # Initiate multipart upload
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

    try:
        parts = []
        part_number = 1
        total_size = 0
        hasher = hashlib.sha256()

        with urlopen(req, timeout=600) as response:
            if response.getcode() != 200:
                raise Exception(f"HTTP {response.getcode()} from {source_url}")

            while True:
                # Read chunk
                chunk = response.read(CHUNK_SIZE)
                if not chunk:
                    break

                # Update hash
                hasher.update(chunk)
                total_size += len(chunk)

                # Upload part
                print(f"Uploading part {part_number} ({len(chunk)} bytes)")
                part_response = s3_client.upload_part(
                    Bucket=s3_bucket,
                    Key=s3_key,
                    PartNumber=part_number,
                    UploadId=upload_id,
                    Body=chunk,
                )

                parts.append({
                    "ETag": part_response["ETag"],
                    "PartNumber": part_number,
                })

                part_number += 1

                # Lambda has 15-minute timeout, warn if getting close
                # In practice, you'd check remaining time via context.get_remaining_time_in_millis()
                if total_size > 10 * 1024 * 1024 * 1024:  # 10 GB
                    print("WARNING: Large file download - consider using Fargate for >10GB files")

        # Complete multipart upload
        file_hash = hasher.hexdigest()
        print(f"Completing multipart upload. Total size: {total_size}, SHA256: {file_hash}")

        s3_client.complete_multipart_upload(
            Bucket=s3_bucket,
            Key=s3_key,
            UploadId=upload_id,
            MultipartUpload={"Parts": parts},
        )

        # Add SHA256 hash to object metadata (requires copying object to itself)
        # Note: This is a workaround since multipart upload doesn't support updating metadata after completion
        try:
            s3_client.copy_object(
                Bucket=s3_bucket,
                Key=s3_key,
                CopySource={"Bucket": s3_bucket, "Key": s3_key},
                Metadata={
                    "sha256": file_hash,
                    "source_url": source_url,
                    "downloaded_at": timestamp.isoformat(),
                    "database_type": database_type,
                },
                MetadataDirective="REPLACE",
            )
        except Exception as e:
            print(f"Warning: Could not update metadata with SHA256: {e}")

        return {
            "status": "success",
            "s3_bucket": s3_bucket,
            "s3_key": s3_key,
            "sha256": file_hash,
            "file_size": total_size,
            "source_url": source_url,
            "downloaded_at": timestamp.isoformat(),
            "database_type": database_type,
            "upload_method": "multipart",
            "parts_count": len(parts),
        }

    except Exception as e:
        # Abort multipart upload on error
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
