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
import re
import sys
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ucc._common import data_path  # noqa: E402

_CURL_CFFI_HINT = (
    "curl_cffi is required for the UCC pilot CA SOS scraper. "
    "Install with: uv sync --extra ucc1-pilot"
)


def _curl_cffi_requests():
    """Lazy-import curl_cffi.requests with a helpful error if the extra is missing.

    Kept out of module scope so unit tests (and other scripts that only
    need the pure helpers) can import this module without the optional
    extra installed.
    """
    try:
        from curl_cffi import requests as ccrequests
    except ImportError as e:  # pragma: no cover - tested only by CI without the extra
        raise ImportError(_CURL_CFFI_HINT) from e
    return ccrequests

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


# Common entity-suffix tokens to strip/swap when generating name variants
_SUFFIX_PATTERN = re.compile(
    r",?\s+(INC|INCORPORATED|LLC|L\.L\.C|L\.L\.C\.|LTD|LIMITED|CORP|CORPORATION|"
    r"CO|COMPANY|LP|L\.P\.|LLP|HOLDINGS?|GROUP|PARTNERS|PARTNERSHIP)\.?\s*$",
    re.IGNORECASE,
)


def generate_name_variants(name: str) -> list[str]:
    """Produce ordered search-variant candidates for a cohort firm name.

    Returns variants in order from most specific to most general:
      1. Original name (unmodified)
      2. Without trailing entity suffix
      3. Without comma+suffix (clean root)
      4. Root + " HOLDINGS" (catches HoldCo-style legal names like
         "23ANDME HOLDING COMPANY, INC.")
      5. First word only (last-ditch broad match)
    Duplicates removed; order preserved.
    """
    if not name:
        return []
    raw = name.strip()
    variants: list[str] = [raw]

    # Strip trailing suffix
    stripped = _SUFFIX_PATTERN.sub("", raw).strip()
    if stripped and stripped != raw:
        variants.append(stripped)

    # Strip any trailing comma
    no_comma = stripped.rstrip(",").strip() if stripped else raw.rstrip(",").strip()
    if no_comma and no_comma not in variants:
        variants.append(no_comma)

    # HoldCo variant
    root = no_comma or stripped or raw
    holdco = f"{root} HOLDING"
    if holdco not in variants:
        variants.append(holdco)

    # First word — only if it's distinctive (>=4 chars or contains a digit)
    first = root.split()[0] if root else ""
    if first and (len(first) >= 4 or any(c.isdigit() for c in first)):
        if first not in variants:
            variants.append(first)

    # Deduplicate case-insensitively while preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for v in variants:
        key = v.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(v)
    return deduped


def lookup_ca_sos_with_variants(
    company_name: str,
    client: Any | None = None,
    max_variants: int = 5,
) -> tuple[dict | None, str | None]:
    """Try name variants until one returns a result.

    Returns (best_record, matched_variant). If at least one variant
    returns a successful (but empty) response, returns (None, None).
    If every variant request fails (e.g., Imperva block), the last
    error is re-raised so the caller can distinguish a true no-result
    from systemic failure.
    """
    own_client = client is None
    if own_client:
        client = make_session()
    try:
        variants = generate_name_variants(company_name)[:max_variants]
        last_error: Exception | None = None
        successful_responses = 0
        for variant in variants:
            payload = {**_BASE_PAYLOAD, "SEARCH_VALUE": variant}
            try:
                response = client.post(
                    BUSINESS_SEARCH_URL, json=payload, headers=_POST_HEADERS,
                )
                response.raise_for_status()
                rows = response.json().get("rows") or {}
            except (OSError, ValueError) as e:
                # curl_cffi RequestsError is an OSError; json.JSONDecodeError
                # is a ValueError. Narrow enough to surface unexpected bugs.
                last_error = e
                continue
            successful_responses += 1
            if rows:
                return (pick_best_match(rows), variant)
        if successful_responses == 0 and last_error is not None:
            raise last_error
        return (None, None)
    finally:
        if own_client:
            client.close()


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


def make_session() -> Any:
    """Build a curl_cffi session primed past Imperva's first-request check."""
    ccrequests = _curl_cffi_requests()
    s = ccrequests.Session(impersonate=_IMPERSONATE)
    s.get(SEARCH_SEED_URL)
    return s


def lookup_ca_sos(
    company_name: str,
    client: Any | None = None,
) -> dict | None:
    """Query CA SOS business search with name-variant retry; return best record.

    Delegates to lookup_ca_sos_with_variants and discards the variant-matched
    indicator. If you need to know which variant succeeded (for debugging
    coverage), call lookup_ca_sos_with_variants directly.
    """
    record, _variant = lookup_ca_sos_with_variants(company_name, client=client)
    return record


def narrow_to_ca_organized(
    cohort: Iterable[dict],
    lookup_fn: Callable[[str], dict | None] | None = None,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    checkpoint_path: Path | None = None,
    session_rotate_every: int = 50,
) -> tuple[list[dict], int]:
    """Filter cohort to CA-organized entities.

    Returns (kept_rows, lookups_performed).

    Writes a JSONL checkpoint (one line per processed firm) so re-runs skip
    completed lookups. Errors are caught per-firm; the checkpoint records
    them so the firm isn't retried on resume (re-runs against the same
    checkpoint will skip).

    For real (non-mocked) lookups, the session is rebuilt every
    `session_rotate_every` firms to avoid Imperva session-age limits.

    Checkpoint format:
        {"company_name": str, "is_ca_organized": bool, "business_record": dict | None,
         "error": str | None}
    """
    using_real_lookup = lookup_fn is None
    lookup_fn = lookup_fn or lookup_ca_sos

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
    session: object | None = None
    since_rotate = 0

    for row in cohort:
        name = row["company_name"]
        if name in decisions:
            if decisions[name]:
                kept.append(row)
            continue

        # Session rotation (only for real lookups)
        if using_real_lookup and (session is None or since_rotate >= session_rotate_every):
            if session is not None:
                try:
                    session.close()
                except Exception:
                    pass
            session = make_session()
            since_rotate = 0

        try:
            if using_real_lookup:
                record = lookup_fn(name, client=session)
            else:
                record = lookup_fn(name)
            error_msg = None
        except Exception as e:
            record = None
            error_msg = f"{type(e).__name__}: {e}"
            # Force session rotation on error
            since_rotate = session_rotate_every

        lookups += 1
        since_rotate += 1
        ca_org = is_ca_organized(record)
        if ca_org:
            kept.append(row)

        if checkpoint_path:
            with checkpoint_path.open("a") as f:
                f.write(json.dumps({
                    "company_name": name,
                    "is_ca_organized": ca_org,
                    "business_record": record,
                    "error": error_msg,
                }) + "\n")

        if delay_seconds:
            time.sleep(delay_seconds)

    if session is not None:
        try:
            session.close()
        except Exception:
            pass

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
