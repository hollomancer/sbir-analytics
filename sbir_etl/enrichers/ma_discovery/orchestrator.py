"""Run search queries for M&A candidates and verify the snippets.

Reads the candidate query CSV emitted by ``queries``, runs each query
through a pluggable ``SearchTool``, and feeds snippets into a
``SnippetExtractor`` (keyword by default). Confirmed hits are written as
JSONL. One confirmed hit per ``(company_name, acquirer)`` is kept.

The CLI constructs the search tool via ``build_search_tool``. Runtime
default is ``none`` (fail-closed). ``mock`` is explicit opt-in.

Usage::

    python -m sbir_etl.enrichers.ma_discovery.orchestrator --search-backend mock
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from sbir_etl.enrichers.ma_discovery.confidence import assign_confidence
from sbir_etl.enrichers.ma_discovery.extractor import (
    ExtractionInput,
    KeywordExtractor,
    SnippetExtractor,
)
from sbir_etl.enrichers.ma_discovery.search import SearchTool, build_search_tool
from sbir_etl.identity import CompanyNameProfile, normalize_company_name


DEFAULT_QUERIES_PATH = Path("data/ma_search_queries.csv")
DEFAULT_OUTPUT_PATH = Path("data/discovered_acquisitions.jsonl")


def _pair_key(company: str, acquirer: str) -> tuple[str, str]:
    profile = CompanyNameProfile.RECIPIENT_V1
    return (
        normalize_company_name(company, profile=profile),
        normalize_company_name(acquirer, profile=profile),
    )


async def process_batch(
    queries: list[dict[str, str]],
    search_tool: SearchTool,
    *,
    extractor: SnippetExtractor | None = None,
    stop_when: str = "first_confirm",
) -> list[dict[str, Any]]:
    """Run a batch of (company, acquirer, query) rows and return verified events.

    ``stop_when`` is ``first_confirm`` (pilot) or ``dated_confirm`` (keep
    scanning hits until medium/high or the query is exhausted).
    """
    if stop_when not in {"first_confirm", "dated_confirm"}:
        raise ValueError(f"unknown stop_when {stop_when!r}")
    verifier = extractor if extractor is not None else KeywordExtractor()
    verified: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    pending_undated: dict[tuple[str, str], dict[str, Any]] = {}
    confirming_urls: dict[tuple[str, str], list[str]] = {}
    for row in queries:
        company = row["company_name"]
        acquirer = row["acquirer"]
        key = _pair_key(company, acquirer)
        if key in seen:
            continue
        query = row["query"]
        results = await search_tool.search(query)
        urls = confirming_urls.setdefault(key, [])
        undated: dict[str, Any] | None = None
        committed = False
        for res in results:
            link = res.get("link")
            snippet = res.get("snippet", "")
            source = link if isinstance(link, str) else None
            if not snippet and not source:
                continue
            verdict = verifier.extract(
                ExtractionInput(
                    company=company,
                    acquirer=acquirer,
                    snippet=str(snippet),
                    source_url=source,
                )
            )
            if not verdict.confirmed:
                continue
            if isinstance(link, str) and link and link not in urls:
                urls.append(link)
            confidence = assign_confidence(verdict, source_count=len(urls))
            event = {
                "company_name": company,
                "acquirer": acquirer,
                "date": verdict.acquisition_date,
                "event_date": verdict.acquisition_date,
                "value": verdict.value_usd,
                "source": source or "Unknown",
                "evidence": snippet,
                "confidence": confidence,
                "reason": verdict.reason,
            }
            if stop_when == "first_confirm" or confidence in {"medium", "high"}:
                seen.add(key)
                pending_undated.pop(key, None)
                verified.append(event)
                committed = True
                break
            if undated is None:
                undated = event
        if committed:
            continue
        if undated is not None and key not in pending_undated:
            pending_undated[key] = undated
    for key, event in pending_undated.items():
        if key not in seen:
            verified.append(event)
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
        help="Search backend: none, mock, snippets, tavily, or brave. Default: config (none).",
    )
    parser.add_argument(
        "--search-api-key",
        default=None,
        help="API key for a live backend. Falls back to config/env.",
    )
    parser.add_argument(
        "--snippets",
        type=Path,
        default=None,
        help="Frozen search-result JSONL for --search-backend snippets.",
    )
    parser.add_argument("--max-candidates", type=int, default=None)
    args = parser.parse_args(argv)

    queries = load_query_csv(args.input)
    if args.max_candidates is not None:
        kept: list[dict[str, str]] = []
        seen_pairs: set[tuple[str, str]] = set()
        for row in queries:
            key = _pair_key(row["company_name"], row["acquirer"])
            if key not in seen_pairs and len(seen_pairs) >= args.max_candidates:
                continue
            seen_pairs.add(key)
            kept.append(row)
        queries = kept
    search_tool = build_search_tool(
        args.search_backend,
        api_key=args.search_api_key,
        snippets_path=args.snippets,
    )
    verified = asyncio.run(_run_batch(queries, search_tool))
    write_verified_jsonl(args.output, verified)
    print(f"Found {len(verified)} verified acquisitions. Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
