#!/usr/bin/env python3
"""Download SAM.gov entity data to S3 as parquet.

Uses the SAM.gov Entity Information API v3 extract mode (format=csv) to
bulk-download active entity registrations, then converts to parquet and
uploads to S3.

Download strategy (in order):
  1. API extract mode (format=csv) — async bulk download, up to 1M records
  2. Paginated API fallback — 10 records/page, capped at 10k records

Exit codes:
    0  Success
    1  General failure (network, S3, parse error)
    2  API key problem — expired, invalid, or missing. CI should treat
       exit code 2 as "rotate the key" rather than a transient failure.

API key lifecycle:
    SAM.gov keys expire every ~60 days. Rotating the key:
      1. Log in at https://sam.gov → Account → API Keys
      2. Generate a new key
      3. Update the GitHub secret:
         gh secret set SAM_GOV_API_KEY --body "SAM-xxxx" --repo <owner/repo>

Usage:
    python scripts/data/download_sam_gov.py
    python scripts/data/download_sam_gov.py --s3-bucket my-bucket
    python scripts/data/download_sam_gov.py --dry-run

Environment:
    SAM_GOV_API_KEY  SAM.gov API key (required)
    S3_BUCKET        S3 bucket name (overridden by --s3-bucket)
"""

import argparse
import io
import os
import re
import sys
import time
import zipfile
from datetime import UTC, datetime
from functools import partial

import boto3
import pandas as pd
import requests

# Force unbuffered output so CI logs stream in real time.
print = partial(print, flush=True)  # noqa: A001

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ENTITY_API_URL = "https://api.sam.gov/entity-information/v3/entities"
S3_KEY = "raw/sam_gov/sam_entity_records.parquet"
REQUEST_TIMEOUT = 120

# Extract polling — SAM.gov generates the file asynchronously
EXTRACT_POLL_INTERVAL = 30  # seconds between polls
EXTRACT_POLL_MAX = 40  # max polls (~20 min)

# Paginated fallback — API returns max 10 per page, 10k record ceiling
PAGE_SIZE = 10
MAX_PAGINATED_RECORDS = 10_000

# Columns the downstream pipeline reads (SAMGovExtractor.ENRICHMENT_COLUMNS).
REQUIRED_COLUMNS = [
    "unique_entity_id",
    "legal_business_name",
    "dba_name",
    "physical_address_city",
    "physical_address_state",
    "cage_code",
    "primary_naics",
    "naics_code_string",
    "duns_number",
]

# SAM.gov CSV/JSON field names → our column names.
# The extract CSV uses UPPER_SNAKE headers; the JSON API uses camelCase.
CSV_COLUMN_MAP = {
    # CSV extract headers (UPPER_SNAKE)
    "UNIQUE_ENTITY_ID": "unique_entity_id",
    "UEI": "unique_entity_id",
    "UEI SAM": "unique_entity_id",
    "LEGAL_BUSINESS_NAME": "legal_business_name",
    "LEGAL BUSINESS NAME": "legal_business_name",
    "DBA_NAME": "dba_name",
    "DBA NAME": "dba_name",
    "PHYSICAL_ADDRESS_CITY": "physical_address_city",
    "PHYSICAL ADDRESS CITY": "physical_address_city",
    "PHYSICAL_ADDRESS_STATE": "physical_address_state",
    "PHYSICAL ADDRESS STATE OR PROVINCE": "physical_address_state",
    "CAGE_CODE": "cage_code",
    "CAGE CODE": "cage_code",
    "PRIMARY_NAICS": "primary_naics",
    "PRIMARY NAICS": "primary_naics",
    "NAICS_CODE_STRING": "naics_code_string",
    "NAICS CODE STRING": "naics_code_string",
    "DUNS_NUMBER": "duns_number",
    "DUNS": "duns_number",
    # JSON API field names (camelCase)
    "ueiSAM": "unique_entity_id",
    "legalBusinessName": "legal_business_name",
    "dbaName": "dba_name",
    "cageCode": "cage_code",
    "primaryNaics": "primary_naics",
    "dunsNumber": "duns_number",
}


# ---------------------------------------------------------------------------
# API key diagnostics
# ---------------------------------------------------------------------------

class APIKeyError(Exception):
    """Raised when the API key is missing, expired, or invalid."""


