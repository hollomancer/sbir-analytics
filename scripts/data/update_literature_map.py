#!/usr/bin/env python3
"""Refresh the committed OpenAlex literature map (exploratory, non-citable).

Epistemic tier: exploratory. Regenerates ``sbir_literature_map.csv`` and a
machine-written ``refresh_status.md``. Does **not** rewrite the authored
narrative memos (``sbir_literature_map.md``, ``citation_gap_memo.md``).

Existing rows keep their human/machine relevance and area labels. New works
are classified with deterministic title keywords only.

Usage::

    uv run python scripts/data/update_literature_map.py
    uv run python scripts/data/update_literature_map.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sbir_etl.enrichers.openalex_client import OpenAlexClient, _last_path_segment

EPISTEMIC_TIER = "exploratory"

MAP_COLUMNS = (
    "relevance",
    "area",
    "year",
    "first_author",
    "n_authors",
    "title",
    "venue",
    "type",
    "citations",
    "fwci",
    "open_access",
    "doi",
    "openalex_id",
)

DEFAULT_MAP = Path("docs/research/literature-map/sbir_literature_map.csv")
DEFAULT_STATUS = Path("docs/research/literature-map/refresh_status.md")
YEAR_START = 2019
PER_PAGE = 50
MAX_PAGES_PER_QUERY = 4  # 200 hits/query ceiling for CI
ID_BATCH = 50

ANCHOR_DOIS = (
    "10.1257/aer.20150491",  # Howell 2017
    "10.1257/aer.20201851",  # Myers & Lanahan 2022
)

# Direct SBIR/STTR searches plus one query per research-question area A–F.
SEARCH_QUERIES: tuple[tuple[str, str], ...] = (
    ("direct", "SBIR STTR"),
    ("direct", '"Small Business Innovation Research"'),
    ("direct", '"Small Business Technology Transfer"'),
    ("A", "defense innovation SBIR OR FOCI acquisition small business"),
    ("B", "SBIR commercialization OR SBIR Phase III"),
    ("C", "R&D subsidy spillover patent government"),
    ("D", "SBIR employment jobs public R&D"),
    ("E", "SBIR evaluation procurement contest"),
    ("F", "SBIR venture capital entrepreneurial finance"),
)

CORE_RE = re.compile(
    r"\bsbir\b|\bsttr\b|small business innovation research|"
    r"small business technology transfer",
    re.IGNORECASE,
)
AREA_KEYWORDS: dict[str, tuple[str, ...]] = {
    "A": (
        "defense",
        "defence",
        "foci",
        "industrial base",
        "procurement",
        "military",
        "national security",
    ),
    "B": ("commercializ", "phase iii", "phase 3", "transition", "spinoff", "spin-off"),
    "C": ("spillover", "patent", "knowledge", "citation"),
    "D": ("employment", "jobs", "wage", "economic impact", "gdp"),
    "E": ("evaluat", "contest", "program management", "award mill"),
    "F": ("venture", "form d", "private capital", "entrepreneurial finance", "ipo"),
}


def parse_work(work: dict[str, Any]) -> dict[str, Any]:
    """Flatten one OpenAlex work into the map CSV schema (labels empty)."""
    authorships = work.get("authorships") or []
    first = ""
    if authorships:
        first = str((authorships[0].get("author") or {}).get("display_name") or "")
    source = (work.get("primary_location") or {}).get("source") or {}
    doi_raw = work.get("doi") or ""
    doi = str(doi_raw).replace("https://doi.org/", "").strip()
    oa = work.get("open_access") or {}
    fwci = work.get("fwci")
    year = work.get("publication_year")
    return {
        "relevance": "",
        "area": "",
        "year": "" if year is None else str(int(year)),
        "first_author": first,
        "n_authors": str(len(authorships)),
        "title": str(work.get("display_name") or work.get("title") or ""),
        "venue": str(source.get("display_name") or ""),
        "type": str(work.get("type") or ""),
        "citations": str(int(work.get("cited_by_count") or 0)),
        "fwci": "" if fwci is None else str(fwci),
        "open_access": str(bool(oa.get("is_oa"))),
        "doi": doi,
        "openalex_id": _last_path_segment(work.get("id")) or "",
    }


def classify_new_work(title: str, hint_area: str | None = None) -> tuple[str, str] | None:
    """Return (relevance, area) for a previously unseen work, or None to drop."""
    text = title or ""
    if not text.strip():
        return None
    is_core = CORE_RE.search(text) is not None
    hits = {area: sum(1 for kw in kws if kw in text.lower()) for area, kws in AREA_KEYWORDS.items()}
    scored = [area for area, n in hits.items() if n > 0]
    if hint_area in AREA_KEYWORDS and hint_area not in scored:
        scored.append(hint_area)
    if not is_core and not scored:
        return None
    if hint_area in scored:
        area = hint_area
    else:
        area = max(hits, key=lambda a: (hits[a], -ord(a))) if scored else "E"
    return ("core" if is_core else "adjacent", area)


def load_map(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_map(path: Path, rows: list[dict[str, str]]) -> None:
    ordered = sorted(
        rows,
        key=lambda r: (
            r.get("relevance", ""),
            r.get("area", ""),
            r.get("year", ""),
            r.get("openalex_id", ""),
        ),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(MAP_COLUMNS), extrasaction="ignore")
        writer.writeheader()
        for row in ordered:
            writer.writerow({col: row.get(col, "") for col in MAP_COLUMNS})


def merge_rows(
    existing: list[dict[str, str]],
    incoming: list[dict[str, str]],
    *,
    hint_area: str | None = None,
) -> tuple[list[dict[str, str]], int]:
    """Update metadata for known IDs; append newly classified works."""
    by_id = {row["openalex_id"]: dict(row) for row in existing if row.get("openalex_id")}
    added = 0
    meta_fields = (
        "year",
        "first_author",
        "n_authors",
        "title",
        "venue",
        "type",
        "citations",
        "fwci",
        "open_access",
        "doi",
    )
    for work in incoming:
        oid = work.get("openalex_id") or ""
        if not oid:
            continue
        if oid in by_id:
            for field in meta_fields:
                if work.get(field) not in {None, ""}:
                    by_id[oid][field] = work[field]
            continue
        labels = classify_new_work(work.get("title") or "", hint_area=hint_area)
        if labels is None:
            continue
        relevance, area = labels
        work["relevance"] = relevance
        work["area"] = area
        by_id[oid] = work
        added += 1
    return list(by_id.values()), added


async def _works_pages(
    client: OpenAlexClient,
    params: dict[str, Any],
    *,
    max_pages: int = MAX_PAGES_PER_QUERY,
) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    cursor = "*"
    for _ in range(max_pages):
        payload = dict(params)
        payload["per_page"] = PER_PAGE
        payload["cursor"] = cursor
        data = await client.search_works(payload)
        results = data.get("results") or []
        pages.extend(work for work in results if isinstance(work, dict))
        cursor = (data.get("meta") or {}).get("next_cursor")
        if not results or not cursor:
            break
    return pages


async def refresh(
    *,
    map_path: Path,
    status_path: Path,
    year_end: int,
    mailto: str | None,
    dry_run: bool,
) -> dict[str, Any]:
    existing = load_map(map_path)
    year_filter = f"publication_year:{YEAR_START}-{year_end}"
    query_counts: dict[str, int] = {}
    added_total = 0

    client = OpenAlexClient(mailto=mailto)
    try:
        for hint, query in SEARCH_QUERIES:
            works = await _works_pages(
                client,
                {"search": query, "filter": year_filter},
            )
            parsed = [parse_work(w) for w in works]
            query_counts[f"search:{hint}:{query[:40]}"] = len(parsed)
            existing, added = merge_rows(
                existing, parsed, hint_area=hint if hint in AREA_KEYWORDS else None
            )
            added_total += added

        for doi in ANCHOR_DOIS:
            cited = await _works_pages(
                client,
                {"filter": f"cites:doi:{doi},{year_filter}"},
            )
            parsed = [parse_work(w) for w in cited]
            query_counts[f"cites:{doi}"] = len(parsed)
            existing, added = merge_rows(existing, parsed)
            added_total += added

        known_ids = [row["openalex_id"] for row in existing if row.get("openalex_id")]
        refreshed = 0
        for i in range(0, len(known_ids), ID_BATCH):
            batch = known_ids[i : i + ID_BATCH]
            joined = "|".join(batch)
            data = await client.search_works(
                {"filter": f"openalex_id:{joined}", "per_page": min(len(batch), PER_PAGE)}
            )
            parsed = [parse_work(w) for w in (data.get("results") or []) if isinstance(w, dict)]
            existing, _ = merge_rows(existing, parsed)
            refreshed += len(parsed)
    finally:
        await client.aclose()

    status = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "existing_before": len(load_map(map_path)) if map_path.exists() else 0,
        "existing_after": len(existing),
        "new_works_classified": added_total,
        "ids_refreshed": refreshed,
        "query_counts": query_counts,
        "year_window": f"{YEAR_START}-{year_end}",
    }
    if not dry_run:
        write_map(map_path, existing)
        _write_status(status_path, status, existing)
    return status


def _write_status(path: Path, status: dict[str, Any], rows: list[dict[str, str]]) -> None:
    counts = Counter((row.get("relevance", ""), row.get("area", "")) for row in rows)
    lines = [
        "# Literature map refresh status",
        "",
        "Machine-written by `scripts/data/update_literature_map.py`. Exploratory.",
        "Does not replace `sbir_literature_map.md` or `citation_gap_memo.md`.",
        "",
        f"- Generated at: `{status['generated_at']}`",
        f"- Year window: `{status['year_window']}`",
        f"- Rows after merge: **{status['existing_after']}**",
        f"- New works classified this run: **{status['new_works_classified']}**",
        f"- Existing OpenAlex IDs metadata-refreshed: **{status['ids_refreshed']}**",
        "",
        "## Counts by relevance × area",
        "",
        "| relevance | area | n |",
        "|---|---|---|",
    ]
    for (relevance, area), n in sorted(counts.items()):
        lines.append(f"| {relevance} | {area} | {n} |")
    lines.extend(["", "## Query hit counts", "", "| query | hits |", "|---|---|"])
    for name, n in status["query_counts"].items():
        lines.append(f"| `{name}` | {n} |")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--status", type=Path, default=DEFAULT_STATUS)
    parser.add_argument("--year-end", type=int, default=datetime.now(UTC).year)
    parser.add_argument(
        "--mailto", default=None, help="OpenAlex polite-pool email (else OPENALEX_MAILTO)"
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    status = asyncio.run(
        refresh(
            map_path=args.map,
            status_path=args.status,
            year_end=args.year_end,
            mailto=args.mailto,
            dry_run=args.dry_run,
        )
    )
    print(
        f"literature map: {status['existing_after']} rows, "
        f"{status['new_works_classified']} new, "
        f"{status['ids_refreshed']} refreshed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
