"""Download SAM.gov entity data to a local directory as parquet.

Epistemic tier: pipelines.

A short paginated fallback is written under a separate name so it never
overwrites a full dataset.

Download strategy (in order):
  1. Public Data Services catalog — keyless download of the latest full
     monthly Public V2 entity ZIP.
  2. Entity API extract mode (format=csv) — async bulk download, up to 1M records.
  3. Paginated API fallback — 10 records/page, capped at 10k records.

Exit codes:
    0  Success
    1  General failure (network, parse error)
    2  API key problem — expired, invalid, or missing. CI should treat
       exit code 2 as "rotate the key" rather than a transient failure.
    3  Daily rate limit exceeded — retry after midnight UTC.

API key lifecycle (only needed for strategies 2 and 3):
    SAM.gov keys expire every ~60 days. Rotating the key:
      1. Log in at https://sam.gov → Account → API Keys
      2. Generate a new key
      3. Update SAM_GOV_API_KEY in the deployment host's .env.server file.

Usage:
    python scripts/data/download_sam_gov.py
    python scripts/data/download_sam_gov.py --dest /Volumes/SSDmini/sbir-analytics/data/raw/sam_gov
    python scripts/data/download_sam_gov.py --dry-run

Environment:
    SAM_GOV_API_KEY  Optional SAM.gov API key for strategies 2 and 3
    SAM_GOV_RAW_DIR  Local output directory (overridden by --dest)
"""

import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
import time
import zipfile
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from tempfile import TemporaryFile
from typing import BinaryIO
from urllib.parse import quote

import pandas as pd

# Standalone script — uses requests (installed ad-hoc in CI) rather than httpx
import requests

# Force unbuffered output so CI logs stream in real time.
print = partial(print, flush=True)  # noqa: A001

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PUBLIC_FILE_CATALOG_URL = "https://sam.gov/api/prod/fileextractservices/v1/api/listfiles"
PUBLIC_FILE_DOWNLOAD_BASE = "https://sam.gov/api/prod/fileextractservices/v1/api/download"
PUBLIC_FILE_DOMAIN = "Entity Registration/Public V2"
PUBLIC_FILE_PATTERN = re.compile(r"^SAM_PUBLIC_UTF-8_MONTHLY_V2_(\d{8})\.ZIP$")
ENTITY_API_URL = "https://api.sam.gov/entity-information/v3/entities"
DEFAULT_DEST = "data/raw/sam_gov"
PARQUET_NAME = "sam_entity_records.parquet"
PARQUET_NAME_PARTIAL = "sam_entity_records_partial.parquet"
META_NAME = "sam_entity_records.meta.json"
REQUEST_TIMEOUT = 120
DOWNLOAD_TIMEOUT = 1800  # 30 min for large ZIP downloads
EPISTEMIC_TIER = "pipelines"

# Extract polling (strategy 2)
EXTRACT_POLL_INTERVAL = 30
EXTRACT_POLL_MAX = 40

# Paginated fallback (strategy 3)
PAGE_SIZE = 10
MAX_PAGINATED_RECORDS = 10_000

# Columns the downstream pipeline reads (SAMGovExtractor.ENRICHMENT_COLUMNS).
REQUIRED_COLUMNS = [
    "unique_entity_id",
    "registration_status",
    "legal_business_name",
    "dba_name",
    "physical_address_line_1",
    "physical_address_line_2",
    "physical_address_city",
    "physical_address_state",
    "physical_address_zip_postal_code",
    "cage_code",
    "primary_naics",
    "naics_code_string",
    "duns_number",
]

