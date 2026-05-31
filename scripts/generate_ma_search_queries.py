#!/usr/bin/env python3
"""Generate web-search queries for unverified M&A candidates.

Reads `data/sbir_ma_events.jsonl`, picks rows that have an acquirer claim but
no Form D detail backing it, and emits a CSV of search queries to feed into
`ma_discovery_orchestrator.py`. Company names are normalized (corporate
suffixes stripped) to widen recall.

Inputs:
  data/sbir_ma_events.jsonl  — one JSON M&A candidate per line
Output:
  data/ma_search_queries.csv — columns: company_name, acquirer, query
"""
from __future__ import annotations

import csv
import json
import re


def clean_name(name: str | None) -> str:
    """Uppercase and strip common corporate suffixes for fuzzier matching."""
    if not name:
        return ""
    suffixes = [
        r"\bINC\.?\b",
        r"\bLLC\b",
        r"\bCORP\.?\b",
        r"\bLTD\.?\b",
        r"\bCORPORATION\b",
        r"\bCOMPANY\b",
        r"\bCO\.?\b",
        r"\bPLC\b",
        r"/DE/",
    ]
    cleaned = name.upper()
    for s in suffixes:
        cleaned = re.sub(s, "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip().rstrip(",")


def generate_queries(company_name: str | None, acquirer: str | None) -> list[str]:
    """Return four web-search query strings exploring the (company, acquirer) pair."""
    if not company_name or not acquirer:
        return []
    c_name = clean_name(company_name)
    a_name = clean_name(acquirer)
    return [
        f'"{c_name}" acquired by "{a_name}" press release',
        f'"{c_name}" "{a_name}" merger announcement',
        f'"{c_name}" bought by "{a_name}"',
        f'"{a_name}" announces acquisition of "{c_name}"',
    ]


def main() -> None:
    candidates = []
    with open("data/sbir_ma_events.jsonl") as f:
        for line in f:
            try:
                data = json.loads(line)
                if not data.get("form_d_detail") and data.get("acquirer"):
                    candidates.append({
                        "company_name": data.get("company_name"),
                        "acquirer": data.get("acquirer"),
                        "confidence": data.get("confidence"),
                    })
            except json.JSONDecodeError:
                continue

    print(f"Generating queries for {len(candidates)} candidates...")

    output_path = "data/ma_search_queries.csv"
    with open(output_path, "w", newline="") as csvfile:
        fieldnames = ["company_name", "acquirer", "query"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for cand in candidates:
            for q in generate_queries(cand["company_name"], cand["acquirer"]):
                writer.writerow({
                    "company_name": cand["company_name"],
                    "acquirer": cand["acquirer"],
                    "query": q,
                })

    print(f"Queries saved to {output_path}")


if __name__ == "__main__":
    main()
