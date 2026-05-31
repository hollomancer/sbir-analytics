#!/usr/bin/env python3
"""Enrich existing SBIR M&A events with press-wire signals.

Loads `data/sbir_ma_events.jsonl`, builds a watchlist of company names, polls
press-wire feeds via `SyncPressWireClient`, and merges any matched press
releases back into each event as `press_wire_signals`. Writes the result to
`data/enriched_sbir_ma_events.jsonl`.

The press-wire client does substring matching across all monitored feeds, so
watchlist size has little effect on poll latency — the limiting factor is
feed size, not watchlist size.

Inputs:
  data/sbir_ma_events.jsonl
Outputs:
  data/enriched_sbir_ma_events.jsonl
"""
from __future__ import annotations

import asyncio
import json
from collections import defaultdict

from sbir_etl.enrichers.sync_wrappers import SyncPressWireClient


async def main() -> None:
    # 1. Load existing M&A events and create a watchlist of company names
    ma_events: list[dict] = []
    watchlist: set[str] = set()
    try:
        with open("data/sbir_ma_events.jsonl") as f:
            for line in f:
                try:
                    data = json.loads(line)
                    ma_events.append(data)
                    name = data.get("company_name")
                    if name:
                        watchlist.add(name)
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        print("Error: data/sbir_ma_events.jsonl not found.")
        return

    print(f"Loaded {len(ma_events)} M&A events. Watchlist size: {len(watchlist)}")

    # 2. Poll Press Wire feeds for these companies
    print("Polling Press Wire feeds... (this may take a minute)")
    press_hits = []
    try:
        with SyncPressWireClient() as client:
            client.set_watchlist(list(watchlist))
            press_hits = client.poll()
    except Exception as e:
        print(f"Error polling press wire: {e}")

    print(f"Found {len(press_hits)} press release matches.")

    # 3. Index press hits by matched company name
    company_press: dict[str, list[dict]] = defaultdict(list)
    for hit in press_hits:
        company_press[hit.matched_company].append({
            "title": hit.title,
            "link": hit.link,
            "published": hit.published,
            "summary": hit.summary,
            "source": hit.source,
        })

    # 4. Merge press signals into each event
    enriched_events = []
    for event in ma_events:
        company = event.get("company_name")
        if company in company_press:
            event["press_wire_signals"] = company_press[company]
            event["signal_count"] = event.get("signal_count", 0) + 1
            event["enriched"] = True
        else:
            event["press_wire_signals"] = []
            event["enriched"] = False
        enriched_events.append(event)

    # 5. Write enriched output
    output_path = "data/enriched_sbir_ma_events.jsonl"
    with open(output_path, "w") as f:
        for event in enriched_events:
            f.write(json.dumps(event) + "\n")

    print(f"Successfully wrote enriched data to {output_path}")
    enriched_count = sum(1 for e in enriched_events if e["enriched"])
    print(f"Enriched {enriched_count} out of {len(ma_events)} events with press wire data.")


if __name__ == "__main__":
    asyncio.run(main())
