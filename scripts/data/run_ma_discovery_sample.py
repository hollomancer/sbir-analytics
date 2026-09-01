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

from sbir_etl.enrichers.ma_discovery.collision import apply_c3
from sbir_etl.enrichers.ma_discovery.orchestrator import process_batch
from sbir_etl.enrichers.ma_discovery.queries import (
    load_ma_events,
    query_rows_from_events,
)
from sbir_etl.enrichers.ma_discovery.search import build_search_tool


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


async def _search(
    queries: list[dict[str, str]],
    *,
    backend: str | None,
    api_key: str | None,
    snippets: Path | None,
) -> list[dict[str, Any]]:
    tool = build_search_tool(backend, api_key=api_key, snippets_path=snippets)
    try:
        return await process_batch(queries, tool)
    finally:
        aclose = getattr(tool, "aclose", None)
        if aclose is not None:
            await aclose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, default=Path("data/sbir_ma_events.jsonl"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed/ma_discovery"))
    parser.add_argument("--search-backend", default=None)
    parser.add_argument("--search-api-key", default=None)
    parser.add_argument("--snippets", type=Path, default=None)
    parser.add_argument("--max-candidates", type=int, default=200)
    args = parser.parse_args()

    events = load_ma_events(args.events)
    queries = query_rows_from_events(events)
    seen: set[tuple[str, str]] = set()
    bounded: list[dict[str, str]] = []
    for row in queries:
        key = (row["company_name"], row["acquirer"])
        if key not in seen and len(seen) >= args.max_candidates:
            continue
        seen.add(key)
        bounded.append(row)

    discovered = asyncio.run(
        _search(
            bounded,
            backend=args.search_backend,
            api_key=args.search_api_key,
            snippets=args.snippets,
        )
    )
    collision = apply_c3(events, discovered)
    queue = build_review_queue(collision.inserted + collision.promoted)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    discovered_path = args.output_dir / "discovered_acquisitions.jsonl"
    queue_path = args.output_dir / "review_queue.jsonl"
    summary_path = args.output_dir / "sample_run_summary.json"
    with discovered_path.open("w", encoding="utf-8") as handle:
        for row in discovered:
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
        "candidate_pairs": len(seen),
        "discovered_n": len(discovered),
        "discovered_medium_high_n": len(medium_high),
        "inserted_n": len(collision.inserted),
        "promoted_n": len(collision.promoted),
        "review_queue_n": len(queue),
        "search_backend": args.search_backend,
        "snippets_path": str(args.snippets) if args.snippets else None,
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
