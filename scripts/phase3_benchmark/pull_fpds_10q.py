"""Pull FPDS Element 10Q (SBIR/STTR research code) records from the public FPDS ATOM feed.

Structured, non-leaking label source for the Phase III match-quality benchmark (P1 positives).
Read-only public feed; paginated and cached under data/raw/fpds/atom_<code>/. Re-runnable.

Usage:
    python scripts/phase3_benchmark/pull_fpds_10q.py SR3 --pages 40
"""
from __future__ import annotations

import argparse
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
FEED = "https://www.fpds.gov/ezsearch/FEEDS/ATOM?FEEDNAME=PUBLIC"
UA = "sbir-analytics-research/1.0 (Phase III benchmark; contact repo owner)"

# Fields to lift from each <entry> (tag -> whether we also want the description attr)
TEXT_FIELDS = [
    "PIID", "UEI", "vendorName", "descriptionOfContractRequirement",
    "signedDate", "effectiveDate", "currentCompletionDate",
    "productOrServiceCode", "principalNAICSCode", "research",
    "agencyID", "contractActionType", "referencedIDVID", "extentCompeted",
    # funding office / command — enables true same-office hard negatives (N1)
    "contractingOfficeID", "contractingOfficeAgencyID", "fundingRequestingOfficeID",
]


def fetch_page(code: str, start: int, cache_dir: Path) -> str:
    cache_dir.mkdir(parents=True, exist_ok=True)
    f = cache_dir / f"page_{start:04d}.xml"
    if f.exists():
        return f.read_text(encoding="utf-8", errors="replace")
    q = urllib.parse.quote(f"RESEARCH:{code}")
    url = f"{FEED}&q={q}&start={start}"
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read().decode("utf-8", errors="replace")
            f.write_text(body, encoding="utf-8")
            return body
        except Exception as e:  # noqa: BLE001 - public feed, best-effort with backoff
            if attempt == 4:
                print(f"  page start={start} failed: {e}")
                return ""
            time.sleep(3 * (attempt + 1))
    return ""


def _subfield(block: str, tag: str) -> str:
    """Text of a leaf <ns:tag> within a sub-block (empty if absent)."""
    m = re.search(rf"<ns\d+:{tag}\b[^>]*>([^<]*)</ns\d+:{tag}>", block)
    return m.group(1).strip() if m else ""


def _award_key_fields(entry: str) -> dict:
    """Extract the compound-award-key parts from the NESTED awardContractID / referencedIDVID
    blocks. FPDS ``<referencedIDVID>`` is a PARENT element (agencyID + PIID children), so a flat
    text regex misses the parent-IDV PIID — the varying disambiguator. See audit-piid-grain.md.
    """
    ac = re.search(r"<ns\d+:awardContractID\b.*?</ns\d+:awardContractID>", entry, re.S)
    iv = re.search(r"<ns\d+:referencedIDVID\b.*?</ns\d+:referencedIDVID>", entry, re.S)
    acb = ac.group(0) if ac else ""
    ivb = iv.group(0) if iv else ""
    order_piid = _subfield(acb, "PIID")
    order_agency = _subfield(acb, "agencyID")
    idv_piid = _subfield(ivb, "PIID")
    idv_agency = _subfield(ivb, "agencyID")
    # Award-unique compound key: order PIID + awarding agency + parent-IDV PIID + parent-IDV agency.
    award_key = "|".join([order_piid, order_agency, idv_piid, idv_agency])
    return {
        "order_piid": order_piid, "order_agency_id": order_agency,
        "referenced_idv_piid": idv_piid, "referenced_idv_agency_id": idv_agency,
        "mod_number": _subfield(acb, "modNumber"),
        "transaction_number": _subfield(acb, "transactionNumber"),
        "award_key": award_key,
    }


def parse_entry(entry: str) -> dict:
    rec: dict[str, str | None] = {}
    for tag in TEXT_FIELDS:
        m = re.search(rf"<ns\d+:{tag}\b[^>]*>([^<]*)</ns\d+:{tag}>", entry)
        rec[tag] = m.group(1).strip() if m else None
        # capture the human-readable code description where present (PSC/NAICS/agency)
        ma = re.search(rf'<ns\d+:{tag}\b[^>]*\bdescription="([^"]*)"', entry)
        if ma:
            rec[f"{tag}_desc"] = ma.group(1).strip()
        man = re.search(rf'<ns\d+:{tag}\b[^>]*\bname="([^"]*)"', entry)
        if man:
            rec[f"{tag}_name"] = man.group(1).strip()
    # nested compound-key fields (fixes the degenerate all-"0001" bare-PIID census)
    rec.update(_award_key_fields(entry))
    return rec


def total_results(page_xml: str) -> int:
    m = re.search(r"<opensearch:totalResults>(\d+)</opensearch:totalResults>", page_xml)
    return int(m.group(1)) if m else 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("code", nargs="?", default="SR3", help="10Q research code (SR3, SR2, ST3, ...)")
    ap.add_argument("--pages", type=int, default=40, help="pages to pull (10 records each)")
    args = ap.parse_args()

    cache_dir = REPO / "data" / "raw" / "fpds" / f"atom_{args.code.lower()}"
    rows: list[dict] = []
    total = None
    for i in range(args.pages):
        start = i * 10
        xml = fetch_page(args.code, start, cache_dir)
        if not xml:
            break
        if total is None:
            total = total_results(xml)
            print(f"feed reports {total} total {args.code} records; pulling up to {args.pages*10}")
        entries = re.findall(r"<entry>.*?</entry>", xml, re.S)
        if not entries:
            break
        for e in entries:
            r = parse_entry(e)
            r["_research_code"] = args.code
            rows.append(r)
        if total and start + 10 >= total:
            break
        time.sleep(0.3)

    df = pd.DataFrame(rows)
    out = REPO / "data" / "derived" / f"fpds_10q_{args.code.lower()}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out)
    print(f"parsed {len(df)} records -> {out}")
    if len(df):
        desc = df["descriptionOfContractRequirement"].fillna("")
        print(f"  UEI fill: {df['UEI'].notna().mean():.0%}  "
              f"desc fill: {(desc.str.len()>0).mean():.0%}  "
              f"median desc len: {int(desc.str.len().median())} chars")
        print(f"  distinct UEIs: {df['UEI'].nunique()}")
        # key structure — bare order PIID vs recoverable compound award key
        print(f"  distinct bare order PIID: {df['order_piid'].nunique()}  "
              f"distinct parent-IDV PIID: {df['referenced_idv_piid'].nunique()}  "
              f"distinct COMPOUND award_key: {df['award_key'].nunique()}  of {len(df)} rows")


if __name__ == "__main__":
    main()
