#!/usr/bin/env python3
"""Pull and filter GSA archived Contract-Opportunity notices for the Phase III corpus.

Research utility (specs/phase3-notice-corpus-fusion), not a production source
adapter. Streams the per-fiscal-year archive CSVs from the public
``falextracts`` bucket over plain HTTPS (no AWS credentials; ListObjects is
denied but GetObject is public) and keeps only rows matching the study's join
keys, so a ~1 GB yearly file reduces to a small filtered parquet.

Network access is isolated behind an injectable ``opener`` so parsing and
filtering are testable offline. Every pull is manifested (URL, bytes read,
rows scanned/kept, fetch time) for provenance.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import urllib.request
from collections.abc import Callable, Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd


ARCHIVE_URL_TEMPLATE = (
    "https://falextracts.s3.amazonaws.com/Contract%20Opportunities/"
    "Archived%20Data/FY{year}_archived_opportunities.csv"
)
USER_AGENT = "sbir-analytics-research/1.0 (Phase III notice corpus)"

# Columns kept from the archive schema (subset; Description is the payload).
KEEP_COLUMNS: tuple[str, ...] = (
    "NoticeId",
    "Title",
    "Sol#",
    "Department/Ind.Agency",
    "Sub-Tier",
    "Office",
    "PostedDate",
    "Type",
    "BaseType",
    "NaicsCode",
    "ClassificationCode",
    "AwardNumber",
    "AwardDate",
    "Awardee",
    "Link",
    "Description",
)

_NKEY_RE = re.compile(r"[^A-Z0-9]")


def normalize_key(value: object) -> str:
    """Collapse an identifier to bare uppercase alphanumerics for joining."""

    return _NKEY_RE.sub("", str(value or "").upper())


def load_join_keys(path: Path) -> frozenset[str]:
    """Load newline-delimited join keys (PIIDs / Sol#s), normalized; >=6 chars."""

    keys = {
        normalize_key(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    return frozenset(key for key in keys if len(key) >= 6)


def row_matches(row: dict[str, str], join_keys: frozenset[str]) -> str | None:
    """Return the matching rule name, or None.

    ``award_number`` / ``sol_number`` are exact normalized-key equality on the
    archive's own key columns — the high-precision joins. ``text_citation``
    catches notices whose description cites a key inline (the J&A pattern).
    """

    award_number = normalize_key(row.get("AwardNumber"))
    if len(award_number) >= 6 and award_number in join_keys:
        return "award_number"
    sol_number = normalize_key(row.get("Sol#"))
    if len(sol_number) >= 6 and sol_number in join_keys:
        return "sol_number"
    description = row.get("Description") or ""
    # Cheap gate before the expensive normalized scan: a J&A citing a prior
    # SBIR identifier always talks about SBIR; most archive rows never do.
    if description and "sbir" in description.lower():
        haystack = normalize_key(description)
        for key in join_keys:
            if key in haystack:
                return "text_citation"
    return None


def filter_stream(
    lines: Iterable[str],
    join_keys: frozenset[str],
) -> Iterator[dict[str, str]]:
    """Yield matching archive rows (KEEP_COLUMNS + match_rule) from a CSV text stream."""

    reader = csv.DictReader(lines)
    for row in reader:
        rule = row_matches(row, join_keys)
        if rule is None:
            continue
        kept = {column: (row.get(column) or "") for column in KEEP_COLUMNS}
        kept["match_rule"] = rule
        yield kept


def _default_opener(url: str) -> io.TextIOWrapper:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    response = urllib.request.urlopen(request)  # noqa: S310 - fixed https host
    return io.TextIOWrapper(response, encoding="utf-8", errors="replace", newline="")


def pull_fiscal_year(
    year: int,
    join_keys: frozenset[str],
    output_dir: Path,
    *,
    opener: Callable[[str], io.TextIOWrapper] = _default_opener,
) -> dict[str, object]:
    """Stream one fiscal year, write the filtered parquet, return a manifest entry."""

    url = ARCHIVE_URL_TEMPLATE.format(year=year)
    started = datetime.now(UTC).isoformat()
    rows: list[dict[str, str]] = []
    scanned = 0
    with opener(url) as stream:
        reader = csv.DictReader(stream)
        for row in reader:
            scanned += 1
            rule = row_matches(row, join_keys)
            if rule is None:
                continue
            kept = {column: (row.get(column) or "") for column in KEEP_COLUMNS}
            kept["match_rule"] = rule
            rows.append(kept)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"FY{year}_filtered.parquet"
    frame = pd.DataFrame(rows, columns=[*KEEP_COLUMNS, "match_rule"])
    frame.to_parquet(output_path, index=False)
    return {
        "fiscal_year": year,
        "url": url,
        "fetched_at": started,
        "rows_scanned": scanned,
        "rows_kept": len(rows),
        "match_rule_counts": frame["match_rule"].value_counts().to_dict() if len(frame) else {},
        "output": str(output_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", type=int, nargs="+", required=True)
    parser.add_argument(
        "--join-keys",
        type=Path,
        required=True,
        help="Newline-delimited PIIDs / Sol#s to keep (normalized before matching).",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("data/raw/gsa_falextracts"))
    args = parser.parse_args()

    join_keys = load_join_keys(args.join_keys)
    print(f"{len(join_keys)} join keys loaded")
    manifest: list[dict[str, object]] = []
    for year in args.years:
        entry = pull_fiscal_year(year, join_keys, args.output_dir)
        manifest.append(entry)
        print(
            f"FY{year}: scanned {entry['rows_scanned']:,} rows, kept {entry['rows_kept']:,} "
            f"({entry['match_rule_counts']})"
        )
    manifest_path = args.output_dir / "pull_manifest.json"
    existing = (
        json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else []
    )
    merged = {entry["fiscal_year"]: entry for entry in [*existing, *manifest]}
    manifest_path.write_text(
        json.dumps([merged[year] for year in sorted(merged)], indent=2), encoding="utf-8"
    )
    print(f"manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
