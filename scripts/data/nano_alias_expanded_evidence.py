#!/usr/bin/env python3
"""
WS6b / T16 — alias-expanded re-check of the dark firms.

For every dark firm, look for commercialization evidence under its ALIASES
(renames / mergers from the firm alias graph), which the exact-name instruments
structurally miss. The recall delta is the set of firms that were negative under
their own name but are shown active under a successor name.

Corroboration rule: patent-assignment namechg/merger edges are documentary
(USPTO recorded the conveyance) and trusted directly. Shared-UEI edges are weak
and are used ONLY when the alias also carries independent evidence here.

Evidence checked under each alias name (exact normalized match):
  trademark  post-2000 registered mark in TRCFECO2/2023
  patent     assignee on ≥1 patent in the PatentsView assignee table
  federal    ≥1 USAspending prime award (name search, cached)

Inputs:
  data/processed/firm_aliases.csv                   — WS6a alias graph
  data/nano_dark_firm_liveness.csv                  — dark firms + own-name evidence
  data/nano_dark_firm_trademarks.csv                — own-name trademark evidence
  data/raw/uspto/trademarks/{owner,case_file}.csv.zip
  data/raw/uspto/patentsview/g_assignee_disambiguated.tsv.zip
  USAspending API (cached: data/api_cache/usaspending_alias/)

Outputs:
  data/nano_alias_expanded_evidence.csv

Usage:
  python scripts/data/nano_alias_expanded_evidence.py [--no-federal]
"""

import argparse
import csv
import importlib.util
import io
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data"

sys.path.insert(0, str(REPO))
from sbir_etl.utils.firm_aliases import build_alias_index  # noqa: E402
from sbir_etl.utils.text_normalization import normalize_name  # noqa: E402

_ws2_spec = importlib.util.spec_from_file_location(
    "nano_ws2", Path(__file__).parent / "nano_ws2_resolve_no_uei.py"
)
ws2 = importlib.util.module_from_spec(_ws2_spec)
_ws2_spec.loader.exec_module(ws2)


class _E:
    """Minimal edge for build_alias_index (needs .firm_normalized/.alias_normalized)."""

    def __init__(self, f, a):
        self.firm_normalized = f
        self.alias_normalized = a


def _norm(s: str) -> str:
    return normalize_name(s, remove_suffixes=True)


