"""Shared utilities for downloading files and uploading to S3.

This module provides common functionality used across multiple Lambda functions
to download files from URLs and upload them to S3 with proper error handling,
hashing, and metadata.
"""

import hashlib
from datetime import datetime, UTC
from typing import Any
from urllib.request import Request, urlopen

import boto3

s3_client = boto3.client("s3")


def download_file(
    source_url: str,
    user_agent: str = "SBIR-Analytics-Lambda/1.0",
    timeout: int = 600,
    max_size_mb: int | None = None,
) -> tuple[bytes, str]:
    """
    Download a file from a URL.

    Args:
        source_url: URL to download from
        user_agent: User-Agent header to send
        timeout: Request timeout in seconds
        max_size_mb: Maximum file size in MB (for memory-based downloads)

    Returns:
        Tuple of (file_data, content_type)

    Raises:
        ValueError: If response is invalid or file is too large
        Exception: If download fails
    """
    print(f"Downloading from: {source_url}")
    req = Request(source_url)
    req.add_header("User-Agent", user_agent)
    req.add_header("Accept", "*/*")
    req.add_header("Accept-Encoding", "gzip, deflate")

    with urlopen(req, timeout=timeout) as response:
        if response.getcode() != 200:
            raise ValueError(f"HTTP {response.getcode()} from {source_url}")

        content_type = response.headers.get("Content-Type", "") or ""

        # Check if response is HTML (likely an error page)
        if "text/html" in content_type.lower():
            raise ValueError("Received HTML instead of expected file - likely error page")

        data = response.read()

        # Validate size if specified
        if max_size_mb and len(data) > max_size_mb * 1024 * 1024:
            raise ValueError(
                f"File too large: {len(data) / 1024 / 1024:.1f} MB (max: {max_size_mb} MB)"
            )

        print(f"Downloaded {len(data) / 1024 / 1024:.1f} MB")
        return data, content_type


def stream_download_to_s3(
    source_url: str,
    s3_bucket: str,
    s3_key: str,
    metadata: dict[str, str] | None = None,
    user_agent: str = "SBIR-Analytics-Lambda/1.0",
    timeout: int = 600,
    chunk_size: int = 10 * 1024 * 1024,  # 10 MB
    min_size: int = 0,
    validate_zip: bool = False,
) -> tuple[int, str]:
    """
    Stream download a file directly to S3 using multipart upload.

    This is more memory-efficient for large files as it doesn't load
    the entire file into memory.

    Args:
        source_url: URL to download from
        s3_bucket: S3 bucket name
        s3_key: S3 object key
        metadata: Optional metadata to attach to S3 object
        user_agent: User-Agent header
        timeout: Request timeout in seconds
        chunk_size: Size of chunks to stream (bytes)
        min_size: Minimum expected file size (bytes)
        validate_zip: If True, validate that file is a ZIP

    Returns:
        Tuple of (total_size, sha256_hash)

    Raises:
        ValueError: If file validation fails
        Exception: If upload fails
    """
    print(f"Streaming from {source_url} to s3://{s3_bucket}/{s3_key}")

    req = Request(source_url)
    req.add_header("User-Agent", user_agent)

    with urlopen(req, timeout=timeout) as response:
        content_type = response.headers.get("Content-Type", "")

        # Check if response is HTML
        if "text/html" in content_type:
            raise ValueError("Received HTML instead of expected file - likely error page")

        # Read first chunk to validate
        first_chunk = response.read(8192)

        # Validate ZIP format if requested
        if validate_zip and not first_chunk.startswith(b"PK\x03\x04"):
            raise ValueError("Not a valid ZIP file")

        # Determine content type
        if not content_type:
            content_type = "application/octet-stream"

        # Create multipart upload
        upload = s3_client.create_multipart_upload(
            Bucket=s3_bucket,
            Key=s3_key,
            ContentType=content_type,
            Metadata=metadata or {},
        )
        upload_id = upload["UploadId"]

        try:
            parts = []
            part_num = 1
            hasher = hashlib.sha256()
            total_size = 0

            # Process first chunk
            hasher.update(first_chunk)
            total_size += len(first_chunk)
            buffer = first_chunk

            # Stream remaining data
            while True:
                chunk = response.read(chunk_size - len(buffer))
                if not chunk:
                    # Upload final buffer if exists
                    if buffer:
                        part = s3_client.upload_part(
                            Bucket=s3_bucket,
                            Key=s3_key,
                            PartNumber=part_num,
                            UploadId=upload_id,
                            Body=buffer,
                        )
                        parts.append({"PartNumber": part_num, "ETag": part["ETag"]})
                    break

                buffer += chunk
                hasher.update(chunk)
                total_size += len(chunk)

                # Upload when buffer reaches chunk size
                if len(buffer) >= chunk_size:
                    part = s3_client.upload_part(
                        Bucket=s3_bucket,
                        Key=s3_key,
                        PartNumber=part_num,
                        UploadId=upload_id,
                        Body=buffer,
                    )
                    parts.append({"PartNumber": part_num, "ETag": part["ETag"]})
                    part_num += 1
                    buffer = b""
                    print(f"Uploaded part {part_num - 1}, total: {total_size / 1_000_000:.1f} MB")

            # Complete multipart upload
            s3_client.complete_multipart_upload(
                Bucket=s3_bucket,
                Key=s3_key,
                UploadId=upload_id,
                MultipartUpload={"Parts": parts},
            )

            file_hash = hasher.hexdigest()

            # Validate size if specified
            if min_size > 0 and total_size < min_size:
                raise ValueError(
                    f"Downloaded file is too small ({total_size} bytes, expected >{min_size})"
                )

            print(f"Upload complete: {total_size / 1_000_000:.1f} MB, SHA256: {file_hash}")
            return total_size, file_hash

        except Exception:
            # Abort multipart upload on error
            s3_client.abort_multipart_upload(Bucket=s3_bucket, Key=s3_key, UploadId=upload_id)
            raise


