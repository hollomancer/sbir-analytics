#!/usr/bin/env python3
"""
WS6a / T15 — build the firm alias graph for the nanotech cohort + dark firms.

Exact-name matching is the shared false-negative of every firm-level instrument.
This builds `data/processed/firm_aliases.csv` so WS6b can re-run the patent,
trademark, and USAspending matchers under a firm's alternate names.

Sources (reconnaissance 2026-07-12):
  patent_assignment  USPTO ECORSEXC assignor→assignee edges where convey_ty is a
                     name change or merger and one side matches a cohort/dark firm.
                     The rich source: 213k name-changes + 68k mergers nationally.
  shared_uei         USAspending recipient names sharing one UEI (from WS1/WS2
                     caches). Thin and noisy (UEIs are occasionally reused), so
                     these edges REQUIRE corroboration downstream.

Dead / degraded sources, documented not used:
  - PatentsView assignee_id clusters: disambiguation already collapses variants
    to one canonical org string (0 of 293k sampled ids carried >1 name).
  - TRCFECO2 owner_name_change: a coded transaction annotation, not a clean
    old→new name pair; reconstruction deferred (low expected marginal yield).

Inputs:
  data/nano_cohort_keyword.csv, data/nano_dark_firm_liveness.csv   — firm universe
  data/raw/uspto/assignments/{assignor,assignee,assignment_conveyance}.csv.zip
  data/api_cache/usaspending_ws1/*.json, data/api_cache/usaspending_ws2/*.json

Outputs:
  data/processed/firm_aliases.csv   — one row per alias edge

Usage:
  python scripts/data/build_firm_alias_graph.py
"""

import csv
import io
import json
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data"
ASGN = DATA / "raw/uspto/assignments"

sys.path.insert(0, str(REPO))
from sbir_etl.utils.firm_aliases import (  # noqa: E402
    alias_edges_from_shared_uei,
    classify_conveyance,
    make_alias_edge,
)
from sbir_etl.utils.text_normalization import normalize_name  # noqa: E402


def _norm(s: str) -> str:
    return normalize_name(s, remove_suffixes=True)


def tsv_or_csv_rows(zip_path: Path):
    z = zipfile.ZipFile(zip_path)
    with z.open(z.infolist()[0].filename) as f:
        reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8", errors="replace"))
        header = next(reader)
        idx = {c: i for i, c in enumerate(header)}
        for row in reader:
            yield idx, row


def load_firm_universe() -> set[str]:
    """Normalized names of every cohort + dark firm (the alias targets)."""
    norms: set[str] = set()
    csv.field_size_limit(sys.maxsize)
    for path, col in (
        (DATA / "nano_cohort_keyword.csv", "company"),
        (DATA / "nano_dark_firm_liveness.csv", "company"),
    ):
        if path.exists():
            for r in csv.DictReader(open(path, newline="", encoding="utf-8")):
                n = _norm(r[col])
                if n:
                    norms.add(n)
    return norms


def patent_assignment_edges(firms: set[str]) -> list:
    """Alias/merger edges where a cohort firm is the assignor OR assignee."""
    conv_path = ASGN / "assignment_conveyance.csv.zip"
    assignor_path = ASGN / "assignor.csv.zip"
    assignee_path = ASGN / "assignee.csv.zip"
    for p in (conv_path, assignor_path, assignee_path):
        if not p.exists():
            print(f"  SKIP patent_assignment: {p.name} absent "
                  f"(download ECORSEXC/2023 via download_uspto.py --product-file)",
                  file=sys.stderr)
            return []

    print("  conveyance types...")
    relation: dict[str, str] = {}  # rf_id -> namechg|merger (alias only)
    for idx, row in tsv_or_csv_rows(conv_path):
        kind = classify_conveyance(row[idx["convey_ty"]])
        if kind == "alias":
            relation[row[idx["rf_id"]]] = row[idx["convey_ty"]].strip().lower()
    print(f"    {len(relation):,} alias-type (namechg/merger) reels")

    print("  assignors...")
    rf_assignor: dict[str, tuple[str, str, str]] = {}  # rf -> (raw_name, norm, exec_dt)
    for idx, row in tsv_or_csv_rows(assignor_path):
        rf = row[idx["rf_id"]]
        if rf in relation:
            raw = row[idx["or_name"]]
            rf_assignor[rf] = (raw, _norm(raw), row[idx["exec_dt"]])

    print("  assignees...")
    edges = []
    for idx, row in tsv_or_csv_rows(assignee_path):
        rf = row[idx["rf_id"]]
        a = rf_assignor.get(rf)
        if not a:
            continue
        or_raw, or_norm, exec_dt = a
        ee_raw = row[idx["ee_name"]]
        ee_state = row[idx["ee_state"]]
        # Emit an edge only if one endpoint is a firm we care about.
        if or_norm not in firms and _norm(ee_raw) not in firms:
            continue
        edge = make_alias_edge(
            or_raw, ee_raw, source="patent_assignment",
            relation=relation[rf], effective_date=(exec_dt or "")[:10],
            corrob_state=ee_state,
        )
        if edge:
            edges.append(edge)
    return edges


