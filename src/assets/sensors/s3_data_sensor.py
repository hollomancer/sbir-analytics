"""S3 data arrival sensor for triggering ETL pipelines.

Monitors S3 bucket for new data files and triggers appropriate Dagster jobs.
"""

import os
from datetime import datetime, UTC

import boto3
from dagster import RunRequest, SensorEvaluationContext, SensorResult, SkipReason, sensor


def _get_s3_client():
    """Get boto3 S3 client."""
    return boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-east-2"))


def _get_latest_s3_file(bucket: str, prefix: str) -> dict | None:
    """Get the most recent file under an S3 prefix."""
    s3 = _get_s3_client()
    try:
        response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
        if "Contents" not in response:
            return None

        # Find most recent file
        files = [obj for obj in response["Contents"] if not obj["Key"].endswith("/")]
        if not files:
            return None

        latest = max(files, key=lambda x: x["LastModified"])
        return {
            "key": latest["Key"],
            "last_modified": latest["LastModified"].isoformat(),
            "size": latest["Size"],
        }
    except Exception:
        return None


@sensor(
    job_name="sbir_ingestion_job",
    name="s3_sbir_data_sensor",
    description="Monitors S3 for new SBIR award data and triggers ingestion pipeline",
    minimum_interval_seconds=300,  # Check every 5 minutes
)
def s3_sbir_data_sensor(context: SensorEvaluationContext) -> SensorResult | SkipReason:
    """Sensor that monitors S3 for new SBIR data files.

    Checks the raw/awards/ prefix in S3 for new files. When a new file is detected
    (based on LastModified timestamp), triggers the sbir_ingestion_job.

    Uses cursor to track the last processed file timestamp.
    """
    bucket = os.getenv("S3_BUCKET", "sbir-etl-production-data")
    prefix = "raw/awards/"

    # Get latest file info
    latest_file = _get_latest_s3_file(bucket, prefix)

    if not latest_file:
        return SkipReason(f"No files found in s3://{bucket}/{prefix}")

    # Get cursor (last processed timestamp)
    last_processed = context.cursor

    current_timestamp = latest_file["last_modified"]

    # Check if this is a new file
    if last_processed and current_timestamp <= last_processed:
        return SkipReason(
            f"No new data. Latest file: {latest_file['key']} "
            f"(modified: {current_timestamp}, last processed: {last_processed})"
        )

    # New file detected - trigger run
    context.log.info(
        f"New SBIR data detected: {latest_file['key']} "
        f"(size: {latest_file['size']} bytes, modified: {current_timestamp})"
    )

    return SensorResult(
        run_requests=[
            RunRequest(
                run_key=f"sbir-{current_timestamp}",
                run_config={},
                tags={
                    "source": "s3_sensor",
                    "s3_key": latest_file["key"],
                    "triggered_at": datetime.now(UTC).isoformat(),
                },
            )
        ],
        cursor=current_timestamp,
    )
