"""Lambda function to run SBIR enrichment coverage analysis."""

import json
import os
from typing import Any, Dict

import boto3
import pandas as pd

# Import enrichment logic
# Note: This will need to be available in the Lambda layer or container
from src.enrichers.company_enricher import enrich_awards_with_companies

s3_client = boto3.client("s3")


def load_dataframe_from_s3(bucket: str, key: str) -> pd.DataFrame:
    """Load DataFrame from S3 CSV."""
    response = s3_client.get_object(Bucket=bucket, Key=key)
    return pd.read_csv(response["Body"])


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


def load_company_catalog_from_s3(bucket: str, prefix: str) -> pd.DataFrame:
    """Load company catalog from multiple S3 CSVs."""
    csv_keys = list_company_csvs(bucket, prefix)
    if not csv_keys:
        raise FileNotFoundError(f"No company search CSVs found in s3://{bucket}/{prefix}")

    frames = []
    for key in csv_keys:
        df = load_dataframe_from_s3(bucket, key)
        df["_source_file"] = key.split("/")[-1]
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def summarize_enrichment(enriched: pd.DataFrame) -> dict[str, Any]:
    """Summarize enrichment results."""
    method_series = enriched.get("_match_method")
    score_series = enriched.get("_match_score")

    match_counts: dict[str, int] = {}
    matched_rows = 0
    if method_series is not None:
        method_counts = method_series.fillna("unmatched").astype(str).value_counts(dropna=False)
        match_counts = method_counts.to_dict()
        matched_rows = int(method_counts.sum() - method_counts.get("unmatched", 0))
    total_rows = int(len(enriched))
    match_rate = matched_rows / total_rows if total_rows else 0.0

    avg_match_score = None
    if score_series is not None and score_series.notna().any():
        avg_match_score = float(score_series.dropna().mean())

    company_columns = sorted([col for col in enriched.columns if col.startswith("company_")])

    return {
        "total_awards": total_rows,
        "matched_awards": matched_rows,
        "match_rate": match_rate,
        "average_match_score": avg_match_score,
        "match_counts": match_counts,
        "company_columns": company_columns,
    }


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Run SBIR enrichment coverage analysis.
    
    Event structure:
    {
        "s3_bucket": "sbir-etl-production-data",
        "awards_csv_s3_key": "raw/awards/2025-01-15/award_data.csv",
        "company_dir_s3_prefix": "raw/companies/",
        "high_threshold": 90,
        "low_threshold": 75
    }
    """
    try:
        s3_bucket = event.get("s3_bucket") or os.environ.get("S3_BUCKET")
        awards_csv_key = event.get("awards_csv_s3_key")
        company_dir_prefix = event.get("company_dir_s3_prefix", "raw/companies/")
        high_threshold = event.get("high_threshold", 90)
        low_threshold = event.get("low_threshold", 75)

        if not s3_bucket or not awards_csv_key:
            raise ValueError("s3_bucket and awards_csv_s3_key required")

        # Load data
        awards_df = load_dataframe_from_s3(s3_bucket, awards_csv_key)
        companies_df = load_company_catalog_from_s3(s3_bucket, company_dir_prefix)

        # Run enrichment
        enriched_df = enrich_awards_with_companies(
            awards_df,
            companies_df,
            award_company_col="Company",
            company_name_col="Company Name",
            uei_col="UEI",
            duns_col="DUNs",
            high_threshold=high_threshold,
            low_threshold=low_threshold,
            return_candidates=False,
        )

        # Summarize
        summary = summarize_enrichment(enriched_df)

        # Build report
        report = {
            "summary": summary,
            "awards_rows": int(len(awards_df)),
            "company_rows": int(len(companies_df)),
        }

        # Upload to S3
        from datetime import datetime, timezone

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        enrichment_json_key = f"artifacts/{date_str}/enrichment_summary.json"
        enrichment_md_key = f"artifacts/{date_str}/enrichment_summary.md"

        s3_client.put_object(
            Bucket=s3_bucket,
            Key=enrichment_json_key,
            Body=json.dumps(report, indent=2).encode("utf-8"),
            ContentType="application/json",
        )

        # Generate markdown
        lines = [
            "# SBIR company enrichment coverage",
            "",
            "| Metric | Value |",
            "| --- | --- |",
            f"| Award rows | {report['awards_rows']:,} |",
            f"| Company rows | {report['company_rows']:,} |",
            f"| Matched awards | {summary['matched_awards']:,} |",
            f"| Match rate | {summary['match_rate']:.2%} |",
        ]
        if summary.get("average_match_score") is not None:
            lines.append(f"| Average match score | {summary['average_match_score']:.2f} |")
        lines.append("")
        lines.append("## Matches by method")
        lines.append("")
        lines.append("| Method | Rows |")
        lines.append("| --- | ---: |")
        for method, count in summary["match_counts"].items():
            lines.append(f"| {method} | {count:,} |")

        markdown_content = "\n".join(lines)
        s3_client.put_object(
            Bucket=s3_bucket,
            Key=enrichment_md_key,
            Body=markdown_content.encode("utf-8"),
            ContentType="text/markdown",
        )

        return {
            "statusCode": 200,
            "body": {
                "status": "success",
                "enrichment_json_s3_key": enrichment_json_key,
                "enrichment_md_s3_key": enrichment_md_key,
            },
        }

    except Exception as e:
        print(f"Error running enrichment checks: {e}")
        return {
            "statusCode": 500,
            "body": {
                "status": "error",
                "error": str(e),
            },
        }

