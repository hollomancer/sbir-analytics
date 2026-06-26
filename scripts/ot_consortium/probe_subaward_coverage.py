#!/usr/bin/env python3
"""Probe FSRS sub-award coverage of CMF (consortium management firm) prime awards.

Answers the go/no-go question for the OT consortium sub-award attribution work
(see specs/ot-consortium-subaward-attribution/): of the dollars flowing through
CMF prime awards, what share is covered by reported sub-awards? If that share is
near zero, route (c) would recover almost nothing and is not worth building.

Read-only against the public USAspending API. Requires outbound egress to
api.usaspending.gov (blocked under some session network policies — run where
egress is allowed, or allowlist the host).

Usage:
    uv run python scripts/ot_consortium/probe_subaward_coverage.py \
        --max-primes-per-cmf 100 --out reports/subaward_coverage_probe.json

Metric reported per CMF and overall:
    * primes found, primes_with_subawards
    * sum prime obligation vs sum reported sub-award amount
    * coverage_pct = sum_subaward_amount / sum_obligation  (the recovery ceiling)

Caveat baked into the result: OTs are inconsistently represented in USAspending
and FFATA/FSRS reporting of OT distributions is partial, so a LOW number is the
expected risk, not a bug. Award-type representation of OTs varies; this probe
pulls procurement + IDV award types for each CMF and records the types it saw.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import requests

API = "https://api.usaspending.gov/api/v2"

# Seed CMFs (mirrors data/reference/cmf_registry.csv). Name search is how we find
# their prime awards; the probe does not need verified UEIs to compute coverage.
DEFAULT_CMFS = [
    "Advanced Technology International",
    "National Security Technology Accelerator",
    "Consortium Management Group",
    "SOSSEC",
    "National Center for Manufacturing Sciences",
    "Medical Technology Enterprise Consortium",
]

# Procurement + IDV award types. OTs are not cleanly typed in USAspending; we pull
# these and record what comes back rather than assuming an OT-specific code.
AWARD_TYPE_CODES = ["A", "B", "C", "D", "IDV_A", "IDV_B", "IDV_C", "IDV_D", "IDV_E"]


def _post(session: requests.Session, path: str, body: dict[str, Any], retries: int = 4) -> dict:
    url = f"{API}{path}"
    for attempt in range(retries):
        resp = session.post(url, json=body, timeout=60)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code in (429, 502, 503, 504):
            time.sleep(2**attempt)
            continue
        resp.raise_for_status()
    resp.raise_for_status()
    return {}


def _get(session: requests.Session, path: str, retries: int = 4) -> dict:
    url = f"{API}{path}"
    for attempt in range(retries):
        resp = session.get(url, timeout=60)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code in (429, 502, 503, 504):
            time.sleep(2**attempt)
            continue
        resp.raise_for_status()
    resp.raise_for_status()
    return {}


def find_primes(session: requests.Session, cmf: str, limit: int) -> list[dict[str, Any]]:
    """Return prime awards for a CMF: generated_internal_id, amount, award id, type."""
    body = {
        "filters": {
            "recipient_search_text": [cmf],
            "award_type_codes": AWARD_TYPE_CODES,
        },
        "fields": ["Award ID", "Recipient Name", "Award Amount", "Award Type"],
        "page": 1,
        "limit": min(limit, 100),
        "sort": "Award Amount",
        "order": "desc",
        "subawards": False,
    }
    out: list[dict[str, Any]] = []
    page = 1
    while len(out) < limit:
        body["page"] = page
        data = _post(session, "/search/spending_by_award/", body)
        results = data.get("results", [])
        if not results:
            break
        out.extend(results)
        if not data.get("page_metadata", {}).get("hasNext"):
            break
        page += 1
    return out[:limit]


def award_subaward_stats(session: requests.Session, internal_id: str) -> dict[str, Any]:
    """Per-award obligation, total reported sub-award amount, and sub-award count."""
    data = _get(session, f"/awards/{internal_id}/")
    return {
        "obligation": float(data.get("total_obligation") or 0.0),
        "subaward_amount": float(data.get("total_subaward_amount") or 0.0),
        "subaward_count": int(data.get("subaward_count") or 0),
    }


def probe(cmfs: list[str], max_primes: int, out_path: Path | None) -> dict[str, Any]:
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})

    per_cmf: dict[str, Any] = {}
    grand = {"primes": 0, "with_subawards": 0, "obligation": 0.0, "subaward_amount": 0.0}

    for cmf in cmfs:
        print(f"[{cmf}] searching primes…", file=sys.stderr)
        try:
            primes = find_primes(session, cmf, max_primes)
        except requests.HTTPError as exc:
            print(f"  ! search failed: {exc}", file=sys.stderr)
            per_cmf[cmf] = {"error": str(exc)}
            continue

        agg = {
            "primes": 0,
            "with_subawards": 0,
            "obligation": 0.0,
            "subaward_amount": 0.0,
            "award_types": {},
        }
        for p in primes:
            internal_id = p.get("generated_internal_id")
            if not internal_id:
                continue
            atype = str(p.get("Award Type") or "unknown")
            agg["award_types"][atype] = agg["award_types"].get(atype, 0) + 1
            try:
                stats = award_subaward_stats(session, internal_id)
            except requests.HTTPError as exc:
                print(f"  ! award {internal_id} failed: {exc}", file=sys.stderr)
                continue
            agg["primes"] += 1
            agg["obligation"] += stats["obligation"]
            agg["subaward_amount"] += stats["subaward_amount"]
            if stats["subaward_count"] > 0:
                agg["with_subawards"] += 1
            time.sleep(0.1)  # be polite

        agg["coverage_pct"] = (
            100.0 * agg["subaward_amount"] / agg["obligation"] if agg["obligation"] else 0.0
        )
        per_cmf[cmf] = agg
        for k in ("primes", "with_subawards", "obligation", "subaward_amount"):
            grand[k] += agg[k]
        print(
            f"  {agg['primes']} primes, {agg['with_subawards']} with sub-awards, "
            f"coverage {agg['coverage_pct']:.1f}% of ${agg['obligation']:,.0f}",
            file=sys.stderr,
        )

    grand["coverage_pct"] = (
        100.0 * grand["subaward_amount"] / grand["obligation"] if grand["obligation"] else 0.0
    )
    result = {"per_cmf": per_cmf, "overall": grand}

    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2))
        print(f"\nWrote {out_path}", file=sys.stderr)

    print("\n=== OVERALL ===")
    print(
        f"primes={grand['primes']} with_subawards={grand['with_subawards']} "
        f"obligation=${grand['obligation']:,.0f} subaward=${grand['subaward_amount']:,.0f}"
    )
    print(f"COVERAGE = {grand['coverage_pct']:.1f}%  (the route-(c) recovery ceiling)")
    print(
        "\nRead: >~20% → build sub-award attribution; ~single digits → shelve it; "
        "OT under-representation in USAspending means this is a floor, not a verdict."
    )
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--cmf", action="append", help="CMF name (repeatable); defaults to the seed set"
    )
    ap.add_argument("--max-primes-per-cmf", type=int, default=100)
    ap.add_argument("--out", type=Path, default=None, help="Write full JSON result here")
    args = ap.parse_args()
    cmfs = args.cmf or DEFAULT_CMFS
    try:
        probe(cmfs, args.max_primes_per_cmf, args.out)
    except requests.RequestException as exc:
        print(
            f"\nAPI unreachable: {exc}\n"
            "If this is a proxy 403, api.usaspending.gov is blocked by the session's egress "
            "policy — run where egress is allowed or allowlist the host.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
