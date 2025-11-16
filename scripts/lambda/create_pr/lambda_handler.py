"""Lambda function to create GitHub PR with refresh results."""

import json
import os
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict

import boto3

s3_client = boto3.client("s3")
secrets_client = boto3.client("secretsmanager")


def get_github_token(secret_name: str) -> str:
    """Get GitHub token from Secrets Manager."""
    response = secrets_client.get_secret_value(SecretId=secret_name)
    secret = json.loads(response["SecretString"])
    return secret.get("token") or secret.get("github_token")


def read_s3_object(bucket: str, key: str) -> str:
    """Read text object from S3."""
    response = s3_client.get_object(Bucket=bucket, Key=key)
    return response["Body"].read().decode("utf-8")


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Create GitHub PR with refresh results.
    
    Event structure:
    {
        "s3_bucket": "sbir-etl-production-data",
        "metadata_s3_key": "artifacts/2025-01-15/metadata.json",
        "github_repo": "owner/repo",
        "github_secret_name": "sbir-etl/github-token",
        "csv_s3_key": "raw/awards/2025-01-15/award_data.csv"
    }
    """
    try:
        s3_bucket = event.get("s3_bucket") or os.environ.get("S3_BUCKET")
        metadata_key = event.get("metadata_s3_key")
        github_repo = event.get("github_repo") or os.environ.get("GITHUB_REPO")
        github_secret_name = event.get("github_secret_name") or os.environ.get("GITHUB_SECRET_NAME", "sbir-etl/github-token")
        csv_s3_key = event.get("csv_s3_key")

        if not s3_bucket or not metadata_key or not github_repo:
            raise ValueError("s3_bucket, metadata_s3_key, and github_repo required")

        # Get GitHub token
        github_token = get_github_token(github_secret_name)

        # Read metadata
        metadata_json = read_s3_object(s3_bucket, metadata_key)
        metadata = json.loads(metadata_json)

        # Build PR body
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        pr_title = f"chore(data): refresh sbir awards {date_str}"
        branch_name = f"data-refresh/{date_str}"

        # Build PR body from metadata
        pr_body_lines = [
            "## SBIR awards data refresh",
            "",
            f"Automated sync of award data from the SBIR.gov public dataset.",
            "",
            "### Summary",
            "",
            "| Metric | Value |",
            "| --- | --- |",
            f"| Source URL | {metadata.get('source_url', 'N/A')} |",
            f"| Downloaded (UTC) | {metadata.get('refreshed_at_utc', 'N/A')} |",
            f"| SHA-256 | `{metadata.get('sha256', 'N/A')}` |",
            f"| File size | {metadata.get('bytes', 0):,} bytes |",
            f"| Row count | {metadata.get('row_count', 0):,} |",
            f"| Column count | {metadata.get('column_count', 0)} |",
            "",
            f"**Metadata file:** `{metadata_key}`",
        ]

        if csv_s3_key:
            pr_body_lines.append(f"**CSV file:** `{csv_s3_key}`")

        pr_body = "\n".join(pr_body_lines)

        # Create PR via GitHub API
        owner, repo = github_repo.split("/")
        github_api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls"

        headers = {
            "Authorization": f"token {github_token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
        }

        # Note: This assumes the branch and commit already exist
        # In practice, you might need to create the branch first via GitHub API
        # For now, we'll just create the PR
        pr_data = {
            "title": pr_title,
            "body": pr_body,
            "head": branch_name,
            "base": "main",  # or "develop" based on your workflow
        }

        req = urllib.request.Request(
            github_api_url,
            data=json.dumps(pr_data).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        with urllib.request.urlopen(req) as response:
            pr_result = json.loads(response.read().decode("utf-8"))

        pr_url = pr_result.get("html_url") or pr_result.get("url")

        return {
            "statusCode": 200,
            "body": {
                "status": "success",
                "pr_url": pr_url,
                "pr_number": pr_result.get("number"),
                "branch": branch_name,
            },
        }

    except Exception as e:
        print(f"Error creating PR: {e}")
        return {
            "statusCode": 500,
            "body": {
                "status": "error",
                "error": str(e),
            },
        }

