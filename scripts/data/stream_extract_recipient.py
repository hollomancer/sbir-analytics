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
import io
import json
import struct
import sys
from datetime import datetime, timezone

import boto3
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

RECIPIENT_LOOKUP_FILE_ID = "5876"  # pg_dump file ID for recipient_lookup table

RECIPIENT_LOOKUP_COLUMNS = [
    "id", "recipient_hash", "legal_business_name", "duns", "address_line_1",
    "address_line_2", "business_types_codes", "city", "congressional_district",
    "country_code", "parent_duns", "parent_legal_business_name", "state",
    "parent_uei", "zip5", "alternate_names", "source", "uei", "zip4", "update_date",
]


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

    def extract_file(self, file_info: dict) -> bytes:
        """Extract a single file from the ZIP."""
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

        # Download in chunks for large files
        chunk_size = 50 * 1024 * 1024  # 50 MB chunks
        chunks = []
        downloaded = 0

        while downloaded < total_size:
            end = min(downloaded + chunk_size, total_size)
            chunk = self.read_range(data_offset + downloaded, data_offset + end)
            chunks.append(chunk)
            downloaded = end
            print(f"  Downloaded {downloaded / (1024**2):.0f} / {total_size / (1024**2):.0f} MB ({100*downloaded/total_size:.0f}%)")

        compressed_data = b"".join(chunks)

        if compression == 0:  # Stored
            return compressed_data
        elif compression == 8:  # Deflate
            return zlib.decompress(compressed_data, -zlib.MAX_WBITS)
        else:
            raise ValueError(f"Unsupported compression method: {compression}")


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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--s3-bucket", required=True)
    parser.add_argument("--source-key", help="S3 key for ZIP file (auto-detect if not provided)")
    parser.add_argument("--output-prefix", default="raw/usaspending/recipient_lookup")
    parser.add_argument("--list-only", action="store_true", help="Just list files in ZIP")
    args = parser.parse_args()

    s3 = boto3.client("s3")

    # Find source file
    source_key = args.source_key or find_latest_dump(s3, args.s3_bucket)
    if not source_key:
        print("ERROR: No USAspending dump found")
        sys.exit(1)

    print(f"Source: s3://{args.s3_bucket}/{source_key}")

    # Create ZIP reader
    reader = S3ZipReader(s3, args.s3_bucket, source_key)

    # List files
    print("\nScanning ZIP contents...")
    files = reader.list_files()
    print(f"Found {len(files)} files in archive")

    # Find recipient_lookup file
    target_file = None
    for f in files:
        if f["filename"] == f"{RECIPIENT_LOOKUP_FILE_ID}.dat.gz":
            target_file = f
            print(f"\nFound target: {f['filename']}")
            print(f"  Compressed: {f['compressed_size'] / (1024**2):.1f} MB")
            print(f"  Uncompressed: {f['uncompressed_size'] / (1024**2):.1f} MB")
            break

    if args.list_only:
        print("\n=== All files ===")
        for f in files[:20]:
            print(f"  {f['filename']}: {f['uncompressed_size'] / (1024**2):.1f} MB")
        if len(files) > 20:
            print(f"  ... and {len(files) - 20} more")
        return

    if not target_file:
        print(f"ERROR: Could not find recipient_lookup file ({RECIPIENT_LOOKUP_FILE_ID}.dat.gz)")
        sys.exit(1)

    # Extract the file
    print("\nExtracting...")
    data = reader.extract_file(target_file)
    print(f"Extracted {len(data) / (1024**2):.1f} MB from ZIP")

    # Decompress gzip (the .dat.gz files are gzip-compressed inside the ZIP)
    import gzip
    print("Decompressing gzip...")
    data = gzip.decompress(data)
    print(f"Decompressed to {len(data) / (1024**2):.1f} MB")

    # Parse as CSV
    print("\nParsing CSV...")
    df = pd.read_csv(
        io.BytesIO(data),
        sep="\t",
        header=None,
        names=RECIPIENT_LOOKUP_COLUMNS,
        na_values=["\\N", ""],
        low_memory=False,
        dtype=str,
    )
    print(f"Loaded {len(df):,} records")

    # Upload as parquet
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
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
        "source_key": source_key,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "row_count": len(df),
        "parquet_key": parquet_key,
    }
    meta_key = f"{args.output_prefix}/{today}/recipient_lookup_metadata.json"
    s3.put_object(Bucket=args.s3_bucket, Key=meta_key, Body=json.dumps(metadata, indent=2))

    print(f"\nSUCCESS: Extracted {len(df):,} recipients")


if __name__ == "__main__":
    main()
