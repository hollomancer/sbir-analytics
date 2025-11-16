"""Lambda function to run SBIR ingestion validation using Dagster assets."""

import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict

import boto3
import pandas as pd
from dagster import build_asset_context

import src.assets.sbir_ingestion as assets_module

s3_client = boto3.client("s3")


def _make_config(csv_s3_key: str, duckdb_s3_key: str, table_name: str, threshold: float) -> Any:
    """Create Dagster config for Lambda execution."""
    sbir = SimpleNamespace(
        csv_path=csv_s3_key, database_path=duckdb_s3_key, table_name=table_name
    )
    extraction = SimpleNamespace(sbir=sbir)
    data_quality = SimpleNamespace(
        sbir_awards=SimpleNamespace(pass_rate_threshold=threshold)
    )
    return SimpleNamespace(extraction=extraction, data_quality=data_quality)


def _output_value(output: Any) -> Any:
    """Extract value from Dagster output."""
    return getattr(output, "value", output)


def _output_metadata(output: Any) -> dict[str, Any]:
    """Extract metadata from Dagster output."""
    return getattr(output, "metadata", {}) or {}


def _serialize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Convert Dagster metadata values to JSON-serializable plain values."""
    result = {}
    for key, value in metadata.items():
        if hasattr(value, "value"):
            result[key] = value.value
        else:
            result[key] = value
    return result


def download_from_s3(bucket: str, key: str, local_path: Path) -> None:
    """Download file from S3 to local path."""
    response = s3_client.get_object(Bucket=bucket, Key=key)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    with local_path.open("wb") as f:
        f.write(response["Body"].read())


def upload_to_s3(bucket: str, key: str, local_path: Path) -> None:
    """Upload file from local path to S3."""
    with local_path.open("rb") as f:
        s3_client.put_object(Bucket=bucket, Key=key, Body=f.read())


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Run SBIR ingestion validation using Dagster assets.
    
    Event structure:
    {
        "s3_bucket": "sbir-etl-production-data",
        "csv_s3_key": "raw/awards/2025-01-15/award_data.csv",
        "table_name": "sbir_awards_refresh",
        "pass_rate_threshold": 0.95
    }
    """
    try:
        s3_bucket = event.get("s3_bucket") or os.environ.get("S3_BUCKET")
        csv_s3_key = event.get("csv_s3_key")
        table_name = event.get("table_name", "sbir_awards_refresh")
        pass_rate_threshold = event.get("pass_rate_threshold", 0.95)

        if not s3_bucket or not csv_s3_key:
            raise ValueError("s3_bucket and csv_s3_key required")

        # Use temporary directory for local processing
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            # Download CSV from S3
            csv_local_path = tmp_path / "award_data.csv"
            download_from_s3(s3_bucket, csv_s3_key, csv_local_path)

            # Create DuckDB path (local, will upload to S3 later)
            duckdb_local_path = tmp_path / "ingestion.duckdb"
            duckdb_s3_key = f"processed/ingestion/{Path(csv_s3_key).parent.name}/ingestion.duckdb"

            # Configure Dagster
            config = _make_config(str(csv_local_path), str(duckdb_local_path), table_name, pass_rate_threshold)
            assets_module.get_config = lambda: config  # type: ignore[assignment]

            # Materialize assets
            raw_ctx = build_asset_context()
            raw_output = assets_module.raw_sbir_awards(context=raw_ctx)
            raw_df = _output_value(raw_output)
            if not isinstance(raw_df, pd.DataFrame):
                raise TypeError("raw_sbir_awards did not return a pandas DataFrame.")
            raw_metadata = _output_metadata(raw_output)

            validated_ctx = build_asset_context()
            validated_output = assets_module.validated_sbir_awards(
                context=validated_ctx, raw_sbir_awards=raw_df
            )
            validated_df = _output_value(validated_output)
            if not isinstance(validated_df, pd.DataFrame):
                raise TypeError("validated_sbir_awards did not return a pandas DataFrame.")
            validated_metadata = _output_metadata(validated_output)

            report_ctx = build_asset_context()
            report_output = assets_module.sbir_validation_report(
                context=report_ctx, raw_sbir_awards=raw_df
            )
            report_dict = _output_value(report_output)
            if not isinstance(report_dict, dict):
                raise TypeError("sbir_validation_report did not return a dict.")
            report_metadata = _output_metadata(report_output)

            # Save validated CSV
            validated_csv_local = tmp_path / "validated_sbir_awards.csv"
            validated_df.to_csv(validated_csv_local, index=False)
            validated_csv_s3_key = f"processed/ingestion/{Path(csv_s3_key).parent.name}/validated_sbir_awards.csv"

            # Upload artifacts to S3
            date_str = Path(csv_s3_key).parent.name
            artifacts_prefix = f"artifacts/{date_str}"

            # Upload DuckDB
            if duckdb_local_path.exists():
                upload_to_s3(s3_bucket, duckdb_s3_key, duckdb_local_path)

            # Upload validated CSV
            upload_to_s3(s3_bucket, validated_csv_s3_key, validated_csv_local)

            # Upload metadata JSONs
            raw_meta_key = f"{artifacts_prefix}/raw_sbir_awards_metadata.json"
            validated_meta_key = f"{artifacts_prefix}/validated_sbir_awards_metadata.json"
            report_key = f"{artifacts_prefix}/sbir_validation_report.json"

            s3_client.put_object(
                Bucket=s3_bucket,
                Key=raw_meta_key,
                Body=json.dumps({"metadata": _serialize_metadata(raw_metadata)}, indent=2).encode("utf-8"),
                ContentType="application/json",
            )

            s3_client.put_object(
                Bucket=s3_bucket,
                Key=validated_meta_key,
                Body=json.dumps({"metadata": _serialize_metadata(validated_metadata)}, indent=2).encode("utf-8"),
                ContentType="application/json",
            )

            s3_client.put_object(
                Bucket=s3_bucket,
                Key=report_key,
                Body=json.dumps(
                    {"report": report_dict, "metadata": _serialize_metadata(report_metadata)}, indent=2
                ).encode("utf-8"),
                ContentType="application/json",
            )

            # Check if validation passed
            passed = report_dict.get("passed", False)

            return {
                "statusCode": 200,
                "body": {
                    "status": "success" if passed else "validation_failed",
                    "passed": passed,
                    "validated_csv_s3_key": validated_csv_s3_key,
                    "duckdb_s3_key": duckdb_s3_key,
                    "raw_metadata_s3_key": raw_meta_key,
                    "validated_metadata_s3_key": validated_meta_key,
                    "validation_report_s3_key": report_key,
                    "report": report_dict,
                },
            }

    except Exception as e:
        print(f"Error running ingestion checks: {e}")
        import traceback

        traceback.print_exc()
        return {
            "statusCode": 500,
            "body": {
                "status": "error",
                "error": str(e),
            },
        }

