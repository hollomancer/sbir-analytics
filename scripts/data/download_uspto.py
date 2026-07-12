#!/usr/bin/env python3
"""Download USPTO data files to S3 or a local directory.

Replaces the Lambda function with a script that runs on GitHub Actions
(S3 mode) or a laptop (--local mode).

Usage:
    python scripts/data/download_uspto.py --dataset patentsview --table cpc --local data/raw/uspto/patentsview
    python scripts/data/download_uspto.py --dataset patentsview --table patent   # streams to S3
    python scripts/data/download_uspto.py --dataset assignments
    python scripts/data/download_uspto.py --dataset ai_patents

PatentsView access (verified July 2026):
- Anonymous downloads from data.uspto.gov ended June 18, 2026. Requests without
  credentials get a ~20 KB HTML shell with HTTP 200, not the file.
- Flow: GET api.uspto.gov/api/v1/datasets/products/files/{product}/{file} with an
  X-API-KEY header returns JSON containing a presigned CloudFront URL. That URL
  EXPIRES ~30 SECONDS after minting, so this script downloads immediately after
  minting (an in-flight download continues past expiry).
- The mint endpoint allows 20 requests per file per 365 days — don't burn mints
  on probes or retries.
- API key: set USPTO_ODP_API_KEY (environment or repo-root .env), or --api-key.
  Keys are free with a USPTO.gov account: https://data.uspto.gov

Other datasets:
- USPTO Assignments: 2023 is latest release (verified Dec 2024)
- USPTO AI Patents: 2023 is latest release (verified Dec 2024, updated Jan 8, 2025)
"""

import argparse
import hashlib
import os
import re
import sys
import time
from datetime import datetime, UTC
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

REPO = Path(__file__).resolve().parents[2]

# PatentsView configuration
# Updated: July 2026 — PatentsView lives on the USPTO Open Data Portal (ODP).
# Migration: https://data.uspto.gov/support/transition-guide/patentsview
# Files are served via a mint-then-download flow (see module docstring); the
# relational tables below belong to the PVGPATDIS bulk product.
ODP_FILES_API = "https://api.uspto.gov/api/v1/datasets/products/files"
PATENTSVIEW_PRODUCT = "PVGPATDIS"  # PatentsView Granted Patent Disambiguated Data
API_KEY_ENV_VAR = "USPTO_ODP_API_KEY"
PATENTSVIEW_TABLES = {
    "patent": "g_patent.tsv.zip",
    "application": "g_application.tsv.zip",
    "assignee": "g_assignee_disambiguated.tsv.zip",
    "inventor": "g_inventor_disambiguated.tsv.zip",
    "location": "g_location_disambiguated.tsv.zip",
    "cpc": "g_cpc_current.tsv.zip",
    "gov_interest": "g_gov_interest.tsv.zip",
}

# USPTO Assignment Dataset
# NOTE: As of December 2025, USPTO Open Data Portal requires browser-based download.
# The /ui/ URLs return HTML instead of direct file downloads.
# Workaround: Download individual CSV files which may have different endpoints.
# Source: https://www.uspto.gov/ip-policy/economic-research/research-datasets/patent-assignment-dataset
# Full dataset includes: assignment, assignor, assignee, documentid, assignment_conveyance, documentid_admin
#
# IMPORTANT: These URLs currently return HTML pages, not ZIP files.
# The USPTO has moved to a JavaScript-based download system.
# Contact EconomicsData@uspto.gov for programmatic access or use manual download.
USPTO_ASSIGNMENT_URL = "https://data.uspto.gov/ui/datasets/products/files/ECORSEXC/2023/csv.zip"

# Individual file URLs (also return HTML as of Dec 2025)
USPTO_ASSIGNMENT_FILES = {
    "assignment": "https://data.uspto.gov/ui/datasets/products/files/ECORSEXC/2023/assignment.csv.zip",
    "assignor": "https://data.uspto.gov/ui/datasets/products/files/ECORSEXC/2023/assignor.csv.zip",
    "assignee": "https://data.uspto.gov/ui/datasets/products/files/ECORSEXC/2023/assignee.csv.zip",
    "documentid": "https://data.uspto.gov/ui/datasets/products/files/ECORSEXC/2023/documentid.csv.zip",
}

