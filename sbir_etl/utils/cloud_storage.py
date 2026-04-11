"""Cloud storage utilities with S3-first and local fallback support."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

try:
    from cloudpathlib import S3Path
except ImportError:
    S3Path = None  # type: ignore[assignment, misc]


def is_s3_path(path: str | Path) -> bool:
    """Check if a path is an S3 URL."""
    return str(path).startswith("s3://")


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
        if S3Path is None:
            raise ImportError(
                "S3 support requires the 'cloud' extra: pip install sbir-etl[cloud]"
            )
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


_S3_CACHE_DIR = Path(tempfile.gettempdir()) / "sbir-analytics-s3-cache"


def _get_float_env(var_name: str, default: float) -> float:
    """Read a float environment variable, falling back to *default* if invalid."""
    raw = os.getenv(var_name)
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        logger.warning(f"Invalid value for {var_name}={raw!r}; using default {default}")
        return default


# Cache limits (configurable via env vars)
_S3_CACHE_MAX_SIZE_GB = _get_float_env("SBIR_ETL_S3_CACHE_MAX_GB", 50.0)
_S3_CACHE_TTL_HOURS = _get_float_env("SBIR_ETL_S3_CACHE_TTL_HOURS", 24.0)


def _download_s3_to_temp(s3_path: S3Path) -> Path:
    """Download S3 file to temporary location for local access."""
    _S3_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Use full S3 path as filename hash to avoid collisions
    import hashlib

    path_hash = hashlib.md5(str(s3_path).encode(), usedforsecurity=False).hexdigest()[:8]  # noqa: S324
    local_file = _S3_CACHE_DIR / f"{path_hash}_{s3_path.name}"

    # Download if not cached or stale (TTL check)
    if local_file.exists():
        import time

        age_hours = (time.time() - local_file.stat().st_mtime) / 3600
        if age_hours > _S3_CACHE_TTL_HOURS:
            logger.info(f"Cache expired ({age_hours:.1f}h > {_S3_CACHE_TTL_HOURS}h): {local_file}")
            local_file.unlink()

    if not local_file.exists():
        logger.info(f"Downloading {s3_path} to {local_file}")
        s3_path.download_to(local_file)
        logger.debug(
            f"Downloaded {s3_path.name} ({local_file.stat().st_size / 1024 / 1024:.2f} MB)"
        )
    else:
        logger.debug(f"Using cached S3 file: {local_file}")

    return local_file


def cleanup_s3_cache(
    max_size_gb: float | None = None,
    max_age_hours: float | None = None,
) -> int:
    """Remove stale or excess files from the S3 download cache.

    Eviction strategy: oldest files first (by modification time).

    Args:
        max_size_gb: Maximum cache size in GB. Defaults to SBIR_ETL_S3_CACHE_MAX_GB env (50).
        max_age_hours: Remove files older than this. Defaults to SBIR_ETL_S3_CACHE_TTL_HOURS env (24).

    Returns:
        Number of files removed.
    """
    import time

    max_size = (max_size_gb if max_size_gb is not None else _S3_CACHE_MAX_SIZE_GB) * 1024**3
    max_age = (max_age_hours if max_age_hours is not None else _S3_CACHE_TTL_HOURS) * 3600
    now = time.time()
    removed = 0

    if not _S3_CACHE_DIR.exists():
        return 0

    # Pass 1: remove files older than TTL
    files = sorted(_S3_CACHE_DIR.iterdir(), key=lambda f: f.stat().st_mtime)
    for f in files:
        if f.is_file() and (now - f.stat().st_mtime) > max_age:
            f.unlink()
            removed += 1

    # Pass 2: evict oldest files if total size still exceeds limit
    files = sorted(_S3_CACHE_DIR.iterdir(), key=lambda f: f.stat().st_mtime)
    total_size = sum(f.stat().st_size for f in files if f.is_file())
    for f in files:
        if total_size <= max_size:
            break
        if f.is_file():
            total_size -= f.stat().st_size
            f.unlink()
            removed += 1

    if removed:
        logger.info(f"S3 cache cleanup: removed {removed} files")
    return removed


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


def find_latest_sbir_awards(bucket: str | None = None, prefix: str = "raw/awards/") -> str | None:
    """
    Find the latest SBIR awards CSV file in S3.

    Args:
        bucket: S3 bucket name
        prefix: S3 prefix to search

    Returns:
        S3 URL of latest file, or None if not found
    """
    import boto3

    bucket = bucket or get_s3_bucket_from_env()
    if not bucket:
        return None

    try:
        s3 = boto3.client("s3")
        continuation_token: str | None = None
        latest_obj: dict[str, Any] | None = None

        while True:
            list_kwargs: dict[str, Any] = {"Bucket": bucket, "Prefix": prefix, "MaxKeys": 1000}
            if continuation_token:
                list_kwargs["ContinuationToken"] = continuation_token

            response = s3.list_objects_v2(**list_kwargs)
            for obj in response.get("Contents", []):
                if not obj["Key"].endswith("award_data.csv"):
                    continue
                obj_dict = dict(obj)  # Cast to dict for type checker
                if latest_obj is None or obj_dict["LastModified"] > latest_obj["LastModified"]:
                    latest_obj = obj_dict

            if not response.get("IsTruncated"):
                break
            continuation_token = response.get("NextContinuationToken")

        if latest_obj is None:
            return None

        return f"s3://{bucket}/{latest_obj['Key']}"

    except Exception as e:
        logger.warning(f"Failed to find latest SBIR awards in S3: {e}")
        return None


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


def find_latest_recipient_lookup_parquet(
    bucket: str | None = None,
    prefix: str = "raw/usaspending/recipient_lookup/",
) -> str | None:
    """
    Find the latest recipient_lookup parquet file in S3.

    This is the extracted recipient data (~500MB) instead of the full 217GB dump.

    Args:
        bucket: S3 bucket name (defaults to env var)
        prefix: S3 prefix to search under

    Returns:
        S3 URL of the latest parquet file, or None if not found
    """
    import boto3

    bucket = bucket or get_s3_bucket_from_env()
    if not bucket:
        logger.warning("S3 bucket not configured, cannot find recipient_lookup parquet")
        return None

    s3_client = boto3.client("s3")

    try:
        paginator = s3_client.get_paginator("list_objects_v2")
        latest_file = None
        latest_date = None

        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith(".parquet"):
                    if latest_date is None or obj["LastModified"] > latest_date:
                        latest_file = key
                        latest_date = obj["LastModified"]

        if latest_file:
            s3_url = f"s3://{bucket}/{latest_file}"
            logger.info(
                f"Found latest recipient_lookup parquet: {s3_url} (modified: {latest_date})"
            )
            return s3_url

        logger.warning(f"No recipient_lookup parquet found in s3://{bucket}/{prefix}")
        return None

    except Exception as e:
        logger.error(f"Error finding recipient_lookup parquet: {e}")
        return None


def find_latest_sam_gov_parquet(
    bucket: str | None = None,
    prefix: str = "raw/sam_gov/",
) -> str | None:
    """
    Find the latest SAM.gov parquet file in S3.

    Searches for files matching the pattern:
    - Static: raw/sam_gov/sam_entity_records.parquet
    - Dated: raw/sam_gov/sam_entity_records_YYYYMMDD.parquet

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


