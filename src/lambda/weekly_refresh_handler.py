"""Lambda handler for weekly SBIR award data refresh."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from loguru import logger


# Configure loguru for Lambda
logger.remove()
logger.add(
    lambda msg: print(msg, end=""),
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
    level="INFO",
)

# Initialize AWS clients
s3_client = boto3.client("s3")
secrets_client = boto3.client("secretsmanager")


def lambda_handler(event: dict, context) -> dict:
    """
    Lambda handler for weekly award data refresh.

    Expected event structure (from GitHub Actions):
    {
        "force_refresh": bool,
        "source_url": str | None,
        "s3_bucket": str,
        "neo4j_secret_name": str | None
    }

    Returns:
        dict with statusCode and body (JSON string)
    """
    try:
        # Parse event payload (from GitHub Actions workflow_dispatch)
        # Handle both direct dict and wrapped payload
        payload = event
        if "body" in event:
            # API Gateway format - parse JSON body
            payload = json.loads(event["body"])

        force_refresh = payload.get("force_refresh", False)
        source_url = payload.get("source_url") or os.getenv(
            "DEFAULT_SOURCE_URL",
            "https://data.www.sbir.gov/mod_awarddatapublic/award_data.csv",
        )
        s3_bucket = payload.get("s3_bucket") or os.getenv("S3_BUCKET")
        neo4j_secret_name = payload.get("neo4j_secret_name") or os.getenv("NEO4J_SECRET_NAME")

        if not s3_bucket:
            raise ValueError("S3_BUCKET must be provided in event or environment")

        logger.info(
            "Starting weekly refresh",
            extra={
                "force_refresh": force_refresh,
                "source_url": source_url,
                "s3_bucket": s3_bucket,
            },
        )

        # Create temporary directory for processing
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            csv_path = tmp_path / "award_data.csv"
            metadata_dir = tmp_path / "reports" / "awards_data_refresh"
            metadata_dir.mkdir(parents=True, exist_ok=True)

            # Step 1: Download CSV from sbir.gov
            if not source_url:
                raise ValueError("source_url must be provided in event or environment")
            logger.info(f"Downloading CSV from {source_url}")
            download_csv(source_url, csv_path)

            # Step 2: Check for dataset changes (compare hash with S3)
            csv_hash = calculate_file_hash(csv_path)
            previous_hash = get_previous_csv_hash(s3_bucket)
            has_changes = csv_hash != previous_hash

            logger.info(
                "Change detection",
                extra={
                    "current_hash": csv_hash,
                    "previous_hash": previous_hash,
                    "has_changes": has_changes,
                },
            )

            # Step 3: Process if changed or force_refresh
            if has_changes or force_refresh:
                logger.info("Processing dataset changes")

                # Run validation and checks
                # source_url is already validated above (line 82-83)
                run_validation_scripts(
                    csv_path=csv_path,
                    metadata_dir=metadata_dir,
                    source_url=source_url,  # type: ignore[arg-type]
                    s3_bucket=s3_bucket,
                )

                # Optionally load to Neo4j
                if neo4j_secret_name:
                    neo4j_credentials = get_neo4j_credentials(neo4j_secret_name)
                    load_to_neo4j(
                        csv_path=csv_path,
                        metadata_dir=metadata_dir,
                        credentials=neo4j_credentials,
                    )

                # Upload CSV and metadata to S3
                upload_to_s3(
                    csv_path=csv_path,
                    metadata_dir=metadata_dir,
                    s3_bucket=s3_bucket,
                    csv_hash=csv_hash,
                )

                return {
                    "statusCode": 200,
                    "body": json.dumps(
                        {
                            "status": "success",
                            "message": "Dataset refreshed successfully",
                            "csv_hash": csv_hash,
                            "has_changes": True,
                        }
                    ),
                }
            else:
                logger.info("No changes detected, skipping processing")
                return {
                    "statusCode": 200,
                    "body": json.dumps(
                        {
                            "status": "skipped",
                            "message": "No changes detected",
                            "csv_hash": csv_hash,
                            "has_changes": False,
                        }
                    ),
                }

    except Exception as e:
        logger.error(f"Lambda execution failed: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps(
                {
                    "status": "error",
                    "message": str(e),
                }
            ),
        }


def download_csv(url: str, output_path: Path) -> None:
    """Download CSV file from URL."""
    import urllib.request

    urllib.request.urlretrieve(url, output_path)
    logger.info(f"Downloaded CSV: {output_path.stat().st_size / 1024 / 1024:.2f} MB")


def calculate_file_hash(file_path: Path) -> str:
    """Calculate SHA-256 hash of file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def get_previous_csv_hash(s3_bucket: str) -> str | None:
    """Get hash of previous CSV from S3 metadata."""
    try:
        # Check for hash in S3 object metadata
        response = s3_client.head_object(
            Bucket=s3_bucket,
            Key="data/raw/sbir/award_data.csv",
        )
        return response.get("Metadata", {}).get("csv_hash")
    except ClientError as e:
        if e.response["Error"]["Code"] == "404":
            logger.info("No previous CSV found in S3")
            return None
        raise


