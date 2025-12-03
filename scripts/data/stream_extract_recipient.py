#!/usr/bin/env python3
"""Stream-extract recipient_lookup from USAspending ZIP in S3.

Uses S3 range requests to read only the needed portions of the ZIP file,
avoiding the need to download the full 217GB file.

This works because:
1. ZIP central directory is at the end of the file
2. S3 supports byte-range requests
3. We only need one file from the archive

Usage:
    python stream_extract_recipient.py --s3-bucket sbir-etl-production-data
"""

import argparse
import gzip
import io
import json
import struct
import sys
import tempfile
from datetime import datetime, timezone

import boto3
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# Expected columns for recipient_lookup table
RECIPIENT_LOOKUP_COLUMNS = [
    "id", "recipient_hash", "legal_business_name", "duns", "address_line_1",
    "address_line_2", "business_types_codes", "city", "congressional_district",
    "country_code", "parent_duns", "parent_legal_business_name", "state",
    "parent_uei", "zip5", "alternate_names", "source", "uei", "zip4", "update_date",
]


import requests


class HttpZipReader:
    """Read ZIP files from HTTP using range requests."""

    def __init__(self, url: str):
        self.url = url
        self.session = requests.Session()

        # Get file size
        head = self.session.head(url, allow_redirects=True)
        self.size = int(head.headers["Content-Length"])
        print(f"ZIP file size: {self.size / (1024**3):.2f} GB")

    def read_range(self, start: int, end: int) -> bytes:
        """Read a byte range from HTTP."""
        headers = {"Range": f"bytes={start}-{end-1}"}
        response = self.session.get(self.url, headers=headers)
        return response.content

    def find_central_directory(self) -> tuple[int, int]:
        """Find the ZIP central directory location."""
        eocd_search_size = 65536
        tail = self.read_range(self.size - eocd_search_size, self.size)

        eocd_sig = b"PK\x05\x06"
        eocd_pos = tail.rfind(eocd_sig)
        if eocd_pos == -1:
            raise ValueError("Could not find ZIP End of Central Directory")

        eocd = tail[eocd_pos:eocd_pos + 22]
        cd_size = struct.unpack("<I", eocd[12:16])[0]
        cd_offset = struct.unpack("<I", eocd[16:20])[0]

        if cd_offset == 0xFFFFFFFF:
            zip64_loc_sig = b"PK\x06\x07"
            zip64_loc_pos = tail.rfind(zip64_loc_sig)
            if zip64_loc_pos != -1:
                zip64_eocd_offset = struct.unpack("<Q", tail[zip64_loc_pos + 8:zip64_loc_pos + 16])[0]
                zip64_eocd = self.read_range(zip64_eocd_offset, zip64_eocd_offset + 56)
                cd_size = struct.unpack("<Q", zip64_eocd[40:48])[0]
                cd_offset = struct.unpack("<Q", zip64_eocd[48:56])[0]

        print(f"Central directory at offset {cd_offset}, size {cd_size / (1024**2):.2f} MB")
        return cd_offset, cd_size

    def list_files(self) -> list[dict]:
        """List files in the ZIP archive."""
        cd_offset, cd_size = self.find_central_directory()
        cd_data = self.read_range(cd_offset, cd_offset + cd_size)

        files = []
        pos = 0
        while pos < len(cd_data):
            if cd_data[pos:pos + 4] != b"PK\x01\x02":
                break

            fname_len = struct.unpack("<H", cd_data[pos + 28:pos + 30])[0]
            extra_len = struct.unpack("<H", cd_data[pos + 30:pos + 32])[0]
            comment_len = struct.unpack("<H", cd_data[pos + 32:pos + 34])[0]
            comp_size = struct.unpack("<I", cd_data[pos + 20:pos + 24])[0]
            uncomp_size = struct.unpack("<I", cd_data[pos + 24:pos + 28])[0]
            local_header_offset = struct.unpack("<I", cd_data[pos + 42:pos + 46])[0]

            if comp_size == 0xFFFFFFFF or uncomp_size == 0xFFFFFFFF or local_header_offset == 0xFFFFFFFF:
                extra_data = cd_data[pos + 46 + fname_len:pos + 46 + fname_len + extra_len]
                extra_pos = 0
                while extra_pos < len(extra_data):
                    tag = struct.unpack("<H", extra_data[extra_pos:extra_pos + 2])[0]
                    size = struct.unpack("<H", extra_data[extra_pos + 2:extra_pos + 4])[0]
                    if tag == 0x0001:
                        field_pos = extra_pos + 4
                        if uncomp_size == 0xFFFFFFFF:
                            uncomp_size = struct.unpack("<Q", extra_data[field_pos:field_pos + 8])[0]
                            field_pos += 8
                        if comp_size == 0xFFFFFFFF:
                            comp_size = struct.unpack("<Q", extra_data[field_pos:field_pos + 8])[0]
                            field_pos += 8
                        if local_header_offset == 0xFFFFFFFF:
                            local_header_offset = struct.unpack("<Q", extra_data[field_pos:field_pos + 8])[0]
                        break
                    extra_pos += 4 + size

            filename = cd_data[pos + 46:pos + 46 + fname_len].decode("utf-8", errors="replace")
            files.append({
                "filename": filename,
                "compressed_size": comp_size,
                "uncompressed_size": uncomp_size,
                "local_header_offset": local_header_offset,
            })
            pos += 46 + fname_len + extra_len + comment_len

        return files

    def sample_file(self, file_info: dict, sample_bytes: int = 50000) -> bytes:
        """Read first N bytes of a file for sampling."""
        local_header = self.read_range(
            file_info["local_header_offset"],
            file_info["local_header_offset"] + 30
        )
        fname_len = struct.unpack("<H", local_header[26:28])[0]
        extra_len = struct.unpack("<H", local_header[28:30])[0]
        data_offset = file_info["local_header_offset"] + 30 + fname_len + extra_len
        read_size = min(sample_bytes, file_info["compressed_size"])
        return self.read_range(data_offset, data_offset + read_size)

    def extract_file_to_path(self, file_info: dict, output_path: str) -> None:
        """Extract a single file from the ZIP to disk."""
        local_header = self.read_range(
            file_info["local_header_offset"],
            file_info["local_header_offset"] + 30
        )
        fname_len = struct.unpack("<H", local_header[26:28])[0]
        extra_len = struct.unpack("<H", local_header[28:30])[0]
        data_offset = file_info["local_header_offset"] + 30 + fname_len + extra_len
        total_size = file_info["compressed_size"]

        print(f"Extracting {file_info['filename']} ({total_size / (1024**2):.1f} MB)")

        chunk_size = 50 * 1024 * 1024
        downloaded = 0

        with open(output_path, "wb") as f:
            while downloaded < total_size:
                end = min(downloaded + chunk_size, total_size)
                chunk = self.read_range(data_offset + downloaded, data_offset + end)
                f.write(chunk)
                downloaded = end
                print(f"  Downloaded {downloaded / (1024**2):.0f} / {total_size / (1024**2):.0f} MB ({100*downloaded/total_size:.0f}%)", flush=True)

        print(f"Saved to {output_path}")