def csv_rows(zip_path: Path, delimiter: str = ","):
    z = zipfile.ZipFile(zip_path)
    with z.open(z.infolist()[0].filename) as f:
        reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8", errors="replace"),
                            delimiter=delimiter)
        header = next(reader)
        idx = {c: i for i, c in enumerate(header)}
        for row in reader:
            yield idx, row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-federal", action="store_true",
                        help="Skip the USAspending alias check (offline only)")
    args = parser.parse_args()

    csv.field_size_limit(sys.maxsize)
    alias_csv = DATA / "processed/firm_aliases.csv"
    liveness_csv = DATA / "nano_dark_firm_liveness.csv"
    tm_csv = DATA / "nano_dark_firm_trademarks.csv"
    for p in (alias_csv, liveness_csv, tm_csv):
        if not p.exists():
            print(f"ERROR: {p} not found", file=sys.stderr)
            return 1

    # Alias graph → index, plus per-alias provenance (source, relation).
    edges = list(csv.DictReader(open(alias_csv, newline="", encoding="utf-8")))
    index = build_alias_index([_E(e["firm_normalized"], e["alias_normalized"]) for e in edges])
    provenance: dict[tuple[str, str], dict] = {}
    for e in edges:
        provenance[(e["firm_normalized"], e["alias_normalized"])] = e
        provenance[(e["alias_normalized"], e["firm_normalized"])] = e

    liv = {r["normalized_name"]: r for r in csv.DictReader(open(liveness_csv, newline="", encoding="utf-8"))}
    tm_own = {r["normalized_name"]: r for r in csv.DictReader(open(tm_csv, newline="", encoding="utf-8"))}

    def own_negative(f: str) -> bool:
        l, t = liv.get(f, {}), tm_own.get(f, {})
        pat = l.get("match_confidence") == "high" and l.get("any_filed_post_award") == "True"
        tmk = t.get("tm_filed_post_award") == "True"
        return not (pat or tmk)

    # Dark firm → set of alias normals (excluding self) that are NOT themselves dark firms.
    dark = set(liv)
    firm_aliases: dict[str, set[str]] = {}
    for f in dark:
        if f in index:
            others = {a for a in index[f] if a != f}
            if others:
                firm_aliases[f] = others
    all_alias_names = set().union(*firm_aliases.values()) if firm_aliases else set()
    print(f"Dark firms with ≥1 alias: {len(firm_aliases)};  distinct alias names: {len(all_alias_names)}")

    # --- On-disk evidence for the alias names ---
    print("Scanning trademark owners for alias names...")
    alias_tm_serials: dict[str, set[str]] = defaultdict(set)
    for idx, row in csv_rows(DATA / "raw/uspto/trademarks/owner.csv.zip"):
        n = _norm(row[idx["own_name"]])
        if n in all_alias_names:
            alias_tm_serials[n].add(row[idx["serial_no"]])
    wanted = set().union(*alias_tm_serials.values()) if alias_tm_serials else set()
    reg_serials: set[str] = set()
    if wanted:
        for idx, row in csv_rows(DATA / "raw/uspto/trademarks/case_file.csv.zip"):
            sn = row[idx["serial_no"]]
            if sn in wanted:
                rn = (row[idx["registration_no"]] or "").strip()
                if rn and set(rn) != {"0"}:
                    reg_serials.add(sn)
    alias_has_tm = {n for n, ss in alias_tm_serials.items() if ss & reg_serials}
    print(f"  {len(alias_has_tm)} alias names hold a registered mark")

    print("Scanning patent assignees for alias names...")
    alias_has_patent: set[str] = set()
    for idx, row in csv_rows(DATA / "raw/uspto/patentsview/g_assignee_disambiguated.tsv.zip",
                             delimiter="\t"):
        org = row[idx["disambig_assignee_organization"]]
        if org and _norm(org) in all_alias_names:
            alias_has_patent.add(_norm(org))
    print(f"  {len(alias_has_patent)} alias names are patent assignees")

    alias_has_federal: set[str] = set()
    if not args.no_federal:
        print("Checking USAspending for alias names (cached)...")
        ws2.CACHE = DATA / "api_cache/usaspending_alias"
        for i, name in enumerate(sorted(all_alias_names), 1):
            hits = ws2.fetch_by_name(name, ["A", "B", "C", "D"], "contracts", False)
            for a in hits:
                if _norm(a.get("Recipient Name") or "") == name:
                    alias_has_federal.add(name)
                    break
            if i % 25 == 0:
                print(f"  {i}/{len(all_alias_names)}")
        print(f"  {len(alias_has_federal)} alias names hold ≥1 federal prime award")

    # --- Assemble per-firm alias evidence ---
    out_rows = []
    recovered = 0
    for f, aliases in sorted(firm_aliases.items()):
        hit_aliases = []
        channels: set[str] = set()
        for a in sorted(aliases):
            ch = []
            if a in alias_has_tm:
                ch.append("trademark")
            if a in alias_has_patent:
                ch.append("patent")
            if a in alias_has_federal:
                ch.append("federal")
            if ch:
                prov = provenance.get((f, a), {})
                # shared_uei aliases only count with independent evidence (they have it here)
                hit_aliases.append(f"{a} [{prov.get('relation','?')}:{'|'.join(ch)}]")
                channels.update(ch)
        if not hit_aliases:
            continue
        newly = own_negative(f)
        recovered += newly
        out_rows.append({
            "firm_normalized": f,
            "company": liv[f]["company"],
            "bucket": liv[f]["bucket"],
            "alias_evidence": " ; ".join(hit_aliases),
            "channels": "|".join(sorted(channels)),
            "negative_under_own_name": newly,
        })

    out_csv = DATA / "nano_alias_expanded_evidence.csv"
    with open(out_csv, "w", newline="", encoding="utf-8") as fo:
        w = csv.DictWriter(fo, fieldnames=list(out_rows[0].keys()) if out_rows else
                           ["firm_normalized", "company", "bucket", "alias_evidence",
                            "channels", "negative_under_own_name"])
        w.writeheader()
        w.writerows(out_rows)
    print(f"\nWritten: {out_csv} ({len(out_rows)} firms with alias-borne evidence)")

    print()
    print("=" * 70)
    print("ALIAS-EXPANDED RECALL DELTA")
    print("=" * 70)
    print(f"Dark firms with evidence under an alias:            {len(out_rows)}")
    print(f"  of which NEGATIVE under their own name (RECALL):  {recovered}")
    for r in out_rows:
        if r["negative_under_own_name"]:
            print(f"    + {r['company'][:32]:<32} via {r['alias_evidence'][:80]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