def _check_api_key_response(resp: requests.Response, context: str) -> None:
    """Raise APIKeyError with a clear remediation message on auth failures.

    SAM.gov returns 401/403 for expired, invalid, or missing keys, and
    429 when the daily quota is exhausted.
    """
    if resp.status_code not in (401, 403, 429):
        return

    try:
        body = resp.json()
    except Exception:
        body = {"raw": resp.text[:500]}

    # Flatten nested error structures into a single string for matching
    message = " ".join(str(v) for v in body.values()).lower()

    if any(kw in message for kw in ("expired", "expir")):
        hint = (
            "API key EXPIRED — it needs to be rotated.\n"
            "  1. Log in at https://sam.gov → Account → API Keys\n"
            "  2. Generate a new key\n"
            "  3. Update the GitHub secret:\n"
            "     gh secret set SAM_GOV_API_KEY --body 'SAM-xxxx' --repo hollomancer/sbir-analytics"
        )
    elif any(kw in message for kw in ("invalid", "not found", "unrecognized")):
        hint = (
            "API key INVALID or not recognised.\n"
            "  Verify the key at https://sam.gov → Account → API Keys.\n"
            "  Expected format: SAM-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
        )
    elif resp.status_code == 429 or any(kw in message for kw in ("throttle", "quota", "exceeded", "rate")):
        # Extract next access time if provided
        try:
            next_access = resp.json().get("nextAccessTime", "midnight UTC")
        except Exception:
            next_access = "midnight UTC"
        hint = (
            f"DAILY RATE LIMIT exceeded.  Retry after: {next_access}\n"
            "  Non-federal personal keys: 10 requests/day.\n"
            "  Non-federal system keys: 1,000 requests/day.\n"
            "  Consider requesting a system key at https://sam.gov.\n"
            "  The previous run may have consumed the quota — check workflow history."
        )
    else:
        hint = (
            f"Unrecognised auth failure.  Raw response:\n"
            f"  {body}\n"
            "  Check your key at https://sam.gov → Account → API Keys."
        )

    raise APIKeyError(
        f"SAM.gov auth failure during: {context}\n"
        f"  HTTP {resp.status_code}: {resp.reason}\n"
        f"  {hint}"
    )


def _validate_api_key(api_key: str) -> None:
    """Quick connectivity check — fetch 1 entity to validate the key works."""
    print("🔑 Validating SAM.gov API key...")
    resp = requests.get(
        ENTITY_API_URL,
        params={
            "api_key": api_key,
            "registrationStatus": "A",
            "includeSections": "entityRegistration",
            "page": 0,
            "size": 1,
        },
        timeout=REQUEST_TIMEOUT,
    )
    _check_api_key_response(resp, "API key validation (single entity fetch)")

    if not resp.ok:
        raise RuntimeError(
            f"Unexpected response during key validation: HTTP {resp.status_code}\n"
            f"  Body: {resp.text[:300]}"
        )

    data = resp.json()
    total = data.get("totalRecords", 0)
    print(f"   Key valid.  SAM.gov reports {total:,} active entities.")
    return total


# ---------------------------------------------------------------------------
# Strategy 1: Extract mode (format=csv) — async bulk download
# ---------------------------------------------------------------------------

