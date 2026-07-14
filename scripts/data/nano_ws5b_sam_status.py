#!/usr/bin/env python3
"""
WS5b / T14 — SAM.gov registration status for the cohort's UEI'd firms.

SAM registration renewal is an annual requirement, so an *active* registration
is affirmative liveness and a registration's expiry/last-update date brackets
when a firm stopped seeking federal work — the closest quasi-negative signal
available without state registries. Feeds the WS4 survival framing as dormancy
timestamps.

Queries the SAM Entity Management API (v3) for each known UEI:
  - cohort firms' UEIs (nano_cohort_keyword.csv)
  - WS2-resolved no-UEI firms' candidate UEIs (nano_no_uei_resolution.csv)
Registration status is looked up with registrationStatus omitted (so lapsed
entities are returned, not just active ones).

CREDENTIAL: needs SAM_GOV_API_KEY (env or repo-root .env). SAM keys are tied to
a SAM.gov login and cannot be self-issued; without one this script exits with a
clear message and no partial output. Key lifecycle: ~60-day expiry.

Path convention (same as nano_form_d_temporal.py / nano_ws1):
  --area <id>   → data/reports/<id>/sam_status.csv
  (no flag)     → data/nano_sam_status.csv  (legacy PR #428)

Inputs:
  cohort_keyword.csv (area-scoped), no_uei_resolution.csv (area-scoped)
  SAM Entity API (cached: data/api_cache/sam_status/)

Outputs:
  sam_status.csv

Usage:
  python scripts/data/nano_ws5b_sam_status.py [--area AREA] [--legacy]
"""

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data"
CACHE = DATA / "api_cache/sam_status"
API = "https://api.sam.gov/entity-information/v3/entities"
KEY_ENV = "SAM_GOV_API_KEY"

sys.path.insert(0, str(REPO))
from sbir_etl.utils.transition_report_paths import (  # noqa: E402
    add_area_args,
    resolve_area_paths,
)


def resolve_key() -> str | None:
    if os.environ.get(KEY_ENV):
        return os.environ[KEY_ENV]
    env_file = REPO / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith(f"{KEY_ENV}=") and line.split("=", 1)[1]:
                return line.split("=", 1)[1]
    return None


def fetch_entity(uei: str, api_key: str) -> dict:
    cache_file = CACHE / f"{uei}.json"
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text())
        except json.JSONDecodeError:
            pass
    params = {
        "api_key": api_key,
        "ueiSAM": uei,
        "includeSections": "entityRegistration",
        # No registrationStatus filter → return lapsed/expired entities too.
    }
    payload: dict = {}
    for attempt in range(4):
        try:
            r = requests.get(API, params=params, timeout=45)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(2 ** (attempt + 1))
                continue
            if r.status_code in (401, 403):
                raise SystemExit(
                    f"SAM API returned {r.status_code} — {KEY_ENV} is invalid or expired "
                    f"(keys expire ~60 days; rotate at sam.gov). No output written."
                )
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
    time.sleep(0.5)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_area_args(parser)
    args = parser.parse_args(argv)
    paths = resolve_area_paths(args, argv)

    api_key = resolve_key()
    if not api_key:
        print(
            f"BLOCKED: no {KEY_ENV} found (environment or repo-root .env).\n"
            f"SAM.gov keys are tied to a SAM.gov login and cannot be self-issued.\n"
            f"Provide one (see scripts/data/download_sam_gov.py) and re-run; the script\n"
            f"and its caching are ready. No output written.",
            file=sys.stderr,
        )
        return 2  # matches the repo convention: exit 2 = credential problem

    csv.field_size_limit(sys.maxsize)
    ueis: dict[str, str] = {}  # uei -> a company label
    for r in csv.DictReader(open(paths.artifact("cohort_keyword"), newline="", encoding="utf-8")):
        u = (r.get("uei") or "").strip()
        if u:
            ueis.setdefault(u, r["company"])
    res_path = paths.artifact("no_uei_resolution")
    if res_path.exists():
        for r in csv.DictReader(open(res_path, newline="", encoding="utf-8")):
            if r["resolution_confidence"] in ("high", "medium"):
                for u in r["candidate_ueis"].split("|"):
                    if u:
                        ueis.setdefault(u, r["company"])
    print(f"UEIs to check: {len(ueis):,}")

    out_rows = []
    for i, (uei, label) in enumerate(sorted(ueis.items()), 1):
        data = fetch_entity(uei, api_key)
        entities = data.get("entityData", []) if isinstance(data, dict) else []
        reg = (entities[0].get("entityRegistration", {}) if entities else {})
        status = reg.get("registrationStatus", "") or ("NOT_FOUND" if not entities else "")
        out_rows.append({
            "uei": uei,
            "company": label,
            "sam_status": status,  # A=active, E/expired, etc.
            "legal_business_name": reg.get("legalBusinessName", ""),
            "registration_date": reg.get("registrationDate", ""),
            "expiration_date": reg.get("registrationExpirationDate", ""),
            "last_update_date": reg.get("lastUpdateDate", ""),
        })
        if i % 100 == 0:
            print(f"  {i}/{len(ueis)}")

    out_csv = paths.artifact("sam_status")
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)
    print(f"  Written: {out_csv} ({len(out_rows)} entities)")

    from collections import Counter
    st = Counter(r["sam_status"] for r in out_rows)
    print(f"\nStatus distribution: {dict(st)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
