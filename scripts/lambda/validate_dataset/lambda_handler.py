"""Lambda function to validate SBIR awards dataset."""

import csv
import hashlib
import json
import os
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Dict

import boto3

s3_client = boto3.client("s3")


def load_schema_from_s3(bucket: str, key: str) -> list[str]:
    """Load schema JSON from S3."""
    response = s3_client.get_object(Bucket=bucket, Key=key)
    data = json.loads(response["Body"].read())
    if isinstance(data, dict):
        columns = data.get("columns")
        if not isinstance(columns, list):
            raise ValueError(f"Schema file {key} missing 'columns' array.")
        return [str(col) for col in columns]
    if isinstance(data, list):
        return [str(col) for col in data]
    raise ValueError(f"Schema file {key} must contain a list of columns.")


def compute_sha256_from_s3(bucket: str, key: str) -> str:
    """Compute SHA-256 hash of S3 object."""
    digest = hashlib.sha256()
    response = s3_client.get_object(Bucket=bucket, Key=key)
    for chunk in iter(lambda: response["Body"].read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def read_previous_metadata(bucket: str, key: str | None) -> Dict[str, Any] | None:
    """Read previous metadata from S3."""
    if not key:
        return None
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        return json.loads(response["Body"].read())
    except s3_client.exceptions.NoSuchKey:
        return None


def validate_header(header: list[str], expected: list[str]) -> Dict[str, Any]:
    """Validate CSV header against expected schema."""
    missing = [col for col in expected if col not in header]
    extra = [col for col in header if col not in expected]
    matches = list(header) == list(expected)
    return {
        "matches_expected": matches,
        "missing_columns": missing,
        "extra_columns": extra,
        "expected_columns": list(expected),
        "observed_columns": list(header),
    }


def count_rows_from_s3(bucket: str, key: str) -> tuple[int, list[str]]:
    """Count rows and get header from S3 CSV."""
    response = s3_client.get_object(Bucket=bucket, Key=key)
    csv_content = response["Body"].read().decode("utf-8")
    reader = csv.reader(csv_content.splitlines())
    try:
        header = next(reader)
    except StopIteration:
        raise ValueError(f"{key} is empty.")
    row_count = sum(1 for _ in reader)
    return row_count, header


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Validate SBIR awards CSV from S3.
    
    Event structure:
    {
        "s3_bucket": "sbir-etl-production-data",
        "s3_key": "raw/awards/2025-01-15/award_data.csv",
        "schema_s3_key": "schemas/sbir_awards_columns.json",
        "previous_metadata_s3_key": "artifacts/2025-01-08/metadata.json",  # Optional
        "source_url": "https://...",
        "allow_schema_drift": false
    }
    """
    try:
        s3_bucket = event.get("s3_bucket") or os.environ.get("S3_BUCKET")
        s3_key = event.get("s3_key")
        if not s3_bucket or not s3_key:
            raise ValueError("s3_bucket and s3_key required")

        schema_s3_key = event.get("schema_s3_key", "schemas/sbir_awards_columns.json")
        previous_metadata_key = event.get("previous_metadata_s3_key")
        source_url = event.get("source_url", "https://data.www.sbir.gov/mod_awarddatapublic/award_data.csv")
        allow_schema_drift = event.get("allow_schema_drift", False)

        # Load schema
        expected_columns = load_schema_from_s3(s3_bucket, schema_s3_key)

        # Count rows and get header
        row_count, header = count_rows_from_s3(s3_bucket, s3_key)

        # Validate schema
        schema_report = validate_header(header, expected_columns)
        if not schema_report["matches_expected"] and not allow_schema_drift:
            raise ValueError(
                f"Schema drift detected. Missing: {schema_report['missing_columns']} "
                f"Extra: {schema_report['extra_columns']}"
            )

        # Get file size and hash
        response = s3_client.head_object(Bucket=s3_bucket, Key=s3_key)
        file_size = response["ContentLength"]
        file_hash = compute_sha256_from_s3(s3_bucket, s3_key)

        # Compare with previous metadata
        previous_metadata = read_previous_metadata(s3_bucket, previous_metadata_key)
        prev_row_count = previous_metadata.get("row_count") if previous_metadata else None
        row_delta = row_count - prev_row_count if isinstance(prev_row_count, int) else None
        row_delta_pct = None
        if isinstance(prev_row_count, int) and prev_row_count > 0:
            row_delta_pct = (row_count - prev_row_count) / prev_row_count

        # Determine if changed
        prev_hash = previous_metadata.get("sha256") if previous_metadata else None
        changed = file_hash != prev_hash if prev_hash else True

        # Build metadata
        timestamp = datetime.now(timezone.utc)
        metadata = {
            "dataset": "sbir_awards",
            "s3_bucket": s3_bucket,
            "s3_key": s3_key,
            "source_url": source_url,
            "refreshed_at_utc": timestamp.isoformat().replace("+00:00", "Z"),
            "sha256": file_hash,
            "bytes": file_size,
            "row_count": row_count,
            "row_delta": row_delta,
            "row_delta_pct": row_delta_pct,
            "column_count": len(header),
            "schema": schema_report,
            "changed": changed,
        }

        # Upload metadata to S3
        date_str = timestamp.strftime("%Y-%m-%d")
        metadata_key = f"artifacts/{date_str}/metadata.json"
        latest_metadata_key = "artifacts/latest/metadata.json"

        s3_client.put_object(
            Bucket=s3_bucket,
            Key=metadata_key,
            Body=json.dumps(metadata, indent=2).encode("utf-8"),
            ContentType="application/json",
        )

        s3_client.put_object(
            Bucket=s3_bucket,
            Key=latest_metadata_key,
            Body=json.dumps(metadata, indent=2).encode("utf-8"),
            ContentType="application/json",
        )

        return {
            "statusCode": 200,
            "body": {
                "status": "success",
                "changed": changed,
                "metadata_s3_key": metadata_key,
                "latest_metadata_s3_key": latest_metadata_key,
                "metadata": metadata,
            },
        }

    except Exception as e:
        print(f"Error validating dataset: {e}")
        return {
            "statusCode": 500,
            "body": {
                "status": "error",
                "error": str(e),
            },
        }

