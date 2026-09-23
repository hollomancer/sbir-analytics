"""Download SBIR awards CSV from SBIR.gov to a local directory.

Epistemic tier: pipelines.

Writes the compatibility CSV plus an immutable dated capture under
``award-export/YYYY-MM-DD/``. Each capture has complete source metadata. The
legacy ``history/`` tree is read for discovery but is not moved or overwritten.

Usage:
    python scripts/data/download_sbir.py
    python scripts/data/download_sbir.py --dest /Volumes/SSDmini/sbir-analytics/data/raw/sbir
"""

import argparse
import hashlib
import os
import shutil
import sys
import tempfile
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from importlib.metadata import version
from pathlib import Path
from urllib.parse import quote

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from sbir_etl.extractors.sbir_award_export import inspect_sbir_gov_csv
from sbir_etl.models.award_export import AwardExportSourceMetadata
from sbir_etl.utils.data.file_io import file_sha256

try:
    from sbir_etl.extractors.sbir_gov_api import SBIR_AWARDS_CSV_URL as SBIR_AWARDS_URL
except ImportError:
    SBIR_AWARDS_URL = "https://data.www.sbir.gov/mod_awarddatapublic/award_data.csv"

DEFAULT_DEST = "data/raw/sbir"
CSV_NAME = "award_data.csv"
META_NAME = "award_data.meta.json"
VINTAGE_DIR = "award-export"
LEGACY_VINTAGE_DIR = "history"
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


def _fetch() -> tuple[bytes, str, dict[str, str]]:
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
    headers = {key.lower(): value for key, value in response.headers.items()}
    response.close()
    return b"".join(chunks), hasher.hexdigest(), headers


