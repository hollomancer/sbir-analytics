"""Cloud storage utilities with S3-first and local fallback support."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from cloudpathlib import S3Path
from loguru import logger


def resolve_data_path(
    cloud_path: str | Path,
    local_fallback: Path | None = None,
    prefer_local: bool = False,
) -> Path:
    """
    Resolve data file path with S3-first and local fallback.

    Strategy:
    1. If prefer_local=True and local_fallback exists → use local
    2. If cloud_path is S3 URL → try S3 first, fallback to local
    3. If cloud_path is local path → use local (no cloud check)
    4. If S3 fails → fallback to local

    Args:
        cloud_path: S3 URL (s3://bucket/path) or local path
        local_fallback: Local path to use if S3 unavailable
        prefer_local: If True, prefer local even if S3 available

    Returns:
        Path object pointing to accessible file

    Raises:
        FileNotFoundError: If neither S3 nor local file exists
    """
    # Convert to Path for local, CloudPath for S3
    cloud_str = str(cloud_path)

    # If prefer_local and local exists, use it
    if prefer_local and local_fallback and local_fallback.exists():
        logger.debug(f"Using local file (prefer_local=True): {local_fallback}")
        return local_fallback

    # Check if it's an S3 URL
    is_s3 = cloud_str.startswith("s3://")

    if is_s3:
        # Try S3 first
        try:
            s3_path = S3Path(cloud_str)
            if s3_path.exists():
                logger.info(f"Using S3 file: {cloud_str}")
                # Download to temp location for DuckDB/pandas to read
                # DuckDB doesn't support S3 URLs directly, so we download
                return _download_s3_to_temp(s3_path)
        except Exception as e:
            logger.warning(f"S3 access failed ({e}), falling back to local")

        # Fallback to local
        if local_fallback and local_fallback.exists():
            logger.info(f"Using local fallback: {local_fallback}")
            return local_fallback

        raise FileNotFoundError(
            f"Neither S3 ({cloud_str}) nor local ({local_fallback}) file exists"
        )
    else:
        # Local path - use directly
        local_path = Path(cloud_str)
        if local_path.exists():
            return local_path

        # Try local_fallback if provided
        if local_fallback and local_fallback.exists():
            logger.info(f"Using local fallback: {local_fallback}")
            return local_fallback

        raise FileNotFoundError(f"Local file not found: {local_path}")


def _download_s3_to_temp(s3_path: S3Path) -> Path:
    """Download S3 file to temporary location for local access."""
    temp_dir = Path(tempfile.gettempdir()) / "sbir-analytics-s3-cache"
    temp_dir.mkdir(parents=True, exist_ok=True)

    # Use full S3 path as filename hash to avoid collisions
    import hashlib

    path_hash = hashlib.md5(str(s3_path).encode(), usedforsecurity=False).hexdigest()[:8]  # noqa: S324
    local_file = temp_dir / f"{path_hash}_{s3_path.name}"

    # Download if not cached or stale
    if not local_file.exists():
        logger.info(f"Downloading {s3_path} to {local_file}")
        s3_path.download_to(local_file)
        logger.debug(
            f"Downloaded {s3_path.name} ({local_file.stat().st_size / 1024 / 1024:.2f} MB)"
        )
    else:
        logger.debug(f"Using cached S3 file: {local_file}")

    return local_file


def get_s3_bucket_from_env() -> str | None:
    """Get S3 bucket name from environment variable."""
    return os.getenv("SBIR_ANALYTICS_S3_BUCKET") or os.getenv("S3_BUCKET")


def build_s3_path(relative_path: str, bucket: str | None = None) -> str:
    """
    Build S3 URL from relative path.

    Args:
        relative_path: Relative path (e.g., "data/raw/sbir/awards_data.csv")
        bucket: S3 bucket name (defaults to env var)

    Returns:
        S3 URL (e.g., "s3://bucket-name/data/raw/sbir/awards_data.csv")
    """
    bucket = bucket or get_s3_bucket_from_env()
    if not bucket:
        raise ValueError("S3 bucket not configured. Set SBIR_ANALYTICS_S3_BUCKET env var.")

    # Remove leading slash if present
    relative_path = relative_path.lstrip("/")
    return f"s3://{bucket}/{relative_path}"


def find_latest_usaspending_dump(
    bucket: str | None = None,
    database_type: str = "full",
    prefix: str = "raw/usaspending/database/",
) -> str | None:
    """
    Find the latest USAspending database dump file in S3.

    Searches for files matching the pattern:
    - Full: raw/usaspending/database/YYYY-MM-DD/usaspending-db_YYYYMMDD.zip
    - Test: raw/usaspending/database/YYYY-MM-DD/usaspending-db-subset_YYYYMMDD.zip

    Args:
        bucket: S3 bucket name (defaults to env var)
        database_type: "full" or "test"
        prefix: S3 prefix to search under

    Returns:
        S3 URL of the latest file, or None if not found
    """
    import boto3

    bucket = bucket or get_s3_bucket_from_env()
    if not bucket:
        logger.warning("S3 bucket not configured, cannot find latest dump")
        return None

    s3_client = boto3.client("s3")

    # Determine file pattern
    if database_type == "full":
        pattern = "usaspending-db_"
    elif database_type == "test":
        pattern = "usaspending-db-subset_"
    else:
        logger.warning(f"Unknown database_type: {database_type}")
        return None

    try:
        # List all files in the database directory
        paginator = s3_client.get_paginator("list_objects_v2")
        latest_file = None
        latest_date = None

        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                # Check if this matches the database type pattern
                if pattern in key and key.endswith(".zip"):
                    if latest_date is None or obj["LastModified"] > latest_date:
                        latest_file = key
                        latest_date = obj["LastModified"]

        if latest_file:
            s3_url = f"s3://{bucket}/{latest_file}"
            logger.info(
                f"Found latest USAspending {database_type} dump: {s3_url} (modified: {latest_date})"
            )
            return s3_url

        logger.warning(f"No USAspending {database_type} dump found in s3://{bucket}/{prefix}")
        return None

    except Exception as e:
        logger.error(f"Error finding latest USAspending dump: {e}")
        return None


def find_latest_sam_gov_parquet(
    bucket: str | None = None,
    prefix: str = "data/raw/sam_gov/",
) -> str | None:
    """
    Find the latest SAM.gov parquet file in S3.

    Searches for files matching the pattern:
    - Static: data/raw/sam_gov/sam_entity_records.parquet
    - Dated: data/raw/sam_gov/sam_entity_records_YYYYMMDD.parquet

    Args:
        bucket: S3 bucket name (defaults to env var)
        prefix: S3 prefix to search under

    Returns:
        S3 URL of the latest file, or None if not found
    """
    import boto3

    bucket = bucket or get_s3_bucket_from_env()
    if not bucket:
        logger.warning("S3 bucket not configured, cannot find latest SAM.gov parquet")
        return None

    s3_client = boto3.client("s3")

    try:
        # List all files in the SAM.gov directory
        paginator = s3_client.get_paginator("list_objects_v2")
        latest_file = None
        latest_date = None

        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                # Check if this matches the SAM.gov parquet pattern
                if "sam_entity_records" in key and key.endswith(".parquet"):
                    if latest_date is None or obj["LastModified"] > latest_date:
                        latest_file = key
                        latest_date = obj["LastModified"]

        if latest_file:
            s3_url = f"s3://{bucket}/{latest_file}"
            logger.info(f"Found latest SAM.gov parquet: {s3_url} (modified: {latest_date})")
            return s3_url

        logger.warning(f"No SAM.gov parquet found in s3://{bucket}/{prefix}")
        return None

    except Exception as e:
        logger.error(f"Error finding latest SAM.gov parquet: {e}")
        return None
