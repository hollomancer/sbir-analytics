"""Generate web-search queries for Form-D-missing M&A candidates.

Company names are normalized through ``sbir_etl.identity`` with
``CompanyNameProfile.RECIPIENT_V1`` (suffix-stripping) so query strings
do not carry Inc/LLC/Corp tokens.

Usage::

    python -m sbir_etl.enrichers.ma_discovery.queries
"""

from __future__ import annotations

import argparse
import csv
import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from sbir_etl.identity import CompanyNameProfile, normalize_company_name


DEFAULT_EVENTS_PATH = Path("data/sbir_ma_events.jsonl")
DEFAULT_QUERIES_PATH = Path("data/ma_search_queries.csv")
QUERY_CSV_FIELDS = ("company_name", "acquirer", "query")


def _clean_name(name: str | None) -> str:
    """Normalize a company name with the suffix-stripping recipient profile."""
    if not name:
        return ""
    return normalize_company_name(name, profile=CompanyNameProfile.RECIPIENT_V1)


def generate_queries(company_name: str | None, acquirer: str | None) -> list[str]:
    """Return four web-search query strings for the (company, acquirer) pair."""
    if not company_name or not acquirer:
        return []
    c_name = _clean_name(company_name)
    a_name = _clean_name(acquirer)
    if not c_name or not a_name:
        return []
    return [
        f'"{c_name}" acquired by "{a_name}" press release',
        f'"{c_name}" "{a_name}" merger announcement',
        f'"{c_name}" bought by "{a_name}"',
        f'"{a_name}" announces acquisition of "{c_name}"',
    ]


def is_query_candidate(event: Mapping[str, Any]) -> bool:
    """True when the event has an acquirer and no Form D detail."""
    return bool(event.get("acquirer")) and not event.get("form_d_detail")


def query_rows_from_events(events: Iterable[Mapping[str, Any]]) -> list[dict[str, str]]:
    """Build CSV rows for Form-D-missing events that name an acquirer."""
    rows: list[dict[str, str]] = []
    for event in events:
        if not is_query_candidate(event):
            continue
        company_name = event.get("company_name")
        acquirer = event.get("acquirer")
        for query in generate_queries(company_name, acquirer):
            rows.append(
                {
                    "company_name": str(company_name),
                    "acquirer": str(acquirer),
                    "query": query,
                }
            )
    return rows


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


def write_query_csv(path: Path, rows: Sequence[Mapping[str, str]]) -> None:
    """Write ``company_name,acquirer,query`` rows to ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(QUERY_CSV_FIELDS))
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row[field] for field in QUERY_CSV_FIELDS})


def build_query_csv(events: Iterable[Mapping[str, Any]], output_path: Path) -> int:
    """Select candidates, generate queries, and write a CSV. Return row count."""
    rows = query_rows_from_events(events)
    write_query_csv(output_path, rows)
    return len(rows)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate M&A search-query CSV rows")
    parser.add_argument("--input", type=Path, default=DEFAULT_EVENTS_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_QUERIES_PATH)
    args = parser.parse_args(argv)
    events = load_ma_events(args.input)
    count = build_query_csv(events, args.output)
    print(f"Wrote {count} queries to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