def shared_uei_edges() -> list:
    """Recipient names sharing one UEI, from the WS1/WS2 USAspending caches.

    WS2 records carry a "Recipient UEI" field. WS1 fetched *by* UEI and did not
    store the field, but the cache filename is `{UEI}_{contracts|assistance}.json`
    — so the UEI is the filename prefix and every name in the file shares it.
    """
    uei_names: dict[str, set[str]] = defaultdict(set)
    for cache in ("usaspending_ws1", "usaspending_ws2"):
        d = DATA / "api_cache" / cache
        if not d.exists():
            continue
        for f in d.glob("*.json"):
            try:
                records = json.loads(f.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            # WS1 filename prefix is a 12-char UEI; WS2 filenames are name slugs.
            fname_uei = f.name.split("_")[0]
            file_uei = fname_uei if len(fname_uei) == 12 and fname_uei.isalnum() else None
            for a in records:
                name = a.get("Recipient Name")
                if not name:
                    continue
                uei = (a.get("Recipient UEI") or "").strip() or file_uei
                if uei:
                    uei_names[uei].add(name)
    return alias_edges_from_shared_uei(uei_names)


def main() -> int:
    print("Loading firm universe...")
    firms = load_firm_universe()
    print(f"  {len(firms):,} normalized firm names")

    print("Building patent-assignment edges...")
    pa_edges = patent_assignment_edges(firms)
    print(f"  {len(pa_edges):,} name-change/merger edges touching cohort firms")

    print("Building shared-UEI edges (WS1/WS2 caches)...")
    su_edges = shared_uei_edges()
    print(f"  {len(su_edges):,} shared-UEI edges")

    # Keep only edges where at least one endpoint is a cohort/dark firm, and
    # dedupe on the (firm, alias, source) triple.
    all_edges = pa_edges + su_edges
    seen: set[tuple] = set()
    out = []
    for e in all_edges:
        if e.firm_normalized not in firms and e.alias_normalized not in firms:
            continue
        key = (e.firm_normalized, e.alias_normalized, e.source)
        if key in seen:
            continue
        seen.add(key)
        out.append(e)

    out_csv = DATA / "processed/firm_aliases.csv"
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["firm_normalized", "alias_name", "alias_normalized", "source",
                    "relation", "effective_date", "corrob_state"])
        for e in sorted(out, key=lambda x: (x.firm_normalized, x.alias_normalized)):
            w.writerow([e.firm_normalized, e.alias_name, e.alias_normalized, e.source,
                        e.relation, e.effective_date, e.corrob_state])
    print(f"\nWritten: {out_csv} ({len(out):,} edges)")

    from collections import Counter
    by_source = Counter(e.source for e in out)
    by_rel = Counter(e.relation for e in out)
    firms_with = len({e.firm_normalized for e in out} | {e.alias_normalized for e in out} & firms)
    print(f"  by source: {dict(by_source)}")
    print(f"  by relation: {dict(by_rel)}")
    print(f"  distinct cohort/dark firms with ≥1 alias: "
          f"{len({e.firm_normalized for e in out if e.firm_normalized in firms} | {e.alias_normalized for e in out if e.alias_normalized in firms}):,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