def _request_extract(api_key: str) -> str | None:
    """Request a CSV extract and return the download URL (with token).

    The SAM.gov entity API supports ``format=csv`` which triggers an async
    extract.  The response contains a download URL with a placeholder
    ``REPLACE_WITH_API_KEY`` that must be swapped for the real key.
    """
    print("\n📦 Requesting CSV extract of all active entities...")
    resp = requests.get(
        ENTITY_API_URL,
        params={
            "api_key": api_key,
            "registrationStatus": "A",
            "includeSections": "entityRegistration,coreData",
            "format": "csv",
        },
        timeout=REQUEST_TIMEOUT,
    )
    _check_api_key_response(resp, "entity extract request (format=csv)")

    if not resp.ok:
        print(f"⚠️  Extract request failed: HTTP {resp.status_code}")
        print(f"   Body: {resp.text[:300]}")
        return None

    # The response body may be JSON with a download URL, or it may contain
    # the URL in plain text.  Try several extraction strategies.
    content_type = resp.headers.get("content-type", "")
    text = resp.text.strip()

    # Strategy A: JSON with a download link field
    download_url = None
    if "json" in content_type or text.startswith("{"):
        try:
            data = resp.json()
            download_url = (
                data.get("downloadUrl")
                or data.get("downloadLink")
                or data.get("fileUrl")
                or data.get("url")
                or data.get("extractUrl")
            )
            # If none of the known fields matched, search all string values
            if not download_url:
                for v in data.values():
                    if isinstance(v, str) and ("http" in v and "REPLACE_WITH_API_KEY" in v):
                        download_url = v
                        break
            if download_url:
                print(f"   Got download URL from JSON response")
        except Exception as e:
            print(f"   Could not parse JSON: {e}")

    # Strategy B: look for a URL anywhere in the response text
    if not download_url:
        urls = re.findall(r'https?://[^\s"<>]+REPLACE_WITH_API_KEY[^\s"<>]*', text)
        if urls:
            download_url = urls[0]
            print(f"   Found download URL in response text")

    # Strategy C: the response might be a redirect or direct CSV
    if not download_url and ("csv" in content_type or text.startswith('"') or "," in text[:200]):
        print("   Response appears to be direct CSV data")
        return "__DIRECT_CSV__"

    if not download_url:
        print(f"⚠️  Could not find download URL in extract response")
        print(f"   Content-Type: {content_type}")
        print(f"   Response preview: {text[:300]}")
        return None

    # Replace the API key placeholder
    final_url = download_url.replace("REPLACE_WITH_API_KEY", api_key)
    return final_url


def _download_extract(api_key: str) -> pd.DataFrame | None:
    """Request, poll, and download a CSV extract → DataFrame."""
    url = _request_extract(api_key)
    if url is None:
        return None

    # If the response was direct CSV, we already have data (not expected for bulk)
    if url == "__DIRECT_CSV__":
        print("⚠️  Direct CSV not expected for bulk extract, falling back")
        return None

    # Poll until the file is ready
    print(f"⏳ Polling for extract file (up to {EXTRACT_POLL_MAX * EXTRACT_POLL_INTERVAL // 60} min)...")
    for attempt in range(1, EXTRACT_POLL_MAX + 1):
        resp = requests.get(url, timeout=600, stream=True)
        _check_api_key_response(resp, f"extract download (poll {attempt})")

        content_type = resp.headers.get("content-type", "")
        content_length = int(resp.headers.get("content-length", 0))

        # File not ready yet — SAM.gov returns various indicators
        if resp.status_code in (202, 204):
            print(f"   Poll {attempt}/{EXTRACT_POLL_MAX}: not ready yet (HTTP {resp.status_code})")
            time.sleep(EXTRACT_POLL_INTERVAL)
            continue

        if not resp.ok:
            # Non-auth failures during polling might be transient
            print(f"   Poll {attempt}: HTTP {resp.status_code}, retrying...")
            time.sleep(EXTRACT_POLL_INTERVAL)
            continue

        # Check if this looks like a real data file vs. a "not ready" JSON message
        if "json" in content_type and content_length < 10_000:
            try:
                data = resp.json()
                msg = str(data).lower()
                if "not ready" in msg or "processing" in msg or "pending" in msg:
                    print(f"   Poll {attempt}/{EXTRACT_POLL_MAX}: still processing...")
                    time.sleep(EXTRACT_POLL_INTERVAL)
                    continue
            except Exception:
                pass

        # We have a real file — download it
        print(f"   File ready! Downloading...")
        return _parse_extract_response(resp)

    print(f"⚠️  Extract not ready after {EXTRACT_POLL_MAX} polls, giving up")
    return None


def _parse_extract_response(resp: requests.Response) -> pd.DataFrame | None:
    """Parse a downloaded extract response (CSV or ZIP) into a DataFrame."""
    total = int(resp.headers.get("content-length", 0))
    buf = io.BytesIO()
    downloaded = 0
    for chunk in resp.iter_content(chunk_size=4 * 1024 * 1024):
        buf.write(chunk)
        downloaded += len(chunk)
        if total:
            print(f"   {downloaded / 1024 / 1024:.0f} / {total / 1024 / 1024:.0f} MB", end="\r")
    print()
    buf.seek(0)

    content_type = resp.headers.get("content-type", "")

    # ZIP file
    if "zip" in content_type or buf.read(4) in (b"PK\x03\x04", b"PK\x05\x06"):
        buf.seek(0)
        return _parse_zip_csv(buf)

    # Plain CSV
    buf.seek(0)
    return _parse_csv(buf)


