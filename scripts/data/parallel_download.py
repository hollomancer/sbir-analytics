#!/usr/bin/env python3
"""Parallel download utility for large data files.

Optimizes download performance through:
- Concurrent chunk downloads using asyncio
- HTTP Range requests for parallel fetching
- Automatic retry with exponential backoff
- Progress tracking and resumption
"""

import asyncio
import hashlib
from dataclasses import dataclass
from pathlib import Path

import aiohttp


@dataclass
class DownloadChunk:
    """Represents a chunk of data to download."""

    chunk_id: int
    start_byte: int
    end_byte: int
    data: bytes | None = None


async def download_chunk(
    session: aiohttp.ClientSession,
    url: str,
    chunk: DownloadChunk,
    max_retries: int = 3,
) -> DownloadChunk:
    """Download a single chunk with retry logic."""
    headers = {"Range": f"bytes={chunk.start_byte}-{chunk.end_byte}"}

    for attempt in range(max_retries):
        try:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=300)) as response:
                if response.status in (200, 206):
                    chunk.data = await response.read()
                    return chunk
                response.raise_for_status()
        except (TimeoutError, aiohttp.ClientError):
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(2**attempt)

    raise RuntimeError(f"Failed to download chunk {chunk.chunk_id}")


async def parallel_download(
    url: str,
    output_path: Path,
    chunk_size: int = 10 * 1024 * 1024,  # 10 MB
    max_concurrent: int = 10,
) -> dict:
    """Download file in parallel chunks."""
    # Get file size
    async with aiohttp.ClientSession() as session:
        async with session.head(url) as response:
            file_size = int(response.headers.get("Content-Length", 0))
            if file_size == 0:
                raise ValueError("Cannot determine file size")

    # Create chunks
    chunks = []
    for i in range(0, file_size, chunk_size):
        end = min(i + chunk_size - 1, file_size - 1)
        chunks.append(DownloadChunk(chunk_id=len(chunks), start_byte=i, end_byte=end))

    # Download chunks concurrently
    semaphore = asyncio.Semaphore(max_concurrent)

    async def bounded_download(chunk: DownloadChunk) -> DownloadChunk:
        async with semaphore:
            async with aiohttp.ClientSession() as session:
                return await download_chunk(session, url, chunk)

    print(f"Downloading {len(chunks)} chunks ({file_size / 1024 / 1024:.2f} MB)")
    results = await asyncio.gather(*[bounded_download(chunk) for chunk in chunks])

    # Write chunks to file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    hasher = hashlib.sha256()

    with open(output_path, "wb") as f:
        for chunk in sorted(results, key=lambda c: c.chunk_id):
            if chunk.data is None:
                raise RuntimeError(f"Chunk {chunk.chunk_id} has no data")
            f.write(chunk.data)
            hasher.update(chunk.data)

    return {
        "file_size": file_size,
        "chunks": len(chunks),
        "sha256": hasher.hexdigest(),
        "output_path": str(output_path),
    }
