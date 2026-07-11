#!/usr/bin/env python3
"""
Retrieve actual SEC filing text for prime acquisitions of nanotech SBIR firms.

For each confirmed prime acquisition, queries EDGAR EFTS (full-text search) to
find 8-K filings (acquisition announcements and closings), then fetches the
press release exhibit text to extract deal terms: purchase price, multiples,
revenue, strategic rationale.

Inputs:
  data/nano_prime_acquisitions.csv    — confirmed prime acquisition list

Outputs:
  data/nano_prime_edgar_text.jsonl    — one record per filing fetched
  data/nano_prime_deal_terms.csv      — extracted deal terms per acquisition

Usage:
  python scripts/data/nano_prime_edgar_filings.py
"""

import csv
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data"

EDGAR_EFTS = "https://efts.sec.gov/LATEST/search-index"
EDGAR_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"
UA = "sbir-research/1.0 contact@example.com"

# Acquisition targets with known dates for scoping the search window
TARGETS = [
    {
        "firm": "Physical Optics Corporation",
        "acquirer": "Mercury Systems",
        "category": "defense",
        "start": "2020-01-01",
        "end": "2021-06-30",
        "forms": "8-K",
    },
    {
        "firm": "Intellisense Systems",
        "acquirer": "Mercury Systems",
        "category": "defense",
        "start": "2023-01-01",
        "end": "2025-06-30",
        "forms": "8-K",
    },
    {
        "firm": "Anasys Instruments",
        "acquirer": "Bruker",
        "category": "pharma",
        "start": "2017-06-01",
        "end": "2019-06-30",
        "forms": "8-K",
    },
    {
        "firm": "Senior Scientific",
        "acquirer": "Bruker",
        "category": "pharma",
        "start": "2012-01-01",
        "end": "2016-12-31",
        "forms": "8-K",
    },
    {
        "firm": "Nomadics",
        "acquirer": "FLIR Systems",
        "category": "defense",
        "start": "2003-01-01",
        "end": "2005-12-31",
        "forms": "8-K",
    },
    {
        "firm": "EKOS Corporation",
        "acquirer": "C.R. Bard",
        "category": "pharma",
        "start": "2007-01-01",
        "end": "2011-12-31",
        "forms": "8-K",
    },
    {
        "firm": "EraGen Biosciences",
        "acquirer": "Luminex",
        "category": "pharma",
        "start": "2007-01-01",
        "end": "2012-12-31",
        "forms": "8-K",
    },
    {
        "firm": "Visen Medical",
        "acquirer": "PerkinElmer",
        "category": "pharma",
        "start": "2009-01-01",
        "end": "2013-12-31",
        "forms": "8-K",
    },
    {
        "firm": "GATR Technologies",
        "acquirer": "Cubic Corp",
        "category": "defense",
        "start": "2019-01-01",
        "end": "2022-12-31",
        "forms": "8-K",
    },
    {
        "firm": "SY Technology",
        "acquirer": "L3 Technologies",
        "category": "defense",
        "start": "2004-01-01",
        "end": "2008-12-31",
        "forms": "8-K",
    },
]


def get(url: str, params: dict | None = None) -> bytes:
    """Simple HTTP GET with User-Agent and rate limiting."""
    if params:
        qs = "&".join(f"{k}={quote_plus(str(v))}" for k, v in params.items())
        url = f"{url}?{qs}"
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=30) as resp:
        return resp.read()


def efts_search(firm: str, start: str, end: str, forms: str) -> list[dict]:
    """
    Query EDGAR EFTS full-text search for filings mentioning the firm name.
    Returns a list of hit dicts with _id and _source fields.
    """
    params = {
        "q": f'"{firm}"',
        "dateRange": "custom",
        "startdt": start,
        "enddt": end,
        "forms": forms,
    }
    try:
        raw = get(EDGAR_EFTS, params)
        data = json.loads(raw)
        return data.get("hits", {}).get("hits", [])
    except Exception as e:
        print(f"  EFTS error for '{firm}': {e}", file=sys.stderr)
        return []


def parse_accession(hit_id: str) -> tuple[str, str] | None:
    """
    Parse EDGAR hit _id into (accession_number, filename).
    Format: '0001234567-20-123456:filename.htm'
    """
    if ":" not in hit_id:
        return None
    acc, fname = hit_id.rsplit(":", 1)
    return acc, fname


