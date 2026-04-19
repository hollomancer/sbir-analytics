#!/usr/bin/env python3
"""Download SAM.gov entity data to S3 as parquet.

Download strategy (in order):
  1. Bulk extract API (/data-services/v1/extracts) — single ZIP download of
     the full monthly entity file.  One API call, no polling.
  2. Entity API extract mode (format=csv) — async bulk download, up to 1M records.
  3. Paginated API fallback — 10 records/page, capped at 10k records.

Exit codes:
    0  Success
    1  General failure (network, S3, parse error)
    2  API key problem — expired, invalid, or missing. CI should treat
       exit code 2 as "rotate the key" rather than a transient failure.
    3  Daily rate limit exceeded — retry after midnight UTC.

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
# Standalone script — uses requests (installed ad-hoc in CI) rather than httpx
import requests

# Force unbuffered output so CI logs stream in real time.
print = partial(print, flush=True)  # noqa: A001

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXTRACTS_URL = "https://api.sam.gov/data-services/v1/extracts"
ENTITY_API_URL = "https://api.sam.gov/entity-information/v3/entities"
S3_KEY = "raw/sam_gov/sam_entity_records.parquet"
S3_KEY_PARTIAL = "raw/sam_gov/sam_entity_records_partial.parquet"
MIN_CANONICAL_ROW_COUNT = 50_000
REQUEST_TIMEOUT = 120
DOWNLOAD_TIMEOUT = 1800  # 30 min for large ZIP downloads

# Extract polling (strategy 2)
EXTRACT_POLL_INTERVAL = 30
EXTRACT_POLL_MAX = 40

# Paginated fallback (strategy 3)
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

# SAM.gov CSV/DAT field names → our column names.
# The bulk extract .dat files use UPPER SNAKE or space-separated headers.
CSV_COLUMN_MAP = {
    # Bulk extract .dat headers
    "UNIQUE_ENTITY_ID": "unique_entity_id",
    "UEI": "unique_entity_id",
    "UEI SAM": "unique_entity_id",
    "ENTITY UEI": "unique_entity_id",
    "LEGAL_BUSINESS_NAME": "legal_business_name",
    "LEGAL BUSINESS NAME": "legal_business_name",
    "DBA_NAME": "dba_name",
    "DBA NAME": "dba_name",
    "PHYSICAL_ADDRESS_CITY": "physical_address_city",
    "PHYSICAL ADDRESS CITY": "physical_address_city",
    "PHYSICAL_ADDRESS_STATE": "physical_address_state",
    "PHYSICAL ADDRESS STATE OR PROVINCE": "physical_address_state",
    "PHYSICAL ADDRESS PROVINCE OR STATE": "physical_address_state",
    "SAM ADDRESS STATE": "physical_address_state",
    "CAGE_CODE": "cage_code",
    "CAGE CODE": "cage_code",
    "PRIMARY_NAICS": "primary_naics",
    "PRIMARY NAICS": "primary_naics",
    "NAICS_CODE_STRING": "naics_code_string",
    "NAICS CODE STRING": "naics_code_string",
    "DUNS_NUMBER": "duns_number",
    "DUNS": "duns_number",
    # JSON API field names (camelCase) — used by strategy 2 & 3
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
    """Raise APIKeyError with a clear remediation message on auth/quota failures."""
    if resp.status_code not in (401, 403, 429):
        return

    try:
        body = resp.json()
    except Exception:
        body = {"raw": resp.text[:500]}

    message = " ".join(str(v) for v in body.values()).lower()

    if resp.status_code == 429 or any(kw in message for kw in ("throttle", "quota", "exceeded")):
        try:
            next_access = resp.json().get("nextAccessTime", "midnight UTC")
        except Exception:
            next_access = "midnight UTC"
        raise APIKeyError(
            f"SAM.gov DAILY RATE LIMIT exceeded during: {context}\n"
            f"  Retry after: {next_access}\n"
            "  Non-federal personal keys: 10 requests/day.\n"
            "  Non-federal system keys: 1,000 requests/day.\n"
            "  Consider requesting a system key at https://sam.gov."
        )
    elif any(kw in message for kw in ("expired", "expir")):
        raise APIKeyError(
            f"SAM.gov API key EXPIRED during: {context}\n"
            "  1. Log in at https://sam.gov → Account → API Keys\n"
            "  2. Generate a new key\n"
            "  3. Update the GitHub secret:\n"
            "     gh secret set SAM_GOV_API_KEY --body 'SAM-xxxx' --repo hollomancer/sbir-analytics"
        )
    elif any(kw in message for kw in ("invalid", "not found", "unrecognized")):
        raise APIKeyError(
            f"SAM.gov API key INVALID during: {context}\n"
            "  Verify the key at https://sam.gov → Account → API Keys.\n"
            "  Expected format: SAM-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
        )
    else:
        raise APIKeyError(
            f"SAM.gov auth failure during: {context}\n"
            f"  HTTP {resp.status_code}: {resp.reason}\n"
            f"  Body: {body}\n"
            "  Check your key at https://sam.gov → Account → API Keys."
        )


# ---------------------------------------------------------------------------
# Strategy 1: Bulk extract download (fast — single ZIP, one API call)
# ---------------------------------------------------------------------------

def _download_bulk_extract(api_key: str) -> pd.DataFrame | None:
    """Download the latest monthly public entity extract ZIP from SAM.gov.

    Uses /data-services/v1/extracts — a single GET returns the full ZIP file.
    This is the most efficient path: one API call, no polling.
    """
    print("\n📦 Strategy 1: Bulk extract download...")
    print("   Requesting latest monthly public entity extract...")

    resp = requests.get(
        EXTRACTS_URL,
        params={
            "api_key": api_key,
            "fileType": "ENTITY",
            "sensitivity": "PUBLIC",
            "frequency": "MONTHLY",
        },
        timeout=DOWNLOAD_TIMEOUT,
        stream=True,
    )
    _check_api_key_response(resp, "data-services/v1/extracts (bulk download)")

    if not resp.ok:
        print(f"⚠️  Bulk extract request failed: HTTP {resp.status_code}")
        print(f"   Body preview: {resp.text[:300]}")
        return None

    content_type = resp.headers.get("content-type", "").lower()
    content_length = int(resp.headers.get("content-length", 0))

    # If we got JSON back instead of a file, this endpoint might not support
    # direct downloads — fall through to strategy 2.
    if "json" in content_type and content_length < 100_000:
        print(f"⚠️  Got JSON instead of file (content-type: {content_type})")
        try:
            data = resp.json()
            print(f"   Response keys: {list(data.keys())[:10]}")
            print(f"   Preview: {str(data)[:300]}")
        except Exception:
            print(f"   Preview: {resp.text[:300]}")
        return None

    # Stream the file to memory
    print(f"   Downloading... (content-type: {content_type}, "
          f"size: {content_length / 1024 / 1024:.0f} MB)" if content_length
          else f"   Downloading... (content-type: {content_type}, size: unknown)")

    buf = io.BytesIO()
    downloaded = 0
    for chunk in resp.iter_content(chunk_size=4 * 1024 * 1024):
        buf.write(chunk)
        downloaded += len(chunk)
        if content_length:
            print(f"   {downloaded / 1024 / 1024:.0f} / "
                  f"{content_length / 1024 / 1024:.0f} MB", end="\r")
        elif downloaded % (20 * 1024 * 1024) == 0:
            print(f"   {downloaded / 1024 / 1024:.0f} MB...", end="\r")
    print(f"\n   Downloaded {downloaded / 1024 / 1024:.1f} MB total")

    buf.seek(0)
    return _parse_downloaded_file(buf)


# ---------------------------------------------------------------------------
# Strategy 2: Entity API extract mode (format=csv)
# ---------------------------------------------------------------------------

def _download_entity_extract(api_key: str) -> pd.DataFrame | None:
    """Request a CSV extract via the entity API and poll for completion."""
    print("\n📦 Strategy 2: Entity API extract mode (format=csv)...")

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
    _check_api_key_response(resp, "entity API extract (format=csv)")

    if not resp.ok:
        print(f"⚠️  Extract request failed: HTTP {resp.status_code}")
        print(f"   Body: {resp.text[:300]}")
        return None

    # Find the download URL with REPLACE_WITH_API_KEY token
    text = resp.text.strip()
    download_url = None

    # Try JSON response
    if text.startswith("{"):
        try:
            data = resp.json()
            for v in data.values():
                if isinstance(v, str) and "REPLACE_WITH_API_KEY" in v:
                    download_url = v.replace("REPLACE_WITH_API_KEY", api_key)
                    break
            if not download_url:
                download_url = (data.get("downloadUrl") or data.get("downloadLink")
                                or data.get("fileUrl") or data.get("url"))
        except Exception:
            pass

    # Try regex in raw text
    if not download_url:
        urls = re.findall(r'https?://[^\s"<>]+REPLACE_WITH_API_KEY[^\s"<>]*', text)
        if urls:
            download_url = urls[0].replace("REPLACE_WITH_API_KEY", api_key)

    if not download_url:
        print(f"⚠️  No download URL found in response")
        print(f"   Content-Type: {resp.headers.get('content-type', 'unknown')}")
        print(f"   Preview: {text[:300]}")
        return None

    print(f"   Got download URL, polling for file readiness...")

    # Poll for file
    for attempt in range(1, EXTRACT_POLL_MAX + 1):
        print(f"   Poll {attempt}/{EXTRACT_POLL_MAX}...")
        dl_resp = requests.get(download_url, timeout=DOWNLOAD_TIMEOUT, stream=True)
        _check_api_key_response(dl_resp, f"extract download poll {attempt}")

        if dl_resp.status_code in (202, 204):
            time.sleep(EXTRACT_POLL_INTERVAL)
            continue

        if not dl_resp.ok:
            time.sleep(EXTRACT_POLL_INTERVAL)
            continue

        # Check for "not ready" JSON
        ct = dl_resp.headers.get("content-type", "")
        cl = int(dl_resp.headers.get("content-length", 0))
        if "json" in ct and cl < 10_000:
            try:
                msg = str(dl_resp.json()).lower()
                if any(kw in msg for kw in ("not ready", "processing", "pending")):
                    time.sleep(EXTRACT_POLL_INTERVAL)
                    continue
            except Exception:
                pass

        # Got a real file
        print(f"   File ready!")
        buf = io.BytesIO()
        for chunk in dl_resp.iter_content(chunk_size=4 * 1024 * 1024):
            buf.write(chunk)
        buf.seek(0)
        return _parse_downloaded_file(buf)

    print(f"⚠️  Extract not ready after {EXTRACT_POLL_MAX} polls")
    return None


# ---------------------------------------------------------------------------
# Strategy 3: Paginated API fallback
# ---------------------------------------------------------------------------

def _download_paginated(api_key: str) -> pd.DataFrame:
    """Page through active entities. 10/page, capped at 10k records."""
    max_pages = MAX_PAGINATED_RECORDS // PAGE_SIZE
    print(f"\n📥 Strategy 3: Paginated API ({PAGE_SIZE}/page, max {MAX_PAGINATED_RECORDS:,})...")

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
                    print(f"   ⚠️  Can only fetch {MAX_PAGINATED_RECORDS:,} of "
                          f"{total_records:,} via pagination")

        entities = data.get("entityData", [])
        if not entities:
            break

        for entity in entities:
            reg = entity.get("entityRegistration", {})
            core = entity.get("coreData", {})
            addr = core.get("physicalAddress", {})
            general = core.get("generalInformation", {})
            naics_list = [n.get("naicsCode", "") for n in
                          core.get("naicsInformation", {}).get("naicsList", [])]
            rows.append({
                "unique_entity_id": reg.get("ueiSAM", ""),
                "legal_business_name": reg.get("legalBusinessName", ""),
                "dba_name": reg.get("dbaName", ""),
                "physical_address_city": addr.get("city", ""),
                "physical_address_state": addr.get("stateOrProvinceCode", ""),
                "cage_code": reg.get("cageCode", ""),
                "primary_naics": general.get("primaryNaics", ""),
                "naics_code_string": ", ".join(filter(None, naics_list)),
                "duns_number": reg.get("dunsNumber", ""),
            })

        page += 1
        if page % 50 == 0:
            print(f"   {len(rows):,} entities ({page} pages)...", end="\r")

    print(f"\n   {len(rows):,} entities fetched")
    return pd.DataFrame(rows, columns=REQUIRED_COLUMNS)


# ---------------------------------------------------------------------------
# File parsing
# ---------------------------------------------------------------------------

def _parse_downloaded_file(buf: io.BytesIO) -> pd.DataFrame | None:
    """Parse a downloaded file (ZIP or CSV/DAT) into a DataFrame."""
    header = buf.read(4)
    buf.seek(0)

    if header[:2] == b"PK":
        return _parse_zip(buf)
    else:
        print("   File appears to be plain CSV/DAT")
        return _parse_csv(buf)


def _parse_zip(buf: io.BytesIO) -> pd.DataFrame | None:
    """Extract and parse the first CSV/DAT file from a ZIP."""
    try:
        with zipfile.ZipFile(buf) as zf:
            names = zf.namelist()
            print(f"   ZIP contains {len(names)} file(s): {names[:5]}")

            # Prefer .dat or .csv files
            data_files = [n for n in names if n.lower().endswith((".csv", ".dat"))]
            if not data_files:
                print(f"⚠️  No CSV/DAT files in ZIP: {names[:10]}")
                return None

            target = data_files[0]
            info = zf.getinfo(target)
            print(f"   Parsing {target} "
                  f"({info.file_size / 1024 / 1024:.0f} MB uncompressed)")
            with zf.open(target) as fh:
                return _parse_csv(fh)

    except zipfile.BadZipFile as exc:
        print(f"⚠️  Bad ZIP file: {exc}")
        return None


def _parse_csv(fh) -> pd.DataFrame:
    """Parse a CSV/DAT file handle in chunks, normalising columns."""
    # SAM.gov .dat files use pipe (|) delimiter; CSV uses comma
    sample = fh.read(2048)
    fh.seek(0)
    delimiter = "|" if sample.count(b"|") > sample.count(b",") else ","
    print(f"   Detected delimiter: {'pipe' if delimiter == '|' else 'comma'}")

    chunks = []
    reader = pd.read_csv(
        fh,
        dtype=str,
        delimiter=delimiter,
        chunksize=100_000,
        on_bad_lines="warn",
        encoding_errors="replace",
    )
    for i, chunk in enumerate(reader):
        normalised = _normalise_chunk(chunk)
        chunks.append(normalised)
        if (i + 1) % 5 == 0:
            print(f"   Parsed {(i + 1) * 100_000:,} rows...", end="\r")

        # Log available columns on first chunk for debugging
        if i == 0:
            print(f"   Source columns ({len(chunk.columns)}): "
                  f"{list(chunk.columns)[:15]}...")
            mapped = [c for c in normalised.columns if (normalised[c] != "").any()]
            print(f"   Mapped non-empty: {mapped}")

    print()
    if not chunks:
        print("⚠️  File was empty")
        return pd.DataFrame(columns=REQUIRED_COLUMNS)

    df = pd.concat(chunks, ignore_index=True)
    print(f"   {len(df):,} rows loaded")
    return df


def _normalise_chunk(chunk: pd.DataFrame) -> pd.DataFrame:
    """Rename columns and keep only REQUIRED_COLUMNS."""
    chunk = chunk.rename(columns={k: v for k, v in CSV_COLUMN_MAP.items()
                                  if k in chunk.columns})
    for col in REQUIRED_COLUMNS:
        if col not in chunk.columns:
            chunk[col] = ""
    return chunk[REQUIRED_COLUMNS].fillna("")


# ---------------------------------------------------------------------------
# S3 upload
# ---------------------------------------------------------------------------

def _upload_to_s3(df: pd.DataFrame, bucket: str, *, s3_key: str = S3_KEY) -> None:
    """Write DataFrame to parquet and upload to S3."""
    print(f"\n📤 Uploading {len(df):,} rows to s3://{bucket}/{s3_key}")
    buf = io.BytesIO()
    df.to_parquet(buf, index=False, engine="pyarrow")
    buf.seek(0)
    size_mb = buf.getbuffer().nbytes / 1024 / 1024

    s3 = boto3.client("s3")
    s3.put_object(
        Bucket=bucket,
        Key=s3_key,
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
    parser.add_argument("--s3-bucket",
                        default=os.environ.get("S3_BUCKET", "sbir-etl-prod-data"))
    parser.add_argument("--dry-run", action="store_true",
                        help="Download and parse only — skip S3 upload")
    parser.add_argument("--strategy", type=int, choices=[1, 2, 3], default=None,
                        help="Force a specific download strategy (1=bulk, 2=extract, 3=paginated)")
    args = parser.parse_args()

    api_key = os.environ.get("SAM_GOV_API_KEY", "")
    if not api_key:
        print("❌ SAM_GOV_API_KEY not set.\n"
              "   Obtain a key from https://sam.gov → Account → API Keys.",
              file=sys.stderr)
        sys.exit(2)

    if not api_key.startswith("SAM-"):
        print(f"⚠️  Key '{api_key[:12]}...' doesn't look like a SAM.gov key.",
              file=sys.stderr)

    try:
        df = None

        strategies = (
            [args.strategy] if args.strategy
            else [1, 2, 3]
        )

        for strat in strategies:
            if strat == 1:
                df = _download_bulk_extract(api_key)
            elif strat == 2:
                df = _download_entity_extract(api_key)
            elif strat == 3:
                df = _download_paginated(api_key)

            if df is not None and not df.empty:
                break
            print(f"   Strategy {strat} did not produce data, trying next...")

        if df is None or df.empty:
            print("❌ No entity data retrieved from any strategy", file=sys.stderr)
            sys.exit(1)

        print(f"\n📊 Final: {len(df):,} entities, {len(df.columns)} columns")
        non_empty = {c: int((df[c] != "").sum()) for c in df.columns}
        print(f"   Non-empty counts: {non_empty}")

        if args.dry_run:
            print("\n🔵 Dry run — skipping S3 upload")
        else:
            # If row count is below the minimum threshold, this is likely a
            # partial result from paginated fallback. Upload to a separate key
            # so we don't overwrite the canonical full dataset.
            if len(df) < MIN_CANONICAL_ROW_COUNT:
                print(f"\n⚠️  Only {len(df):,} rows — below {MIN_CANONICAL_ROW_COUNT:,} "
                      f"threshold. Uploading as partial dataset to avoid overwriting "
                      f"canonical data.")
                _upload_to_s3(df, args.s3_bucket, s3_key=S3_KEY_PARTIAL)
            else:
                _upload_to_s3(df, args.s3_bucket)

    except APIKeyError as exc:
        print(f"\n{'='*60}", file=sys.stderr)
        print("❌ SAM.GOV API KEY PROBLEM", file=sys.stderr)
        print(f"{'='*60}", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        print(f"{'='*60}", file=sys.stderr)
        # Distinguish rate limits (exit 3) from expired/invalid keys (exit 2)
        if "RATE LIMIT" in str(exc):
            sys.exit(3)
        sys.exit(2)

    except Exception as exc:
        print(f"\n❌ Error: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