def _parse_zip_csv(buf: io.BytesIO) -> pd.DataFrame | None:
    """Extract a CSV from a ZIP buffer and parse it."""
    try:
        with zipfile.ZipFile(buf) as zf:
            csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if not csv_names:
                print(f"⚠️  No CSV files in ZIP archive: {zf.namelist()[:10]}")
                return None
            csv_name = csv_names[0]
            info = zf.getinfo(csv_name)
            print(f"   Parsing {csv_name} ({info.file_size / 1024 / 1024:.0f} MB uncompressed)")
            with zf.open(csv_name) as fh:
                return _parse_csv(fh)
    except zipfile.BadZipFile as exc:
        print(f"⚠️  Bad ZIP file: {exc}")
        return None


def _parse_csv(fh) -> pd.DataFrame:
    """Parse a CSV file handle in chunks, normalising columns."""
    chunks = []
    reader = pd.read_csv(
        fh,
        dtype=str,
        chunksize=100_000,
        on_bad_lines="warn",
        encoding_errors="replace",
    )
    for i, chunk in enumerate(reader):
        chunks.append(_normalise_chunk(chunk))
        if (i + 1) % 5 == 0:
            print(f"   Parsed {(i + 1) * 100_000:,} rows...", end="\r")

    print()
    if not chunks:
        print("⚠️  CSV was empty")
        return pd.DataFrame(columns=REQUIRED_COLUMNS)

    df = pd.concat(chunks, ignore_index=True)
    print(f"   {len(df):,} rows loaded")
    return df


# ---------------------------------------------------------------------------
# Strategy 2: Paginated API fallback (slow — 10 records/page)
# ---------------------------------------------------------------------------

def _download_paginated(api_key: str) -> pd.DataFrame:
    """Page through active entities.  Max 10 per page, ceiling of 10k records."""
    max_pages = MAX_PAGINATED_RECORDS // PAGE_SIZE
    print(f"\n📥 Paginated fallback: up to {MAX_PAGINATED_RECORDS:,} records, "
          f"{PAGE_SIZE}/page ({max_pages} pages)...")

    rows: list[dict] = []
    page = 0
    total_records = None

    while page < max_pages:
        resp = requests.get(
            ENTITY_API_URL,
            params={
                "api_key": api_key,
                "registrationStatus": "A",
                "includeSections": "entityRegistration,coreData",
                "page": page,
                "size": PAGE_SIZE,
            },
            timeout=REQUEST_TIMEOUT,
        )
        _check_api_key_response(resp, f"paginated fetch page {page}")
        resp.raise_for_status()

        data = resp.json()
        if total_records is None:
            total_records = data.get("totalRecords", "?")
            if isinstance(total_records, int):
                print(f"   Total active entities: {total_records:,}")
                if total_records > MAX_PAGINATED_RECORDS:
                    print(f"   ⚠️  Pagination can only fetch {MAX_PAGINATED_RECORDS:,} "
                          f"of {total_records:,} (SAM.gov API limit)")
            else:
                print(f"   Total: {total_records}")

        entities = data.get("entityData", [])
        if not entities:
            break

        for entity in entities:
            rows.append(_flatten_entity(entity))

        page += 1
        if page % 50 == 0:
            print(f"   Fetched {len(rows):,} entities ({page} pages)...", end="\r")

    print(f"\n   {len(rows):,} entities fetched via API")
    return pd.DataFrame(rows, columns=REQUIRED_COLUMNS)