# USPTO AI Patent Dataset
# Verified: December 2024 - 2023 is latest release (updated Jan 8, 2025)
# Source: https://www.uspto.gov/ip-policy/economic-research/research-datasets/artificial-intelligence-patent-dataset
# Note: 2023 release uses CSV format (2020 release used TSV)
USPTO_AI_PATENT_URL = "https://data.uspto.gov/ui/datasets/products/files/ECOPATAI/2023/ai_model_predictions.csv.zip"

# User-Agent header for USPTO downloads
USER_AGENT = "SBIR-Analytics/1.0 (GitHub Actions; +https://github.com/your-org/sbir-analytics)"


def create_session_with_retries() -> requests.Session:
    """Create requests session with retry logic and exponential backoff."""
    session = requests.Session()

    # Configure retry strategy
    retry_strategy = Retry(
        total=3,  # Maximum 3 retry attempts
        backoff_factor=2,  # Exponential backoff: 2, 4, 8 seconds
        status_forcelist=[429, 500, 502, 503, 504],  # Retry on these HTTP status codes
        allowed_methods=["GET"],  # Only retry GET requests
    )

    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    # Set User-Agent header
    session.headers.update({"User-Agent": USER_AGENT})

    return session


def _redact_url(url: str) -> str:
    """Strip the query string before logging — presigned URLs carry signatures."""
    return url.split("?", 1)[0] + ("?<redacted>" if "?" in url else "")


def resolve_api_key(cli_value: str | None) -> str:
    """Resolve the ODP API key: --api-key flag, environment, then repo-root .env."""
    if cli_value:
        return cli_value
    if os.environ.get(API_KEY_ENV_VAR):
        return os.environ[API_KEY_ENV_VAR]
    env_file = REPO / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith(f"{API_KEY_ENV_VAR}=") and line.split("=", 1)[1]:
                return line.split("=", 1)[1]
    raise ValueError(
        f"No USPTO ODP API key found. Set {API_KEY_ENV_VAR} in the environment or "
        f"repo-root .env, or pass --api-key. Free keys: https://data.uspto.gov "
        f"(see .env.example)."
    )


def download_odp_file(product_file: str, api_key: str, dest_path: Path, session: requests.Session) -> dict:
    """Download any ODP bulk product file (e.g. "PVGPATDIS/g_patent.tsv.zip",
    "TRCFECO2/2023/owner.csv.zip") via the ODP files API.

    The API has two response modes (both observed July 2026):
    - Small files: the response body IS the ZIP — stream it straight to disk.
    - Large files: the body is a JSON message containing a presigned CloudFront
      URL that EXPIRES ~30 SECONDS after minting — download it immediately.

    Each file allows 20 API requests per 365 days, so do not call speculatively.
    """
    api_url = f"{ODP_FILES_API}/{product_file}"
    print(f"🔑 Requesting {product_file} from ODP files API...")
    resp = session.get(api_url, headers={"X-API-KEY": api_key}, stream=True, timeout=300)
    resp.raise_for_status()

    content_type = resp.headers.get("content-type", "")
    if "json" in content_type or content_type.startswith("text/plain"):
        # Mint-message mode: extract the presigned URL and download NOW
        body = resp.text
        m = re.search(r'https://[^\s"]+', body)
        if not m:
            raise ValueError(f"ODP response contained no presigned URL. Body: {body[:300]}")
        # Surface the remaining-mints notice the API appends to its response
        quota = re.search(r"you submitted[^.]*", body)
        if quota:
            print(f"   Mint quota: {quota.group(0)}")
        return stream_download(m.group(0).rstrip("."), dest_path, session)
    if "text/html" in content_type:
        raise ValueError(
            f"ODP files API returned HTML (Content-Type: {content_type}) — "
            f"check that the API key is valid (see {API_KEY_ENV_VAR} in .env.example)."
        )
    # Direct-file mode: this response is the ZIP itself
    result = _stream_response_to_file(resp, dest_path)
    # Defensive: a mint message served with a binary content-type would land
    # here as a tiny non-ZIP "file" — detect it and chase the presigned URL.
    if result["size"] < 4096:
        head = dest_path.read_bytes()
        if not head.startswith(b"PK"):
            m = re.search(rb'https://[^\s"]+', head)
            if m:
                print("   Response was a mint message, not the file — following presigned URL...")
                return stream_download(m.group(0).decode().rstrip("."), dest_path, session)
    return result