def run_validation_scripts(
    csv_path: Path,
    metadata_dir: Path,
    source_url: str,
    s3_bucket: str,
) -> None:
    """Run all validation and profiling scripts."""
    # Try multiple possible locations for schema files
    schema_paths = [
        Path("/var/task/docs/data/sbir_awards_columns.json"),
        Path("/var/task/src/docs/data/sbir_awards_columns.json"),
    ]
    schema_path = next((p for p in schema_paths if p.exists()), None)
    if not schema_path:
        raise FileNotFoundError("Schema file not found: sbir_awards_columns.json")

    company_schema_paths = [
        Path("/var/task/docs/data/sbir_company_columns.json"),
        Path("/var/task/src/docs/data/sbir_company_columns.json"),
    ]
    company_schema_path = next((p for p in company_schema_paths if p.exists()), None)
    if not company_schema_path:
        raise FileNotFoundError("Company schema file not found: sbir_company_columns.json")
    company_dir = metadata_dir.parent.parent / "data" / "raw" / "sbir"
    company_dir.mkdir(parents=True, exist_ok=True)

    # Get previous metadata from S3 if available
    previous_metadata_path = None
    try:
        s3_client.download_file(
            s3_bucket,
            "reports/awards_data_refresh/latest.json",
            str(metadata_dir / "previous_metadata.json"),
        )
        previous_metadata_path = metadata_dir / "previous_metadata.json"
    except ClientError:
        logger.info("No previous metadata found")

    # Run validation script
    logger.info("Running validation script")
    run_script(
        "scripts/data/awards_refresh_validation.py",
        [
            "--csv-path",
            str(csv_path),
            "--schema-path",
            str(schema_path),
            "--metadata-dir",
            str(metadata_dir),
            "--summary-path",
            str(metadata_dir / "latest.md"),
            "--previous-metadata",
            str(previous_metadata_path) if previous_metadata_path else "",
            "--source-url",
            source_url,
        ],
    )

    # Run profiling script
    logger.info("Running profiling script")
    run_script(
        "scripts/data/profile_sbir_inputs.py",
        [
            "--award-csv",
            str(csv_path),
            "--company-dir",
            str(company_dir),
            "--company-schema-path",
            str(company_schema_path),
            "--output-json",
            str(metadata_dir / "inputs_profile.json"),
            "--output-md",
            str(metadata_dir / "inputs_profile.md"),
        ],
    )

    # Run ingestion checks
    logger.info("Running ingestion checks")
    run_script(
        "scripts/data/run_sbir_ingestion_checks.py",
        [
            "--csv-path",
            str(csv_path),
            "--duckdb-path",
            str(metadata_dir / "ingestion.duckdb"),
            "--table-name",
            "sbir_awards_refresh",
            "--pass-rate-threshold",
            "0.95",
            "--output-dir",
            str(metadata_dir),
            "--report-json",
            str(metadata_dir / "sbir_validation_report.json"),
            "--summary-md",
            str(metadata_dir / "ingestion_summary.md"),
        ],
    )

    # Run enrichment checks
    logger.info("Running enrichment checks")
    run_script(
        "scripts/data/run_sbir_enrichment_check.py",
        [
            "--awards-csv",
            str(csv_path),
            "--company-dir",
            str(company_dir),
            "--output-json",
            str(metadata_dir / "enrichment_summary.json"),
            "--output-md",
            str(metadata_dir / "enrichment_summary.md"),
        ],
    )


def run_script(script_path: str, args: list[str]) -> None:
    """Run a Python script with arguments."""
    # Try multiple possible locations for scripts
    possible_paths = [
        Path("/var/task") / script_path,  # Lambda task root
        Path(os.getenv("LAMBDA_TASK_ROOT", "/var/task")) / script_path,
        Path(script_path),  # Absolute path
    ]

    full_script_path = None
    for path in possible_paths:
        if path.exists():
            full_script_path = path
            break

    if not full_script_path:
        raise FileNotFoundError(f"Script not found: {script_path} (tried: {possible_paths})")

    # Use python3 explicitly
    cmd = ["python3", str(full_script_path)] + [arg for arg in args if arg]  # Filter empty strings
    logger.debug(f"Running: {' '.join(cmd)}")

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=os.getenv("LAMBDA_TASK_ROOT", "/var/task"),
    )

    if result.returncode != 0:
        logger.error(f"Script failed: {script_path}")
        logger.error(f"stdout: {result.stdout}")
        logger.error(f"stderr: {result.stderr}")
        raise RuntimeError(f"Script {script_path} failed with return code {result.returncode}")

    logger.info(f"Script completed: {script_path}")