def _flatten_entity(entity: dict) -> dict:
    """Flatten a nested SAM.gov entity JSON object to our column schema."""
    reg = entity.get("entityRegistration", {})
    core = entity.get("coreData", {})
    addr = core.get("physicalAddress", {})
    general = core.get("generalInformation", {})

    # NAICS: may be in several locations depending on API version
    naics_list_raw = core.get("naicsInformation", {}).get("naicsList", [])
    naics_codes = [n.get("naicsCode", "") for n in naics_list_raw if n.get("naicsCode")]

    return {
        "unique_entity_id": reg.get("ueiSAM", ""),
        "legal_business_name": reg.get("legalBusinessName", ""),
        "dba_name": reg.get("dbaName", ""),
        "physical_address_city": addr.get("city", ""),
        "physical_address_state": addr.get("stateOrProvinceCode", ""),
        "cage_code": reg.get("cageCode", ""),
        "primary_naics": general.get("primaryNaics", ""),
        "naics_code_string": ", ".join(naics_codes),
        "duns_number": reg.get("dunsNumber", ""),
    }


# ---------------------------------------------------------------------------
# Column normalisation
# ---------------------------------------------------------------------------

def _normalise_chunk(chunk: pd.DataFrame) -> pd.DataFrame:
    """Rename CSV columns to match REQUIRED_COLUMNS and drop the rest."""
    chunk = chunk.rename(columns={k: v for k, v in CSV_COLUMN_MAP.items() if k in chunk.columns})

    for col in REQUIRED_COLUMNS:
        if col not in chunk.columns:
            chunk[col] = ""

    return chunk[REQUIRED_COLUMNS].fillna("")


# ---------------------------------------------------------------------------
# S3 upload
# ---------------------------------------------------------------------------

def _upload_to_s3(df: pd.DataFrame, bucket: str) -> None:
    """Write DataFrame to parquet in memory and upload to S3."""
    print(f"\n📤 Uploading {len(df):,} rows to s3://{bucket}/{S3_KEY}")

    buf = io.BytesIO()
    df.to_parquet(buf, index=False, engine="pyarrow")
    buf.seek(0)
    size_mb = buf.getbuffer().nbytes / 1024 / 1024

    s3 = boto3.client("s3")
    s3.put_object(
        Bucket=bucket,
        Key=S3_KEY,
        Body=buf,
        ContentType="application/octet-stream",
        Metadata={
            "source": "api.sam.gov",
            "row_count": str(len(df)),
            "downloaded_at": datetime.now(UTC).isoformat(),
        },
    )
    print(f"✅ Uploaded: {size_mb:.1f} MB, {len(df):,} entities")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Download SAM.gov entities to S3")
    parser.add_argument(
        "--s3-bucket",
        default=os.environ.get("S3_BUCKET", "sbir-etl-prod-data"),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Download and parse only — skip S3 upload",
    )
    args = parser.parse_args()

    # --- API key validation ---
    api_key = os.environ.get("SAM_GOV_API_KEY", "")
    if not api_key:
        print(
            "❌ SAM_GOV_API_KEY not set.\n"
            "   Set it in GitHub Secrets or export it locally.\n"
            "   Obtain a key from https://sam.gov → Account → API Keys.",
            file=sys.stderr,
        )
        sys.exit(2)

    if not api_key.startswith("SAM-"):
        print(
            f"⚠️  Key '{api_key[:12]}...' doesn't look like a SAM.gov key.\n"
            "   Expected format: SAM-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
            file=sys.stderr,
        )

    try:
        _validate_api_key(api_key)

        # Strategy 1: CSV extract (up to 1M records)
        df = _download_extract(api_key)

        # Strategy 2: paginated fallback (up to 10k records)
        if df is None or df.empty:
            print("⚠️  Extract unavailable, falling back to paginated API")
            df = _download_paginated(api_key)

        if df.empty:
            print("❌ No entity data retrieved from any source", file=sys.stderr)
            sys.exit(1)

        print(f"\n📊 Final dataset: {len(df):,} entities, {len(df.columns)} columns")
        print(f"   Columns: {list(df.columns)}")
        non_empty = {c: int((df[c] != "").sum()) for c in df.columns}
        print(f"   Non-empty: {non_empty}")

        if args.dry_run:
            print("\n🔵 Dry run — skipping S3 upload")
        else:
            _upload_to_s3(df, args.s3_bucket)

    except APIKeyError as exc:
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"❌ SAM.GOV API KEY PROBLEM", file=sys.stderr)
        print(f"{'='*60}", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        print(f"{'='*60}", file=sys.stderr)
        sys.exit(2)

    except Exception as exc:
        print(f"\n❌ Error: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
