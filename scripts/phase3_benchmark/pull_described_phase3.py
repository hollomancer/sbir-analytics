"""Manifested USAspending puller for SBIR/STTR Phase III phrase flags."""

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
FIELDS = [
    "Award ID", "Description", "Recipient Name", "Award Amount", "Awarding Agency",
    "Awarding Sub Agency", "Action Date", "Contract Award Type",
]
AWARD_TYPE_GROUPS = {
    "contract": ["A", "B", "C", "D"],
    "idv": ["IDV_A", "IDV_B", "IDV_C", "IDV_D", "IDV_E"],
}
DESCRIPTION_SIGNALS = {"SBIR": "SBIR PHASE III", "STTR": "STTR PHASE III"}
REQUIRED_COMPLETENESS_FIELDS = ("generated_internal_id", "Award ID", "Description")
Fetch = Callable[[bytes], bytes]


def _post(body: bytes) -> bytes:
    request = urllib.request.Request(
        ENDPOINT,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "sbir-phase3/1.0"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def _request_body(agency: str, award_types: list[str], phrase: str, page: int,
                  start_date: str, end_date: str) -> bytes:
    return json.dumps({
        "filters": {
            "award_type_codes": award_types,
            "time_period": [{"start_date": start_date, "end_date": end_date}],
            "description": phrase,
            "agencies": [{"type": "awarding", "tier": "toptier", "name": agency}],
        },
        "fields": FIELDS,
        "limit": 100,
        "page": page,
    }).encode()


def _field_completeness(frame: pd.DataFrame) -> dict[str, float]:
    if frame.empty:
        return dict.fromkeys(REQUIRED_COMPLETENESS_FIELDS, 0.0)
    return {
        field: (round(float(frame[field].fillna("").astype(str).str.strip().ne("").mean()), 6)
                if field in frame else 0.0)
        for field in REQUIRED_COMPLETENESS_FIELDS
    }


def pull_described(
    agency: str,
    *,
    start_date: str = "2015-10-01",
    end_date: str = "2025-09-30",
    max_pages: int = 100,
    fetcher: Fetch = _post,
    source_vintage: str = "unknown",
    signals: dict[str, str] | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Retrieve each phrase/award-type query and track completion independently."""
    signals = signals or DESCRIPTION_SIGNALS
    frames: list[pd.DataFrame] = []
    digest = hashlib.sha256()
    pages: list[dict[str, object]] = []
    query_status: dict[str, str] = {}
    for signal, phrase in signals.items():
        for group, award_types in AWARD_TYPE_GROUPS.items():
            query_id = f"{signal}:{group}"
            termination = "page_limit_reached"
            for page in range(1, max_pages + 1):
                payload = fetcher(
                    _request_body(agency, award_types, phrase, page, start_date, end_date)
                )
                digest.update(payload)
                parsed = json.loads(payload)
                rows = pd.DataFrame(parsed.get("results", []))
                if not rows.empty:
                    rows["description_signal"] = signal
                    rows["award_type_group"] = group
                    frames.append(rows)
                has_next = bool(parsed.get("page_metadata", {}).get("hasNext"))
                pages.append({
                    "query_id": query_id,
                    "page": page,
                    "row_count": len(rows),
                    "raw_sha256": hashlib.sha256(payload).hexdigest(),
                    "has_next": has_next,
                })
                if not has_next:
                    termination = "feed_exhausted"
                    break
            query_status[query_id] = termination

    frame = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if "generated_internal_id" in frame:
        frame = frame.drop_duplicates(
            ["generated_internal_id", "description_signal", "award_type_group"]
        )
    complete = bool(query_status) and all(
        status == "feed_exhausted" for status in query_status.values()
    )
    manifest: dict[str, object] = {
        "status": "provisional",
        "queries": dict(signals),
        "endpoint": ENDPOINT,
        "agency": agency,
        "source_vintage": source_vintage,
        "run_at": datetime.now(UTC).isoformat(),
        "parameters": {
            "time_period": [start_date, end_date],
            "award_type_groups": AWARD_TYPE_GROUPS,
            "max_pages": max_pages,
        },
        "pages_retrieved": len(pages),
        "row_count": int(len(frame)),
        "contract_rows": int(frame["award_type_group"].eq("contract").sum())
        if len(frame) and "award_type_group" in frame else 0,
        "idv_rows": int(frame["award_type_group"].eq("idv").sum())
        if len(frame) and "award_type_group" in frame else 0,
        "grain": "award (USAspending generated_internal_id); contract and IDV strata separate",
        "raw_pages_sha256": digest.hexdigest(),
        "field_completeness": _field_completeness(frame),
        "retrieval_complete": complete,
        "query_termination": query_status,
        "page_provenance": pages,
    }
    return frame, manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agency", default="Department of Defense")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args(argv)
    frame, manifest = pull_described(args.agency)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(args.out, index=False)
    if args.manifest:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({key: value for key, value in manifest.items()
                      if key != "page_provenance"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
