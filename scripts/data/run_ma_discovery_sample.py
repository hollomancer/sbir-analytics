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
from sbir_etl.enrichers.ma_discovery.collision import apply_c3, name_key
from sbir_etl.enrichers.ma_discovery.extractor import (
    FrozenLlmExtractor,
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

    def __init__(
        self,
        inner: SearchTool,
        sink: list[dict[str, Any]],
        *,
        path: Path | None = None,
    ) -> None:
        self._inner = inner
        self._sink = sink
        self._path = path

    def _record(self, record: dict[str, Any]) -> None:
        self._sink.append(record)
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    async def search(self, query: str) -> list[dict[str, Any]]:
        hits = await self._inner.search(query)
        if not hits:
            self._record({"query": query, "snippet": "", "link": None, "hit_count": 0})
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
            self._record(record)
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
    skip_pairs: int = 0,
) -> list[dict[str, str]]:
    """Keep the first ``queries_per_pair`` templates after skipping unique pairs."""
    kept: list[dict[str, str]] = []
    skipped: set[tuple[str, str]] = set()
    per_pair: dict[tuple[str, str], int] = {}
    for row in queries:
        key = (row["company_name"], row["acquirer"])
        if key in skipped:
            continue
        if key not in per_pair:
            if len(skipped) < skip_pairs:
                skipped.add(key)
                continue
            if len(per_pair) >= max_candidates:
                continue
        used = per_pair.get(key, 0)
        if used >= queries_per_pair:
            continue
        per_pair[key] = used + 1
        kept.append(row)
    return kept


def load_recorded_queries(path: Path) -> set[str]:
    """Return query strings already frozen in a snippets JSONL cut."""
    if not path.is_file():
        return set()
    recorded: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        query = record.get("query")
        if isinstance(query, str) and query:
            recorded.add(query)
    return recorded


def drop_recorded_queries(
    queries: list[dict[str, str]],
    recorded: set[str],
) -> list[dict[str, str]]:
    """Drop rows whose query string is already in a frozen snippets cut."""
    if not recorded:
        return list(queries)
    return [row for row in queries if row["query"] not in recorded]


def pair_key(company: object, acquirer: object) -> tuple[str, str]:
    return (name_key(str(company or "")), name_key(str(acquirer or "")))


def existing_medium_high_pairs(events: list[dict[str, Any]]) -> set[tuple[str, str]]:
    """Pairs the detector already called medium or high (any date)."""
    pairs: set[tuple[str, str]] = set()
    for row in events:
        if row.get("confidence") not in {"medium", "high"}:
            continue
        key = pair_key(row.get("company_name"), row.get("acquirer"))
        if key[0]:
            pairs.add(key)
    return pairs


def strict_medium_high_n(
    events: list[dict[str, Any]],
    mutated: list[dict[str, Any]],
) -> int:
    """Count insert/promote medium/high pairs that were not already medium/high."""
    already = existing_medium_high_pairs(events)
    seen: set[tuple[str, str]] = set()
    for row in mutated:
        if row.get("confidence") not in {"medium", "high"}:
            continue
        key = pair_key(row.get("company_name"), row.get("acquirer"))
        if not key[0] or key in already or key in seen:
            continue
        seen.add(key)
    return len(seen)


def check_run_manifest(
    manifest_path: Path,
    *,
    events: Path,
    snippets: Path,
    llm: Path | None,
) -> list[str]:
    """Return SHA mismatches vs a tracked run manifest. Empty means match."""
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    inputs = payload.get("inputs") if isinstance(payload, dict) else None
    if not isinstance(inputs, dict):
        return [f"run manifest missing inputs: {manifest_path}"]
    errors: list[str] = []
    mapping = {
        "events": events,
        "snippets": snippets,
        "llm_responses": llm,
    }
    for name, path in mapping.items():
        spec = inputs.get(name)
        if not isinstance(spec, dict):
            continue
        expected = spec.get("sha256")
        if not isinstance(expected, str) or not expected:
            continue
        if path is None or not path.is_file():
            errors.append(f"{name} freeze missing for SHA check: {path}")
            continue
        actual = _sha256(path)
        if actual != expected:
            errors.append(f"{name} SHA mismatch: expected {expected}, found {actual}")
    return errors


