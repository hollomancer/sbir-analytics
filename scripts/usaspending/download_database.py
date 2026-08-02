#!/usr/bin/env python3
"""Download the USAspending database dump to a local directory.

Features:
- Resume capability: HTTP Range requests continue a partial file
- Checkpoint tracking: progress saved to a sidecar next to the partial file
- Disk guard: fails fast when the volume cannot hold the dump

Usage:
    python download_database.py --database-type full --date 20251106
    python download_database.py --dest /Volumes/SSDmini/sbir-analytics/data/usaspending
    python download_database.py --source-url https://files.usaspending.gov/...

On failure, simply re-run the script to resume from the checkpoint.
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.exceptions import IncompleteRead, ProtocolError, ReadTimeoutError
from urllib3.util.retry import Retry

# Import file checking and discovery logic from check_new_file.py
from scripts.usaspending.check_new_file import check_file_availability, find_latest_available_file


# USAspending database download base URL
USASPENDING_DB_BASE_URL = "https://files.usaspending.gov/database_download"

USASPENDING_DOWNLOADS = {
    "full": "{base}/usaspending-db_{date}.zip",
    "test": "{base}/usaspending-db-subset_{date}.zip",
}

DEFAULT_DEST = "data/usaspending"


def resolve_source_url(
    database_type: str = "full",
    date_str: str | None = None,
    source_url: str | None = None,
) -> str:
    """Resolve the dump URL, auto-discovering the latest file when no date is given."""
    if source_url:
        return source_url

    if database_type not in USASPENDING_DOWNLOADS:
        raise ValueError(
            f"Unknown database_type '{database_type}'. "
            f"Known types: {', '.join(USASPENDING_DOWNLOADS.keys())}"
        )

    if date_str:
        return USASPENDING_DOWNLOADS[database_type].format(
            base=USASPENDING_DB_BASE_URL, date=date_str
        )

    print("No date specified - searching for latest available file...")
    latest_file = find_latest_available_file(database_type=database_type, s3_bucket=None)
    if not latest_file:
        raise FileNotFoundError(
            f"No available {database_type} database file found in recent months.\n"
            f"Please specify a date with --date YYYYMMDD or check available files manually."
        )
    return latest_file["source_url"]


def get_checkpoint_path(dest_path: Path) -> Path:
    """Checkpoint sidecar for a local download, alongside the partial file."""
    return dest_path.with_suffix(dest_path.suffix + ".checkpoint")


def load_local_checkpoint(checkpoint_path: Path) -> dict | None:
    """Load a local download checkpoint, or None when absent or unreadable."""
    if not checkpoint_path.is_file():
        return None
    try:
        data = json.loads(checkpoint_path.read_text())
        print(f"Loaded checkpoint from {checkpoint_path}")
        return data
    except (OSError, json.JSONDecodeError) as e:
        print(f"Warning: Failed to load checkpoint {checkpoint_path}: {e}")
        return None


def save_local_checkpoint(
    checkpoint_path: Path, bytes_downloaded: int, source_url: str, total_bytes: int | None
) -> None:
    """Persist download progress next to the partial file."""
    try:
        checkpoint_path.write_text(
            json.dumps(
                {
                    "bytes_downloaded": bytes_downloaded,
                    "source_url": source_url,
                    "total_bytes": total_bytes,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
                indent=2,
            )
        )
    except OSError as e:
        print(f"Warning: Failed to save checkpoint {checkpoint_path}: {e}")


def clear_local_checkpoint(checkpoint_path: Path) -> None:
    """Remove the checkpoint after a verified complete download."""
    try:
        checkpoint_path.unlink(missing_ok=True)
    except OSError as e:
        print(f"Warning: Failed to clear checkpoint {checkpoint_path}: {e}")


def check_free_space(dest_dir: Path, required_bytes: int, multiplier: float = 1.5) -> None:
    """Raise before downloading if the volume cannot hold the dump.

    The dump is large and downloading onto a full SSD fails late and leaves a
    useless partial file, so this fails fast instead.
    """
    if not required_bytes:
        return
    usage = shutil.disk_usage(dest_dir)
    needed = int(required_bytes * multiplier)
    if usage.free < needed:
        raise OSError(
            f"Insufficient disk space at {dest_dir}: "
            f"{usage.free / 1024**3:.1f} GB free, need ~{needed / 1024**3:.1f} GB "
            f"({required_bytes / 1024**3:.1f} GB dump x {multiplier})"
        )
    print(
        f"Disk space OK: {usage.free / 1024**3:.1f} GB free, "
        f"need ~{needed / 1024**3:.1f} GB"
    )


def download_local(
    dest_dir: Path,
    database_type: str = "full",
    date_str: str | None = None,
    source_url: str | None = None,
    force_refresh: bool = False,
    chunk_size: int = 8 * 1024 * 1024,
) -> dict:
    """Download the USAspending dump to a local directory, resuming if interrupted.

    Uses HTTP Range requests to continue a partial file rather than restarting,
    with progress checkpointed to a sidecar so a killed run resumes cheaply.
    """
    source_url = resolve_source_url(database_type, date_str, source_url)
    filename = source_url.rsplit("/", 1)[-1]

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / filename
    checkpoint_path = get_checkpoint_path(dest_path)

    availability = check_file_availability(source_url)
    if not availability["available"]:
        raise FileNotFoundError(f"Source file not available: {source_url}")
    total_bytes = availability.get("content_length") or 0

    if dest_path.is_file() and not force_refresh:
        if total_bytes and dest_path.stat().st_size == total_bytes:
            print(f"Already downloaded: {dest_path} ({total_bytes / 1024**3:.1f} GB)")
            clear_local_checkpoint(checkpoint_path)
            return {
                "status": "skipped",
                "path": str(dest_path),
                "size": total_bytes,
                "source_url": source_url,
            }

    if force_refresh:
        dest_path.unlink(missing_ok=True)
        clear_local_checkpoint(checkpoint_path)

    resume_from = dest_path.stat().st_size if dest_path.is_file() else 0
    checkpoint = load_local_checkpoint(checkpoint_path)
    if checkpoint and checkpoint.get("source_url") != source_url:
        # Checkpoint belongs to a different dump; start over rather than splice.
        print("Checkpoint is for a different source URL - restarting download")
        dest_path.unlink(missing_ok=True)
        resume_from = 0

    check_free_space(dest_dir, max(total_bytes - resume_from, 0))

    headers = {}
    if resume_from:
        headers["Range"] = f"bytes={resume_from}-"
        print(f"Resuming from byte {resume_from:,} ({resume_from / 1024**3:.1f} GB)")

    session = requests.Session()
    session.mount(
        "https://",
        HTTPAdapter(
            max_retries=Retry(
                total=5, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504]
            )
        ),
    )

    print(f"Downloading {source_url}")
    print(f"   -> {dest_path}")
    start = time.time()
    downloaded = resume_from

    with session.get(source_url, headers=headers, stream=True, timeout=300) as response:
        response.raise_for_status()
        # A server ignoring Range returns 200 with the whole body; restart cleanly.
        if resume_from and response.status_code == 200:
            print("Server ignored Range request - restarting from byte 0")
            dest_path.unlink(missing_ok=True)
            resume_from = downloaded = 0

        mode = "ab" if resume_from else "wb"
        with open(dest_path, mode) as fh:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if not chunk:
                    continue
                fh.write(chunk)
                downloaded += len(chunk)
                save_local_checkpoint(checkpoint_path, downloaded, source_url, total_bytes)
                if total_bytes:
                    pct = downloaded / total_bytes * 100
                    print(
                        f"  {pct:.1f}% ({downloaded / 1024**3:.2f} / "
                        f"{total_bytes / 1024**3:.2f} GB)",
                        end="\r",
                    )
    print()

    actual = dest_path.stat().st_size
    if total_bytes and actual != total_bytes:
        raise OSError(
            f"Download incomplete: {actual:,} bytes on disk, expected {total_bytes:,}. "
            f"Re-run to resume from the checkpoint."
        )

    clear_local_checkpoint(checkpoint_path)
    elapsed = time.time() - start
    print(f"Downloaded {actual / 1024**3:.2f} GB in {elapsed / 60:.1f} min")

    return {
        "status": "success",
        "path": str(dest_path),
        "size": actual,
        "source_url": source_url,
        "download_time_seconds": elapsed,
    }


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Download the USAspending database dump to a local directory"
    )
    parser.add_argument(
        "--dest",
        default=os.environ.get("USASPENDING_DUMP_DIR", DEFAULT_DEST),
        help=f"Directory to download the dump into (default: {DEFAULT_DEST})",
    )
    parser.add_argument(
        "--database-type",
        choices=["full", "test"],
        default=os.environ.get("DATABASE_TYPE", "full"),
        help="Database type to download (default: full)",
    )
    parser.add_argument(
        "--date",
        default=os.environ.get("DATE"),
        help="Date in YYYYMMDD format (default: current date)",
    )
    parser.add_argument(
        "--source-url",
        default=os.environ.get("SOURCE_URL"),
        help="Override source URL (optional)",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        default=os.environ.get("FORCE_REFRESH", "false").lower() == "true",
        help="Force refresh even if file already exists",
    )

    args = parser.parse_args()

    try:
        result = download_local(
            dest_dir=Path(args.dest),
            database_type=args.database_type,
            date_str=args.date,
            source_url=args.source_url,
            force_refresh=args.force_refresh,
        )
        sys.exit(0 if result.get("status") in ["success", "skipped"] else 1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