# GSA's Public V2 layout is positional and contains 142 pipe-delimited fields.
# The monthly file has BOF/EOF control records rather than a header row. These
# zero-based positions are pinned to the official Public V2 extract layout:
# https://open.gsa.gov/api/sam-entity-extracts-api/v1/
# SAM_Entity_Management_Public_V2_Extract_Layout.pdf
PUBLIC_V2_FIELD_COUNT = 142
PUBLIC_V2_POSITION_MAP = {
    0: "unique_entity_id",
    1: "duns_number",
    3: "cage_code",
    5: "registration_status",
    11: "legal_business_name",
    12: "dba_name",
    15: "physical_address_line_1",
    16: "physical_address_line_2",
    17: "physical_address_city",
    18: "physical_address_state",
    19: "physical_address_zip_postal_code",
    32: "primary_naics",
    34: "naics_code_string",
    141: "end_of_record",
}
PUBLIC_V2_COLUMNS = tuple(
    PUBLIC_V2_POSITION_MAP.get(position, f"public_v2_field_{position + 1}")
    for position in range(PUBLIC_V2_FIELD_COUNT)
)
PUBLIC_V2_CONTROL_PATTERN = re.compile(
    r"^(?P<marker>BOF|EOF) PUBLIC(?: V2)? "
    r"(?P<first_date>\d{8}) (?P<file_date>\d{8}) "
    r"(?P<row_count>\d{7}) (?P<sequence>\d{7})$"
)

