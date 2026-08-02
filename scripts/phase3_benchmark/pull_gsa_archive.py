#!/usr/bin/env python3
"""Pull and firm-attribute GSA archived Contract-Opportunity notices.

Research utility (specs/phase3-notice-corpus-fusion), not a production source
adapter. Streams the per-fiscal-year archive CSVs from the public
``falextracts`` bucket over plain HTTPS (no AWS credentials; ListObjects is
denied but GetObject is public), keeps only SBIR-mentioning notices, and
attributes each to a seed Phase III firm (see ``notice_matching``). A ~1 GB
yearly file reduces to a small firm-tagged parquet.

Network access is isolated behind an injectable ``opener`` so parsing,
gating, and attribution are testable offline. Every pull is manifested.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from scripts.phase3_benchmark.notice_matching import (
    FirmKey,
    attribute_notice,
    build_firm_keys,
)


ARCHIVE_URL_TEMPLATE = (
    "https://falextracts.s3.amazonaws.com/Contract%20Opportunities/"
    "Archived%20Data/FY{year}_archived_opportunities.csv"
)
USER_AGENT = "sbir-analytics-research/1.0 (Phase III notice corpus)"

# Archive columns kept; Description is the payload, Awardee aids attribution.
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


def load_firm_keys(seed_path: Path) -> list[FirmKey]:
    """Load the firm seed parquet into match keys."""

    seed = pd.read_parquet(seed_path)
    records = [
        {
            "firm": row["firm"],
            "piids": str(row.get("piids") or "").split(";") if row.get("piids") else [],
        }
        for _, row in seed.iterrows()
    ]
    return build_firm_keys(records)


def _default_opener(url: str) -> io.TextIOWrapper:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    response = urllib.request.urlopen(request)  # noqa: S310 - fixed https host
    return io.TextIOWrapper(response, encoding="utf-8", errors="replace", newline="")


def pull_fiscal_year(
    year: int,
    firms: list[FirmKey],
    output_dir: Path,
    *,
    opener: Callable[[str], io.TextIOWrapper] = _default_opener,
) -> dict[str, object]:
    """Stream one fiscal year, attribute SBIR notices, write parquet + manifest entry."""

    url = ARCHIVE_URL_TEMPLATE.format(year=year)
    started = datetime.now(UTC).isoformat()
    rows: list[dict[str, str]] = []
    scanned = 0
    sbir_seen = 0
    with opener(url) as stream:
        for row in csv.DictReader(stream):
            scanned += 1
            description = row.get("Description") or ""
            if "sbir" not in description.lower():
                continue
            sbir_seen += 1
            attribution = attribute_notice(description, row.get("Awardee") or "", firms)
            if attribution is None:
                continue
            firm, rule = attribution
            kept = {column: (row.get(column) or "") for column in KEEP_COLUMNS}
            kept["firm"] = firm
            kept["match_rule"] = rule
            rows.append(kept)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"FY{year}_filtered.parquet"
    frame = pd.DataFrame(rows, columns=[*KEEP_COLUMNS, "firm", "match_rule"])
    frame.to_parquet(output_path, index=False)
    return {
        "fiscal_year": year,
        "url": url,
        "fetched_at": started,
        "rows_scanned": scanned,
        "sbir_notices": sbir_seen,
        "rows_kept": len(rows),
        "match_rule_counts": frame["match_rule"].value_counts().to_dict() if len(frame) else {},
        "output": str(output_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", type=int, nargs="+", required=True)
    parser.add_argument("--seed", type=Path, default=Path("data/derived/phase3_firm_seed.parquet"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/raw/gsa_falextracts"))
    args = parser.parse_args()

    firms = load_firm_keys(args.seed)
    print(f"{len(firms)} seed firms loaded")
    manifest: list[dict[str, object]] = []
    for year in args.years:
        entry = pull_fiscal_year(year, firms, args.output_dir)
        manifest.append(entry)
        print(
            f"FY{year}: scanned {entry['rows_scanned']:,}, SBIR {entry['sbir_notices']:,}, "
            f"attributed {entry['rows_kept']:,} ({entry['match_rule_counts']})"
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
