#!/usr/bin/env python3
"""Run a bounded M&A discovery sample and emit a human review queue.

Epistemic tier: exploratory. This is the sample-run / review-queue CLI for
``studies/ma-discovery-recall``. It does not promote a rank. Default search
backend is fail-closed; pass ``--search-backend mock`` or ``snippets``.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sbir_etl.config.schemas.domain import MADiscoveryConfig
from sbir_etl.enrichers.ma_discovery.collision import apply_c3
from sbir_etl.enrichers.ma_discovery.extractor import (
    RecordingLlmExtractor,
    SnippetExtractor,
    build_llm_extractor,
)
from sbir_etl.enrichers.ma_discovery.orchestrator import process_batch
from sbir_etl.enrichers.ma_discovery.queries import (
    load_ma_events,
    query_rows_from_events,
)
from sbir_etl.enrichers.ma_discovery.search import SearchTool, build_search_tool


EPISTEMIC_TIER = "exploratory"
REVIEW_SIZE = 20


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_review_queue(
    result_rows: list[dict[str, Any]],
    *,
    limit: int = REVIEW_SIZE,
) -> list[dict[str, Any]]:
    """Medium-confidence discovery-touched rows for human labeling."""
    queue: list[dict[str, Any]] = []
    for row in result_rows:
        signals = row.get("signals") or {}
        if row.get("confidence") != "medium":
            continue
        if not signals.get("discovery_confirmed"):
            continue
        queue.append(
            {
                "company_name": row.get("company_name"),
                "acquirer": row.get("acquirer"),
                "event_date": row.get("event_date"),
                "source": row.get("source"),
                "evidence": row.get("evidence"),
                "confidence": row.get("confidence"),
                "review_outcome": "unreviewed",
                "review_rationale": None,
            }
        )
        if len(queue) >= limit:
            break
    return queue


class RecordingSearchTool:
    """Wrap a SearchTool and append every query/hit to a sink. Exploratory."""

    def __init__(self, inner: SearchTool, sink: list[dict[str, Any]]) -> None:
        self._inner = inner
        self._sink = sink

    async def search(self, query: str) -> list[dict[str, Any]]:
        hits = await self._inner.search(query)
        if not hits:
            self._sink.append({"query": query, "snippet": "", "link": None, "hit_count": 0})
            return hits
        for hit in hits:
            record = {
                "query": query,
                "snippet": hit.get("snippet") or "",
                "link": hit.get("link"),
                "hit_count": len(hits),
            }
            title = hit.get("title")
            if title:
                record["title"] = title
            self._sink.append(record)
        return hits

    async def aclose(self) -> None:
        aclose = getattr(self._inner, "aclose", None)
        if aclose is not None:
            await aclose()


def bound_queries(
    queries: list[dict[str, str]],
    *,
    max_candidates: int,
    queries_per_pair: int,
) -> list[dict[str, str]]:
    """Keep the first ``queries_per_pair`` templates for up to ``max_candidates`` pairs."""
    kept: list[dict[str, str]] = []
    per_pair: dict[tuple[str, str], int] = {}
    for row in queries:
        key = (row["company_name"], row["acquirer"])
        if key not in per_pair and len(per_pair) >= max_candidates:
            continue
        used = per_pair.get(key, 0)
        if used >= queries_per_pair:
            continue
        per_pair[key] = used + 1
        kept.append(row)
    return kept


async def _search(
    queries: list[dict[str, str]],
    *,
    backend: str | None,
    api_key: str | None,
    snippets: Path | None,
    sink: list[dict[str, Any]],
    extractor: SnippetExtractor | None = None,
) -> list[dict[str, Any]]:
    config = MADiscoveryConfig(
        search_backend=backend or "none",
        search_api_key=api_key,
        rate_limit_per_minute=20,
        max_results=5,
        snippets_path=str(snippets) if snippets else None,
    )
    inner = build_search_tool(
        backend,
        api_key=api_key,
        config=config,
        snippets_path=snippets,
    )
    tool = RecordingSearchTool(inner, sink)
    try:
        return await process_batch(queries, tool, extractor=extractor)
    finally:
        await tool.aclose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, default=Path("data/sbir_ma_events.jsonl"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed/ma_discovery"))
    parser.add_argument("--search-backend", default=None)
    parser.add_argument("--search-api-key", default=None)
    parser.add_argument("--snippets", type=Path, default=None)
    parser.add_argument("--max-candidates", type=int, default=200)
    parser.add_argument(
        "--queries-per-pair",
        type=int,
        default=1,
        help="Query templates per pair. Live capture uses 1 to bound API spend.",
    )
    parser.add_argument(
        "--confirm",
        choices=("keyword", "llm"),
        default="keyword",
        help="Snippet confirmer. llm uses OpenRouter or xAI grok-4.6 and freezes raw responses.",
    )
    parser.add_argument(
        "--llm-api-key",
        default=None,
        help="Override OPENROUTER_API_KEY or XAI_API_KEY.",
    )
    args = parser.parse_args()

    events = load_ma_events(args.events)
    queries = query_rows_from_events(events)
    bounded = bound_queries(
        queries,
        max_candidates=args.max_candidates,
        queries_per_pair=args.queries_per_pair,
    )
    pair_n = len({(row["company_name"], row["acquirer"]) for row in bounded})
    print(
        f"Searching {len(bounded)} queries across {pair_n} pairs (backend={args.search_backend!r})"
    )
    recorded: list[dict[str, Any]] = []
    llm_records: list[dict[str, Any]] = []
    extractor: SnippetExtractor | None = None
    if args.confirm == "llm":
        live = build_llm_extractor(api_key=args.llm_api_key)
        if live is None:
            raise SystemExit("OPENROUTER_API_KEY or XAI_API_KEY is required for --confirm llm")
        extractor = RecordingLlmExtractor(live, llm_records)

    discovered = asyncio.run(
        _search(
            bounded,
            backend=args.search_backend,
            api_key=args.search_api_key,
            snippets=args.snippets,
            sink=recorded,
            extractor=extractor,
        )
    )
    collision = apply_c3(events, discovered)
    queue = build_review_queue(collision.inserted + collision.promoted)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    discovered_path = args.output_dir / "discovered_acquisitions.jsonl"
    snippets_path = args.output_dir / "search_snippets.jsonl"
    queue_path = args.output_dir / "review_queue.jsonl"
    summary_path = args.output_dir / "sample_run_summary.json"
    with discovered_path.open("w", encoding="utf-8") as handle:
        for row in discovered:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    replay = args.snippets is not None
    if not replay:
        with snippets_path.open("w", encoding="utf-8") as handle:
            for row in recorded:
                handle.write(json.dumps(row, sort_keys=True) + "\n")
    llm_path = args.output_dir / "llm_responses.jsonl"
    if llm_records:
        with llm_path.open("w", encoding="utf-8") as handle:
            for row in llm_records:
                handle.write(json.dumps(row, sort_keys=True) + "\n")
    with queue_path.open("w", encoding="utf-8") as handle:
        for row in queue:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    medium_high = [row for row in discovered if row.get("confidence") in {"medium", "high"}]
    summary = {
        "_epistemic": {
            "citable": False,
            "tier": "exploratory",
            "notice": "Sample run; not a validated or citable result.",
        },
        "as_of_utc": datetime.now(UTC).isoformat(),
        "events_path": str(args.events),
        "events_sha256": _sha256(args.events),
        "events_n": len(events),
        "query_rows": len(bounded),
        "candidate_pairs": pair_n,
        "queries_per_pair": args.queries_per_pair,
        "recorded_snippet_rows": len(recorded),
        "snippets_sha256": _sha256(args.snippets or snippets_path),
        "confirm": args.confirm,
        "llm_model": llm_records[0]["model"] if llm_records else None,
        "llm_response_n": len(llm_records),
        "llm_responses_sha256": _sha256(llm_path) if llm_records else None,
        "discovered_n": len(discovered),
        "discovered_medium_high_n": len(medium_high),
        "inserted_n": len(collision.inserted),
        "promoted_n": len(collision.promoted),
        "review_queue_n": len(queue),
        "search_backend": args.search_backend,
        "snippets_path": str(snippets_path),
        "snippets_input": str(args.snippets) if args.snippets else None,
        "kill_gate": {
            "recall_floor_met": len(medium_high) >= 10,
            "precision_review_complete": False,
            "cost_cap_measured": False,
        },
    }
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"Discovered {len(discovered)} rows; review queue {len(queue)} → {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
