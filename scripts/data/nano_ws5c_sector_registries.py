#!/usr/bin/env python3
"""
WS5c / T17 — sector go-to-market registries for the biomed dark-firm slice.

Commercialization-specific registries for the pathway federal procurement sees
worst (NIH/NSF biomedical). For dark firms with any HHS-funded award:

  ClinicalTrials.gov  firm is the lead sponsor of a registered trial → active
                      clinical development (v2 API, keyless)
  openFDA 510(k)      firm is the applicant on a cleared device → market entry
                      (keyless)

Matching is exact-normalized on the returned sponsor/applicant name (these name
fields are messy; exact match is the conservative, precision-first bar). Alias
expansion (WS6) is applied so successor names are also searched.

Inputs:
  data/nano_dark_firm_liveness.csv     — dark firms
  data/nano_cohort_keyword.csv          — agency (biomed slice = HHS-funded)
  data/processed/firm_aliases.csv       — alias expansion (optional)
  ClinicalTrials.gov v2 + openFDA APIs (cached: data/api_cache/sector_registries/)

Outputs:
  data/nano_ws5c_sector_registries.csv  — per biomed-firm registry evidence

Usage:
  python scripts/data/nano_ws5c_sector_registries.py [--refresh]
"""

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from urllib.parse import quote

import requests

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data"
CACHE = DATA / "api_cache/sector_registries"
HEADERS = {"User-Agent": "SBIR-Analytics/0.1.0"}

sys.path.insert(0, str(REPO))
from sbir_etl.utils.text_normalization import normalize_name  # noqa: E402


def _norm(s: str) -> str:
    return normalize_name(s, remove_suffixes=True)


def _get(url: str, cache_key: str, refresh: bool) -> dict:
    cache_file = CACHE / f"{cache_key}.json"
    if cache_file.exists() and not refresh:
        try:
            return json.loads(cache_file.read_text())
        except json.JSONDecodeError:
            pass
    payload: dict = {}
    for attempt in range(4):
        try:
            r = requests.get(url, headers=HEADERS, timeout=45)
            if r.status_code == 404:
                payload = {}
                break
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(2 ** (attempt + 1))
                continue
            r.raise_for_status()
            payload = r.json()
            break
        except requests.RequestException:
            if attempt == 3:
                payload = {}
            else:
                time.sleep(2 ** (attempt + 1))
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(payload))
    time.sleep(0.4)
    return payload


def clinicaltrials_sponsor_hits(name: str, targets: set[str], refresh: bool) -> list[dict]:
    url = (
        "https://clinicaltrials.gov/api/v2/studies?"
        f"query.spons={quote(name)}&pageSize=30&fields="
        "protocolSection.identificationModule.nctId,"
        "protocolSection.sponsorCollaboratorsModule.leadSponsor.name,"
        "protocolSection.statusModule.startDateStruct.date"
    )
    data = _get(url, f"ct_{_norm(name).replace(' ', '_')[:70]}", refresh)
    hits = []
    for st in data.get("studies", []):
        ps = st.get("protocolSection", {})
        spons = ps.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {}).get("name", "")
        if _norm(spons) in targets:
            hits.append({
                "nct": ps.get("identificationModule", {}).get("nctId", ""),
                "date": ps.get("statusModule", {}).get("startDateStruct", {}).get("date", ""),
                "sponsor": spons,
            })
    return hits


def fda_510k_hits(name: str, targets: set[str], refresh: bool) -> list[dict]:
    url = f'https://api.fda.gov/device/510k.json?search=applicant:"{quote(name)}"&limit=30'
    data = _get(url, f"fda_{_norm(name).replace(' ', '_')[:70]}", refresh)
    hits = []
    for res in data.get("results", []):
        if _norm(res.get("applicant", "")) in targets:
            hits.append({
                "k_number": res.get("k_number", ""),
                "date": res.get("decision_date", ""),
                "device": (res.get("device_name", "") or "")[:50],
            })
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    csv.field_size_limit(sys.maxsize)
    dark = {r["normalized_name"]: r for r in
            csv.DictReader(open(DATA / "nano_dark_firm_liveness.csv", newline="", encoding="utf-8"))}
    biomed: set[str] = set()
    for r in csv.DictReader(open(DATA / "nano_cohort_keyword.csv", newline="", encoding="utf-8")):
        f = _norm(r["company"])
        if f in dark and "Health" in r.get("agency", ""):
            biomed.add(f)
    print(f"Biomed-slice dark firms: {len(biomed)}")

    # Alias expansion: each firm's search names = itself + aliases.
    aliases: dict[str, set[str]] = {}
    ap = DATA / "processed/firm_aliases.csv"
    if ap.exists():
        for e in csv.DictReader(open(ap, newline="", encoding="utf-8")):
            for a, b in ((e["firm_normalized"], e["alias_normalized"]),
                         (e["alias_normalized"], e["firm_normalized"])):
                aliases.setdefault(a, set()).add(b)

    out_rows = []
    for i, f in enumerate(sorted(biomed), 1):
        search_norms = {f} | aliases.get(f, set())
        # Search under the raw company name and any alias raw names we can recover.
        search_names = {dark[f]["company"]}
        search_names |= {n for n in search_norms if n != f}  # alias normals as queries
        ct_hits, fda_hits = [], []
        for nm in search_names:
            ct_hits += clinicaltrials_sponsor_hits(nm, search_norms, args.refresh)
            fda_hits += fda_510k_hits(nm, search_norms, args.refresh)
        # dedupe
        ct_hits = {h["nct"]: h for h in ct_hits}.values()
        fda_hits = {h["k_number"]: h for h in fda_hits}.values()
        if not ct_hits and not fda_hits:
            continue
        channels = []
        if ct_hits:
            channels.append("clinical_trial")
        if fda_hits:
            channels.append("fda_510k")
        out_rows.append({
            "firm_normalized": f,
            "company": dark[f]["company"],
            "bucket": dark[f]["bucket"],
            "channels": "|".join(channels),
            "n_trials": len(ct_hits),
            "n_510k": len(fda_hits),
            "trials": " | ".join(f"{h['nct']}({h['date']})" for h in list(ct_hits)[:3]),
            "clearances": " | ".join(f"{h['k_number']}({h['date']}) {h['device']}" for h in list(fda_hits)[:3]),
        })
        if i % 50 == 0:
            print(f"  {i}/{len(biomed)}")

    out_csv = DATA / "nano_ws5c_sector_registries.csv"
    with open(out_csv, "w", newline="", encoding="utf-8") as fo:
        cols = ["firm_normalized", "company", "bucket", "channels", "n_trials",
                "n_510k", "trials", "clearances"]
        w = csv.DictWriter(fo, fieldnames=cols)
        w.writeheader()
        w.writerows(out_rows)
    print(f"  Written: {out_csv} ({len(out_rows)} firms with registry evidence)")

    print()
    print("=" * 70)
    print("WS5c SECTOR REGISTRY SUMMARY (biomed slice)")
    print("=" * 70)
    ct = sum(1 for r in out_rows if "clinical_trial" in r["channels"])
    fda = sum(1 for r in out_rows if "fda_510k" in r["channels"])
    print(f"Biomed dark firms: {len(biomed)}")
    print(f"  with a registered clinical trial (lead sponsor): {ct}")
    print(f"  with a cleared 510(k) device:                    {fda}")
    print(f"  with either:                                     {len(out_rows)}")
    for r in out_rows[:12]:
        print(f"    {r['company'][:34]:<34} [{r['channels']}] {r['trials'][:40]}{r['clearances'][:40]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
