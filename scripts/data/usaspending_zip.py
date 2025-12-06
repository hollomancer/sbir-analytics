"""Shared ZIP reader for USAspending dumps with S3 central directory caching."""

import hashlib
import json
import struct
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

import requests


class HttpZipReader:
    """Read ZIP files from HTTP using range requests with optional S3 caching."""

    def __init__(self, url: str, s3_client=None, cache_bucket: str = None):
        self.url = url
        self.session = requests.Session()
        self.s3 = s3_client
        self.cache_bucket = cache_bucket

        head = self.session.head(url, allow_redirects=True)
        self.size = int(head.headers["Content-Length"])
        self._files_cache = None

    def read_range(self, start: int, end: int) -> bytes:
        headers = {"Range": f"bytes={start}-{end-1}"}
        return self.session.get(self.url, headers=headers).content

    def _get_cache_key(self) -> str:
        """Generate cache key from URL and size."""
        h = hashlib.md5(f"{self.url}:{self.size}".encode()).hexdigest()[:12]
        return f"cache/usaspending_zip_index/{h}.json"

    def _load_cached_files(self) -> list[dict] | None:
        """Try to load file list from S3 cache."""
        if not self.s3 or not self.cache_bucket:
            return None
        try:
            key = self._get_cache_key()
            obj = self.s3.get_object(Bucket=self.cache_bucket, Key=key)
            data = json.loads(obj["Body"].read())
            if data.get("size") == self.size:
                print(f"  Using cached ZIP index from s3://{self.cache_bucket}/{key}")
                return data["files"]
        except Exception:
            pass
        return None

    def _save_files_cache(self, files: list[dict]) -> None:
        """Save file list to S3 cache."""
        if not self.s3 or not self.cache_bucket:
            return
        try:
            key = self._get_cache_key()
            data = {"url": self.url, "size": self.size, "files": files,
                    "cached_at": datetime.now(timezone.utc).isoformat()}
            self.s3.put_object(Bucket=self.cache_bucket, Key=key,
                              Body=json.dumps(data), ContentType="application/json")
            print(f"  Cached ZIP index to s3://{self.cache_bucket}/{key}")
        except Exception as e:
            print(f"  Warning: Could not cache ZIP index: {e}")

    def find_central_directory(self) -> tuple[int, int]:
        tail = self.read_range(self.size - 65536, self.size)
        eocd_pos = tail.rfind(b"PK\x05\x06")
        if eocd_pos == -1:
            raise ValueError("Could not find ZIP EOCD")
        eocd = tail[eocd_pos:eocd_pos + 22]
        cd_size = struct.unpack("<I", eocd[12:16])[0]
        cd_offset = struct.unpack("<I", eocd[16:20])[0]
        if cd_offset == 0xFFFFFFFF:
            zip64_pos = tail.rfind(b"PK\x06\x07")
            if zip64_pos != -1:
                zip64_eocd_offset = struct.unpack("<Q", tail[zip64_pos + 8:zip64_pos + 16])[0]
                zip64_eocd = self.read_range(zip64_eocd_offset, zip64_eocd_offset + 56)
                cd_size = struct.unpack("<Q", zip64_eocd[40:48])[0]
                cd_offset = struct.unpack("<Q", zip64_eocd[48:56])[0]
        return cd_offset, cd_size

    def list_files(self) -> list[dict]:
        # Check cache first
        if self._files_cache is not None:
            return self._files_cache

        cached = self._load_cached_files()
        if cached:
            self._files_cache = cached
            return cached

        # Parse central directory
        cd_offset, cd_size = self.find_central_directory()
        cd_data = self.read_range(cd_offset, cd_offset + cd_size)
        files, pos = [], 0
        while pos < len(cd_data) and cd_data[pos:pos + 4] == b"PK\x01\x02":
            fname_len = struct.unpack("<H", cd_data[pos + 28:pos + 30])[0]
            extra_len = struct.unpack("<H", cd_data[pos + 30:pos + 32])[0]
            comment_len = struct.unpack("<H", cd_data[pos + 32:pos + 34])[0]
            comp_size = struct.unpack("<I", cd_data[pos + 20:pos + 24])[0]
            uncomp_size = struct.unpack("<I", cd_data[pos + 24:pos + 28])[0]
            offset = struct.unpack("<I", cd_data[pos + 42:pos + 46])[0]
            if comp_size == 0xFFFFFFFF or uncomp_size == 0xFFFFFFFF or offset == 0xFFFFFFFF:
                extra = cd_data[pos + 46 + fname_len:pos + 46 + fname_len + extra_len]
                ep = 0
                while ep + 4 <= len(extra):
                    tag, sz = struct.unpack("<HH", extra[ep:ep + 4])
                    if tag == 0x0001:
                        fp = ep + 4
                        if uncomp_size == 0xFFFFFFFF and fp + 8 <= len(extra):
                            uncomp_size = struct.unpack("<Q", extra[fp:fp + 8])[0]
                            fp += 8
                        if comp_size == 0xFFFFFFFF and fp + 8 <= len(extra):
                            comp_size = struct.unpack("<Q", extra[fp:fp + 8])[0]
                            fp += 8
                        if offset == 0xFFFFFFFF and fp + 8 <= len(extra):
                            offset = struct.unpack("<Q", extra[fp:fp + 8])[0]
                        break
                    ep += 4 + sz
            filename = cd_data[pos + 46:pos + 46 + fname_len].decode("utf-8", errors="replace")
            files.append({"filename": filename, "compressed_size": comp_size,
                          "uncompressed_size": uncomp_size, "local_header_offset": offset})
            pos += 46 + fname_len + extra_len + comment_len

        self._files_cache = files
        self._save_files_cache(files)
        return files

    def download_file(self, file_info: dict, output_path: str,
                      chunk_size: int = 50 * 1024 * 1024, parallel: int = 10,
                      max_retries: int = 5) -> None:
        """Download a file from the ZIP to disk with parallel chunks and retry logic."""
        import time

        local_header = self.read_range(file_info["local_header_offset"], file_info["local_header_offset"] + 30)
        fname_len = struct.unpack("<H", local_header[26:28])[0]
        extra_len = struct.unpack("<H", local_header[28:30])[0]
        data_offset = file_info["local_header_offset"] + 30 + fname_len + extra_len
        total_size = file_info["compressed_size"]

        # Build list of chunks
        chunks = []
        pos = 0
        while pos < total_size:
            end = min(pos + chunk_size, total_size)
            chunks.append((pos, end))
            pos = end

        print(f"  Downloading {len(chunks)} chunks with {parallel} parallel connections...")

        # Download chunks in parallel
        chunk_data = {}

        def download_chunk(chunk_idx: int, start: int, end: int) -> tuple[int, bytes]:
            """Download a chunk with retry logic."""
            for attempt in range(max_retries):
                try:
                    data = self.read_range(data_offset + start, data_offset + end)
                    return chunk_idx, data
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    wait = 2 ** attempt  # Exponential backoff: 1, 2, 4, 8, 16 seconds
                    print(f"  Chunk {chunk_idx} failed (attempt {attempt + 1}/{max_retries}), retrying in {wait}s: {e}")
                    time.sleep(wait)
            raise RuntimeError(f"Failed to download chunk {chunk_idx} after {max_retries} attempts")

        completed = 0
        with ThreadPoolExecutor(max_workers=parallel) as executor:
            futures = {
                executor.submit(download_chunk, i, start, end): i
                for i, (start, end) in enumerate(chunks)
            }
            for future in as_completed(futures):
                idx, data = future.result()
                chunk_data[idx] = data
                completed += 1
                pct = 100 * completed / len(chunks)
                downloaded = sum(len(chunk_data[i]) for i in chunk_data)
                print(f"  {downloaded / (1024**3):.2f} / {total_size / (1024**3):.2f} GB ({pct:.0f}%)", flush=True)

        # Write chunks in order
        with open(output_path, "wb") as f:
            for i in range(len(chunks)):
                f.write(chunk_data[i])

    def sample_file(self, file_info: dict, sample_bytes: int = 50000) -> bytes:
        """Read first N bytes of a file for sampling."""
        local_header = self.read_range(file_info["local_header_offset"], file_info["local_header_offset"] + 30)
        fname_len = struct.unpack("<H", local_header[26:28])[0]
        extra_len = struct.unpack("<H", local_header[28:30])[0]
        data_offset = file_info["local_header_offset"] + 30 + fname_len + extra_len
        read_size = min(sample_bytes, file_info["compressed_size"])
        return self.read_range(data_offset, data_offset + read_size)


def find_latest_usaspending_url() -> str | None:
    """Find the latest USAspending dump URL."""
    base_url = "https://files.usaspending.gov/database_download"
    for days_ago in range(0, 30):
        date = datetime.now() - timedelta(days=days_ago)
        url = f"{base_url}/usaspending-db_{date.strftime('%Y%m%d')}.zip"
        try:
            if requests.head(url, timeout=5).status_code == 200:
                return url
        except Exception:
            continue
    return None