async def _search(
    queries: list[dict[str, str]],
    *,
    backend: str | None,
    api_key: str | None,
    snippets: Path | None,
    sink: list[dict[str, Any]],
    extractor: SnippetExtractor | None = None,
    record_path: Path | None = None,
    stop_when: str = "first_confirm",
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
    tool = RecordingSearchTool(inner, sink, path=record_path)
    try:
        return await process_batch(
            queries, tool, extractor=extractor, stop_when=stop_when
        )
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
        "--skip-pairs",
        type=int,
        default=0,
        help="Skip this many unique pairs before applying --max-candidates (held-out cuts).",
    )
    parser.add_argument(
        "--queries-per-pair",
        type=int,
        default=1,
        help="Query templates per pair. Live capture uses 1 to bound API spend.",
    )
    parser.add_argument(
        "--stop-when",
        choices=("first_confirm", "dated_confirm"),
        default="first_confirm",
        help="first_confirm is the pilot rule; dated_confirm keeps scanning until medium/high.",
    )
    parser.add_argument(
        "--confirm",
        choices=("keyword", "llm"),
        default="keyword",
        help="Snippet confirmer. llm needs --llm-freeze (replay) or --capture-llm (live).",
    )
    parser.add_argument(
        "--llm-freeze",
        type=Path,
        default=None,
        help="Replay FrozenLlmExtractor from this JSONL. No network.",
    )
    parser.add_argument(
        "--capture-llm",
        action="store_true",
        help="Live OpenRouter/xAI capture; checkpoint into output-dir/llm_responses.jsonl.",
    )
    parser.add_argument(
        "--llm-api-key",
        default=None,
        help="Override OPENROUTER_API_KEY or XAI_API_KEY (capture only).",
    )
    parser.add_argument(
        "--run-manifest",
        type=Path,
        default=None,
        help="Fail if events/snippets/LLM SHA-256 do not match this tracked manifest.",
    )
    parser.add_argument(
        "--strict-recall",
        action="store_true",
        help="Recall floor counts only pairs not already medium/high in the events file.",
    )
    parser.add_argument(
        "--fail-on-gate",
        action="store_true",
        help="Exit 1 when the recall floor is not met.",
    )
    args = parser.parse_args()

    events = load_ma_events(args.events)
    queries = query_rows_from_events(events)
    bounded = bound_queries(
        queries,
        max_candidates=args.max_candidates,
        queries_per_pair=args.queries_per_pair,
        skip_pairs=args.skip_pairs,
    )
    replay = args.snippets is not None
    snippets_path = args.output_dir / "search_snippets.jsonl"
    skipped_n = 0
    if not replay:
        recorded_queries = load_recorded_queries(snippets_path)
        if recorded_queries:
            before = len(bounded)
            bounded = drop_recorded_queries(bounded, recorded_queries)
            skipped_n = before - len(bounded)
    pair_n = len({(row["company_name"], row["acquirer"]) for row in bounded})
    skip_note = f", skipped {skipped_n} frozen" if skipped_n else ""
    print(
        f"Searching {len(bounded)} queries across {pair_n} pairs "
        f"(backend={args.search_backend!r}{skip_note})"
    )
    recorded: list[dict[str, Any]] = []
    llm_records: list[dict[str, Any]] = []
    extractor: SnippetExtractor | None = None
    llm_path = args.output_dir / "llm_responses.jsonl"
    if args.confirm == "llm":
        if args.capture_llm and args.llm_freeze is not None:
            raise SystemExit("use either --capture-llm or --llm-freeze, not both")
        if args.capture_llm:
            live = build_llm_extractor(api_key=args.llm_api_key)
            if live is None:
                raise SystemExit(
                    "OPENROUTER_API_KEY or XAI_API_KEY is required for --capture-llm"
                )
            extractor = RecordingLlmExtractor(live, llm_records, path=llm_path)
        else:
            freeze = args.llm_freeze or llm_path
            if not freeze.is_file():
                raise SystemExit(
                    "--confirm llm requires --llm-freeze JSONL or --capture-llm"
                )
            extractor = FrozenLlmExtractor(freeze)
            llm_path = freeze

    if args.run_manifest is not None:
        sha_errors = check_run_manifest(
            args.run_manifest,
            events=args.events,
            snippets=args.snippets or snippets_path,
            llm=llm_path if args.confirm == "llm" else None,
        )
        if sha_errors:
            raise SystemExit("run-manifest SHA check failed:\n" + "\n".join(sha_errors))

    discovered = asyncio.run(
        _search(
            bounded,
            backend=args.search_backend,
            api_key=args.search_api_key,
            snippets=args.snippets,
            sink=recorded,
            extractor=extractor,
            record_path=None if replay else snippets_path,
            stop_when=args.stop_when,
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
    strict_n = strict_medium_high_n(events, collision.inserted + collision.promoted)
    recall_n = strict_n if args.strict_recall else len(medium_high)
    recall_met = recall_n >= 10
    llm_n = len(llm_records)
    if not llm_n and args.confirm == "llm" and llm_path.is_file():
        llm_n = sum(
            1 for line in llm_path.read_text(encoding="utf-8").splitlines() if line.strip()
        )
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
        "skip_pairs": args.skip_pairs,
        "queries_per_pair": args.queries_per_pair,
        "stop_when": args.stop_when,
        "recorded_snippet_rows": len(recorded),
        "snippets_sha256": _sha256(args.snippets or snippets_path),
        "confirm": args.confirm,
        "llm_model": llm_records[0]["model"] if llm_records else None,
        "llm_response_n": llm_n,
        "llm_responses_sha256": _sha256(llm_path) if args.confirm == "llm" else None,
        "discovered_n": len(discovered),
        "discovered_medium_high_n": len(medium_high),
        "strict_medium_high_n": strict_n,
        "inserted_n": len(collision.inserted),
        "promoted_n": len(collision.promoted),
        "review_queue_n": len(queue),
        "search_backend": args.search_backend,
        "snippets_path": str(snippets_path),
        "snippets_input": str(args.snippets) if args.snippets else None,
        "kill_gate": {
            "recall_floor_met": recall_met,
            "recall_n": recall_n,
            "recall_rule": "strict" if args.strict_recall else "discovered_medium_high",
            "precision_review_complete": False,
            "cost_cap_measured": False,
        },
    }
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"Discovered {len(discovered)} rows; review queue {len(queue)} → {args.output_dir}")
    if args.fail_on_gate and not recall_met:
        print(f"recall floor missed ({recall_n} < 10, rule={summary['kill_gate']['recall_rule']})")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