def extract_cik_from_accession(acc: str) -> str:
    """Extract the 10-digit CIK from the accession number prefix."""
    parts = acc.replace("-", "").split("-")
    # accession format: XXXXXXXXXX-YY-NNNNNN (10-2-6 digits)
    return acc.replace("-", "")[:10].lstrip("0")


def fetch_filing_text(acc: str, fname: str) -> str | None:
    """
    Fetch the text of a specific filing document from EDGAR Archives.
    Derives CIK from the accession number.
    """
    cik = acc.replace("-", "")[:10].lstrip("0")
    acc_nodash = acc.replace("-", "")
    url = f"{EDGAR_ARCHIVES}/{cik}/{acc_nodash}/{fname}"
    try:
        raw = get(url)
        html = raw.decode("utf-8", errors="replace")
        # Strip HTML tags
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"&nbsp;", " ", text)
        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"&#[0-9]+;", " ", text)
        text = re.sub(r"&[a-z]+;", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text
    except Exception as e:
        print(f"    fetch error {url}: {e}", file=sys.stderr)
        return None


def score_hit_relevance(firm: str, text: str) -> float:
    """
    Score a filing text for acquisition-announcement relevance.
    Higher = more likely to contain deal terms.
    """
    score = 0.0
    firm_lower = firm.lower()
    text_lower = text.lower()

    if firm_lower in text_lower:
        score += 2.0

    acquisition_terms = [
        "purchase price", "acquisition price", "aggregate consideration",
        "total consideration", "acquire", "acquisition", "definitive agreement",
        "definitive merger", "merger agreement", "all-cash", "cash consideration",
        "million", "billion",
    ]
    for term in acquisition_terms:
        if term in text_lower:
            score += 0.5

    # Strong signal: explicit dollar amounts near "acquire"
    if re.search(r"\$\d+[\.,]?\d*\s*(?:million|billion)", text_lower):
        score += 3.0

    # Weak signal if it's just a quarterly earnings mention
    if re.search(r"(earnings|revenue|quarterly|guidance)", text_lower[:200]):
        score -= 1.0

    return score


def extract_deal_terms(firm: str, text: str) -> dict:
    """
    Heuristically extract deal terms from filing text.
    Returns dict with price, multiple, revenue, rationale snippets.
    """
    terms: dict = {
        "price_mention": "",
        "multiple_mention": "",
        "revenue_mention": "",
        "rationale_snippet": "",
        "text_length": len(text),
    }

    # Find dollar amounts mentioned near acquisition language
    price_patterns = [
        r"\$\s*(\d[\d,\.]+)\s*(million|billion)[^.]*(?:purchase price|consideration|acquire|acquisition)",
        r"(?:purchase price|consideration|acquire|acquisition)[^.]*\$\s*(\d[\d,\.]+)\s*(million|billion)",
        r"all-cash[^.]*\$\s*(\d[\d,\.]+)\s*(million|billion)",
        r"(\d[\d,\.]+)\s*(million|billion)[^.]*all.cash",
    ]
    for pat in price_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            # Grab surrounding sentence
            start = max(0, m.start() - 100)
            end = min(len(text), m.end() + 100)
            terms["price_mention"] = text[start:end].strip()
            break

    # EBITDA / revenue multiples
    mult_m = re.search(
        r"(\d+(?:\.\d+)?)\s*x\s+(?:next twelve months|ntm|ltm|trailing|forward|annualized)?\s*(?:ebitda|revenue|sales)",
        text, re.IGNORECASE
    )
    if mult_m:
        start = max(0, mult_m.start() - 80)
        end = min(len(text), mult_m.end() + 80)
        terms["multiple_mention"] = text[start:end].strip()

    # Revenue of acquired company
    rev_m = re.search(
        rf"{re.escape(firm.split()[0])}[^.]*revenue[^.]*\$\s*(\d[\d,\.]+)\s*(?:million|billion)",
        text, re.IGNORECASE
    )
    if not rev_m:
        rev_m = re.search(
            r"(?:generate|generates|generated|revenue)[^.]*\$\s*(\d[\d,\.]+)\s*(?:million|billion)",
            text, re.IGNORECASE
        )
    if rev_m:
        start = max(0, rev_m.start() - 60)
        end = min(len(text), rev_m.end() + 100)
        terms["revenue_mention"] = text[start:end].strip()

    # Strategic rationale: sentence containing "enables" / "expands" / "strengthens"
    rat_m = re.search(
        r"[A-Z][^.]*(?:enables|expands|strengthens|accelerates|broadens|adds)[^.]*\.",
        text
    )
    if rat_m:
        terms["rationale_snippet"] = rat_m.group(0).strip()

    return terms


def main() -> int:
    out_jsonl = DATA / "nano_prime_edgar_text.jsonl"
    out_csv = DATA / "nano_prime_deal_terms.csv"

    results: list[dict] = []

    for target in TARGETS:
        firm = target["firm"]
        acquirer = target["acquirer"]
        print(f"\n{'='*60}")
        print(f"  {firm}  ←  {acquirer}")
        print(f"{'='*60}")

        hits = efts_search(firm, target["start"], target["end"], target["forms"])
        print(f"  EFTS hits: {len(hits)}")

        if not hits:
            results.append({
                "firm": firm,
                "acquirer": acquirer,
                "category": target["category"],
                "filing_date": "",
                "accession": "",
                "filename": "",
                "score": 0,
                "found": False,
                **{k: "" for k in ["price_mention", "multiple_mention", "revenue_mention", "rationale_snippet", "text_length"]},
            })
            continue

        # Score and rank hits; fetch top candidates
        best_result = None
        best_score = -1.0

        for hit in hits[:8]:
            parsed = parse_accession(hit.get("_id", ""))
            if not parsed:
                continue
            acc, fname = parsed

            # Skip index/header files; prefer .htm press releases
            if not fname.endswith((".htm", ".html", ".txt")):
                continue
            if fname in ("index.htm", "filing-summary.htm"):
                continue

            src = hit.get("_source", {})
            file_date = src.get("file_date", "")

            print(f"  Fetching {file_date} {fname[:50]}...")
            text = fetch_filing_text(acc, fname)
            time.sleep(0.3)  # EDGAR rate limit courtesy

            if not text or len(text) < 200:
                continue

            score = score_hit_relevance(firm, text)
            print(f"    relevance score: {score:.1f}  len:{len(text):,}")

            if score > best_score:
                best_score = score
                terms = extract_deal_terms(firm, text)
                best_result = {
                    "firm": firm,
                    "acquirer": acquirer,
                    "category": target["category"],
                    "filing_date": file_date,
                    "accession": acc,
                    "filename": fname,
                    "score": score,
                    "found": True,
                    "full_text_excerpt": text[:5000],
                    **terms,
                }

        if best_result:
            results.append(best_result)
            print(f"\n  Best result (score {best_result['score']:.1f}):")
            if best_result["price_mention"]:
                print(f"  PRICE:    {best_result['price_mention'][:200]}")
            if best_result["multiple_mention"]:
                print(f"  MULTIPLE: {best_result['multiple_mention'][:200]}")
            if best_result["revenue_mention"]:
                print(f"  REVENUE:  {best_result['revenue_mention'][:200]}")
            if best_result["rationale_snippet"]:
                print(f"  RATIONALE:{best_result['rationale_snippet'][:200]}")
        else:
            results.append({
                "firm": firm,
                "acquirer": acquirer,
                "category": target["category"],
                "filing_date": "",
                "accession": "",
                "filename": "",
                "score": 0,
                "found": False,
                **{k: "" for k in ["price_mention", "multiple_mention", "revenue_mention",
                                    "rationale_snippet", "text_length", "full_text_excerpt"]},
            })

        time.sleep(1.0)

    # Write JSONL (full text included)
    with open(out_jsonl, "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")
    print(f"\n\nWritten: {out_jsonl}")

    # Write CSV (no full text)
    csv_fields = ["firm", "acquirer", "category", "filing_date", "accession",
                  "score", "found", "price_mention", "multiple_mention",
                  "revenue_mention", "rationale_snippet", "text_length"]
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=csv_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(results)
    print(f"Written: {out_csv}")

    # Summary
    print("\n" + "="*60)
    print("DEAL TERMS EXTRACTION SUMMARY")
    print("="*60)
    found = [r for r in results if r.get("found")]
    with_price = [r for r in found if r.get("price_mention")]
    with_multiple = [r for r in found if r.get("multiple_mention")]
    print(f"Targets:           {len(results)}")
    print(f"Filings found:     {len(found)}")
    print(f"Price extracted:   {len(with_price)}")
    print(f"Multiple extracted:{len(with_multiple)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