def stream_download(source_url: str, dest_path: Path, session: requests.Session) -> dict:
    """Stream a URL to disk with progress, hashing, and HTML-shell detection.

    Returns dict with size, sha256, and download_time_seconds.

    Raises:
        requests.exceptions.RequestException: On download failure after retries
        ValueError: If response is HTML instead of the expected binary file
                    (for presigned URLs this usually means the mint expired)
    """
    print(f"📥 Downloading: {_redact_url(source_url)}")
    print(f"   User-Agent: {USER_AGENT}")

    response = session.get(source_url, stream=True, timeout=300)
    response.raise_for_status()

    # Validate content type — USPTO serves an HTML shell (HTTP 200) for
    # unauthorized paths and for presigned URLs used after their ~30s expiry.
    content_type = response.headers.get("content-type", "")
    if "text/html" in content_type:
        raise ValueError(
            f"USPTO returned HTML instead of a file (Content-Type: {content_type}). "
            f"For presigned URLs this means the mint expired before the download "
            f"started; re-run to mint a fresh URL (20 mints per file per year)."
        )

    return _stream_response_to_file(response, dest_path)


def _stream_response_to_file(response: requests.Response, dest_path: Path) -> dict:
    """Stream an open HTTP response to disk with progress and ZIP validation."""
    content_length = int(response.headers.get("content-length", 0))
    print(f"📊 Size: {content_length / 1024 / 1024:.1f} MB")

    hasher = hashlib.sha256()
    downloaded = 0
    start_time = time.time()
    first_bytes = b""

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dest_path, "wb") as out:
        for chunk in response.iter_content(chunk_size=8 * 1024 * 1024):  # 8MB chunks
            if not chunk:  # Filter out keep-alive chunks
                continue
            if not first_bytes:
                first_bytes = chunk[:100]
            out.write(chunk)
            hasher.update(chunk)
            downloaded += len(chunk)

            if content_length:
                pct = downloaded / content_length * 100
                elapsed = time.time() - start_time
                speed = downloaded / elapsed / 1024 / 1024 if elapsed > 0 else 0
                print(f"  {pct:.1f}% ({downloaded / 1024 / 1024:.1f} MB) - {speed:.1f} MB/s", end="\r")

    print()  # New line after progress
    elapsed = time.time() - start_time
    print(f"⏱️  Download completed in {elapsed:.1f}s")

    # Validate that we got a ZIP file, not HTML
    # ZIP files start with PK (0x504B), HTML starts with <!DOCTYPE or <html
    if first_bytes[:2] != b"PK":
        if b"<!doctype" in first_bytes.lower() or b"<html" in first_bytes.lower():
            dest_path.unlink(missing_ok=True)
            raise ValueError(
                f"Downloaded file is HTML, not a ZIP archive ({downloaded} bytes). "
                f"For presigned URLs this means the mint expired before the download "
                f"started; re-run to mint a fresh URL."
            )
        print(f"⚠️  Warning: File does not appear to be a ZIP (magic bytes: {first_bytes[:4].hex()})")

    return {
        "size": downloaded,
        "sha256": hasher.hexdigest(),
        "download_time_seconds": elapsed,
    }


