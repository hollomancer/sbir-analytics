"""Lambda function to load validated SBIR awards into Neo4j using Dagster assets."""

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict

import boto3
import pandas as pd
from dagster import build_asset_context

import src.assets.sbir_neo4j_loading as loading_module

s3_client = boto3.client("s3")
secrets_client = boto3.client("secretsmanager")


def get_neo4j_credentials(secret_name: str) -> Dict[str, str]:
    """Get Neo4j credentials from Secrets Manager."""
    response = secrets_client.get_secret_value(SecretId=secret_name)
    secret = json.loads(response["SecretString"])
    return {
        "uri": secret["uri"],
        "username": secret["username"],
        "password": secret["password"],
        "database": secret.get("database", "neo4j"),
    }


def download_from_s3(bucket: str, key: str, local_path: Path) -> None:
    """Download file from S3 to local path."""
    response = s3_client.get_object(Bucket=bucket, Key=key)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    with local_path.open("wb") as f:
        f.write(response["Body"].read())


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


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Load validated SBIR awards into Neo4j using Dagster assets.
    
    Event structure:
    {
        "s3_bucket": "sbir-etl-production-data",
        "validated_csv_s3_key": "processed/ingestion/2025-01-15/validated_sbir_awards.csv",
        "neo4j_secret_name": "sbir-etl/neo4j-aura"
    }
    """
    try:
        s3_bucket = event.get("s3_bucket") or os.environ.get("S3_BUCKET")
        validated_csv_s3_key = event.get("validated_csv_s3_key")
        secret_name = event.get("neo4j_secret_name") or os.environ.get("NEO4J_SECRET_NAME", "sbir-etl/neo4j-aura")

        if not s3_bucket or not validated_csv_s3_key:
            raise ValueError("s3_bucket and validated_csv_s3_key required")

        # Get Neo4j credentials and set environment variables for Dagster
        creds = get_neo4j_credentials(secret_name)
        os.environ["NEO4J_URI"] = creds["uri"]
        os.environ["NEO4J_USERNAME"] = creds["username"]
        os.environ["NEO4J_PASSWORD"] = creds["password"]
        os.environ["NEO4J_DATABASE"] = creds["database"]

        # Download validated CSV from S3
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            validated_csv_local = tmp_path / "validated_sbir_awards.csv"
            download_from_s3(s3_bucket, validated_csv_s3_key, validated_csv_local)

            # Load DataFrame
            validated_df = pd.read_csv(validated_csv_local)

            # Materialize Neo4j loading asset
            context = build_asset_context()
            load_output = loading_module.neo4j_sbir_awards(context=context, validated_sbir_awards=validated_df)
            load_result = _output_value(load_output)
            load_metadata = _output_metadata(load_output)

            if not isinstance(load_result, dict):
                raise TypeError(f"Unexpected load result type: {type(load_result)}")

            # Upload metrics to S3
            date_str = Path(validated_csv_s3_key).parent.name
            metrics_key = f"artifacts/{date_str}/neo4j_load_metrics.json"
            summary_md_key = f"artifacts/{date_str}/neo4j_load_summary.md"

            s3_client.put_object(
                Bucket=s3_bucket,
                Key=metrics_key,
                Body=json.dumps(
                    {"result": load_result, "metadata": _serialize_metadata(load_metadata)}, indent=2
                ).encode("utf-8"),
                ContentType="application/json",
            )

            # Generate markdown summary
            lines = [
                "# Neo4j SBIR Awards Load",
                "",
                f"**Status:** {load_result.get('status', 'unknown')}",
                "",
                "| Metric | Value |",
                "| --- | --- |",
            ]

            if load_result.get("status") == "success":
                lines.append(f"| Awards loaded | {load_result.get('awards_loaded', 0)} |")
                lines.append(f"| Awards updated | {load_result.get('awards_updated', 0)} |")
                lines.append(f"| Companies loaded | {load_result.get('companies_loaded', 0)} |")
                lines.append(f"| Companies updated | {load_result.get('companies_updated', 0)} |")
                lines.append(f"| Relationships created | {load_result.get('relationships_created', 0)} |")
                lines.append(f"| Errors | {load_result.get('errors', 0)} |")
            else:
                reason = load_result.get("reason") or load_result.get("error", "unknown")
                lines.append(f"| Reason | {reason} |")

            markdown_content = "\n".join(lines)
            s3_client.put_object(
                Bucket=s3_bucket,
                Key=summary_md_key,
                Body=markdown_content.encode("utf-8"),
                ContentType="text/markdown",
            )

            # Run asset check
            check_result = loading_module.neo4j_sbir_awards_load_check(neo4j_sbir_awards=load_result)
            check_passed = check_result.passed if hasattr(check_result, "passed") else True

            return {
                "statusCode": 200,
                "body": {
                    "status": "success" if load_result.get("status") == "success" else "failed",
                    "load_status": load_result.get("status"),
                    "check_passed": check_passed,
                    "metrics_s3_key": metrics_key,
                    "summary_md_s3_key": summary_md_key,
                    "load_result": load_result,
                },
            }

    except Exception as e:
        print(f"Error loading Neo4j: {e}")
        import traceback

        traceback.print_exc()
        return {
            "statusCode": 500,
            "body": {
                "status": "error",
                "error": str(e),
            },
        }