class S3ZipReader:
    """Read ZIP files from S3 using range requests."""

    def __init__(self, s3_client, bucket: str, key: str):
        self.s3 = s3_client
        self.bucket = bucket
        self.key = key

        # Get file size
        head = s3_client.head_object(Bucket=bucket, Key=key)
        self.size = head["ContentLength"]
        print(f"ZIP file size: {self.size / (1024**3):.2f} GB")

    def read_range(self, start: int, end: int) -> bytes:
        """Read a byte range from S3."""
        response = self.s3.get_object(
            Bucket=self.bucket,
            Key=self.key,
            Range=f"bytes={start}-{end-1}"
        )
        return response["Body"].read()

    def find_central_directory(self) -> tuple[int, int]:
        """Find the ZIP central directory location."""
        # Read last 64KB to find End of Central Directory
        eocd_search_size = 65536
        tail = self.read_range(self.size - eocd_search_size, self.size)

        # Find EOCD signature (PK\x05\x06)
        eocd_sig = b"PK\x05\x06"
        eocd_pos = tail.rfind(eocd_sig)
        if eocd_pos == -1:
            raise ValueError("Could not find ZIP End of Central Directory")

        # Parse EOCD
        eocd = tail[eocd_pos:eocd_pos + 22]
        cd_size = struct.unpack("<I", eocd[12:16])[0]
        cd_offset = struct.unpack("<I", eocd[16:20])[0]

        # Check for ZIP64
        if cd_offset == 0xFFFFFFFF:
            # Find ZIP64 EOCD locator
            zip64_loc_sig = b"PK\x06\x07"
            zip64_loc_pos = tail.rfind(zip64_loc_sig)
            if zip64_loc_pos != -1:
                zip64_eocd_offset = struct.unpack("<Q", tail[zip64_loc_pos + 8:zip64_loc_pos + 16])[0]
                # Read ZIP64 EOCD
                zip64_eocd = self.read_range(zip64_eocd_offset, zip64_eocd_offset + 56)
                cd_size = struct.unpack("<Q", zip64_eocd[40:48])[0]
                cd_offset = struct.unpack("<Q", zip64_eocd[48:56])[0]

        print(f"Central directory at offset {cd_offset}, size {cd_size / (1024**2):.2f} MB")
        return cd_offset, cd_size

    def list_files(self) -> list[dict]:
        """List files in the ZIP archive."""
        cd_offset, cd_size = self.find_central_directory()
        cd_data = self.read_range(cd_offset, cd_offset + cd_size)

        files = []
        pos = 0
        while pos < len(cd_data):
            if cd_data[pos:pos + 4] != b"PK\x01\x02":
                break

            # Parse central directory file header
            fname_len = struct.unpack("<H", cd_data[pos + 28:pos + 30])[0]
            extra_len = struct.unpack("<H", cd_data[pos + 30:pos + 32])[0]
            comment_len = struct.unpack("<H", cd_data[pos + 32:pos + 34])[0]

            comp_size = struct.unpack("<I", cd_data[pos + 20:pos + 24])[0]
            uncomp_size = struct.unpack("<I", cd_data[pos + 24:pos + 28])[0]
            local_header_offset = struct.unpack("<I", cd_data[pos + 42:pos + 46])[0]

            # Check for ZIP64 extra field
            if comp_size == 0xFFFFFFFF or uncomp_size == 0xFFFFFFFF or local_header_offset == 0xFFFFFFFF:
                extra_data = cd_data[pos + 46 + fname_len:pos + 46 + fname_len + extra_len]
                extra_pos = 0
                while extra_pos < len(extra_data):
                    tag = struct.unpack("<H", extra_data[extra_pos:extra_pos + 2])[0]
                    size = struct.unpack("<H", extra_data[extra_pos + 2:extra_pos + 4])[0]
                    if tag == 0x0001:  # ZIP64
                        field_pos = extra_pos + 4
                        if uncomp_size == 0xFFFFFFFF:
                            uncomp_size = struct.unpack("<Q", extra_data[field_pos:field_pos + 8])[0]
                            field_pos += 8
                        if comp_size == 0xFFFFFFFF:
                            comp_size = struct.unpack("<Q", extra_data[field_pos:field_pos + 8])[0]
                            field_pos += 8
                        if local_header_offset == 0xFFFFFFFF:
                            local_header_offset = struct.unpack("<Q", extra_data[field_pos:field_pos + 8])[0]
                        break
                    extra_pos += 4 + size

            filename = cd_data[pos + 46:pos + 46 + fname_len].decode("utf-8", errors="replace")

            files.append({
                "filename": filename,
                "compressed_size": comp_size,
                "uncompressed_size": uncomp_size,
                "local_header_offset": local_header_offset,
            })

            pos += 46 + fname_len + extra_len + comment_len

        return files

    def extract_file_to_path(self, file_info: dict, output_path: str) -> None:
        """Extract a single file from the ZIP to disk."""
        import zlib

        # Read local file header
        local_header = self.read_range(
            file_info["local_header_offset"],
            file_info["local_header_offset"] + 30
        )

        fname_len = struct.unpack("<H", local_header[26:28])[0]
        extra_len = struct.unpack("<H", local_header[28:30])[0]
        compression = struct.unpack("<H", local_header[8:10])[0]

        data_offset = file_info["local_header_offset"] + 30 + fname_len + extra_len
        total_size = file_info["compressed_size"]

        print(f"Extracting {file_info['filename']} ({total_size / (1024**2):.1f} MB)")

        # Download in chunks directly to file
        chunk_size = 50 * 1024 * 1024  # 50 MB chunks
        downloaded = 0

        with open(output_path, "wb") as f:
            while downloaded < total_size:
                end = min(downloaded + chunk_size, total_size)
                chunk = self.read_range(data_offset + downloaded, data_offset + end)
                f.write(chunk)
                downloaded = end
                print(f"  Downloaded {downloaded / (1024**2):.0f} / {total_size / (1024**2):.0f} MB ({100*downloaded/total_size:.0f}%)", flush=True)

        print(f"Saved to {output_path}")

    def sample_file(self, file_info: dict, sample_bytes: int = 50000) -> bytes:
        """Read first N bytes of a file for sampling."""
        local_header = self.read_range(
            file_info["local_header_offset"],
            file_info["local_header_offset"] + 30
        )
        fname_len = struct.unpack("<H", local_header[26:28])[0]
        extra_len = struct.unpack("<H", local_header[28:30])[0]
        data_offset = file_info["local_header_offset"] + 30 + fname_len + extra_len

        read_size = min(sample_bytes, file_info["compressed_size"])
        return self.read_range(data_offset, data_offset + read_size)


