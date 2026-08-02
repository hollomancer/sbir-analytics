#!/usr/bin/env python3
"""Download SBIR awards CSV from SBIR.gov to a local directory.

Writes the canonical CSV plus a dated vintage under ``history/``. SBIR.gov only
serves the current snapshot, so the vintage series is the only record of past
data. A ``.meta.json`` sidecar carries the source URL, sha256, and download
timestamp for each vintage; the sha256 drives change detection.

Usage:
    python scripts/data/download_sbir.py
    python scripts/data/download_sbir.py --dest /Volumes/SSDmini/sbir-analytics/data/raw/sbir
    python scripts/data/download_sbir.py --s3-bucket my-bucket  # also upload
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

try:
    from sbir_etl.extractors.sbir_gov_api import SBIR_AWARDS_CSV_URL as SBIR_AWARDS_URL
except ImportError:
    SBIR_AWARDS_URL = "https://data.www.sbir.gov/mod_awarddatapublic/award_data.csv"

DEFAULT_DEST = "data/raw/sbir"
CSV_NAME = "award_data.csv"
META_NAME = "award_data.meta.json"


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    retry=retry_if_exception_type(
        (requests.ConnectionError, requests.Timeout, requests.exceptions.HTTPError)
    ),
    reraise=True,
)
def _download_with_retry(url: str) -> requests.Response:
    """Download with retry on transient network errors."""
    resp = requests.get(url, stream=True, timeout=300)
    if resp.status_code in (429, 500, 502, 503, 504):
        resp.close()
        resp.raise_for_status()  # triggers retry via HTTPError
    return resp


def _fetch() -> tuple[bytes, str]:
    """Stream the awards CSV, returning its bytes and sha256."""
    print(f"📥 Downloading SBIR awards from: {SBIR_AWARDS_URL}")

    response = _download_with_retry(SBIR_AWARDS_URL)
    response.raise_for_status()

    content_length = int(response.headers.get("content-length", 0))
    if content_length:
        print(f"📊 Size: {content_length / 1024 / 1024:.1f} MB")

    hasher = hashlib.sha256()
    chunks = []
    downloaded = 0

    for chunk in response.iter_content(chunk_size=1024 * 1024):  # 1MB chunks
        chunks.append(chunk)
        hasher.update(chunk)
        downloaded += len(chunk)
        if content_length:
            pct = downloaded / content_length * 100
            print(f"  {pct:.1f}% ({downloaded / 1024 / 1024:.1f} MB)", end="\r")

    print()
    return b"".join(chunks), hasher.hexdigest()


def find_latest_vintage(history_dir: Path) -> Path | None:
    """Return the newest dated vintage directory, or None if there are none."""
    if not history_dir.is_dir():
        return None
    vintages = sorted(d for d in history_dir.iterdir() if d.is_dir() and (d / CSV_NAME).is_file())
    return vintages[-1] if vintages else None


def _previous_hash(history_dir: Path) -> tuple[str, Path | None]:
    """Read the sha256 of the newest vintage. Returns ('', None) if absent."""
    latest = find_latest_vintage(history_dir)
    if latest is None:
        return "", None
    meta_path = latest / META_NAME
    if not meta_path.is_file():
        return "", latest
    try:
        return json.loads(meta_path.read_text()).get("sha256", ""), latest
    except (OSError, json.JSONDecodeError) as e:
        print(f"⚠️ Could not read {meta_path}: {e}")
        return "", latest


def download_sbir_awards(dest: Path, s3_bucket: str | None = None) -> dict:
    """Download the awards CSV to ``dest``, keeping a dated vintage under history/.

    Uploads to S3 as well when ``s3_bucket`` is set. Returns a result dict whose
    ``changed`` flag is False when the download matches the newest vintage.
    """
    data, file_hash = _fetch()

    history_dir = dest / "history"
    previous, latest_vintage = _previous_hash(history_dir)

    if previous and previous == file_hash:
        print(f"✅ No changes detected (hash matches {latest_vintage})")
        return {
            "changed": False,
            "path": str(dest / CSV_NAME),
            "vintage": str(latest_vintage),
            "sha256": file_hash,
        }

    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    vintage_dir = history_dir / date_str
    vintage_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "source_url": SBIR_AWARDS_URL,
        "sha256": file_hash,
        "downloaded_at": datetime.now(UTC).isoformat(),
        "size": len(data),
    }

    vintage_csv = vintage_dir / CSV_NAME
    vintage_csv.write_bytes(data)
    (vintage_dir / META_NAME).write_text(json.dumps(metadata, indent=2))

    # The canonical path the extractors read (config: extraction.sbir.csv_path).
    canonical = dest / CSV_NAME
    canonical.write_bytes(data)
    (dest / META_NAME).write_text(json.dumps(metadata, indent=2))

    print(f"✅ Wrote {len(data) / 1024 / 1024:.1f} MB to {canonical}")
    print(f"   Vintage: {vintage_csv}")
    print(f"   SHA256:  {file_hash[:16]}...")

    result = {
        "changed": True,
        "path": str(canonical),
        "vintage": str(vintage_dir),
        "size": len(data),
        "sha256": file_hash,
    }

    if s3_bucket:
        result.update(_upload_to_s3(data, file_hash, s3_bucket, date_str, metadata))

    return result


def _upload_to_s3(
    data: bytes, file_hash: str, s3_bucket: str, date_str: str, metadata: dict
) -> dict:
    """Mirror the download to S3. Retained until the AWS data plane is retired."""
    import boto3

    s3_key = f"raw/awards/{date_str}/{CSV_NAME}"
    print(f"📤 Uploading to s3://{s3_bucket}/{s3_key}")
    boto3.client("s3").put_object(
        Bucket=s3_bucket,
        Key=s3_key,
        Body=data,
        ContentType="text/csv",
        Metadata={
            "source_url": metadata["source_url"],
            "sha256": file_hash,
            "downloaded_at": metadata["downloaded_at"],
        },
    )
    return {"s3_bucket": s3_bucket, "s3_key": s3_key}


def main():
    parser = argparse.ArgumentParser(description="Download SBIR awards to a local directory")
    parser.add_argument(
        "--dest",
        default=os.environ.get("SBIR_RAW_DIR", DEFAULT_DEST),
        help=f"Directory to write {CSV_NAME} and history/ into (default: {DEFAULT_DEST})",
    )
    parser.add_argument(
        "--s3-bucket",
        default=os.environ.get("S3_BUCKET"),
        help="Also upload to this S3 bucket (optional; omit for local-only)",
    )
    args = parser.parse_args()

    try:
        result = download_sbir_awards(Path(args.dest), args.s3_bucket)

        if result["changed"]:
            print(f"\n✅ New data: {result['path']}")
        else:
            print(f"\n✅ No changes - existing data current: {result['path']}")
    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
