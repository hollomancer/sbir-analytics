"""Cloud storage utilities with S3-first and local fallback support."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from cloudpathlib import CloudPath, S3Path
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
    temp_dir = Path(tempfile.gettempdir()) / "sbir-etl-s3-cache"
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    # Use full S3 path as filename hash to avoid collisions
    import hashlib
    path_hash = hashlib.md5(str(s3_path).encode()).hexdigest()[:8]
    local_file = temp_dir / f"{path_hash}_{s3_path.name}"
    
    # Download if not cached or stale
    if not local_file.exists():
        logger.info(f"Downloading {s3_path} to {local_file}")
        s3_path.download_to(local_file)
        logger.debug(f"Downloaded {s3_path.name} ({local_file.stat().st_size / 1024 / 1024:.2f} MB)")
    else:
        logger.debug(f"Using cached S3 file: {local_file}")
    
    return local_file


def get_s3_bucket_from_env() -> str | None:
    """Get S3 bucket name from environment variable."""
    return os.getenv("SBIR_ETL__S3_BUCKET") or os.getenv("S3_BUCKET")


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
        raise ValueError("S3 bucket not configured. Set SBIR_ETL__S3_BUCKET env var.")
    
    # Remove leading slash if present
    relative_path = relative_path.lstrip("/")
    return f"s3://{bucket}/{relative_path}"

