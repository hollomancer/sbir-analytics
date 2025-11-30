"""Lambda function to download USPTO Patent Assignment Dataset and upload to S3."""

import hashlib
import os
from datetime import datetime, UTC
from typing import Any
from urllib.request import Request, urlopen

import boto3

s3_client = boto3.client("s3")

# USPTO Patent Assignment Dataset URLs
# Research datasets page: https://www.uspto.gov/ip-policy/economic-research/research-datasets/patent-assignment-dataset
#
# Direct download URLs (2023 release - latest available as of 2025-11-29)
# Full dataset bundles (all tables): csv.zip (1.78 GB), dta.zip (1.56 GB)
USPTO_ASSIGNMENT_BASE = "https://data.uspto.gov/ui/datasets/products/files/ECORSEXC/2023"
USPTO_ASSIGNMENT_DEFAULT_URLS = {
    "csv": f"{USPTO_ASSIGNMENT_BASE}/csv.zip",  # Full dataset: 1.78 GB
    "dta": f"{USPTO_ASSIGNMENT_BASE}/dta.zip",  # Full dataset: 1.56 GB
}

USPTO_ASSIGNMENT_DATASET_PAGE = (
    "https://www.uspto.gov/ip-policy/economic-research/research-datasets/patent-assignment-dataset"
)


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Download USPTO Patent Assignment Dataset and stream to S3.

    Event structure:
    {
        "s3_bucket": "sbir-etl-production-data",
        "source_url": "https://...",  # Optional, defaults to USPTO
        "format": "csv",  # or "dta" - defaults to csv
        "force_refresh": false
    }
    """
    try:
        s3_bucket = event.get("s3_bucket") or os.environ.get("S3_BUCKET")
        if not s3_bucket:
            raise ValueError("S3_BUCKET not provided in event or environment")

        source_url = event.get("source_url")
        file_format = event.get("format", "csv")

        if not source_url:
            if file_format in USPTO_ASSIGNMENT_DEFAULT_URLS:
                source_url = USPTO_ASSIGNMENT_DEFAULT_URLS[file_format]
                print(f"Using default USPTO Patent Assignment URL ({file_format}): {source_url}")
            else:
                raise ValueError(
                    f"Unknown format '{file_format}'. Available: csv, dta. "
                    f"See {USPTO_ASSIGNMENT_DATASET_PAGE}"
                )

        # Generate S3 key
        timestamp = datetime.now(UTC)
        date_str = timestamp.strftime("%Y-%m-%d")
        s3_key = f"raw/uspto/assignments/{date_str}/patent_assignments_{file_format}.zip"

        # Stream download to S3
        print(f"Streaming from {source_url} to s3://{s3_bucket}/{s3_key}")
        req = Request(source_url)
        req.add_header("User-Agent", "SBIR-Analytics-Lambda/1.0")

        with urlopen(req, timeout=600) as response:
            # Check response
            content_type = response.headers.get("Content-Type", "")
            if "text/html" in content_type:
                raise ValueError("Received HTML instead of ZIP - likely error page")

            # Read first chunk to validate
            first_chunk = response.read(8192)
            if not first_chunk.startswith(b'PK\x03\x04'):
                raise ValueError("Not a valid ZIP file")

            # Stream to S3 using multipart upload
            upload = s3_client.create_multipart_upload(
                Bucket=s3_bucket,
                Key=s3_key,
                ContentType="application/zip",
                Metadata={
                    "source_url": source_url,
                    "downloaded_at": timestamp.isoformat(),
                    "format": file_format,
                },
            )
            upload_id = upload["UploadId"]

            try:
                parts = []
                part_num = 1
                hasher = hashlib.sha256()
                total_size = 0
                chunk_size = 10 * 1024 * 1024  # 10 MB chunks

                # Upload first chunk
                hasher.update(first_chunk)
                total_size += len(first_chunk)
                buffer = first_chunk

                while True:
                    chunk = response.read(chunk_size - len(buffer))
                    if not chunk:
                        # Upload final buffer
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
                        print(f"Uploaded part {part_num-1}, total: {total_size / 1_000_000:.1f} MB")

                # Complete upload
                s3_client.complete_multipart_upload(
                    Bucket=s3_bucket,
                    Key=s3_key,
                    UploadId=upload_id,
                    MultipartUpload={"Parts": parts},
                )

                file_hash = hasher.hexdigest()

                # Validate size
                MIN_EXPECTED_SIZE = 100_000_000  # 100 MB
                if total_size < MIN_EXPECTED_SIZE:
                    raise ValueError(
                        f"Downloaded file is too small ({total_size} bytes, expected >{MIN_EXPECTED_SIZE}). "
                        f"Full dataset should be ~1.5-1.8 GB."
                    )

                print(f"Upload complete: {total_size / 1_000_000:.1f} MB, SHA256: {file_hash}")

                return {
                    "statusCode": 200,
                    "body": {
                        "status": "success",
                        "s3_bucket": s3_bucket,
                        "s3_key": s3_key,
                        "sha256": file_hash,
                        "file_size": total_size,
                        "source_url": source_url,
                        "downloaded_at": timestamp.isoformat(),
                        "format": file_format,
                    },
                }

            except Exception as e:
                s3_client.abort_multipart_upload(
                    Bucket=s3_bucket, Key=s3_key, UploadId=upload_id
                )
                raise

    except Exception as e:
        print(f"Error downloading USPTO Assignment data: {e}")
        import traceback

        traceback.print_exc()
        return {
            "statusCode": 500,
            "body": {
                "status": "error",
                "error": str(e),
            },
        }