# ---------------------------------------------------------------------------
# SBIR awards CSV source resolution and freshness checking
# ---------------------------------------------------------------------------


@dataclass
class SbirAwardsSource:
    """Metadata about a resolved SBIR awards CSV source."""

    path: Path
    origin: str  # "s3", "download", or "local"
    s3_key_date: str | None = None


def resolve_sbir_awards_csv(
    download_url: str = "https://data.www.sbir.gov/mod_awarddatapublic/award_data.csv",
    local_path: Path | None = None,
) -> SbirAwardsSource:
    """Resolve the SBIR awards CSV: S3 first, then download, then local.

    Resolution order:
    1. S3 bucket (if ``SBIR_ANALYTICS_S3_BUCKET`` is set and contains a CSV)
    2. Direct HTTP download from *download_url*
    3. *local_path* if provided and exists (e.g. a previously cached copy)

    Args:
        download_url: URL to download CSV from if S3 is unavailable.
        local_path: Optional local path to try as last resort.

    Returns:
        :class:`SbirAwardsSource` with the resolved path and origin metadata.

    Raises:
        FileNotFoundError: If no source could be resolved.
    """
    import re

    import httpx

    # 1. Try S3
    bucket = get_s3_bucket_from_env()
    if bucket:
        try:
            s3_url = find_latest_sbir_awards(bucket)
        except (ImportError, ModuleNotFoundError) as e:
            logger.warning(
                f"S3 lookup unavailable (missing cloud dependencies): {e}"
            )
            s3_url = None
        if s3_url:
            logger.info(f"Using S3-cached CSV: {s3_url}")
            date_match = re.search(r"raw/awards/(\d{4}-\d{2}-\d{2})/", s3_url)
            key_date = date_match.group(1) if date_match else None
            # Download S3 object to a local temp file so downstream code
            # (DuckDB, pandas) can read it without special S3 handling.
            local_path_resolved = resolve_data_path(s3_url)
            return SbirAwardsSource(
                path=local_path_resolved, origin="s3", s3_key_date=key_date
            )

    # 2. Download from URL
    logger.info(f"S3 not available; downloading from {download_url}")
    try:
        with httpx.Client(timeout=600, follow_redirects=True) as client:
            response = client.get(download_url)
            response.raise_for_status()

        with tempfile.NamedTemporaryFile(
            mode="wb", suffix=".csv", prefix="sbir_awards_", delete=False,
        ) as tmp_file:
            tmp_file.write(response.content)
            tmp = Path(tmp_file.name)
        size_mb = tmp.stat().st_size / 1024 / 1024
        logger.info(f"Downloaded {size_mb:.1f} MB to {tmp}")
        return SbirAwardsSource(path=tmp, origin="download")
    except Exception as e:
        logger.warning(f"Download failed: {e}")

    # 3. Local fallback
    if local_path and local_path.exists():
        logger.info(f"Using local fallback: {local_path}")
        return SbirAwardsSource(path=local_path, origin="local")

    raise FileNotFoundError(
        f"Could not resolve SBIR awards CSV from S3, download ({download_url}), "
        f"or local ({local_path})"
    )


