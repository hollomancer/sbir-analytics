#!/usr/bin/env python3
"""Refresh the committed literature map (exploratory, non-citable).

Epistemic tier: exploratory. Regenerates ``sbir_literature_map.csv`` and a
machine-written ``refresh_status.md``. Does **not** rewrite the authored
narrative memos (``sbir_literature_map.md``, ``citation_gap_memo.md``).

Existing rows keep their human/machine relevance and area labels. New works
are classified with deterministic title keywords only.

OpenAlex covers journals well and National Academies Press books when they
are indexed. GAO, CRS, ITIF, and other grey sources are pulled from public
RSS/Atom feeds and stored under synthetic ids (``gao:…``, ``nap:…``, …).

Usage::

    uv run python scripts/data/update_literature_map.py
    uv run python scripts/data/update_literature_map.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from typing import Any, NamedTuple
from urllib.parse import urlparse

import httpx

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
USER_AGENT = (
    "sbir-analytics-literature-map (https://github.com/hollomancer/sbir-analytics; exploratory)"
)

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

# OpenAlex source ids for grey publishers that actually index SBIR titles.
# NASEM Press eBooks: S4306463641. GAO/CRS/CSIS/ITIF have no usable recent
# SBIR coverage in OpenAlex (checked 2026-08); those use RSS instead.
OPENALEX_SOURCE_QUERIES: tuple[tuple[str, str, str], ...] = (("E", "NASEM", "S4306463641"),)


class RssSource(NamedTuple):
    prefix: str
    venue: str
    hint_area: str
    url: str
    first_author: str
    work_type: str


RSS_SOURCES: tuple[RssSource, ...] = (
    RssSource(
        prefix="gao",
        venue="U.S. Government Accountability Office",
        hint_area="E",
        url="https://www.gao.gov/rss/reports.xml",
        first_author="GAO",
        work_type="report",
    ),
    RssSource(
        prefix="nap",
        venue="National Academies Press",
        hint_area="E",
        url="https://nap.nationalacademies.org/rss/",
        first_author="NASEM",
        work_type="book",
    ),
    RssSource(
        prefix="crs",
        venue="Congressional Research Service",
        hint_area="E",
        url="https://www.everycrsreport.com/rss.xml",
        first_author="CRS",
        work_type="report",
    ),
    RssSource(
        prefix="itif",
        venue="Information Technology and Innovation Foundation",
        hint_area="D",
        url="https://itif.org/feed",
        first_author="ITIF",
        work_type="report",
    ),
)

CORE_RE = re.compile(
    r"\bsbir\b|\bsttr\b|small business innovation research|"
    r"small business technology transfer|"
    r"small business research program",
    re.IGNORECASE,
)
# RSS feeds are unfiltered institutional streams; keep only SBIR-adjacent titles.
GREY_KEEP_RE = re.compile(
    r"\bsbir\b|\bsttr\b|"
    r"small business innovation research|"
    r"small business technology transfer|"
    r"small business research program|"
    r"\bphase iii\b|"
    r"\bfoci\b|foreign ownership|"
    r"defense industrial base|defence industrial base|"
    r"award mill",
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
_HTML_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_OPENALEX_WORK_ID_RE = re.compile(r"^W\d+$")


def is_openalex_work_id(oid: str) -> bool:
    return _OPENALEX_WORK_ID_RE.fullmatch(oid or "") is not None


def openalex_ids_for_refresh(rows: list[dict[str, str]]) -> list[str]:
    """IDs that OpenAlex can resolve; skip synthetic grey keys (gao:, nap:, …)."""
    return [row["openalex_id"] for row in rows if is_openalex_work_id(row.get("openalex_id") or "")]


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


def _plain(text: str) -> str:
    return _WS_RE.sub(" ", _HTML_RE.sub(" ", unescape(text or ""))).strip()


def parse_feed_year(raw: str) -> str:
    """Year from RSS pubDate or Atom published/updated; empty if unparseable."""
    text = (raw or "").strip()
    if not text:
        return ""
    try:
        return str(parsedate_to_datetime(text).year)
    except (TypeError, ValueError, OverflowError):
        pass
    try:
        return str(datetime.fromisoformat(text).year)
    except ValueError:
        pass
    match = re.search(r"(?:19|20)\d{2}", text)
    return match.group(0) if match else ""


def synthetic_id(prefix: str, link: str, title: str) -> str:
    """Stable grey-literature key stored in the openalex_id column."""
    if prefix == "gao":
        match = re.search(r"gao-\d{2}-\d+", link, re.I)
        if match:
            return f"gao:{match.group(0).upper()}"
    if prefix == "crs":
        match = re.search(r"/reports/([A-Za-z]{1,3}\d+)\.html", link)
        if match:
            return f"crs:{match.group(1).upper()}"
    if prefix == "nap":
        match = re.search(r"/catalog/(\d+)", link)
        if match:
            return f"nap:{match.group(1)}"
    slug = urlparse(link).path.rstrip("/").rsplit("/", 1)[-1]
    slug = re.sub(r"[^a-z0-9-]+", "-", slug.lower()).strip("-")[:80]
    if not slug:
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:80]
    return f"{prefix}:{slug or 'unknown'}"


def _local_tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_feed(xml_text: str) -> list[dict[str, str]]:
    """Parse RSS 2.0 or Atom XML into title/link/description/published dicts."""
    text = xml_text.lstrip("\ufeff")
    text = re.sub(r"^<\?xml[^?]*\?>", "", text, count=1).lstrip()
    root = ET.fromstring(text)
    return [_parse_feed_entry(el) for el in root.iter() if _local_tag(el.tag) in {"item", "entry"}]


def _parse_feed_entry(el: ET.Element) -> dict[str, str]:
    fields = {
        "title": "",
        "link": "",
        "description": "",
        "published": "",
        "guid": "",
        "creator": "",
    }
    for child in el:
        local = _local_tag(child.tag)
        text = (child.text or "").strip()
        if local == "title" and text:
            fields["title"] = text
        elif local == "link":
            href = (child.attrib.get("href") or text).strip()
            rel = child.attrib.get("rel", "alternate")
            if href and (not fields["link"] or rel == "alternate"):
                fields["link"] = href
        elif local in {"description", "summary", "content"} and text:
            if not fields["description"]:
                fields["description"] = text
        elif local in {"pubDate", "published", "updated", "date"} and text:
            if not fields["published"]:
                fields["published"] = text
        elif local in {"guid", "id"} and text:
            fields["guid"] = text
        elif local in {"creator", "author"}:
            name = text
            if not name:
                for sub in child:
                    if _local_tag(sub.tag) == "name" and (sub.text or "").strip():
                        name = sub.text.strip()
                        break
            if name and not fields["creator"]:
                fields["creator"] = name
    return fields


def feed_entry_to_row(entry: dict[str, str], source: RssSource) -> dict[str, str] | None:
    """Classify one RSS/Atom entry; drop off-topic or pre-window items."""
    title = _plain(entry.get("title") or "")
    # Title only: GAO abstracts often mention "defense industrial base" in passing.
    if not title or GREY_KEEP_RE.search(title) is None:
        return None
    year = parse_feed_year(entry.get("published") or "")
    if year and int(year) < YEAR_START:
        return None
    labels = classify_new_work(title)
    if labels is None:
        area = source.hint_area if source.hint_area in AREA_KEYWORDS else "E"
        labels = ("adjacent", area)
    link = entry.get("link") or ""
    first = (entry.get("creator") or "").strip() or source.first_author
    relevance, area = labels
    return {
        "relevance": relevance,
        "area": area,
        "year": year,
        "first_author": first,
        "n_authors": "1",
        "title": title,
        "venue": source.venue,
        "type": source.work_type,
        "citations": "",
        "fwci": "",
        "open_access": "True",
        "doi": "",
        "openalex_id": synthetic_id(source.prefix, link, title),
    }


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


def _norm_doi(value: str | None) -> str:
    return (value or "").replace("https://doi.org/", "").strip().lower()


def _norm_title(value: str | None) -> str:
    return _WS_RE.sub(" ", (value or "").strip().lower())


def merge_rows(
    existing: list[dict[str, str]],
    incoming: list[dict[str, str]],
    *,
    hint_area: str | None = None,
) -> tuple[list[dict[str, str]], int]:
    """Update metadata for known IDs; append newly classified works.

    Dedupes on OpenAlex/synthetic id, DOI, and normalized title so a later
    OpenAlex hit can attach to a grey RSS stub without creating a second row.
    """
    by_id: dict[str, dict[str, str]] = {}
    doi_index: dict[str, str] = {}
    title_index: dict[str, str] = {}

    def remember(row: dict[str, str]) -> None:
        oid = row.get("openalex_id") or ""
        if not oid:
            return
        by_id[oid] = row
        doi = _norm_doi(row.get("doi"))
        if doi:
            doi_index[doi] = oid
        title = _norm_title(row.get("title"))
        if title:
            title_index[title] = oid

    for row in existing:
        if row.get("openalex_id"):
            remember(dict(row))

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
        work = dict(work)
        oid = work.get("openalex_id") or ""
        if not oid:
            continue
        doi = _norm_doi(work.get("doi"))
        title = _norm_title(work.get("title"))
        target = oid if oid in by_id else None
        if target is None and doi:
            target = doi_index.get(doi)
        if target is None and title:
            target = title_index.get(title)
        if target is not None:
            stored = by_id[target]
            fill_blanks_only = not is_openalex_work_id(oid) and is_openalex_work_id(target)
            for field in meta_fields:
                value = work.get(field)
                if value in {None, ""}:
                    continue
                if fill_blanks_only and stored.get(field) not in {None, ""}:
                    continue
                stored[field] = value
            if is_openalex_work_id(oid) and not is_openalex_work_id(target):
                stored["openalex_id"] = oid
                del by_id[target]
                remember(stored)
            continue
        incoming_rel = work.get("relevance") or ""
        incoming_area = work.get("area") or ""
        if incoming_rel and incoming_area:
            labels: tuple[str, str] | None = (incoming_rel, incoming_area)
        else:
            labels = classify_new_work(work.get("title") or "", hint_area=hint_area)
        if labels is None:
            continue
        relevance, area = labels
        work["relevance"] = relevance
        work["area"] = area
        remember(work)
        added += 1
    return list(by_id.values()), added


async def resolve_doi_work_id(client: OpenAlexClient, doi: str) -> str:
    """Resolve a DOI to an OpenAlex work id (``W…``).

    The ``cites`` filter only accepts work ids, not ``doi:`` values.
    """
    data = await client.search_works({"filter": f"doi:{doi}", "per_page": 1})
    results = data.get("results") or []
    first = results[0] if results and isinstance(results[0], dict) else None
    oid = _last_path_segment((first or {}).get("id")) or ""
    if not is_openalex_work_id(oid):
        raise RuntimeError(f"OpenAlex returned no work id for DOI {doi}")
    return oid


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


async def fetch_rss_rows() -> list[tuple[RssSource, list[dict[str, str]]]]:
    """Download grey-literature feeds. One dead feed does not abort the run."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml",
    }
    out: list[tuple[RssSource, list[dict[str, str]]]] = []
    async with httpx.AsyncClient(timeout=30.0, headers=headers, follow_redirects=True) as http:
        for source in RSS_SOURCES:
            try:
                response = await http.get(source.url)
                response.raise_for_status()
                rows = [
                    row
                    for entry in parse_feed(response.text)
                    if (row := feed_entry_to_row(entry, source)) is not None
                ]
                out.append((source, rows))
            except (httpx.HTTPError, ET.ParseError, OSError) as exc:
                print(f"warning: {source.prefix} RSS failed: {exc}", file=sys.stderr)
                out.append((source, []))
    return out


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

        for hint, label, source_id in OPENALEX_SOURCE_QUERIES:
            works = await _works_pages(
                client,
                {
                    "search": "SBIR",
                    "filter": f"primary_location.source.id:{source_id},{year_filter}",
                },
            )
            parsed = [parse_work(w) for w in works]
            query_counts[f"source:{label}:{source_id}"] = len(parsed)
            existing, added = merge_rows(existing, parsed, hint_area=hint)
            added_total += added

        for doi in ANCHOR_DOIS:
            work_id = await resolve_doi_work_id(client, doi)
            cited = await _works_pages(
                client,
                {"filter": f"cites:{work_id},{year_filter}"},
            )
            parsed = [parse_work(w) for w in cited]
            query_counts[f"cites:{work_id}"] = len(parsed)
            existing, added = merge_rows(existing, parsed)
            added_total += added

        for source, rows in await fetch_rss_rows():
            query_counts[f"rss:{source.prefix}"] = len(rows)
            existing, added = merge_rows(existing, rows, hint_area=source.hint_area)
            added_total += added

        known_ids = openalex_ids_for_refresh(existing)
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
