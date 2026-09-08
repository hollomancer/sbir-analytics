"""Run search queries for M&A candidates and verify the snippets.

Reads the candidate query CSV emitted by ``queries``, runs each query
through a pluggable ``SearchTool``, and feeds snippets into
``verify_acquisition``. Confirmed hits are written as JSONL.

This PR ships only ``MockSearchTool``. A live search-API client is a
later step.

Usage::

    python -m sbir_etl.enrichers.ma_discovery.orchestrator
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from sbir_etl.enrichers.ma_discovery.search import MockSearchTool, SearchTool
from sbir_etl.enrichers.ma_discovery.verifier import verify_acquisition


DEFAULT_QUERIES_PATH = Path("data/ma_search_queries.csv")
DEFAULT_OUTPUT_PATH = Path("data/discovered_acquisitions.jsonl")


async def process_batch(
    queries: list[dict[str, str]], search_tool: SearchTool
) -> list[dict[str, Any]]:
    """Run a batch of (company, acquirer, query) rows and return verified events."""
    verified: list[dict[str, Any]] = []
    for row in queries:
        company = row["company_name"]
        acquirer = row["acquirer"]
        query = row["query"]
        results = await search_tool.search(query)
        for res in results:
            snippet = res.get("snippet", "")
            verification = verify_acquisition(company, acquirer, snippet)
            if verification["confirmed"]:
                verified.append(
                    {
                        "company_name": company,
                        "acquirer": acquirer,
                        "date": verification["date"],
                        "value": verification["value"],
                        "source": res.get("link", "Unknown"),
                        "evidence": snippet,
                    }
                )
                break  # one hit per (company, acquirer) is enough
    return verified


def load_query_csv(path: Path) -> list[dict[str, str]]:
    """Load search-query CSV rows."""
    with path.open() as handle:
        return list(csv.DictReader(handle))


def write_verified_jsonl(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    """Write verified acquisition rows as JSONL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify M&A search-query snippets")
    parser.add_argument("--input", type=Path, default=DEFAULT_QUERIES_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args(argv)

    queries = load_query_csv(args.input)
    verified = asyncio.run(process_batch(queries, MockSearchTool()))
    write_verified_jsonl(args.output, verified)
    print(f"Found {len(verified)} verified acquisitions. Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
