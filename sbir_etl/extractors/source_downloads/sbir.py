"""Download SBIR awards CSV from SBIR.gov to a local directory.

Epistemic tier: pipelines.

Writes the canonical CSV plus a dated vintage under ``history/``. SBIR.gov only
serves the current snapshot, so the vintage series is the only record of past
data. A ``.meta.json`` sidecar carries the source URL, sha256, and download
timestamp for each vintage; the sha256 drives change detection.

Usage:
    python scripts/data/download_sbir.py
    python scripts/data/download_sbir.py --dest /Volumes/SSDmini/sbir-analytics/data/raw/sbir
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
EPISTEMIC_TIER = "pipelines"


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


def _atomic_write(path: Path, data: bytes) -> None:
    """Write bytes via a temp file and rename, so readers never see a partial."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def _atomic_write_text(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)


def _metadata_json(file_hash: str, size: int) -> str:
    return json.dumps(
        {
            "source_url": SBIR_AWARDS_URL,
            "sha256": file_hash,
            "downloaded_at": datetime.now(UTC).isoformat(),
            "size": size,
        },
        indent=2,
    )


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


def download_sbir_awards(dest: Path) -> dict:
    """Download the awards CSV to ``dest``, keeping a dated vintage under history/.

    Returns a result dict whose ``changed`` flag is False when the download
    matches the newest vintage.
    """
    data, file_hash = _fetch()

    history_dir = dest / "history"
    previous, latest_vintage = _previous_hash(history_dir)

    if previous and previous == file_hash:
        # The vintage matches, but the canonical file discovery prefers may be
        # missing or truncated. Repair it from the fetched bytes before
        # reporting no change, or every rerun would keep returning unchanged
        # while discovery keeps serving a bad file.
        canonical = dest / CSV_NAME
        if not canonical.is_file() or canonical.stat().st_size != len(data):
            print(f"⚠️  Canonical {canonical} missing or truncated; repairing from fetch")
            _atomic_write(canonical, data)
            _atomic_write_text(dest / META_NAME, _metadata_json(file_hash, len(data)))
        print(f"✅ No changes detected (hash matches {latest_vintage})")
        return {
            "changed": False,
            "path": str(canonical),
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
    _atomic_write(vintage_csv, data)
    _atomic_write_text(vintage_dir / META_NAME, json.dumps(metadata, indent=2))

    # The canonical path the extractors read (config: extraction.sbir.csv_path).
    canonical = dest / CSV_NAME
    _atomic_write(canonical, data)
    _atomic_write_text(dest / META_NAME, json.dumps(metadata, indent=2))

    print(f"✅ Wrote {len(data) / 1024 / 1024:.1f} MB to {canonical}")
    print(f"   Vintage: {vintage_csv}")
    print(f"   SHA256:  {file_hash[:16]}...")

    return {
        "changed": True,
        "path": str(canonical),
        "vintage": str(vintage_dir),
        "size": len(data),
        "sha256": file_hash,
    }


def main():
    parser = argparse.ArgumentParser(description="Download SBIR awards to a local directory")
    parser.add_argument(
        "--dest",
        default=os.environ.get("SBIR_RAW_DIR", DEFAULT_DEST),
        help=f"Directory to write {CSV_NAME} and history/ into (default: {DEFAULT_DEST})",
    )
    args = parser.parse_args()

    try:
        result = download_sbir_awards(Path(args.dest))

        if result["changed"]:
            print(f"\n✅ New data: {result['path']}")
        else:
            print(f"\n✅ No changes - existing data current: {result['path']}")
    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
