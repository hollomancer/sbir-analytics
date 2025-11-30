"""Lambda function to download USPTO AI Patent Dataset and upload to S3."""

import hashlib
import os
from datetime import datetime, UTC
from typing import Any
from urllib.request import Request, urlopen

import boto3

s3_client = boto3.client("s3")

# USPTO AI Patent Dataset URLs
# Research datasets page: https://www.uspto.gov/ip-policy/economic-research/research-datasets/artificial-intelligence-patent-dataset
#
# Direct download URLs (2023 release - latest available)
# CSV: 764 MB, DTA: 649 MB
USPTO_AI_PATENT_BASE = "https://data.uspto.gov/ui/datasets/products/files/ECOPATAI/2023"
USPTO_AI_PATENT_DEFAULT_URLS = {
    "csv": f"{USPTO_AI_PATENT_BASE}/ai_model_predictions.csv.zip",
    "dta": f"{USPTO_AI_PATENT_BASE}/ai_model_predictions.dta.zip",
}

USPTO_AI_PATENT_DATASET_PAGE = (
    "https://www.uspto.gov/ip-policy/economic-research/research-datasets/artificial-intelligence-patent-dataset"
)


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Download USPTO AI Patent Dataset and stream to S3.

    Event structure:
    {
        "s3_bucket": "sbir-etl-production-data",
        "source_url": "https://...",  # Optional
        "force_refresh": false
    }
    """
    try:
        s3_bucket = event.get("s3_bucket") or os.environ.get("S3_BUCKET")
        if not s3_bucket:
            raise ValueError("S3_BUCKET not provided in event or environment")

        source_url = event.get("source_url") or USPTO_AI_PATENT_DEFAULT_URLS["csv"]
        print(f"Using USPTO AI Patent Dataset URL: {source_url}")

        # Generate S3 key
        timestamp = datetime.now(UTC)
        date_str = timestamp.strftime("%Y-%m-%d")
        s3_key = f"raw/uspto/ai_patents/{date_str}/ai_patent_dataset.zip"

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
                    "dataset": "ai_patents",
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

                # Validate size (2023 CSV is 764 MB)
                MIN_EXPECTED_SIZE = 100_000_000  # 100 MB
                if total_size < MIN_EXPECTED_SIZE:
                    raise ValueError(
                        f"Downloaded file is too small ({total_size} bytes, expected >{MIN_EXPECTED_SIZE}). "
                        f"2023 dataset should be ~650-760 MB."
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
                    },
                }

            except Exception:
                s3_client.abort_multipart_upload(
                    Bucket=s3_bucket, Key=s3_key, UploadId=upload_id
                )
                raise

    except Exception as e:
        print(f"Error downloading USPTO AI Patent data: {e}")
        import traceback

        traceback.print_exc()
        return {
            "statusCode": 500,
            "body": {
                "status": "error",
                "error": str(e),
            },
        }
