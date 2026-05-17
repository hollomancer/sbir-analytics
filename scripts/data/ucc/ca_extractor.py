#!/usr/bin/env python3
"""Per-debtor UCC scraper for CA bizfileOnline.

For each debtor name, queries the UCC search with the Financing Statement
filter, walks each result's detail + History, and emits one UCCFiling row
per filing event (initial + UCC-3 amendments/continuations/assignments/
terminations).

Free-text search matches both debtor and secured-party fields; this
extractor returns ALL hits — the matcher filters to debtor-side only.

Uses curl_cffi + chrome124 impersonation + Imperva priming GET (same
pattern as cohort_state_filter); bare httpx is 403'd by Imperva.

Usage:
    python scripts/data/ucc/ca_extractor.py
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Protocol

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ucc._common import data_path  # noqa: E402
from ucc.schema import FilingType  # noqa: E402

_CURL_CFFI_HINT = (
    "curl_cffi is required for the UCC pilot CA bizfileOnline extractor. "
    "Install with: uv sync --extra ucc1-pilot"
)


def _curl_cffi_requests():
    """Lazy-import curl_cffi.requests with a helpful error if the extra is missing.

    Kept out of module scope so unit tests (and helpers like
    build_filings_from_history that don't make HTTP calls) can import
    this module without the optional extra installed.
    """
    try:
        from curl_cffi import requests as ccrequests
    except ImportError as e:  # pragma: no cover - tested only by CI without the extra
        raise ImportError(_CURL_CFFI_HINT) from e
    return ccrequests

UCC_SEARCH_URL = "https://bizfileonline.sos.ca.gov/api/Records/uccsearch"
UCC_DETAIL_URL_TPL = "https://bizfileonline.sos.ca.gov/api/FilingDetail/ucc/{id}/false"
UCC_HISTORY_URL_TPL = "https://bizfileonline.sos.ca.gov/api/History/ucc/{record_num}"
SEARCH_SEED_URL = "https://bizfileonline.sos.ca.gov/search/ucc"

DEFAULT_DELAY_SECONDS = 1.0
RECORD_TYPE_ID_FINANCING_STATEMENT = "2170"
_IMPERSONATE = "chrome124"

_POST_HEADERS = {
    "authorization": "undefined",
    "Origin": "https://bizfileonline.sos.ca.gov",
    "Referer": "https://bizfileonline.sos.ca.gov/search/ucc",
}

# Map portal-side AMENDMENT_TYPE strings to FilingType
DOC_TYPE_MAP = {
    "Lien Financing Stmt": FilingType.INITIAL,
    "Amendment": FilingType.AMENDMENT,
    "Continuation": FilingType.CONTINUATION,
    "Assignment": FilingType.ASSIGNMENT,
    "Termination": FilingType.TERMINATION,
}


def _normalize_date(raw: str | None) -> str:
    """Convert MM/DD/YYYY (CA portal format) to ISO YYYY-MM-DD."""
    if not raw:
        return ""
    s = str(raw)
    if "/" in s:
        m, d, y = s.split("/")
        return f"{y}-{m.zfill(2)}-{d.zfill(2)}"
    return s[:10]


class _BizfileClient(Protocol):
    def search(self, debtor_name: str) -> list[dict]: ...
    def detail(self, internal_id: int | str) -> dict: ...
    def history(self, record_num: str) -> list[dict]: ...


class HttpBizfileClient:
    """curl_cffi-based client against bizfileOnline UCC API."""

    def __init__(self, session: Any | None = None):
        if session is None:
            ccrequests = _curl_cffi_requests()
            session = ccrequests.Session(impersonate=_IMPERSONATE)
            session.get(SEARCH_SEED_URL)
        self.session = session

    def search(self, debtor_name: str) -> list[dict]:
        payload = {
            "SEARCH_VALUE": debtor_name,
            "STATUS": "ALL",
            "RECORD_TYPE_ID": RECORD_TYPE_ID_FINANCING_STATEMENT,
            "FILING_DATE": {"start": None, "end": None},
            "LAPSE_DATE": {"start": None, "end": None},
        }
        r = self.session.post(UCC_SEARCH_URL, json=payload, headers=_POST_HEADERS)
        r.raise_for_status()
        body = r.json()
        rows = body.get("rows") or {}
        return list(rows.values())

    def detail(self, internal_id: int | str) -> dict:
        url = UCC_DETAIL_URL_TPL.format(id=internal_id)
        r = self.session.get(url, headers=_POST_HEADERS)
        r.raise_for_status()
        body = r.json()
        # Flatten DRAWER_DETAIL_LIST into a dict keyed by canonical names
        out: dict = {}
        for item in body.get("DRAWER_DETAIL_LIST") or []:
            label = (item.get("LABEL") or "").strip()
            val = item.get("VALUE")
            if label == "Debtor Name":
                out["DEBTOR_NAME"] = val
            elif label == "Debtor Address":
                out["DEBTOR_ADDRESS"] = val
            elif label == "Secured Party Name":
                out["SEC_PARTY_NAME"] = val
            elif label == "Secured Party Address":
                out["SEC_PARTY_ADDRESS"] = val
        return out

    def history(self, record_num: str) -> list[dict]:
        url = UCC_HISTORY_URL_TPL.format(record_num=record_num)
        r = self.session.get(url, headers=_POST_HEADERS)
        r.raise_for_status()
        body = r.json()
        return body.get("AMENDMENT_LIST") or []


def build_filings_from_history(detail: dict, history: list[dict]) -> list[dict]:
    """Build UCCFiling rows for the History group anchored on detail.RECORD_NUM.

    The earliest "Lien Financing Stmt" in history is the parent (initial);
    every other event is a UCC-3 with parent_filing_number = initial's
    AMENDMENT_NUM.
    """
    rows: list[dict] = []
    initials = [e for e in history if e.get("AMENDMENT_TYPE") == "Lien Financing Stmt"]
    if not initials:
        return rows
    initial_filing_number = initials[0]["AMENDMENT_NUM"]

    for event in history:
        doc_type = event.get("AMENDMENT_TYPE", "")
        ft = DOC_TYPE_MAP.get(doc_type)
        if ft is None:
            continue
        is_initial = ft == FilingType.INITIAL
        rows.append({
            "filing_number": event["AMENDMENT_NUM"],
            "parent_filing_number": None if is_initial else initial_filing_number,
            "filing_date": _normalize_date(event.get("AMENDMENT_DATE")),
            "filing_type": ft.value,
            "debtor_name": detail.get("DEBTOR_NAME") or "",
            "debtor_address": detail.get("DEBTOR_ADDRESS") or "",
            "secured_party_name": detail.get("SEC_PARTY_NAME") or "",
            "secured_party_address": detail.get("SEC_PARTY_ADDRESS") or "",
            "status_portal": detail.get("STATUS") or "",
            "lapse_date": _normalize_date(detail.get("LAPSE_DATE")) or None,
            "source": "CA",
        })
    return rows


def extract_for_debtor(
    debtor_name: str, client: _BizfileClient | None = None,
) -> list[dict]:
    """Return all UCCFiling rows from any search hit for debtor_name."""
    client = client or HttpBizfileClient()
    rows: list[dict] = []
    for result in client.search(debtor_name):
        internal_id = result.get("ID")
        record_num = result.get("RECORD_NUM")
        if not (internal_id and record_num):
            continue
        detail = client.detail(internal_id)
        # Carry status/lapse from search-row response, where they live
        detail["STATUS"] = result.get("STATUS", "")
        detail["LAPSE_DATE"] = result.get("LAPSE_DATE")
        history = client.history(record_num)
        rows.extend(build_filings_from_history(detail, history))
    return rows


def _read_checkpoint(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with path.open() as f:
        return {json.loads(line)["company_name"] for line in f if line.strip()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cohort", type=Path,
                        default=data_path("ucc1_pilot_ca_org_cohort.jsonl"))
    parser.add_argument("--out", type=Path,
                        default=data_path("ucc1_pilot_raw.jsonl"))
    parser.add_argument("--checkpoint", type=Path,
                        default=data_path("ucc1_pilot_extractor_checkpoint.jsonl"))
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS)
    args = parser.parse_args()

    done = _read_checkpoint(args.checkpoint)
    client = HttpBizfileClient()

    with args.cohort.open() as cohort_f, \
         args.out.open("a") as out_f, \
         args.checkpoint.open("a") as ckpt_f:
        for line in cohort_f:
            row = json.loads(line)
            name = row["company_name"]
            if name in done:
                continue
            try:
                filings = extract_for_debtor(name, client=client)
            except Exception as e:
                print(f"ERROR for {name}: {e}", file=sys.stderr)
                ckpt_f.write(json.dumps({
                    "company_name": name, "filing_count": 0, "error": str(e),
                }) + "\n")
                continue
            for f in filings:
                f["cohort_company_name"] = name
                out_f.write(json.dumps(f) + "\n")
            ckpt_f.write(json.dumps({
                "company_name": name, "filing_count": len(filings),
            }) + "\n")
            if args.delay:
                time.sleep(args.delay)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
