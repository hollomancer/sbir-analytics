#!/usr/bin/env python3
"""Run web searches for M&A query candidates and verify the snippets.

Reads the candidate query CSV emitted by `generate_ma_search_queries.py`,
runs each query through a pluggable `search_tool`, and feeds the snippets
into `verify_acquisition` from `ma_verifier`. Confirmed hits are written
to a JSONL output for downstream integration.

The included `MockSearchTool` is a placeholder for testing the pipeline
end-to-end; in production swap it for a real search-API client (Bing,
Brave, Tavily, etc.) that returns `[{"snippet": ..., "link": ...}, ...]`.

Inputs:
  data/ma_search_queries.csv      — queries produced upstream
Outputs:
  data/discovered_acquisitions.jsonl — one verified M&A event per line
"""
from __future__ import annotations

import asyncio
import csv
import json
from typing import Any, Protocol

from ma_verifier import verify_acquisition


class SearchTool(Protocol):
    async def search(self, query: str) -> list[dict[str, Any]]: ...


async def process_batch(
    queries: list[dict[str, str]], search_tool: SearchTool
) -> list[dict[str, Any]]:
    """Run a batch of (company, acquirer, query) rows and return verified events."""
    verified = []
    for row in queries:
        company = row["company_name"]
        acquirer = row["acquirer"]
        query = row["query"]
        results = await search_tool.search(query)
        for res in results:
            snippet = res.get("snippet", "")
            verification = verify_acquisition(company, acquirer, snippet)
            if verification["confirmed"]:
                verified.append({
                    "company_name": company,
                    "acquirer": acquirer,
                    "date": verification["date"],
                    "value": verification["value"],
                    "source": res.get("link", "Unknown"),
                    "evidence": snippet,
                })
                break  # one hit per (company, acquirer) is enough
    return verified


async def main() -> None:
    print("M&A Discovery Orchestrator started.")

    with open("data/ma_search_queries.csv") as f:
        queries = list(csv.DictReader(f))

    # Placeholder: swap MockSearchTool for a real search-API client in production.
    class MockSearchTool:
        async def search(self, query: str) -> list[dict[str, Any]]:
            if "Physical Optics" in query and "Mercury Systems" in query:
                return [{
                    "snippet": "Mercury Systems announced the acquisition of Physical Optics Corporation.",
                    "link": "http://example.com",
                }]
            return []

    search_tool = MockSearchTool()

    batch_size = 100
    all_verified: list[dict[str, Any]] = []
    for i in range(0, len(queries), batch_size):
        batch = queries[i:i + batch_size]
        print(f"Processing batch {i // batch_size + 1}...")
        all_verified.extend(await process_batch(batch, search_tool))

    with open("data/discovered_acquisitions.jsonl", "w") as f:
        for item in all_verified:
            f.write(json.dumps(item) + "\n")

    print(f"Automation complete. Found {len(all_verified)} verified acquisitions.")
    print("Results saved to data/discovered_acquisitions.jsonl")


if __name__ == "__main__":
    asyncio.run(main())