def find_recipient_lookup_file(reader: S3ZipReader, files: list[dict]) -> dict | None:
    """Auto-detect the recipient_lookup file by sampling candidates.

    Looks for files with:
    - Size between 100MB and 3GB (recipient_lookup is ~1.2GB)
    - ~20 tab-separated columns
    - Column 1 is a UUID (recipient_hash)
    - Column 2 looks like a business name
    """
    print("Auto-detecting recipient_lookup file...")

    # Filter candidates by size (100MB - 3GB uncompressed)
    candidates = [
        f for f in files
        if f["filename"].endswith(".dat.gz")
        and 100 * 1024**2 < f["uncompressed_size"] < 3 * 1024**3
    ]
    print(f"  Checking {len(candidates)} candidate files...")

    for f in sorted(candidates, key=lambda x: x["uncompressed_size"]):
        try:
            sample = reader.sample_file(f)
            # Use GzipFile for streaming (works with partial data)
            gz = gzip.GzipFile(fileobj=io.BytesIO(sample))
            decompressed = gz.read(5000)
            first_line = decompressed.decode("utf-8", errors="replace").split("\n")[0]
            cols = first_line.split("\t")

            # Check for recipient_lookup pattern:
            # - ~20 columns
            # - Column 1 is UUID (36 chars, 4 dashes)
            # - Column 2 is a name (has letters)
            if 18 <= len(cols) <= 22:
                col1 = cols[1] if len(cols) > 1 else ""
                col2 = cols[2] if len(cols) > 2 else ""
                if len(col1) == 36 and col1.count("-") == 4 and any(c.isalpha() for c in col2):
                    print(f"  Found: {f['filename']} ({f['uncompressed_size']/(1024**2):.0f} MB, {len(cols)} cols)")
                    return f
        except Exception:
            continue

    return None