def upload_to_s3(
    data: bytes,
    s3_bucket: str,
    s3_key: str,
    content_type: str = "application/octet-stream",
    metadata: dict[str, str] | None = None,
) -> str:
    """
    Upload data to S3.

    Args:
        data: File data to upload
        s3_bucket: S3 bucket name
        s3_key: S3 object key
        content_type: Content-Type header
        metadata: Optional metadata to attach

    Returns:
        SHA256 hash of the uploaded data
    """
    file_hash = hashlib.sha256(data).hexdigest()

    print(f"Uploading to s3://{s3_bucket}/{s3_key}")
    s3_client.put_object(
        Bucket=s3_bucket,
        Key=s3_key,
        Body=data,
        ContentType=content_type,
        Metadata=metadata or {},
    )

    return file_hash


def determine_file_extension(source_url: str, content_type: str) -> str:
    """
    Determine file extension from URL or content type.

    Args:
        source_url: Source URL
        content_type: HTTP Content-Type header

    Returns:
        File extension (e.g., '.zip', '.csv', '.json')
    """
    lower_content_type = content_type.lower()
    lower_url = source_url.lower()

    if "zip" in lower_content_type or lower_url.endswith(".zip"):
        return ".zip"
    elif "csv" in lower_content_type or lower_url.endswith(".csv"):
        return ".csv"
    elif "json" in lower_content_type or lower_url.endswith(".json"):
        return ".json"
    elif "tsv" in lower_content_type or "tab" in lower_content_type or lower_url.endswith(".tsv"):
        return ".tsv"
    elif lower_url.endswith(".dta"):
        return ".dta"
    else:
        return ""


def create_standard_response(
    success: bool,
    s3_bucket: str | None = None,
    s3_key: str | None = None,
    sha256: str | None = None,
    file_size: int | None = None,
    source_url: str | None = None,
    error: str | None = None,
    **extra_fields: Any,
) -> dict[str, Any]:
    """
    Create a standardized Lambda response.

    Args:
        success: Whether the operation succeeded
        s3_bucket: S3 bucket name
        s3_key: S3 object key
        sha256: SHA256 hash of file
        file_size: File size in bytes
        source_url: Source URL
        error: Error message if failed
        **extra_fields: Additional fields to include in response body

    Returns:
        Standardized response dictionary
    """
    timestamp = datetime.now(UTC)

    if success:
        return {
            "statusCode": 200,
            "body": {
                "status": "success",
                "s3_bucket": s3_bucket,
                "s3_key": s3_key,
                "sha256": sha256,
                "file_size": file_size,
                "source_url": source_url,
                "downloaded_at": timestamp.isoformat(),
                **extra_fields,
            },
        }
    else:
        return {
            "statusCode": 500,
            "body": {
                "status": "error",
                "error": error,
                "timestamp": timestamp.isoformat(),
            },
        }


def try_multiple_urls(
    urls: list[str],
    download_func,
    **kwargs: Any,
) -> tuple[Any, str]:
    """
    Try downloading from multiple URLs until one succeeds.

    Args:
        urls: List of URLs to try in order
        download_func: Function to call for each URL (receives url as first arg)
        **kwargs: Additional keyword arguments to pass to download_func

    Returns:
        Tuple of (result, successful_url)

    Raises:
        Exception: If all URLs fail (includes details of last error)
    """
    last_error = None

    for url in urls:
        try:
            print(f"Attempting download from: {url}")
            result = download_func(url, **kwargs)
            print(f"Successfully downloaded from: {url}")
            return result, url
        except Exception as e:
            last_error = e
            print(f"Error downloading from {url}: {e}")
            continue

    error_msg = f"Failed to download from all attempted URLs ({len(urls)} tried). Last error: {last_error}"
    if "403" in str(last_error):
        error_msg += "\n\nNote: Server returned 403 Forbidden. This may indicate authentication is required or the URL is no longer valid."
    raise Exception(error_msg)
