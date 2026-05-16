#!/usr/bin/env python3
"""Filter the Form D cohort to CA-organized entities only.

Per UCC § 9-307, a registered organization's UCC-1s file in its state of
organization. The CA bizfileOnline UCC search only surfaces filings against
CA-organized entities — DE-incorporated firms doing business in CA are
invisible to it. This filter eliminates those false-population members
upfront, before we waste extractor queries on them.

The CA SOS business search returns each entity's FORMED_IN (jurisdiction)
and ENTITY_TYPE. A firm is "CA-organized" iff FORMED_IN == "CALIFORNIA"
AND ENTITY_TYPE does not contain "Out of State" (which marks foreign
registrations).

Usage:
    python scripts/data/ucc/cohort_state_filter.py
"""

import argparse
import json
import sys
import time
from collections.abc import Callable, Iterable
from pathlib import Path

from curl_cffi import requests as ccrequests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ucc._common import data_path  # noqa: E402

BUSINESS_SEARCH_URL = "https://bizfileonline.sos.ca.gov/api/Records/businesssearch"
SEARCH_SEED_URL = "https://bizfileonline.sos.ca.gov/search/business"

DEFAULT_DELAY_SECONDS = 1.0

# bizfileOnline is fronted by Imperva. Defeating its bot defenses needs:
#   1. TLS fingerprint impersonation (curl_cffi impersonate='chrome124')
#   2. A priming GET to /search/business to set Incapsula session cookies
#   3. The literal "authorization: undefined" header the browser sends
# Removing any one of these reproduces 403. Tested 2026-05-16.
_POST_HEADERS = {
    "authorization": "undefined",
    "Origin": "https://bizfileonline.sos.ca.gov",
    "Referer": "https://bizfileonline.sos.ca.gov/search/business",
}
_IMPERSONATE = "chrome124"

# Padding fields the server requires; only SEARCH_VALUE varies per request.
_BASE_PAYLOAD = {
    "SEARCH_FILTER_TYPE_ID": "0",
    "SEARCH_TYPE_ID": "1",
    "FILING_TYPE_ID": "",
    "STATUS_ID": "",
    "FILING_DATE": {"start": None, "end": None},
    "CORPORATION_BANKRUPTCY_YN": False,
    "CORPORATION_LEGAL_PROCEEDINGS_YN": False,
    "OFFICER_OBJECT": {"FIRST_NAME": "", "MIDDLE_NAME": "", "LAST_NAME": ""},
    "NUMBER_OF_FEMALE_DIRECTORS": "99",
    "NUMBER_OF_UNDERREPRESENTED_DIRECTORS": "99",
    "COMPENSATION_FROM": "",
    "COMPENSATION_TO": "",
    "SHARES_YN": False,
    "OPTIONS_YN": False,
    "BANKRUPTCY_YN": False,
    "FRAUD_YN": False,
    "LOANS_YN": False,
    "AUDITOR_NAME": "",
}


def is_ca_organized(business_record: dict | None) -> bool:
    """Return True iff the entity is CA-organized (not a foreign registration)."""
    if not business_record:
        return False
    formed_in = (business_record.get("FORMED_IN") or "").upper()
    entity_type = (business_record.get("ENTITY_TYPE") or "").lower()
    return formed_in == "CALIFORNIA" and "out of state" not in entity_type


def pick_best_match(rows: dict[str, dict]) -> dict | None:
    """Pick the best business-search result for a single firm.

    Strategy: prefer Active entities; among those, take SORT_INDEX 0 (server
    rank). If none are Active, take the lowest SORT_INDEX overall. The
    server already returns results in relevance order.
    """
    if not rows:
        return None
    records = list(rows.values())
    actives = [r for r in records if (r.get("STATUS") or "").lower() == "active"]
    pool = actives or records
    return min(pool, key=lambda r: r.get("SORT_INDEX", 0))


def make_session() -> ccrequests.Session:
    """Build a curl_cffi session primed past Imperva's first-request check."""
    s = ccrequests.Session(impersonate=_IMPERSONATE)
    s.get(SEARCH_SEED_URL)
    return s


def lookup_ca_sos(
    company_name: str, client: ccrequests.Session | None = None,
) -> dict | None:
    """Query CA SOS business search; return the best business record or None.

    If client is None, builds a single-shot session (with priming GET); for
    bulk use, pass a reused session.
    """
    own_client = client is None
    if own_client:
        client = make_session()
    try:
        payload = {**_BASE_PAYLOAD, "SEARCH_VALUE": company_name}
        response = client.post(BUSINESS_SEARCH_URL, json=payload, headers=_POST_HEADERS)
        response.raise_for_status()
        body = response.json()
        return pick_best_match(body.get("rows") or {})
    finally:
        if own_client:
            client.close()


def narrow_to_ca_organized(
    cohort: Iterable[dict],
    lookup_fn: Callable[[str], dict | None] | None = None,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    checkpoint_path: Path | None = None,
) -> tuple[list[dict], int]:
    """Filter cohort to CA-organized entities.

    Returns (kept_rows, lookups_performed).

    Writes a JSONL checkpoint (one line per processed firm) so re-runs skip
    completed lookups. Checkpoint format:
        {"company_name": str, "is_ca_organized": bool, "business_record": dict | None}
    """
    lookup_fn = lookup_fn or lookup_ca_sos

    # Replay checkpoint for prior decisions
    decisions: dict[str, bool] = {}
    if checkpoint_path and checkpoint_path.exists():
        with checkpoint_path.open() as f:
            for line in f:
                line = line.strip()
                if line:
                    rec = json.loads(line)
                    decisions[rec["company_name"]] = bool(rec.get("is_ca_organized"))

    kept: list[dict] = []
    lookups = 0
    for row in cohort:
        name = row["company_name"]
        if name in decisions:
            if decisions[name]:
                kept.append(row)
            continue

        record = lookup_fn(name)
        lookups += 1
        ca_org = is_ca_organized(record)
        if ca_org:
            kept.append(row)

        if checkpoint_path:
            with checkpoint_path.open("a") as f:
                f.write(json.dumps({
                    "company_name": name,
                    "is_ca_organized": ca_org,
                    "business_record": record,
                }) + "\n")

        if delay_seconds:
            time.sleep(delay_seconds)

    return kept, lookups


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cohort", type=Path,
                        default=data_path("form_d_high_conf_cohort.jsonl"))
    parser.add_argument("--out", type=Path,
                        default=data_path("ucc1_pilot_ca_org_cohort.jsonl"))
    parser.add_argument("--checkpoint", type=Path,
                        default=data_path("ucc1_pilot_state_filter_checkpoint.jsonl"))
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS)
    args = parser.parse_args()

    with args.cohort.open() as f:
        cohort_rows = [json.loads(line) for line in f if line.strip()]

    kept, lookups = narrow_to_ca_organized(
        cohort_rows,
        delay_seconds=args.delay,
        checkpoint_path=args.checkpoint,
    )

    with args.out.open("w") as f:
        for r in kept:
            f.write(json.dumps(r) + "\n")

    n = len(cohort_rows)
    print(
        f"Input: {n} | Lookups performed: {lookups} | "
        f"CA-organized: {len(kept)} ({100 * len(kept) / n:.1f}%)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
