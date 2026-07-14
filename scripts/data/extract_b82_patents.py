#!/usr/bin/env python3
"""
Extract USPTO CPC patents with assignees and dates, filtered to a CPC range.

Streams the PatentsView PVGPATDIS zip archives without extracting them, filters
~60M CPC rows to the requested CPC prefixes, and joins assignee organizations
and grant dates for the matched patents. Output feeds Method C of the tech-area
cohort analysis (build_tech_area_cohort.py).

Defaults reproduce the original nanotech B82 extract exactly (subclass field,
``B82`` prefix, ``b82_patents.csv``). Other tech areas parameterize the CPC
range — e.g. quantum information science (G06N10, a CPC *group* rather than a
subclass) via ``--cpc-field cpc_group --cpc-prefixes G06N10``.

CPC prefix levels:
  B82B / B82Y — nanostructures + their applications (matched at the subclass level)
  G06N10      — quantum computing (matched at the group level, cpc_group column)

Inputs (download via: python scripts/data/download_uspto.py --dataset patentsview
        --table {cpc,assignee,patent,application} --local data/raw/uspto/patentsview):
  data/raw/uspto/patentsview/g_cpc_current.tsv.zip
  data/raw/uspto/patentsview/g_assignee_disambiguated.tsv.zip
  data/raw/uspto/patentsview/g_patent.tsv.zip
  data/raw/uspto/patentsview/g_application.tsv.zip   — filing dates (capability-vs-outcome timing)

Outputs:
  <--out> (default data/processed/uspto/b82_patents.csv) — one row per (patent, org assignee)

Usage:
  python scripts/data/extract_b82_patents.py            # nanotech B82 (default)
  python scripts/data/extract_b82_patents.py \\
      --cpc-field cpc_group --cpc-prefixes G06N10 \\
      --out data/processed/uspto/g06n10_patents.csv     # quantum G06N10
"""

import argparse
import csv
import io
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RAW = REPO / "data/raw/uspto/patentsview"
OUT_CSV = REPO / "data/processed/uspto/b82_patents.csv"


def cpc_matches(symbol: str, prefixes: tuple[str, ...]) -> bool:
    """True if the CPC symbol starts with any requested prefix."""
    return any(symbol.startswith(p) for p in prefixes)


def tsv_rows(zip_path: Path):
    """Yield (header_index, row) tuples streaming a single-member TSV zip."""
    z = zipfile.ZipFile(zip_path)
    member = z.infolist()[0].filename
    with z.open(member) as f:
        reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8", newline=""), delimiter="\t")
        header = next(reader)
        idx = {c: i for i, c in enumerate(header)}
        for row in reader:
            yield idx, row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cpc-prefixes", nargs="+", default=["B82"],
        help="CPC symbol prefixes to keep (default: B82 = nanotech B82B/B82Y)",
    )
    parser.add_argument(
        "--cpc-field", default="cpc_subclass",
        help="g_cpc_current column to prefix-match (default: cpc_subclass; "
             "use cpc_group for group-level ranges like G06N10)",
    )
    parser.add_argument(
        "--out", type=Path, default=OUT_CSV,
        help=f"Output CSV path (default: {OUT_CSV})",
    )
    parser.add_argument(
        "--raw", type=Path, default=RAW,
        help=f"PatentsView raw dir (default: {RAW})",
    )
    args = parser.parse_args(argv)
    prefixes = tuple(args.cpc_prefixes)
    label = "/".join(prefixes)

    required = {
        "cpc": args.raw / "g_cpc_current.tsv.zip",
        "assignee": args.raw / "g_assignee_disambiguated.tsv.zip",
        "patent": args.raw / "g_patent.tsv.zip",
        "application": args.raw / "g_application.tsv.zip",
    }
    for table, p in required.items():
        if not p.exists():
            print(
                f"ERROR: {p} not found — run scripts/data/download_uspto.py "
                f"--dataset patentsview --table {table} --local {args.raw}",
                file=sys.stderr,
            )
            return 1

    print(f"Pass 1/4: scanning g_cpc_current[{args.cpc_field}] for {label}...")
    subclasses: dict[str, set[str]] = defaultdict(set)
    rows_seen = 0
    for idx, row in tsv_rows(required["cpc"]):
        rows_seen += 1
        sub = row[idx[args.cpc_field]]
        if cpc_matches(sub, prefixes):
            subclasses[row[idx["patent_id"]]].add(sub)
    b82_ids = set(subclasses)
    print(f"  {rows_seen:,} CPC rows scanned; {len(b82_ids):,} unique {label} patents")

    print("Pass 2/4: joining assignee organizations...")
    org_rows: dict[str, list[tuple[str, str]]] = defaultdict(list)  # patent_id → [(org, type)]
    individual_only = set(b82_ids)
    for idx, row in tsv_rows(required["assignee"]):
        pid = row[idx["patent_id"]]
        if pid not in b82_ids:
            continue
        org = row[idx["disambig_assignee_organization"]].strip()
        if org:
            org_rows[pid].append((org, row[idx["assignee_type"]]))
            individual_only.discard(pid)
    print(
        f"  {len(org_rows):,} B82 patents with ≥1 organization assignee; "
        f"{len(individual_only):,} individual-only or unassigned"
    )

    print("Pass 3/4: joining grant dates and titles...")
    meta: dict[str, tuple[str, str]] = {}
    for idx, row in tsv_rows(required["patent"]):
        pid = row[idx["patent_id"]]
        if pid in b82_ids:
            meta[pid] = (row[idx["patent_date"]], row[idx["patent_title"]][:120])
    print(f"  {len(meta):,} {label} patents matched in g_patent")

    print("Pass 4/4: joining filing dates...")
    filing: dict[str, str] = {}
    for idx, row in tsv_rows(required["application"]):
        pid = row[idx["patent_id"]]
        if pid in b82_ids:
            fd = row[idx["filing_date"]]
            # g_application contains typo'd dates (e.g. year 1074); keep plausible only
            if len(fd) == 10 and "1900" <= fd[:4] <= "2030":
                filing[pid] = fd
    print(f"  {len(filing):,} {label} patents with plausible filing dates")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    n_out = 0
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            ["patent_id", "grant_date", "filing_date", "assignee_organization", "assignee_type",
             "cpc_subclasses", "patent_title"]
        )
        for pid in sorted(org_rows):
            date, title = meta.get(pid, ("", ""))
            for org, a_type in org_rows[pid]:
                w.writerow(
                    [pid, date, filing.get(pid, ""), org, a_type,
                     "|".join(sorted(subclasses[pid])), title]
                )
                n_out += 1
    print(f"  Written: {args.out} ({n_out:,} patent-assignee rows)")

    unique_orgs = {org.upper() for rows in org_rows.values() for org, _ in rows}
    print()
    print("=" * 60)
    print(f"{label} CPC EXTRACTION SUMMARY")
    print("=" * 60)
    print(f"Unique {label} patents:              {len(b82_ids):,}")
    print(f"  with organization assignee:        {len(org_rows):,}")
    print(f"  individual-only / unassigned:      {len(individual_only):,}")
    print(f"Unique assignee organizations:       {len(unique_orgs):,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
