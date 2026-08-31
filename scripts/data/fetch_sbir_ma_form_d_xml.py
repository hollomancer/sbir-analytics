#!/usr/bin/env python3
"""Fetch private Form D XML for an existing candidate ledger.

Epistemic tier: exploratory. This retrieval preserves raw XML and request
provenance only; it does not parse a business-combination predicate or emit an
M&A result.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx


EPISTEMIC_TIER = "exploratory"
REQUESTS_PER_SECOND = 4


def _load_candidates(path: Path) -> dict[str, dict[str, str]]:
    candidates: dict[str, dict[str, str]] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            filing = record["form_d_index"]
            candidates[filing["accession_number"]] = {
                "accession_number": filing["accession_number"],
                "cik": filing["cik"],
                "filing_date": filing["filing_date"],
            }
    return candidates


def _completed_accessions(manifest: Path) -> set[str]:
    if not manifest.exists():
        return set()
    with manifest.open(encoding="utf-8") as handle:
        return {
            json.loads(line)["accession_number"]
            for line in handle
            if line.strip() and json.loads(line).get("status") == 200
        }


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--contact-email", required=True)
    args = parser.parse_args()

    candidates = _load_candidates(args.candidates)
    completed = _completed_accessions(args.manifest)
    remaining = [item for accession, item in candidates.items() if accession not in completed]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)

    next_request_at = 0.0
    request_lock = asyncio.Lock()

    async def request_slot() -> None:
        nonlocal next_request_at
        async with request_lock:
            now = time.monotonic()
            delay = max(0.0, next_request_at - now)
            next_request_at = max(now, next_request_at) + 1 / REQUESTS_PER_SECOND
        if delay:
            await asyncio.sleep(delay)

    headers = {
        "Accept": "application/xml, text/xml, */*",
        "User-Agent": f"SBIR-Analytics/0.11.0 ({args.contact_email})",
    }
    semaphore = asyncio.Semaphore(4)
    write_lock = asyncio.Lock()
    succeeded = failed = 0

    async def fetch(candidate: dict[str, str], client: httpx.AsyncClient, manifest) -> None:
        nonlocal succeeded, failed
        accession = candidate["accession_number"]
        cik = candidate["cik"].zfill(10)
        url = (
            "https://www.sec.gov/Archives/edgar/data/"
            f"{cik}/{accession.replace('-', '')}/primary_doc.xml"
        )
        async with semaphore:
            await request_slot()
            response = await client.get(url, headers=headers, follow_redirects=True)
        payload = response.content if response.status_code == 200 else b""
        if payload:
            (args.output_dir / f"{accession}.xml").write_bytes(payload)
        record = {
            **candidate,
            "url": url,
            "status": response.status_code,
            "retrieved_at_utc": datetime.now(UTC).isoformat(),
            "content_type": response.headers.get("content-type"),
            "last_modified": response.headers.get("last-modified"),
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest() if payload else None,
        }
        async with write_lock:
            manifest.write(json.dumps(record, sort_keys=True) + "\n")
            manifest.flush()
            if payload:
                succeeded += 1
            else:
                failed += 1

    async with httpx.AsyncClient(timeout=60) as client:
        with args.manifest.open("a", encoding="utf-8") as manifest:
            for start in range(0, len(remaining), 100):
                await asyncio.gather(
                    *(fetch(item, client, manifest) for item in remaining[start : start + 100])
                )
                print(
                    f"{min(start + 100, len(remaining))}/{len(remaining)} "
                    f"success={succeeded} failed={failed}"
                )

    print(f"XML retrieval complete: success={succeeded} failed={failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
