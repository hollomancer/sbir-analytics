"""Run search queries for M&A candidates and verify the snippets.

Reads the candidate query CSV emitted by ``queries``, runs each query
through a pluggable ``SearchTool``, and feeds snippets into
``verify_acquisition``. Confirmed hits are written as JSONL.

The CLI constructs the search tool via ``build_search_tool``. Runtime
default is ``mock``. Selecting ``tavily`` or ``brave`` without a key
fails closed.

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

from sbir_etl.enrichers.ma_discovery.search import SearchTool, build_search_tool
from sbir_etl.enrichers.ma_discovery.verifier import verify_acquisition


DEFAULT_QUERIES_PATH = Path("data/ma_search_queries.csv")
DEFAULT_OUTPUT_PATH = Path("data/discovered_acquisitions.jsonl")


async def process_batch(
    queries: list[dict[str, str]], search_tool: SearchTool
) -> list[dict[str, Any]]:
    """Run a batch of (company, acquirer, query) rows and return verified events."""
    verified: list[dict[str, Any]] = []
    # generate_queries emits four rows per (company, acquirer) pair, so the
    # inner break alone would still append the same pair up to four times.
    seen: set[tuple[str, str]] = set()
    for row in queries:
        company = row["company_name"]
        acquirer = row["acquirer"]
        pair = (company, acquirer)
        if pair in seen:
            continue
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
                seen.add(pair)  # one hit per (company, acquirer) is enough
                break
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


async def _run_batch(
    queries: list[dict[str, str]], search_tool: SearchTool
) -> list[dict[str, Any]]:
    """Run ``process_batch`` and close the search client when it supports it."""
    try:
        return await process_batch(queries, search_tool)
    finally:
        aclose = getattr(search_tool, "aclose", None)
        if aclose is not None:
            await aclose()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify M&A search-query snippets")
    parser.add_argument("--input", type=Path, default=DEFAULT_QUERIES_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument(
        "--search-backend",
        default=None,
        help="Search backend: mock, tavily, or brave. Default: config or mock.",
    )
    parser.add_argument(
        "--search-api-key",
        default=None,
        help="API key for a live backend. Falls back to config/env.",
    )
    args = parser.parse_args(argv)

    queries = load_query_csv(args.input)
    search_tool = build_search_tool(args.search_backend, api_key=args.search_api_key)
    verified = asyncio.run(_run_batch(queries, search_tool))
    write_verified_jsonl(args.output, verified)
    print(f"Found {len(verified)} verified acquisitions. Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