def upload_to_s3(local_path: Path, s3_bucket: str, s3_key: str, source_url: str, sha256: str) -> float:
    """Upload a downloaded file to S3. Returns upload time in seconds."""
    import boto3  # Lazy: --local mode must work without boto3/AWS credentials

    print(f"📤 Uploading to s3://{s3_bucket}/{s3_key}")
    upload_start = time.time()
    s3 = boto3.client("s3")
    s3.upload_file(
        str(local_path),
        s3_bucket,
        s3_key,
        ExtraArgs={
            "ContentType": "application/zip",
            "Metadata": {
                "source_url": source_url[:1024],
                "sha256": sha256,
                "downloaded_at": datetime.now(UTC).isoformat(),
                "user_agent": USER_AGENT,
            },
        },
    )
    upload_elapsed = time.time() - upload_start
    print(f"✅ Uploaded in {upload_elapsed:.1f}s")
    return upload_elapsed


def main():
    parser = argparse.ArgumentParser(
        description="Download USPTO data to S3 or a local directory",
        epilog="""
Examples:
  python scripts/data/download_uspto.py --dataset patentsview --table cpc --local data/raw/uspto/patentsview
  python scripts/data/download_uspto.py --dataset patentsview --table patent
  python scripts/data/download_uspto.py --dataset assignments
  python scripts/data/download_uspto.py --dataset patentsview --table assignee --s3-bucket my-bucket
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dataset",
        choices=["patentsview", "assignments", "ai_patents"],
        help="Dataset to download (or use --product-file for any ODP product)",
    )
    parser.add_argument(
        "--product-file",
        metavar="PRODUCT/PATH/FILE",
        help="Any ODP bulk product file, e.g. TRCFECO2/2023/owner.csv.zip "
        "(requires the API key; overrides --dataset)",
    )
    parser.add_argument(
        "--table",
        help="PatentsView table name (for patentsview dataset). Valid: %(choices)s",
        choices=list(PATENTSVIEW_TABLES.keys()),
    )
    parser.add_argument(
        "--s3-bucket",
        default=os.environ.get("S3_BUCKET", "sbir-etl-production-data"),
        help="S3 bucket name (default: %(default)s)",
    )
    parser.add_argument(
        "--local",
        metavar="DIR",
        help="Write the file to this local directory instead of uploading to S3 "
        "(no AWS credentials or boto3 needed)",
    )
    parser.add_argument(
        "--api-key",
        help=f"USPTO ODP API key (default: ${API_KEY_ENV_VAR} or repo-root .env). "
        "Required for the patentsview dataset.",
    )
    args = parser.parse_args()
    if not args.dataset and not args.product_file:
        parser.error("provide --dataset or --product-file")

    date_str = datetime.now(UTC).strftime("%Y-%m-%d")

    print(f"🚀 USPTO Data Download")
    print(f"   Dataset: {args.dataset}")
    print(f"   Date: {date_str}")
    print(f"   Destination: {args.local if args.local else f's3://{args.s3_bucket}'}")
    print()

    try:
        session = create_session_with_retries()
        patentsview_file = None
        product_file = None

        if args.product_file:
            product_file = args.product_file.strip("/")
            filename = product_file.rsplit("/", 1)[-1]
            api_key = resolve_api_key(args.api_key)
            source_url = f"{ODP_FILES_API}/{product_file}"
            s3_key = f"raw/uspto/odp/{date_str}/{filename}"
            print(f"   Product file: {product_file}")

        elif args.dataset == "patentsview":
            table = args.table or "patent"
            if table not in PATENTSVIEW_TABLES:
                print(f"❌ Unknown table: {table}")
                print(f"   Valid tables: {', '.join(PATENTSVIEW_TABLES.keys())}")
                sys.exit(1)

            filename = PATENTSVIEW_TABLES[table]
            api_key = resolve_api_key(args.api_key)
            patentsview_file = filename
            # For error messages; the real download URL is resolved by the API
            source_url = f"{ODP_FILES_API}/{PATENTSVIEW_PRODUCT}/{filename}"
            s3_key = f"raw/uspto/patentsview/{date_str}/{table}.zip"
            print(f"   Table: {table}")

        elif args.dataset == "assignments":
            filename = "patent_assignments.zip"
            source_url = USPTO_ASSIGNMENT_URL
            s3_key = f"raw/uspto/assignments/{date_str}/{filename}"
            print(f"   Format: CSV (2023 release)")

        elif args.dataset == "ai_patents":
            filename = "ai_patent_dataset.zip"
            source_url = USPTO_AI_PATENT_URL
            s3_key = f"raw/uspto/ai_patents/{date_str}/{filename}"
            print(f"   Format: CSV (2023 release, updated Jan 8, 2025)")

        if args.local:
            dest_path = Path(args.local) / filename
        else:
            dest_path = Path(f"/tmp/uspto_download_{os.getpid()}.zip")

        print()
        if product_file:
            result = download_odp_file(product_file, api_key, dest_path, session)
        elif patentsview_file:
            result = download_odp_file(f"{PATENTSVIEW_PRODUCT}/{patentsview_file}", api_key, dest_path, session)
        else:
            result = stream_download(source_url, dest_path, session)

        upload_time = None
        if not args.local:
            upload_time = upload_to_s3(dest_path, args.s3_bucket, s3_key, source_url, result["sha256"])
            dest_path.unlink(missing_ok=True)

        print()
        print("=" * 60)
        print("✅ Download Complete")
        print("=" * 60)
        if args.local:
            print(f"Local File: {dest_path}")
        else:
            print(f"S3 Location: s3://{args.s3_bucket}/{s3_key}")
        print(f"File Size: {result['size'] / 1024 / 1024:.1f} MB")
        print(f"SHA256: {result['sha256']}")
        print(f"Download Time: {result['download_time_seconds']:.1f}s")
        if upload_time is not None:
            print(f"Upload Time: {upload_time:.1f}s")
        print("=" * 60)

    except requests.exceptions.Timeout as e:
        print()
        print("=" * 60)
        print("❌ Download Timeout")
        print("=" * 60)
        print(f"Error: Request timed out after 300 seconds")
        print(f"URL: {_redact_url(source_url)}")
        print(f"Suggestion: Check network connectivity or try again later")
        print("=" * 60)
        sys.exit(1)

    except requests.exceptions.HTTPError as e:
        print()
        print("=" * 60)
        print("❌ HTTP Error")
        print("=" * 60)
        print(f"Status Code: {e.response.status_code}")
        print(f"URL: {_redact_url(source_url)}")
        print(f"Error: {e}")
        print(f"Suggestion: Verify URL is correct and accessible")
        print("=" * 60)
        sys.exit(1)

    except requests.exceptions.RequestException as e:
        print()
        print("=" * 60)
        print("❌ Network Error")
        print("=" * 60)
        print(f"Error: {e}")
        print(f"URL: {_redact_url(source_url)}")
        print(f"Suggestion: Check network connectivity and try again")
        print("=" * 60)
        sys.exit(1)

    except ValueError as e:
        print()
        print("=" * 60)
        print("❌ Invalid Response or Configuration")
        print("=" * 60)
        print(f"Error: {e}")
        print(f"URL: {_redact_url(source_url)}")
        print()
        print("Common causes:")
        print("  1. Missing/invalid API key — set USPTO_ODP_API_KEY (see .env.example)")
        print("  2. Presigned URL expired before download started (mint lasts ~30s) — re-run")
        print("  3. assignments/ai_patents URLs still require browser-based download;")
        print("     contact EconomicsData@uspto.gov for programmatic access")
        print("=" * 60)
        sys.exit(1)

    except Exception as e:
        print()
        print("=" * 60)
        print("❌ Unexpected Error")
        print("=" * 60)
        print(f"Error: {e}")
        print(f"Type: {type(e).__name__}")
        import traceback
        print(f"Traceback:")
        traceback.print_exc()
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
