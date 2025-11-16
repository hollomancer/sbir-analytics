"""Lambda function to profile SBIR input CSVs."""

import csv
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict

import boto3

s3_client = boto3.client("s3")


def load_schema_from_s3(bucket: str, key: str) -> list[str]:
    """Load schema JSON from S3."""
    response = s3_client.get_object(Bucket=bucket, Key=key)
    data = json.loads(response["Body"].read())
    if isinstance(data, dict):
        columns = data.get("columns")
    else:
        columns = data
    if not isinstance(columns, list):
        raise ValueError(f"Schema file {key} must contain a list of columns.")
    return [str(col) for col in columns]


def summarize_csv_from_s3(bucket: str, key: str) -> dict[str, object]:
    """Summarize CSV from S3."""
    response = s3_client.get_object(Bucket=bucket, Key=key)
    csv_content = response["Body"].read().decode("utf-8")
    reader = csv.reader(csv_content.splitlines())
    try:
        header = next(reader)
    except StopIteration as exc:
        raise ValueError(f"{key} is empty.") from exc
    row_count = sum(1 for _ in reader)
    return {
        "path": key,
        "row_count": row_count,
        "column_count": len(header),
        "columns": header,
    }


def compare_schema(observed: list[str], expected: list[str]) -> dict[str, object]:
    """Compare observed schema with expected."""
    missing = [col for col in expected if col not in observed]
    extra = [col for col in observed if col not in expected]
    matches = observed == expected
    return {
        "matches_expected": matches,
        "missing_columns": missing,
        "extra_columns": extra,
        "expected_columns": expected,
        "observed_columns": observed,
    }


def list_company_csvs(bucket: str, prefix: str) -> list[str]:
    """List company search CSV files in S3."""
    response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
    keys = []
    if "Contents" in response:
        for obj in response["Contents"]:
            key = obj["Key"]
            if "company_search" in key and key.endswith(".csv"):
                keys.append(key)
    return sorted(keys)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Profile SBIR input CSVs (awards + company search files).
    
    Event structure:
    {
        "s3_bucket": "sbir-etl-production-data",
        "award_csv_s3_key": "raw/awards/2025-01-15/award_data.csv",
        "company_dir_s3_prefix": "raw/companies/",
        "company_schema_s3_key": "schemas/sbir_company_columns.json"
    }
    """
    try:
        s3_bucket = event.get("s3_bucket") or os.environ.get("S3_BUCKET")
        award_csv_key = event.get("award_csv_s3_key")
        company_dir_prefix = event.get("company_dir_s3_prefix", "raw/companies/")
        company_schema_key = event.get("company_schema_s3_key", "schemas/sbir_company_columns.json")

        if not s3_bucket or not award_csv_key:
            raise ValueError("s3_bucket and award_csv_s3_key required")

        # Load company schema
        expected_company_columns = load_schema_from_s3(s3_bucket, company_schema_key)

        # Profile award CSV
        award_summary = summarize_csv_from_s3(s3_bucket, award_csv_key)
        award_schema_report = compare_schema(
            award_summary["columns"], award_summary["columns"]
        )  # Identity (award schema enforced upstream)

        # Profile company CSVs
        company_csv_keys = list_company_csvs(s3_bucket, company_dir_prefix)
        if not company_csv_keys:
            raise FileNotFoundError(
                f"No company search CSVs found in s3://{s3_bucket}/{company_dir_prefix}"
            )

        company_summaries = []
        company_row_total = 0
        schema_drift_detected = False
        for csv_key in company_csv_keys:
            summary = summarize_csv_from_s3(s3_bucket, csv_key)
            company_row_total += summary["row_count"]
            schema_report = compare_schema(summary["columns"], expected_company_columns)
            summary["schema"] = schema_report
            company_summaries.append(summary)
            if not schema_report["matches_expected"]:
                schema_drift_detected = True

        # Build report
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        report = {
            "generated_at_utc": timestamp,
            "award": {**award_summary, "schema": award_schema_report},
            "company_files": company_summaries,
            "totals": {
                "company_files": len(company_summaries),
                "company_rows": company_row_total,
            },
        }

        # Upload report to S3
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        profile_json_key = f"artifacts/{date_str}/inputs_profile.json"
        profile_md_key = f"artifacts/{date_str}/inputs_profile.md"

        s3_client.put_object(
            Bucket=s3_bucket,
            Key=profile_json_key,
            Body=json.dumps(report, indent=2).encode("utf-8"),
            ContentType="application/json",
        )

        # Generate markdown summary
        lines = [
            "# SBIR input dataset profile",
            "",
            "| Input | Rows | Columns | Schema status |",
            "| --- | ---: | ---: | --- |",
        ]
        award_schema = award_summary["schema"]
        lines.append(
            f"| award_data.csv | {award_summary['row_count']:,} | {award_summary['column_count']} | "
            f"{'match' if award_schema['matches_expected'] else 'drift'} |"
        )
        lines.append("")
        lines.append("## Company search files")
        lines.append("")
        lines.append("| File | Rows | Schema status | Missing | Extra |")
        lines.append("| --- | ---: | --- | --- | --- |")
        for company in company_summaries:
            schema = company["schema"]
            missing = ", ".join(schema["missing_columns"]) if schema["missing_columns"] else "—"
            extra = ", ".join(schema["extra_columns"]) if schema["extra_columns"] else "—"
            status = "match" if schema["matches_expected"] else "drift"
            lines.append(
                f"| {company['path'].split('/')[-1]} | {company['row_count']:,} | {status} | {missing} | {extra} |"
            )
        lines.append("")
        lines.append("## Totals")
        lines.append("")
        lines.append(f"- Company files: {report['totals']['company_files']}")
        lines.append(f"- Company rows: {report['totals']['company_rows']:,}")

        markdown_content = "\n".join(lines)
        s3_client.put_object(
            Bucket=s3_bucket,
            Key=profile_md_key,
            Body=markdown_content.encode("utf-8"),
            ContentType="text/markdown",
        )

        return {
            "statusCode": 200,
            "body": {
                "status": "success",
                "profile_json_s3_key": profile_json_key,
                "profile_md_s3_key": profile_md_key,
                "schema_drift_detected": schema_drift_detected,
            },
        }

    except Exception as e:
        print(f"Error profiling inputs: {e}")
        return {
            "statusCode": 500,
            "body": {
                "status": "error",
                "error": str(e),
            },
        }