def check_sbir_data_freshness(
    source: SbirAwardsSource,
    max_award_date: str | None,
    days: int,
    *,
    s3_slack_days: int = 3,
    data_slack_days: int = 14,
) -> list[str]:
    """Check whether SBIR bulk data is fresh enough for a reporting window.

    Runs two independent checks:
    1. **S3 key date** — was the data-refresh workflow recent?
    2. **Max award date in data** — is the underlying SBIR.gov dataset current?

    Args:
        source: Resolved data source with optional S3 key date.
        max_award_date: The most recent ``Proposal Award Date`` in the dataset.
        days: The reporting window in days (e.g. 7 for weekly).
        s3_slack_days: Allowed slack beyond *days* for S3 key date.
        data_slack_days: Allowed slack beyond *days* for max award date.

    Returns:
        List of warning strings (empty if data is fresh).
    """
    from datetime import datetime, UTC

    from .date_utils import parse_date

    warnings: list[str] = []
    now = datetime.now(UTC).replace(tzinfo=None)

    if source.s3_key_date:
        key_dt = parse_date(source.s3_key_date)
        if key_dt:
            key_datetime = datetime(key_dt.year, key_dt.month, key_dt.day)
            age_days = (now - key_datetime).days
            if age_days > days + s3_slack_days:
                warnings.append(
                    f"S3 data is {age_days} days old (key date: {source.s3_key_date}). "
                    f"The data-refresh workflow may have failed."
                )

    if max_award_date:
        max_dt = parse_date(max_award_date)
        if max_dt:
            max_datetime = datetime(max_dt.year, max_dt.month, max_dt.day)
            data_age = (now - max_datetime).days
            if data_age > days + data_slack_days:
                warnings.append(
                    f"Most recent award in data is from {max_award_date} "
                    f"({data_age} days ago). SBIR.gov bulk data may not have "
                    f"been updated recently."
                )

    return warnings