def find_latest_dump(s3_client, bucket: str) -> str | None:
    """Find the latest USAspending dump in S3."""
    prefix = "raw/usaspending/database/"
    response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
    if "Contents" not in response:
        return None
    dumps = [o for o in response["Contents"] if o["Key"].endswith(".zip") and "subset" not in o["Key"]]
    if not dumps:
        return None
    return max(dumps, key=lambda x: x["Size"])["Key"]


def find_latest_usaspending_url() -> str | None:
    """Find the latest USAspending dump URL."""
    # USAspending publishes dumps with date in filename
    # Try recent dates
    from datetime import datetime, timedelta
    base_url = "https://files.usaspending.gov/database_download"

    for days_ago in range(0, 30):
        date = datetime.now() - timedelta(days=days_ago)
        filename = f"usaspending-db_{date.strftime('%Y%m%d')}.zip"
        url = f"{base_url}/{filename}"
        try:
            resp = requests.head(url, timeout=5)
            if resp.status_code == 200:
                return url
        except Exception:
            continue
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Extract recipient_lookup from USAspending database dump"
    )
    parser.add_argument("--url", help="Direct URL to USAspending ZIP (skips S3)")
    parser.add_argument("--s3-bucket", help="S3 bucket containing ZIP")
    parser.add_argument("--source-key", help="S3 key for ZIP file")
    parser.add_argument("--output-prefix", default="raw/usaspending/recipient_lookup")
    parser.add_argument("--list-only", action="store_true", help="Just list files in ZIP")
    args = parser.parse_args()

    # Determine source: URL or S3
    if args.url:
        print(f"Source: {args.url}")
        reader = HttpZipReader(args.url)
        s3 = boto3.client("s3") if args.s3_bucket else None
    elif args.s3_bucket:
        s3 = boto3.client("s3")
        source_key = args.source_key or find_latest_dump(s3, args.s3_bucket)
        if not source_key:
            print("ERROR: No USAspending dump found in S3")
            sys.exit(1)
        print(f"Source: s3://{args.s3_bucket}/{source_key}")
        reader = S3ZipReader(s3, args.s3_bucket, source_key)
    else:
        # Try to find latest from USAspending directly
        url = find_latest_usaspending_url()
        if url:
            print(f"Source: {url}")
            reader = HttpZipReader(url)
            s3 = None
        else:
            print("ERROR: Provide --url or --s3-bucket")
            sys.exit(1)

    # List files
    print("\nScanning ZIP contents...")
    files = reader.list_files()
    print(f"Found {len(files)} files in archive")

    if args.list_only:
        print("\n=== All files ===")
        for f in sorted(files, key=lambda x: -x["uncompressed_size"])[:20]:
            print(f"  {f['filename']}: {f['uncompressed_size'] / (1024**2):.1f} MB")
        if len(files) > 20:
            print(f"  ... and {len(files) - 20} more")
        return

    # Auto-detect recipient_lookup file
    target_file = find_recipient_lookup_file(reader, files)

    if not target_file:
        print("ERROR: Could not auto-detect recipient_lookup file")
        sys.exit(1)

    print(f"\nTarget: {target_file['filename']}")
    print(f"  Compressed: {target_file['compressed_size'] / (1024**2):.1f} MB")
    print(f"  Uncompressed: {target_file['uncompressed_size'] / (1024**2):.1f} MB")

    # Extract to temp file to avoid memory issues
    with tempfile.TemporaryDirectory() as tmpdir:
        gz_path = f"{tmpdir}/recipient_lookup.dat.gz"

        print("\nExtracting...")
        reader.extract_file_to_path(target_file, gz_path)

        # Parse directly from gzip file (streaming)
        print("\nParsing CSV from gzip...")
        with gzip.open(gz_path, "rt", encoding="utf-8", errors="replace") as f:
            df = pd.read_csv(
                f,
                sep="\t",
                header=None,
                names=RECIPIENT_LOOKUP_COLUMNS,
                na_values=["\\N", ""],
                low_memory=False,
                dtype=str,
            )
        print(f"Loaded {len(df):,} records")

        # Save output
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        if s3 and args.s3_bucket:
            # Upload to S3
            parquet_key = f"{args.output_prefix}/{today}/recipient_lookup.parquet"
            print(f"\nUploading to s3://{args.s3_bucket}/{parquet_key}")
            table = pa.Table.from_pandas(df)
            buffer = io.BytesIO()
            pq.write_table(table, buffer, compression="snappy")
            buffer.seek(0)
            s3.upload_fileobj(buffer, args.s3_bucket, parquet_key)
            print(f"Uploaded {buffer.tell() / (1024**2):.1f} MB")

            # Save metadata
            metadata = {
                "source": args.url or f"s3://{args.s3_bucket}/{source_key}",
                "extracted_at": datetime.now(timezone.utc).isoformat(),
                "row_count": len(df),
                "parquet_key": parquet_key,
            }
            meta_key = f"{args.output_prefix}/{today}/recipient_lookup_metadata.json"
            s3.put_object(Bucket=args.s3_bucket, Key=meta_key, Body=json.dumps(metadata, indent=2))
            print(f"\nSUCCESS: Extracted {len(df):,} recipients to S3")
        else:
            # Save locally
            local_path = f"recipient_lookup_{today}.parquet"
            print(f"\nSaving to {local_path}")
            table = pa.Table.from_pandas(df)
            pq.write_table(table, local_path, compression="snappy")
            print(f"\nSUCCESS: Extracted {len(df):,} recipients to {local_path}")


if __name__ == "__main__":
    main()
