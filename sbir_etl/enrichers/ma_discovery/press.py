"""Enrich existing SBIR M&A events with press-wire signals.

Wraps ``SyncPressWireClient``. Library functions take an injected client
so tests never poll the network.

Usage::

    python -m sbir_etl.enrichers.ma_discovery.press
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from sbir_etl.enrichers.press_wire import PressRelease
from sbir_etl.enrichers.sync_wrappers import SyncPressWireClient


DEFAULT_EVENTS_PATH = Path("data/sbir_ma_events.jsonl")
DEFAULT_OUTPUT_PATH = Path("data/enriched_sbir_ma_events.jsonl")


def load_ma_events(path: Path) -> list[dict[str, Any]]:
    """Load JSONL M&A event rows, skipping malformed lines."""
    events: list[dict[str, Any]] = []
    with path.open() as handle:
        for line in handle:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def watchlist_from_events(events: Iterable[Mapping[str, Any]]) -> list[str]:
    """Unique ``company_name`` values, preserving first-seen order."""
    names: list[str] = []
    seen: set[str] = set()
    for event in events:
        name = event.get("company_name")
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


def merge_press_signals(
    events: Sequence[Mapping[str, Any]],
    hits: Sequence[PressRelease],
) -> list[dict[str, Any]]:
    """Attach matching press hits to events; unmatched events stay unenriched."""
    company_press: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for hit in hits:
        company_press[hit.matched_company].append(
            {
                "title": hit.title,
                "link": hit.link,
                "published": hit.published,
                "summary": hit.summary,
                "source": hit.source,
            }
        )

    enriched_events: list[dict[str, Any]] = []
    for event in events:
        merged = dict(event)
        company = merged.get("company_name")
        if company in company_press:
            merged["press_wire_signals"] = company_press[company]
            merged["signal_count"] = merged.get("signal_count", 0) + 1
            merged["enriched"] = True
        else:
            merged["press_wire_signals"] = []
            merged["enriched"] = False
        enriched_events.append(merged)
    return enriched_events


def enrich_ma_events(events: Sequence[Mapping[str, Any]], client: Any) -> list[dict[str, Any]]:
    """Poll ``client`` for the event watchlist and merge press-wire signals."""
    client.set_watchlist(watchlist_from_events(events))
    hits = client.poll()
    return merge_press_signals(events, hits)


def write_enriched_jsonl(path: Path, events: Sequence[Mapping[str, Any]]) -> None:
    """Write enriched event rows as JSONL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as handle:
        for event in events:
            handle.write(json.dumps(event) + "\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enrich M&A events with press-wire hits")
    parser.add_argument("--input", type=Path, default=DEFAULT_EVENTS_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args(argv)

    events = load_ma_events(args.input)
    with SyncPressWireClient() as client:
        enriched = enrich_ma_events(events, client)
    write_enriched_jsonl(args.output, enriched)
    enriched_count = sum(1 for event in enriched if event["enriched"])
    print(f"Enriched {enriched_count} of {len(events)} events. Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