def get_neo4j_credentials(secret_name: str) -> dict:
    """Retrieve Neo4j credentials from Secrets Manager."""
    try:
        response = secrets_client.get_secret_value(SecretId=secret_name)
        secret = json.loads(response["SecretString"])
        return {
            "uri": secret.get("NEO4J_URI"),
            "user": secret.get("NEO4J_USER"),
            "password": secret.get("NEO4J_PASSWORD"),
            "database": secret.get("NEO4J_DATABASE", "neo4j"),
        }
    except Exception as e:
        logger.error(f"Failed to retrieve Neo4j credentials: {e}")
        raise


def load_to_neo4j(
    csv_path: Path,
    metadata_dir: Path,
    credentials: dict,
) -> None:
    """Load data to Neo4j (optional step)."""
    logger.info("Loading data to Neo4j")

    # Set environment variables for Neo4j scripts
    env = os.environ.copy()
    env.update(
        {
            "NEO4J_URI": credentials["uri"],
            "NEO4J_USER": credentials["user"],
            "NEO4J_PASSWORD": credentials["password"],
            "NEO4J_DATABASE": credentials["database"],
        }
    )

    # Reset Neo4j database
    logger.info("Resetting Neo4j database")
    run_script_with_env("scripts/data/reset_neo4j_sbir.py", [], env)

    # Load SBIR awards
    validated_csv_path = metadata_dir / "validated_awards.csv"
    if validated_csv_path.exists():
        logger.info("Loading SBIR awards to Neo4j")
        run_script_with_env(
            "scripts/data/run_neo4j_sbir_load.py",
            [
                "--validated-csv",
                str(validated_csv_path),
                "--output-dir",
                str(metadata_dir),
                "--summary-md",
                str(metadata_dir / "neo4j_load_summary.md"),
            ],
            env,
        )

        # Run smoke checks
        logger.info("Running Neo4j smoke checks")
        run_script_with_env(
            "scripts/data/run_neo4j_smoke_checks.py",
            [
                "--output-json",
                str(metadata_dir / "neo4j_smoke_check.json"),
                "--output-md",
                str(metadata_dir / "neo4j_smoke_check.md"),
            ],
            env,
        )


def run_script_with_env(script_path: str, args: list[str], env: dict) -> None:
    """Run a Python script with custom environment variables."""
    # Try multiple possible locations for scripts
    possible_paths = [
        Path("/var/task") / script_path,
        Path(os.getenv("LAMBDA_TASK_ROOT", "/var/task")) / script_path,
        Path(script_path),
    ]

    full_script_path = None
    for path in possible_paths:
        if path.exists():
            full_script_path = path
            break

    if not full_script_path:
        logger.warning(f"Script not found: {script_path}, skipping")
        return

    cmd = ["python3", str(full_script_path)] + [arg for arg in args if arg]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
        cwd=os.getenv("LAMBDA_TASK_ROOT", "/var/task"),
    )

    if result.returncode != 0:
        logger.error(f"Script failed: {script_path}")
        logger.error(f"stdout: {result.stdout}")
        logger.error(f"stderr: {result.stderr}")
        # Don't raise for Neo4j operations (they're optional)
        logger.warning("Continuing despite Neo4j script failure")


def upload_to_s3(
    csv_path: Path,
    metadata_dir: Path,
    s3_bucket: str,
    csv_hash: str,
) -> None:
    """Upload CSV and metadata to S3."""
    logger.info(f"Uploading to S3 bucket: {s3_bucket}")

    # Upload CSV with hash in metadata
    s3_client.upload_file(
        str(csv_path),
        s3_bucket,
        "data/raw/sbir/award_data.csv",
        ExtraArgs={
            "Metadata": {
                "csv_hash": csv_hash,
                "upload_date": datetime.utcnow().isoformat(),
            },
            "ContentType": "text/csv",
        },
    )
    logger.info("Uploaded CSV to S3")

    # Upload versioned CSV (with date)
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    s3_client.upload_file(
        str(csv_path),
        s3_bucket,
        f"data/raw/sbir/award_data_{date_str}.csv",
        ExtraArgs={
            "Metadata": {
                "csv_hash": csv_hash,
                "upload_date": datetime.utcnow().isoformat(),
            },
            "ContentType": "text/csv",
        },
    )
    logger.info(f"Uploaded versioned CSV: award_data_{date_str}.csv")

    # Upload all metadata files
    for metadata_file in metadata_dir.rglob("*"):
        if metadata_file.is_file():
            s3_key = f"reports/awards_data_refresh/{metadata_file.name}"
            s3_client.upload_file(
                str(metadata_file),
                s3_bucket,
                s3_key,
            )
            logger.debug(f"Uploaded metadata: {s3_key}")