# SAM.gov CSV/DAT field names → our column names.
# The bulk extract .dat files use UPPER SNAKE or space-separated headers.
CSV_COLUMN_MAP = {
    # Bulk extract .dat headers
    "UNIQUE_ENTITY_ID": "unique_entity_id",
    "UNIQUE ENTITY ID": "unique_entity_id",
    "UEI": "unique_entity_id",
    "UEI SAM": "unique_entity_id",
    "ENTITY UEI": "unique_entity_id",
    "SAM EXTRACT CODE": "registration_status",
    "REGISTRATION STATUS": "registration_status",
    "LEGAL_BUSINESS_NAME": "legal_business_name",
    "LEGAL BUSINESS NAME": "legal_business_name",
    "DBA_NAME": "dba_name",
    "DBA NAME": "dba_name",
    "PHYSICAL_ADDRESS_LINE_1": "physical_address_line_1",
    "PHYSICAL ADDRESS LINE 1": "physical_address_line_1",
    "PHYSICAL ADDRESS LINE 1 TEXT": "physical_address_line_1",
    "PHYSICAL_ADDRESS_LINE_2": "physical_address_line_2",
    "PHYSICAL ADDRESS LINE 2": "physical_address_line_2",
    "PHYSICAL ADDRESS LINE 2 TEXT": "physical_address_line_2",
    "PHYSICAL_ADDRESS_CITY": "physical_address_city",
    "PHYSICAL ADDRESS CITY": "physical_address_city",
    "PHYSICAL_ADDRESS_STATE": "physical_address_state",
    "PHYSICAL ADDRESS STATE OR PROVINCE": "physical_address_state",
    "PHYSICAL ADDRESS PROVINCE OR STATE": "physical_address_state",
    "SAM ADDRESS STATE": "physical_address_state",
    "PHYSICAL_ADDRESS_ZIP_POSTAL_CODE": "physical_address_zip_postal_code",
    "PHYSICAL ADDRESS ZIP POSTAL CODE": "physical_address_zip_postal_code",
    "PHYSICAL ADDRESS ZIP/POSTAL CODE": "physical_address_zip_postal_code",
    "PHYSICAL ADDRESS ZIP CODE": "physical_address_zip_postal_code",
    "ZIP CODE": "physical_address_zip_postal_code",
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
    "registrationStatus": "registration_status",
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
            "  3. Update SAM_GOV_API_KEY in the deployment host's .env.server file."
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
# Strategy 1: keyless public bulk extract
# ---------------------------------------------------------------------------


def _latest_public_extract(items: list[dict]) -> dict:
    """Select the newest UTF-8 monthly Public V2 record from the official catalog."""

    candidates = [
        (match.group(1), item)
        for item in items
        if isinstance(item, dict)
        and (match := PUBLIC_FILE_PATTERN.fullmatch(str(item.get("displayKey", ""))))
    ]
    if not candidates:
        raise ValueError("SAM.gov public catalog has no UTF-8 monthly Public V2 extract")
    return max(candidates, key=lambda candidate: candidate[0])[1]


def _public_extract_download_url(item: dict) -> str:
    """Build the keyless SAM.gov download URL after validating the catalog record."""

    display_key = str(item.get("displayKey", ""))
    if not PUBLIC_FILE_PATTERN.fullmatch(display_key):
        raise ValueError("SAM.gov public catalog record has an invalid extract filename")
    expected_key = f"{PUBLIC_FILE_DOMAIN}/{display_key}"
    if item.get("key") != expected_key:
        raise ValueError("SAM.gov public catalog record has an unexpected object key")
    encoded_key = quote(expected_key, safe="/")
    return f"{PUBLIC_FILE_DOWNLOAD_BASE}/{encoded_key}?privacy=Public"


def _download_bulk_extract() -> pd.DataFrame | None:
    """Download the latest monthly public entity ZIP without an API key."""

    print("\n📦 Strategy 1: Bulk extract download...")
    print("   Reading the public SAM.gov Data Services catalog...")

    catalog_response = requests.get(
        PUBLIC_FILE_CATALOG_URL,
        params={
            "domain": PUBLIC_FILE_DOMAIN,
            "privacy": "Public",
        },
        timeout=REQUEST_TIMEOUT,
    )
    if not catalog_response.ok:
        print(f"⚠️  Public catalog request failed: HTTP {catalog_response.status_code}")
        return None

    try:
        items = catalog_response.json()["_embedded"]["customS3ObjectSummaryList"]
        item = _latest_public_extract(items)
        download_url = _public_extract_download_url(item)
    except (KeyError, TypeError, ValueError) as exc:
        print(f"⚠️  Public catalog response is unusable: {exc}")
        return None

    print(f"   Selected: {item['displayKey']}")
    resp = requests.get(download_url, timeout=DOWNLOAD_TIMEOUT, stream=True)
    if not resp.ok:
        print(f"⚠️  Public bulk download failed: HTTP {resp.status_code}")
        return None

    content_type = resp.headers.get("content-type", "").lower()
    content_length = int(resp.headers.get("content-length", 0))
    print(
        (
            f"   Downloading... (content-type: {content_type}, "
            f"size: {content_length / 1024 / 1024:.0f} MB)"
        )
        if content_length
        else f"   Downloading... (content-type: {content_type}, size: unknown)"
    )

    # A seekable temporary file avoids holding both the compressed ZIP and the
    # parsed entity frame in memory at the same time.
    with TemporaryFile() as buffer:
        downloaded = 0
        digest = hashlib.sha256()
        for chunk in resp.iter_content(chunk_size=4 * 1024 * 1024):
            buffer.write(chunk)
            digest.update(chunk)
            downloaded += len(chunk)
            if content_length:
                print(
                    f"   {downloaded / 1024 / 1024:.0f} / {content_length / 1024 / 1024:.0f} MB",
                    end="\r",
                )
            elif downloaded % (20 * 1024 * 1024) == 0:
                print(f"   {downloaded / 1024 / 1024:.0f} MB...", end="\r")
        print(f"\n   Downloaded {downloaded / 1024 / 1024:.1f} MB total")
        if content_length and downloaded != content_length:
            print("⚠️  Public bulk download length does not match Content-Length")
            return None
        buffer.seek(0)
        if buffer.read(2) != b"PK":
            print("⚠️  Public bulk download is not a ZIP archive")
            return None
        buffer.seek(0)
        frame = _parse_downloaded_file(buffer)
        if frame is not None:
            frame.attrs.update(
                {
                    "sam_source_file": item["displayKey"],
                    "sam_source_date": item.get("dateModified"),
                    "sam_source_sha256": digest.hexdigest(),
                    "sam_source_url": download_url,
                }
            )
        return frame


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
                download_url = (
                    data.get("downloadUrl")
                    or data.get("downloadLink")
                    or data.get("fileUrl")
                    or data.get("url")
                )
        except Exception:
            pass

    # Try regex in raw text
    if not download_url:
        urls = re.findall(r'https?://[^\s"<>]+REPLACE_WITH_API_KEY[^\s"<>]*', text)
        if urls:
            download_url = urls[0].replace("REPLACE_WITH_API_KEY", api_key)

    if not download_url:
        print("⚠️  No download URL found in response")
        print(f"   Content-Type: {resp.headers.get('content-type', 'unknown')}")
        print(f"   Preview: {text[:300]}")
        return None

    print("   Got download URL, polling for file readiness...")

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
        print("   File ready!")
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
        params: dict[str, str | int] = {
            "api_key": api_key,
            "registrationStatus": "A",
            "includeSections": "entityRegistration,coreData",
            "page": page,
            "size": PAGE_SIZE,
        }
        resp = requests.get(
            ENTITY_API_URL,
            params=params,
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
                    print(
                        f"   ⚠️  Can only fetch {MAX_PAGINATED_RECORDS:,} of "
                        f"{total_records:,} via pagination"
                    )

        entities = data.get("entityData", [])
        if not entities:
            break

        for entity in entities:
            reg = entity.get("entityRegistration", {})
            core = entity.get("coreData", {})
            addr = core.get("physicalAddress", {})
            general = core.get("generalInformation", {})
            naics_list = [
                n.get("naicsCode", "")
                for n in core.get("naicsInformation", {}).get("naicsList", [])
            ]
            rows.append(
                {
                    "unique_entity_id": reg.get("ueiSAM", ""),
                    "registration_status": reg.get("registrationStatus", ""),
                    "legal_business_name": reg.get("legalBusinessName", ""),
                    "dba_name": reg.get("dbaName", ""),
                    "physical_address_line_1": addr.get("addressLine1", ""),
                    "physical_address_line_2": addr.get("addressLine2", ""),
                    "physical_address_city": addr.get("city", ""),
                    "physical_address_state": addr.get("stateOrProvinceCode", ""),
                    "physical_address_zip_postal_code": addr.get("zipCode", ""),
                    "cage_code": reg.get("cageCode", ""),
                    "primary_naics": general.get("primaryNaics", ""),
                    "naics_code_string": ", ".join(filter(None, naics_list)),
                    "duns_number": reg.get("dunsNumber", ""),
                }
            )

        page += 1
        if page % 50 == 0:
            print(f"   {len(rows):,} entities ({page} pages)...", end="\r")

    print(f"\n   {len(rows):,} entities fetched")
    return pd.DataFrame(rows, columns=REQUIRED_COLUMNS)


# ---------------------------------------------------------------------------
# File parsing
# ---------------------------------------------------------------------------


def _parse_downloaded_file(buf: BinaryIO) -> pd.DataFrame | None:
    """Parse a downloaded file (ZIP or CSV/DAT) into a DataFrame."""
    header = buf.read(4)
    buf.seek(0)

    if header[:2] == b"PK":
        return _parse_zip(buf)
    else:
        print("   File appears to be plain CSV/DAT")
        return _parse_csv(buf)


def _parse_zip(buf: BinaryIO) -> pd.DataFrame | None:
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
            print(f"   Parsing {target} ({info.file_size / 1024 / 1024:.0f} MB uncompressed)")
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
    if sample.startswith(b"BOF PUBLIC"):
        return _parse_public_v2(fh)

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
            print(f"   Source columns ({len(chunk.columns)}): {list(chunk.columns)[:15]}...")
            mapped = [c for c in normalised.columns if (normalised[c] != "").any()]
            print(f"   Mapped non-empty: {mapped}")

    print()
    if not chunks:
        print("⚠️  File was empty")
        return pd.DataFrame(columns=REQUIRED_COLUMNS)

    df = pd.concat(chunks, ignore_index=True)
    print(f"   {len(df):,} rows loaded")
    return df


def _parse_public_v2(fh) -> pd.DataFrame:
    """Parse and validate a headerless SAM Public V2 monthly extract."""

    header = fh.readline().decode("utf-8-sig").rstrip("\r\n")
    header_match = PUBLIC_V2_CONTROL_PATTERN.fullmatch(header)
    if header_match is None or header_match.group("marker") != "BOF":
        raise ValueError("SAM Public V2 extract has an invalid BOF control record")

    expected_rows = int(header_match.group("row_count"))
    expected_trailer = f"EOF{header[3:]}"
    chunks = []
    trailer_records: list[str] = []

    print("   Detected headerless SAM Public V2 positional layout")
    reader = pd.read_csv(
        fh,
        dtype=str,
        delimiter="|",
        header=None,
        names=PUBLIC_V2_COLUMNS,
        usecols=sorted(PUBLIC_V2_POSITION_MAP),
        chunksize=100_000,
        quoting=csv.QUOTE_NONE,
        on_bad_lines="error",
        encoding_errors="strict",
    )
    try:
        for i, chunk in enumerate(reader):
            trailer_mask = chunk["unique_entity_id"].str.startswith("EOF PUBLIC", na=False)
            trailer_records.extend(chunk.loc[trailer_mask, "unique_entity_id"].tolist())
            data = chunk.loc[~trailer_mask]
            if not data["end_of_record"].eq("!end").all():
                raise ValueError("SAM Public V2 extract contains a malformed positional record")
            chunks.append(data.drop(columns="end_of_record")[REQUIRED_COLUMNS].fillna(""))
            if (i + 1) % 5 == 0:
                print(f"   Parsed {(i + 1) * 100_000:,} rows...", end="\r")
    except pd.errors.ParserError as exc:
        raise ValueError("SAM Public V2 extract contains a malformed positional record") from exc

    if trailer_records != [expected_trailer]:
        raise ValueError("SAM Public V2 extract has a missing or mismatched EOF control record")
    if not chunks:
        raise ValueError("SAM Public V2 extract contains no entity records")

    frame = pd.concat(chunks, ignore_index=True)
    if len(frame) != expected_rows:
        raise ValueError(
            "SAM Public V2 entity count does not match its BOF/EOF control records: "
            f"expected {expected_rows:,}, parsed {len(frame):,}"
        )
    _validate_public_v2_identity_fields(frame)
    frame.attrs["sam_expected_row_count"] = expected_rows
    print(f"\n   {len(frame):,} validated Public V2 entity rows loaded")
    return frame


def _validate_public_v2_identity_fields(frame: pd.DataFrame) -> None:
    """Fail closed when positional drift would corrupt the census identity fields."""

    if list(frame.columns) != REQUIRED_COLUMNS:
        raise ValueError("SAM Public V2 parser did not produce the pinned census field set")
    if not frame["unique_entity_id"].str.fullmatch(r"[A-Z0-9]{12}").all():
        raise ValueError("SAM Public V2 extract contains a missing or malformed UEI")
    if not frame["registration_status"].isin({"A", "E"}).all():
        raise ValueError("SAM Public V2 extract contains an invalid registration status")
    if frame["legal_business_name"].eq("").any():
        raise ValueError("SAM Public V2 extract contains a missing legal business name")


def _normalise_chunk(chunk: pd.DataFrame) -> pd.DataFrame:
    """Rename columns and keep only REQUIRED_COLUMNS."""
    chunk = chunk.rename(columns={k: v for k, v in CSV_COLUMN_MAP.items() if k in chunk.columns})
    for col in REQUIRED_COLUMNS:
        if col not in chunk.columns:
            chunk[col] = ""
    return chunk[REQUIRED_COLUMNS].fillna("")


def _is_partial_result(strategy: int | None) -> bool:
    """Only a structurally validated official monthly bulk file is canonical."""

    return strategy != 1


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def _write_local(df: pd.DataFrame, dest: Path, *, name: str = PARQUET_NAME) -> Path:
    """Write DataFrame to parquet under ``dest``, with a metadata sidecar."""
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / name
    print(f"\n💾 Writing {len(df):,} rows to {path}")
    df.to_parquet(path, index=False, engine="pyarrow")

    metadata = {
        "source": "sam.gov public data services",
        "source_file": df.attrs.get("sam_source_file"),
        "source_date": df.attrs.get("sam_source_date"),
        "source_sha256": df.attrs.get("sam_source_sha256"),
        "source_url": df.attrs.get("sam_source_url"),
        "expected_row_count": df.attrs.get("sam_expected_row_count"),
        "row_count": len(df),
        "downloaded_at": datetime.now(UTC).isoformat(),
        "partial": name == PARQUET_NAME_PARTIAL,
    }
    # Sidecar is named after the parquet it describes: a partial write must
    # not replace the canonical dataset's row count and provenance.
    (dest / f"{path.stem}.meta.json").write_text(json.dumps(metadata, indent=2))

    print(f"✅ Wrote: {path.stat().st_size / 1024 / 1024:.1f} MB, {len(df):,} entities")
    return path


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Download SAM.gov entities to a local directory")
    parser.add_argument(
        "--dest",
        default=os.environ.get("SAM_GOV_RAW_DIR", DEFAULT_DEST),
        help=f"Directory to write the parquet into (default: {DEFAULT_DEST})",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Download and parse only — skip writing output"
    )
    parser.add_argument(
        "--strategy",
        type=int,
        choices=[1, 2, 3],
        default=None,
        help="Force a specific download strategy (1=bulk, 2=extract, 3=paginated)",
    )
    args = parser.parse_args()

    api_key = os.environ.get("SAM_GOV_API_KEY", "")
    if args.strategy in (2, 3) and not api_key:
        print(
            f"❌ Strategy {args.strategy} requires SAM_GOV_API_KEY.",
            file=sys.stderr,
        )
        sys.exit(2)
    if api_key and not api_key.startswith("SAM-"):
        print("⚠️  SAM_GOV_API_KEY doesn't look like a SAM.gov key.", file=sys.stderr)

    try:
        df = None
        completed_strategy: int | None = None

        strategies = [args.strategy] if args.strategy else [1, 2, 3]

        for strat in strategies:
            if strat == 1:
                df = _download_bulk_extract()
            elif strat == 2:
                if not api_key:
                    print("   Strategy 2 requires SAM_GOV_API_KEY; skipping")
                    continue
                df = _download_entity_extract(api_key)
            elif strat == 3:
                if not api_key:
                    print("   Strategy 3 requires SAM_GOV_API_KEY; skipping")
                    continue
                df = _download_paginated(api_key)

            if df is not None and not df.empty:
                completed_strategy = strat
                break
            print(f"   Strategy {strat} did not produce data, trying next...")

        if df is None or df.empty:
            print("❌ No entity data retrieved from any strategy", file=sys.stderr)
            sys.exit(1)

        print(f"\n📊 Final: {len(df):,} entities, {len(df.columns)} columns")
        non_empty = {c: int((df[c] != "").sum()) for c in df.columns}
        print(f"   Non-empty counts: {non_empty}")

        if args.dry_run:
            print("\n🔵 Dry run — skipping output")
        else:
            # Authenticated extract and paginated fallbacks are partial by
            # contract, regardless of row count. Only strategy 1 can produce
            # the canonical monthly snapshot.
            partial_result = _is_partial_result(completed_strategy)
            if partial_result:
                print(
                    f"\n⚠️  Strategy {completed_strategy} is a capped fallback. "
                    "Writing as a partial dataset regardless of row count."
                )

            _write_local(
                df,
                Path(args.dest),
                name=PARQUET_NAME_PARTIAL if partial_result else PARQUET_NAME,
            )

    except APIKeyError as exc:
        print(f"\n{'=' * 60}", file=sys.stderr)
        print("❌ SAM.GOV API KEY PROBLEM", file=sys.stderr)
        print(f"{'=' * 60}", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        print(f"{'=' * 60}", file=sys.stderr)
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