def _atomic_write(path: Path, data: bytes) -> None:
    """Write bytes via a temp file and rename, so readers never see a partial."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def _atomic_write_text(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _utc_now() -> datetime:
    """Return capture time through a patchable deterministic seam."""

    return datetime.now(UTC)


def _source_url(headers: dict[str, str]) -> tuple[str, str | None]:
    """Return the strongest upstream URL and its object-version identity."""

    object_version = headers.get("x-amz-version-id")
    if not object_version:
        return SBIR_AWARDS_URL, None
    separator = "&" if "?" in SBIR_AWARDS_URL else "?"
    return (
        f"{SBIR_AWARDS_URL}{separator}versionId={quote(object_version, safe='')}",
        object_version,
    )


def _source_metadata(
    path: Path,
    *,
    file_hash: str,
    captured_at: datetime,
    headers: dict[str, str],
    operator_identity: str,
) -> AwardExportSourceMetadata:
    """Build complete source metadata from verified staged bytes."""

    inspection = inspect_sbir_gov_csv(path)
    observed_hash = file_sha256(path)
    if observed_hash != file_hash:
        raise ValueError(
            "staged SBIR.gov bytes changed after download: "
            f"streamed {file_hash}, staged {observed_hash}"
        )
    last_modified = headers.get("last-modified")
    upstream_published_at = parsedate_to_datetime(last_modified) if last_modified else None
    source_url, object_version = _source_url(headers)
    return AwardExportSourceMetadata(
        source_url=source_url,
        retrieved_at=captured_at,
        upstream_published_at=upstream_published_at,
        upstream_date_unknown_reason=(
            None if upstream_published_at else "The upstream response omitted Last-Modified."
        ),
        upstream_object_version=object_version,
        sha256=observed_hash,
        size_bytes=path.stat().st_size,
        row_count=inspection.row_count,
        column_count=inspection.column_count,
        ordered_schema_sha256=inspection.ordered_schema_sha256,
        retrieval_tool="requests",
        retrieval_tool_version=version("requests"),
        operator_identity=operator_identity,
        access_license_note=(
            "Public HTTPS access. No separate license statement was captured; this records "
            "access to a public administrative export, not a license grant."
        ),
    )


def find_latest_vintage(history_dir: Path) -> Path | None:
    """Return the newest dated vintage directory, or None if there are none."""
    if not history_dir.is_dir():
        return None
    vintages = sorted(d for d in history_dir.iterdir() if d.is_dir() and (d / CSV_NAME).is_file())
    return vintages[-1] if vintages else None


def _latest_vintage(dest: Path) -> Path | None:
    """Return the newest new-layout or legacy vintage without moving either."""

    candidates = [
        vintage
        for root in (dest / VINTAGE_DIR, dest / LEGACY_VINTAGE_DIR)
        if (vintage := find_latest_vintage(root)) is not None
    ]
    return max(candidates, key=lambda path: path.name, default=None)


def _previous_hash(dest: Path) -> tuple[str, Path | None]:
    """Read the sha256 of the newest vintage. Returns ('', None) if absent."""

    latest = _latest_vintage(dest)
    if latest is None:
        return "", None
    meta_path = latest / META_NAME
    if not meta_path.is_file():
        return "", latest
    try:
        metadata = AwardExportSourceMetadata.model_validate_json(
            meta_path.read_text(encoding="utf-8")
        )
        return metadata.sha256, latest
    except (OSError, ValueError) as e:
        print(f"⚠️ Could not read {meta_path}: {e}")
        return "", latest


def download_sbir_awards(
    dest: Path,
    *,
    operator_identity: str = "automation:sbir-awards-download",
) -> dict:
    """Download the awards CSV and preserve a complete dated source capture.

    Returns a result dict whose ``changed`` flag is False when the download
    matches the newest vintage.
    """
    data, file_hash, headers = _fetch()
    dest.mkdir(parents=True, exist_ok=True)

    previous, latest_vintage = _previous_hash(dest)

    if previous and previous == file_hash:
        # The vintage matches, but the canonical file discovery prefers may be
        # missing or truncated. Repair it from the fetched bytes before
        # reporting no change, or every rerun would keep returning unchanged
        # while discovery keeps serving a bad file.
        canonical = dest / CSV_NAME
        if not canonical.is_file() or canonical.stat().st_size != len(data):
            print(f"⚠️  Canonical {canonical} missing or truncated; repairing from fetch")
            _atomic_write(canonical, data)
            if latest_vintage is None:
                raise RuntimeError("matching source hash has no vintage metadata")
            _atomic_write_text(
                dest / META_NAME,
                (latest_vintage / META_NAME).read_text(encoding="utf-8"),
            )
        print(f"✅ No changes detected (hash matches {latest_vintage})")
        return {
            "changed": False,
            "path": str(canonical),
            "vintage": str(latest_vintage),
            "sha256": file_hash,
        }

    captured_at = _utc_now()
    date_str = captured_at.strftime("%Y-%m-%d")
    vintage_root = dest / VINTAGE_DIR
    vintage_root.mkdir(parents=True, exist_ok=True)
    vintage_dir = vintage_root / date_str
    if vintage_dir.exists():
        raise FileExistsError(
            f"refusing to overwrite existing SBIR.gov vintage: {vintage_dir}; "
            "inspect or reconcile that capture explicitly"
        )

    staging_dir = Path(tempfile.mkdtemp(prefix=f".{date_str}-", dir=vintage_root))
    try:
        staged_csv = staging_dir / CSV_NAME
        staged_csv.write_bytes(data)
        metadata = _source_metadata(
            staged_csv,
            file_hash=file_hash,
            captured_at=captured_at,
            headers=headers,
            operator_identity=operator_identity,
        )
        (staging_dir / META_NAME).write_text(metadata.to_json(), encoding="utf-8")
        staging_dir.replace(vintage_dir)
    finally:
        if staging_dir.exists():
            shutil.rmtree(staging_dir)

    # The canonical path the extractors read (config: extraction.sbir.csv_path).
    canonical = dest / CSV_NAME
    _atomic_write(canonical, data)
    _atomic_write_text(dest / META_NAME, metadata.to_json())

    print(f"✅ Wrote {len(data) / 1024 / 1024:.1f} MB to {canonical}")
    print(f"   Vintage: {vintage_dir / CSV_NAME}")
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
    parser.add_argument(
        "--operator",
        default=os.environ.get("SBIR_CAPTURE_OPERATOR", "automation:sbir-awards-download"),
        help="operator or automation identity recorded in the source sidecar",
    )
    args = parser.parse_args()

    try:
        result = download_sbir_awards(Path(args.dest), operator_identity=args.operator)

        if result["changed"]:
            print(f"\n✅ New data: {result['path']}")
        else:
            print(f"\n✅ No changes - existing data current: {result['path']}")
    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
