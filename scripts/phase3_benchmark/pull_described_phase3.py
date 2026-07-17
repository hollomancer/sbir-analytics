"""Manifested USAspending puller for description-flagged Phase III (the described side of the undercount).

Companion to ``pull_fpds_10q.py`` (the coded side). Retrieves award-grain USAspending contract records
whose description contains "SBIR PHASE III" for a top-tier agency, and returns rows plus a provenance
manifest with the same shape as the FPDS puller: query, source vintage, retrieval time, per-page raw
payload hashes, counts, field completeness, and feed-exhaustion status. Award grain is native here
(``generated_internal_id``); no transaction collapse needed.

Run: ``python scripts/phase3_benchmark/pull_described_phase3.py --agency "Department of Defense"``
"""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

ENDPOINT = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
FIELDS = ["Award ID", "Description", "Recipient Name", "Award Amount", "Awarding Agency",
          "Awarding Sub Agency", "Action Date"]
AWARD_TYPE_GROUPS = (["A", "B", "C", "D"], ["IDV_A", "IDV_B", "IDV_C", "IDV_D", "IDV_E"])
REQUIRED_COMPLETENESS_FIELDS = ("generated_internal_id", "Award ID", "Description")
Fetch = Callable[[bytes], bytes]


def _post(body: bytes) -> bytes:
    request = urllib.request.Request(
        ENDPOINT, data=body, headers={"Content-Type": "application/json", "User-Agent": "sbir-phase3/1.0"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def _request_body(agency: str, award_types: list[str], page: int,
                  start_date: str, end_date: str) -> bytes:
    return json.dumps({
        "filters": {
            "award_type_codes": award_types,
            "time_period": [{"start_date": start_date, "end_date": end_date}],
            "description": "SBIR PHASE III",
            "agencies": [{"type": "awarding", "tier": "toptier", "name": agency}],
        },
        "fields": FIELDS, "limit": 100, "page": page,
    }).encode()


def _field_completeness(frame: pd.DataFrame) -> dict[str, float]:
    if frame.empty:
        return dict.fromkeys(REQUIRED_COMPLETENESS_FIELDS, 0.0)
    out: dict[str, float] = {}
    for field in REQUIRED_COMPLETENESS_FIELDS:
        if field not in frame.columns:
            out[field] = 0.0
            continue
        out[field] = round(float(frame[field].fillna("").astype(str).str.strip().ne("").mean()), 6)
    return out


def pull_described(agency: str, *, start_date: str = "2015-10-01", end_date: str = "2025-09-30",
                   max_pages: int = 100, fetcher: Fetch = _post,
                   source_vintage: str = "unknown") -> tuple[pd.DataFrame, dict[str, object]]:
    """Retrieve description-flagged Phase III award rows for one agency, plus a provenance manifest."""
    run_at = datetime.now(UTC).isoformat()
    frames: list[pd.DataFrame] = []
    digest = hashlib.sha256()
    page_provenance: list[dict[str, object]] = []
    termination_reason = "page_limit_reached"

    for award_types in AWARD_TYPE_GROUPS:
        for page in range(1, max_pages + 1):
            payload = fetcher(_request_body(agency, award_types, page, start_date, end_date))
            digest.update(payload)
            parsed = json.loads(payload)
            rows = pd.DataFrame(parsed.get("results", []))
            if not rows.empty:
                frames.append(rows)
            has_next = bool(parsed.get("page_metadata", {}).get("hasNext"))
            page_provenance.append({
                "award_type_group": award_types[0][:3], "page": page, "row_count": len(rows),
                "raw_sha256": hashlib.sha256(payload).hexdigest(), "has_next": has_next,
            })
            if not has_next:
                termination_reason = "feed_exhausted"
                break

    frame = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if "generated_internal_id" in frame.columns:
        frame = frame.drop_duplicates("generated_internal_id")
    manifest: dict[str, object] = {
        "query": 'description="SBIR PHASE III"',
        "endpoint": ENDPOINT,
        "agency": agency,
        "source_vintage": source_vintage,
        "run_at": run_at,
        "parameters": {"time_period": [start_date, end_date], "award_type_groups": list(AWARD_TYPE_GROUPS)},
        "pages_retrieved": len(page_provenance),
        "row_count": int(len(frame)),
        "grain": "award (generated_internal_id; native award grain)",
        "raw_pages_sha256": digest.hexdigest(),
        "field_completeness": _field_completeness(frame),
        "retrieval_complete": termination_reason == "feed_exhausted",
        "termination_reason": termination_reason,
        "page_provenance": page_provenance,
    }
    return frame, manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agency", default="Department of Defense")
    parser.add_argument("--out", type=Path, default=None, help="optional parquet path for the frame")
    parser.add_argument("--manifest", type=Path, default=None, help="optional manifest json path")
    args = parser.parse_args(argv)
    frame, manifest = pull_described(args.agency)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(args.out, index=False)
    if args.manifest:
        args.manifest.write_text(json.dumps(manifest, indent=2) + "\n")
    manifest_summary = {k: v for k, v in manifest.items() if k != "page_provenance"}
    print(json.dumps(manifest_summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
