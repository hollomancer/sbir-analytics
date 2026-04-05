#!/usr/bin/env python3
"""Generate a weekly SBIR awards report in markdown.

Downloads the SBIR bulk CSV (from S3 if available, else direct from
SBIR.gov) and uses DuckDB to filter for awards whose Proposal Award
Date falls within the past 7 days, then outputs a markdown summary
with links to SBIR.gov, solicitations, and USAspending.

When OPENAI_API_KEY is set, uses the OpenAI API to:
- Search the web for public info on each awardee company
- Generate a two-paragraph synopsis of all weekly award activity
- Generate a brief description per award (informed by the abstract,
  solicitation, USAspending data, and company research)
- Generate a company diligence paragraph per awardee (informed by
  historical SBIR data, web research, and current award context)
- Generate a PI diligence paragraph per Principal Investigator
  (informed by their SBIR history and company context)

Usage:
    python scripts/data/weekly_awards_report.py
    python scripts/data/weekly_awards_report.py --days 14 --output report.md
    OPENAI_API_KEY=sk-... python scripts/data/weekly_awards_report.py
"""

import argparse
import json
import os
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, UTC
from pathlib import Path
from urllib.parse import quote

import httpx

# Lazy imports from the sbir_etl package.  These are optional — the script
# falls back to a standalone CSV download + Python-based filtering when the
# full package isn't installed (e.g. lightweight CI runners).
try:
    from sbir_etl.extractors.sbir import SbirDuckDBExtractor
    from sbir_etl.extractors.sbir_gov_api import SBIR_AWARDS_CSV_URL as SBIR_AWARDS_URL
    from sbir_etl.utils.cloud_storage import find_latest_sbir_awards, get_s3_bucket_from_env
    from sbir_etl.utils.date_utils import parse_date as _parse_date

    _HAS_SBIR_ETL = True
except ImportError:
    SBIR_AWARDS_URL = "https://data.www.sbir.gov/mod_awarddatapublic/award_data.csv"
    _HAS_SBIR_ETL = False
    SbirDuckDBExtractor = None  # type: ignore[assignment, misc]

    def _parse_date(value, **_kwargs):  # type: ignore[misc]
        """Minimal fallback date parser when sbir_etl is unavailable."""
        from datetime import date as _date

        if not value or not str(value).strip():
            return None
        s = str(value).strip()
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S", "%m/%d/%y"):
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                continue
        return None

# URL templates for external links
SBIR_AWARD_SEARCH_URL = "https://www.sbir.gov/sbirsearch/award/all"
SBIR_SOLICITATION_URL = "https://www.sbir.gov/sbirsearch/topic/default"
USASPENDING_SEARCH_URL = "https://www.usaspending.gov/search"

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
OPENAI_MODEL = "gpt-4.1-mini"
OPENAI_DILIGENCE_MODEL = "gpt-4.1"

# Batch size for per-award descriptions (awards per API call)
DESCRIPTION_BATCH_SIZE = 10

# Caps on OpenAI API usage (override via env vars)
MAX_COMPANIES_TO_RESEARCH = int(os.environ.get("MAX_COMPANIES_TO_RESEARCH", "50"))
MAX_AWARDS_TO_DESCRIBE = int(os.environ.get("MAX_AWARDS_TO_DESCRIBE", "100"))

# Retry configuration for OpenAI API calls
OPENAI_MAX_RETRIES = 3
OPENAI_RETRY_BACKOFF_BASE = 2  # seconds

# External API endpoints for PI diligence and solicitation lookup
PATENTSVIEW_API_URL = "https://search.patentsview.org/api/v1/patent"
SEMANTIC_SCHOLAR_API_URL = "https://api.semanticscholar.org/graph/v1"
USASPENDING_API_URL = "https://api.usaspending.gov/api/v2"
SBIR_GOV_API_URL = "https://api.www.sbir.gov/public/api"
SAM_GOV_API_URL = "https://api.sam.gov/entity-information/v3/entities"
ORCID_API_URL = "https://pub.orcid.org/v3.0"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class CompanyResearch:
    """Results of web research on an awardee company."""

    summary: str
    source_urls: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Data loading (reuses SbirDuckDBExtractor + cloud_storage)
# ---------------------------------------------------------------------------


@dataclass
class DataSource:
    """Metadata about the resolved CSV data source."""

    path: Path
    origin: str  # "s3" or "download"
    # S3 key date (e.g. "2026-04-01" from raw/awards/2026-04-01/award_data.csv)
    s3_key_date: str | None = None


def _resolve_csv_path() -> DataSource:
    """Resolve the SBIR CSV path: try S3 first, then download fresh.

    In CI the data-refresh workflow uploads the CSV to S3 weekly, so we
    prefer that cached copy.  Falls back to downloading directly from
    SBIR.gov when S3 isn't configured or the file isn't found.
    """
    # Try S3 first (only when sbir_etl is installed)
    if _HAS_SBIR_ETL:
        bucket = get_s3_bucket_from_env()
        if bucket:
            s3_url = find_latest_sbir_awards(bucket)
            if s3_url:
                print(f"Using S3-cached CSV: {s3_url}", file=sys.stderr)
                # Extract date from S3 key: raw/awards/YYYY-MM-DD/award_data.csv
                import re

                date_match = re.search(r"raw/awards/(\d{4}-\d{2}-\d{2})/", s3_url)
                key_date = date_match.group(1) if date_match else None
                return DataSource(path=Path(s3_url), origin="s3", s3_key_date=key_date)

    # Fall back to direct download
    print(f"S3 not available; downloading from {SBIR_AWARDS_URL}...", file=sys.stderr)
    with httpx.Client(timeout=600, follow_redirects=True) as client:
        response = client.get(SBIR_AWARDS_URL)
        response.raise_for_status()

    tmp = Path(tempfile.gettempdir()) / "sbir_weekly_award_data.csv"
    tmp.write_bytes(response.content)
    print(f"Downloaded {tmp.stat().st_size / 1024 / 1024:.1f} MB", file=sys.stderr)
    return DataSource(path=tmp, origin="download")


def _check_data_freshness(
    source: DataSource,
    max_award_date: str | None,
    days: int,
) -> list[str]:
    """Verify that the bulk data is fresh enough for the reporting window.

    Returns a list of warning strings (empty if everything looks good).
    """
    warnings: list[str] = []
    now = datetime.now(UTC).replace(tzinfo=None)

    # Check 1: S3 key date — was the data-refresh recent?
    if source.s3_key_date:
        key_dt = _parse_date(source.s3_key_date)
        if key_dt:
            key_datetime = datetime(key_dt.year, key_dt.month, key_dt.day)
            age_days = (now - key_datetime).days
            if age_days > days + 3:  # allow a few days of slack
                warnings.append(
                    f"S3 data is {age_days} days old (key date: {source.s3_key_date}). "
                    f"The data-refresh workflow may have failed."
                )

    # Check 2: max Proposal Award Date in the data — is the data itself current?
    if max_award_date:
        max_dt = _parse_date(max_award_date)
        if max_dt:
            max_datetime = datetime(max_dt.year, max_dt.month, max_dt.day)
            data_age = (now - max_datetime).days
            if data_age > days + 14:
                warnings.append(
                    f"Most recent award in data is from {max_award_date} "
                    f"({data_age} days ago). SBIR.gov bulk data may not have "
                    f"been updated recently."
                )

    return warnings


def fetch_weekly_awards(days: int = 7) -> tuple[list[dict], list[str]]:
    """Load SBIR CSV and filter for awards in the past N days.

    When sbir_etl is installed, uses SbirDuckDBExtractor for fast
    columnar import and SQL-based date filtering.  Otherwise falls back
    to csv.DictReader with Python-level filtering.

    Returns (awards, freshness_warnings).
    """
    source = _resolve_csv_path()
    cutoff_str = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%d")

    if _HAS_SBIR_ETL and SbirDuckDBExtractor is not None:
        # Fast path: DuckDB columnar import + SQL filtering
        extractor = SbirDuckDBExtractor(
            csv_path=source.path,
            duckdb_path=":memory:",
            use_s3_first=False,  # we already resolved the path
        )
        extractor.import_csv()

        table = extractor._table_identifier
        query = (
            f"SELECT * FROM {table} "
            f"WHERE \"Proposal Award Date\" >= '{cutoff_str}' "
            f"ORDER BY \"Proposal Award Date\" DESC, "
            f"TRY_CAST(\"Award Amount\" AS DOUBLE) DESC"
        )

        df = extractor.duckdb_client.execute_query_df(query)
        print(f"Found {len(df)} awards since {cutoff_str} (DuckDB)", file=sys.stderr)
        awards = df.fillna("").to_dict("records")

        # Get max date across the full dataset for freshness check
        max_date_df = extractor.duckdb_client.execute_query_df(
            f'SELECT MAX("Proposal Award Date") AS max_date FROM {table}'
        )
        max_award_date = str(max_date_df.iloc[0]["max_date"]) if len(max_date_df) else None

    else:
        # Fallback: csv.DictReader + Python filtering
        import csv
        import io

        print("Using csv.DictReader fallback for filtering", file=sys.stderr)
        cutoff_dt = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)

        text = source.path.read_text(encoding="utf-8")
        reader = csv.DictReader(io.StringIO(text))
        awards = []
        all_dates: list[str] = []
        for row in reader:
            date_val = row.get("Proposal Award Date", "")
            if date_val:
                all_dates.append(date_val)
            parsed = _parse_date(date_val)
            if parsed:
                row_dt = datetime(parsed.year, parsed.month, parsed.day)
                if row_dt >= cutoff_dt:
                    awards.append(row)

        def sort_key(a):
            dt = _parse_date(a.get("Proposal Award Date", ""))
            ts = datetime(dt.year, dt.month, dt.day).timestamp() if dt else 0
            try:
                amount = float(str(a.get("Award Amount", "0")).replace(",", "").replace("$", ""))
            except (ValueError, AttributeError):
                amount = 0
            return (-ts, -amount)

        awards.sort(key=sort_key)
        max_award_date = max(all_dates) if all_dates else None
        print(f"Found {len(awards)} awards since {cutoff_str} (csv fallback)", file=sys.stderr)

    # Verify data freshness
    freshness_warnings = _check_data_freshness(source, max_award_date, days)
    for w in freshness_warnings:
        print(f"WARNING: {w}", file=sys.stderr)

    return awards, freshness_warnings


# ---------------------------------------------------------------------------
# Historical context (for diligence)
# ---------------------------------------------------------------------------


def get_company_history(
    awards: list[dict],
) -> dict[str, dict]:
    """Extract historical SBIR award context per company from the full dataset.

    Scans the complete CSV (not just the weekly window) to build a profile of
    each company's SBIR track record: total awards, phases reached, agencies
    served, cumulative funding, and date range.

    Returns a dict keyed by upper-cased company name.
    """
    source = _resolve_csv_path()

    if _HAS_SBIR_ETL and SbirDuckDBExtractor is not None:
        extractor = SbirDuckDBExtractor(
            csv_path=source.path,
            duckdb_path=":memory:",
            use_s3_first=False,
        )
        extractor.import_csv()
        table = extractor._table_identifier

        # Collect the set of companies we care about (from this week's awards)
        company_names = {str(a.get("Company", "")).strip().upper() for a in awards}
        company_names.discard("")

        history: dict[str, dict] = {}
        for name in company_names:
            escaped = name.replace("'", "''")
            query = (
                f"SELECT \"Phase\", \"Agency\", \"Award Amount\", "
                f"\"Proposal Award Date\", \"Award Title\", \"Program\" "
                f"FROM {table} "
                f"WHERE UPPER(\"Company\") = '{escaped}' "
                f"ORDER BY \"Proposal Award Date\" DESC"
            )
            df = extractor.duckdb_client.execute_query_df(query)
            if df.empty:
                continue

            phases = set()
            agencies = set()
            total_funding = 0.0
            dates: list[str] = []
            titles: list[str] = []
            programs = set()

            for _, row in df.iterrows():
                phase = str(row.get("Phase", "")).strip()
                if phase:
                    phases.add(phase)
                ag = str(row.get("Agency", "")).strip()
                if ag:
                    agencies.add(ag)
                prog = str(row.get("Program", "")).strip()
                if prog:
                    programs.add(prog)
                try:
                    total_funding += float(
                        str(row.get("Award Amount", "0"))
                        .replace(",", "")
                        .replace("$", "")
                    )
                except (ValueError, TypeError):
                    pass
                d = str(row.get("Proposal Award Date", "")).strip()
                if d:
                    dates.append(d)
                t = str(row.get("Award Title", "")).strip()
                if t and t not in titles:
                    titles.append(t)

            history[name] = {
                "total_awards": len(df),
                "phases": sorted(phases),
                "agencies": sorted(agencies),
                "programs": sorted(programs),
                "total_funding": total_funding,
                "earliest_date": min(dates) if dates else None,
                "latest_date": max(dates) if dates else None,
                "sample_titles": titles[:5],
            }

        return history

    # Fallback: scan the CSV with Python
    import csv
    import io

    company_names = {str(a.get("Company", "")).strip().upper() for a in awards}
    company_names.discard("")
    text = source.path.read_text(encoding="utf-8")
    reader = csv.DictReader(io.StringIO(text))

    history = {}
    for row in reader:
        name = str(row.get("Company", "")).strip().upper()
        if name not in company_names:
            continue
        if name not in history:
            history[name] = {
                "total_awards": 0,
                "phases": set(),
                "agencies": set(),
                "programs": set(),
                "total_funding": 0.0,
                "dates": [],
                "sample_titles": [],
            }
        h = history[name]
        h["total_awards"] += 1
        phase = str(row.get("Phase", "")).strip()
        if phase:
            h["phases"].add(phase)
        ag = str(row.get("Agency", "")).strip()
        if ag:
            h["agencies"].add(ag)
        prog = str(row.get("Program", "")).strip()
        if prog:
            h["programs"].add(prog)
        try:
            h["total_funding"] += float(
                str(row.get("Award Amount", "0")).replace(",", "").replace("$", "")
            )
        except (ValueError, TypeError):
            pass
        d = str(row.get("Proposal Award Date", "")).strip()
        if d:
            h["dates"].append(d)
        t = str(row.get("Award Title", "")).strip()
        if t and len(h["sample_titles"]) < 5 and t not in h["sample_titles"]:
            h["sample_titles"].append(t)

    # Normalize the set fields to sorted lists
    for name, h in history.items():
        dates = h.pop("dates", [])
        h["phases"] = sorted(h["phases"])
        h["agencies"] = sorted(h["agencies"])
        h["programs"] = sorted(h["programs"])
        h["earliest_date"] = min(dates) if dates else None
        h["latest_date"] = max(dates) if dates else None

    return history


def get_pi_history(
    awards: list[dict],
) -> dict[str, dict]:
    """Extract historical SBIR context per Principal Investigator.

    Similar to get_company_history but keyed on PI name.
    Returns a dict keyed by upper-cased PI name.
    """
    source = _resolve_csv_path()

    pi_names = set()
    for a in awards:
        pi = str(a.get("PI Name", "")).strip().upper()
        if pi:
            pi_names.add(pi)

    if not pi_names:
        return {}

    if _HAS_SBIR_ETL and SbirDuckDBExtractor is not None:
        extractor = SbirDuckDBExtractor(
            csv_path=source.path,
            duckdb_path=":memory:",
            use_s3_first=False,
        )
        extractor.import_csv()
        table = extractor._table_identifier

        history: dict[str, dict] = {}
        for name in pi_names:
            escaped = name.replace("'", "''")
            query = (
                f"SELECT \"Company\", \"Phase\", \"Agency\", \"Award Amount\", "
                f"\"Proposal Award Date\", \"Award Title\", \"Program\" "
                f"FROM {table} "
                f"WHERE UPPER(\"PI Name\") = '{escaped}' "
                f"ORDER BY \"Proposal Award Date\" DESC"
            )
            df = extractor.duckdb_client.execute_query_df(query)
            if df.empty:
                continue

            companies = set()
            phases = set()
            agencies = set()
            total_funding = 0.0
            dates: list[str] = []
            titles: list[str] = []

            for _, row in df.iterrows():
                co = str(row.get("Company", "")).strip()
                if co:
                    companies.add(co)
                phase = str(row.get("Phase", "")).strip()
                if phase:
                    phases.add(phase)
                ag = str(row.get("Agency", "")).strip()
                if ag:
                    agencies.add(ag)
                try:
                    total_funding += float(
                        str(row.get("Award Amount", "0"))
                        .replace(",", "")
                        .replace("$", "")
                    )
                except (ValueError, TypeError):
                    pass
                d = str(row.get("Proposal Award Date", "")).strip()
                if d:
                    dates.append(d)
                t = str(row.get("Award Title", "")).strip()
                if t and t not in titles:
                    titles.append(t)

            history[name] = {
                "total_awards": len(df),
                "companies": sorted(companies),
                "phases": sorted(phases),
                "agencies": sorted(agencies),
                "total_funding": total_funding,
                "earliest_date": min(dates) if dates else None,
                "latest_date": max(dates) if dates else None,
                "sample_titles": titles[:5],
            }

        return history

    # Fallback: CSV scan
    import csv
    import io

    text = source.path.read_text(encoding="utf-8")
    reader = csv.DictReader(io.StringIO(text))

    history = {}
    for row in reader:
        name = str(row.get("PI Name", "")).strip().upper()
        if name not in pi_names:
            continue
        if name not in history:
            history[name] = {
                "total_awards": 0,
                "companies": set(),
                "phases": set(),
                "agencies": set(),
                "total_funding": 0.0,
                "dates": [],
                "sample_titles": [],
            }
        h = history[name]
        h["total_awards"] += 1
        co = str(row.get("Company", "")).strip()
        if co:
            h["companies"].add(co)
        phase = str(row.get("Phase", "")).strip()
        if phase:
            h["phases"].add(phase)
        ag = str(row.get("Agency", "")).strip()
        if ag:
            h["agencies"].add(ag)
        try:
            h["total_funding"] += float(
                str(row.get("Award Amount", "0")).replace(",", "").replace("$", "")
            )
        except (ValueError, TypeError):
            pass
        d = str(row.get("Proposal Award Date", "")).strip()
        if d:
            h["dates"].append(d)
        t = str(row.get("Award Title", "")).strip()
        if t and len(h["sample_titles"]) < 5 and t not in h["sample_titles"]:
            h["sample_titles"].append(t)

    for name, h in history.items():
        dates = h.pop("dates", [])
        h["companies"] = sorted(h["companies"])
        h["phases"] = sorted(h["phases"])
        h["agencies"] = sorted(h["agencies"])
        h["earliest_date"] = min(dates) if dates else None
        h["latest_date"] = max(dates) if dates else None

    return history


# ---------------------------------------------------------------------------
# PI external data lookups (patents, publications, federal awards)
# ---------------------------------------------------------------------------


@dataclass
class PIPatentRecord:
    """Summary of a PI's patent portfolio from PatentsView."""

    total_patents: int
    sample_titles: list[str]
    assignees: list[str]
    date_range: tuple[str | None, str | None]


@dataclass
class PIPublicationRecord:
    """Summary of a PI's publication history from Semantic Scholar."""

    total_papers: int
    h_index: int | None
    citation_count: int
    sample_titles: list[str]
    affiliations: list[str]


@dataclass
class FederalAwardSummary:
    """Summary of a single federal award from USAspending."""

    award_id: str
    description: str
    amount: float
    agency: str
    award_type: str
    start_date: str
    cfda_number: str  # Assistance Listing Number


@dataclass
class PIFederalAwardRecord:
    """Summary of a PI's company's federal awards from USAspending.

    Separates SBIR/STTR awards from non-SBIR federal work. Non-SBIR
    awards to a company with SBIR history are potential follow-on /
    Phase III commercialization signals.
    """

    total_awards: int
    total_funding: float
    agencies: list[str]
    award_types: list[str]  # e.g. contracts, grants, IDVs
    date_range: tuple[str | None, str | None]
    # Follow-on analysis
    sbir_award_count: int = 0
    sbir_funding: float = 0.0
    non_sbir_award_count: int = 0
    non_sbir_funding: float = 0.0
    non_sbir_agencies: list[str] = field(default_factory=list)
    non_sbir_sample_descriptions: list[str] = field(default_factory=list)


def _split_pi_name(full_name: str) -> tuple[str, str]:
    """Split a PI name into (first, last) for API queries.

    SBIR data typically stores names as 'First Last' or 'Last, First'.
    """
    full_name = full_name.strip()
    if "," in full_name:
        parts = [p.strip() for p in full_name.split(",", 1)]
        return (parts[1], parts[0]) if len(parts) == 2 else (parts[0], "")
    parts = full_name.split()
    if len(parts) >= 2:
        return (parts[0], parts[-1])
    return (full_name, "")


def lookup_pi_patents(pi_name: str, company_name: str | None = None) -> PIPatentRecord | None:
    """Query PatentsView for patents where the PI is a named inventor.

    Uses the PatentsView API inventor_name fields. Falls back to
    filtering assignee results if the direct inventor query returns nothing.
    """
    first, last = _split_pi_name(pi_name)
    if not last:
        return None

    api_key = os.environ.get("PATENTSVIEW_API_KEY", "")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-Api-Key"] = api_key

    # Build query: search by inventor last name + first name
    query: dict = {
        "_and": [
            {"inventor_name_last": last},
        ]
    }
    if first:
        query["_and"].append({"inventor_name_first": first})

    payload = {
        "q": query,
        "f": [
            "patent_number",
            "patent_title",
            "patent_date",
            "assignee_organization",
            "inventor_name_first",
            "inventor_name_last",
        ],
        "o": {"page": 0, "per_page": 100},
    }

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(PATENTSVIEW_API_URL, headers=headers, json=payload)
            if resp.status_code != 200:
                print(
                    f"PatentsView API returned {resp.status_code} for {pi_name}",
                    file=sys.stderr,
                )
                return None
            data = resp.json()
    except Exception as e:
        print(f"PatentsView API error for {pi_name}: {e}", file=sys.stderr)
        return None

    patents = data.get("patents", [])
    if not patents:
        return None

    titles = []
    assignees: set[str] = set()
    dates: list[str] = []

    for p in patents:
        t = p.get("patent_title", "")
        if t and t not in titles and len(titles) < 5:
            titles.append(t)
        org = p.get("assignee_organization", "")
        if org:
            assignees.add(org)
        d = p.get("patent_date", "")
        if d:
            dates.append(d)

    return PIPatentRecord(
        total_patents=len(patents),
        sample_titles=titles,
        assignees=sorted(assignees),
        date_range=(min(dates) if dates else None, max(dates) if dates else None),
    )


def lookup_pi_publications(pi_name: str) -> PIPublicationRecord | None:
    """Query Semantic Scholar for the PI's publication history.

    Uses the author search endpoint to find the PI, then fetches
    their publication summary.
    """
    first, last = _split_pi_name(pi_name)
    if not last:
        return None

    search_query = f"{first} {last}".strip()

    try:
        # Step 1: Search for the author
        with httpx.Client(timeout=30) as client:
            resp = client.get(
                f"{SEMANTIC_SCHOLAR_API_URL}/author/search",
                params={"query": search_query, "limit": 5},
            )
            if resp.status_code != 200:
                print(
                    f"Semantic Scholar search returned {resp.status_code} for {pi_name}",
                    file=sys.stderr,
                )
                return None
            search_data = resp.json()

        authors = search_data.get("data", [])
        if not authors:
            return None

        # Pick the best match (first result from Semantic Scholar's ranking)
        author = authors[0]
        author_id = author.get("authorId")
        if not author_id:
            return None

        # Step 2: Get author details with papers
        with httpx.Client(timeout=30) as client:
            resp = client.get(
                f"{SEMANTIC_SCHOLAR_API_URL}/author/{author_id}",
                params={
                    "fields": "name,hIndex,citationCount,affiliations,papers.title,papers.year",
                },
            )
            if resp.status_code != 200:
                print(
                    f"Semantic Scholar author detail returned {resp.status_code} for {pi_name}",
                    file=sys.stderr,
                )
                return None
            author_data = resp.json()

    except Exception as e:
        print(f"Semantic Scholar API error for {pi_name}: {e}", file=sys.stderr)
        return None

    papers = author_data.get("papers", [])
    sample_titles = [
        p["title"] for p in papers[:5] if p.get("title")
    ]
    affiliations = author_data.get("affiliations", []) or []

    return PIPublicationRecord(
        total_papers=len(papers),
        h_index=author_data.get("hIndex"),
        citation_count=author_data.get("citationCount", 0),
        sample_titles=sample_titles,
        affiliations=affiliations,
    )


def _is_sbir_award_type(description: str, cfda: str) -> bool:
    """Heuristic to identify SBIR/STTR awards in USAspending results.

    Uses CFDA/ALN numbers and description keywords. Mirrors the logic in
    sbir_etl.models.sbir_identification but without the heavy import.
    """
    # Known SBIR/STTR Assistance Listing Numbers (subset of the most common)
    sbir_alns = {
        "10.212", "12.910", "12.911", "81.049", "43.002", "43.003",
        "47.041", "47.084", "66.511", "66.512", "97.077", "20.701",
        "84.133",
        # HHS/NIH common ones
        "93.855", "93.856", "93.859", "93.837", "93.847", "93.853",
        "93.865", "93.866", "93.867", "93.879", "93.242", "93.273",
        "93.279", "93.395", "93.393", "93.394", "93.396", "93.399",
    }
    if cfda and cfda.strip() in sbir_alns:
        return True
    # Keyword heuristic on description
    desc_upper = description.upper()
    if "SBIR" in desc_upper or "STTR" in desc_upper:
        return True
    if "SMALL BUSINESS INNOVATION RESEARCH" in desc_upper:
        return True
    if "SMALL BUSINESS TECHNOLOGY TRANSFER" in desc_upper:
        return True
    return False


def lookup_company_federal_awards(
    company_name: str,
    uei: str | None = None,
) -> PIFederalAwardRecord | None:
    """Query USAspending for all federal awards to the PI's company.

    Separates SBIR/STTR awards from non-SBIR federal work. Non-SBIR
    contracts and grants to a company with SBIR history are the strongest
    signal of successful commercialization / Phase III transition.
    """
    if not company_name:
        return None

    # Build filter — prefer UEI if available
    filters: dict = {}
    if uei:
        filters["recipient_id"] = uei
    else:
        filters["recipient_search_text"] = [company_name]

    payload = {
        "filters": filters,
        "fields": [
            "Award ID",
            "Recipient Name",
            "Award Amount",
            "Awarding Agency",
            "Award Type",
            "Start Date",
            "Description",
            "CFDA Number",
        ],
        "page": 1,
        "limit": 100,
        "sort": "Award Amount",
        "order": "desc",
    }

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                f"{USASPENDING_API_URL}/search/spending_by_award/",
                json=payload,
            )
            if resp.status_code != 200:
                print(
                    f"USAspending API returned {resp.status_code} for {company_name}",
                    file=sys.stderr,
                )
                return None
            data = resp.json()
    except Exception as e:
        print(f"USAspending API error for {company_name}: {e}", file=sys.stderr)
        return None

    results = data.get("results", [])
    if not results:
        return None

    agencies: set[str] = set()
    award_types: set[str] = set()
    total_funding = 0.0
    dates: list[str] = []

    sbir_count = 0
    sbir_funding = 0.0
    non_sbir_count = 0
    non_sbir_funding = 0.0
    non_sbir_agencies: set[str] = set()
    non_sbir_descriptions: list[str] = []

    for r in results:
        ag = r.get("Awarding Agency", "")
        if ag:
            agencies.add(ag)
        at = r.get("Award Type", "")
        if at:
            award_types.add(at)
        try:
            amount = float(r.get("Award Amount", 0) or 0)
        except (ValueError, TypeError):
            amount = 0.0
        total_funding += amount
        d = r.get("Start Date", "")
        if d:
            dates.append(d)

        desc = str(r.get("Description", "") or "")
        cfda = str(r.get("CFDA Number", "") or "")

        if _is_sbir_award_type(desc, cfda):
            sbir_count += 1
            sbir_funding += amount
        else:
            non_sbir_count += 1
            non_sbir_funding += amount
            if ag:
                non_sbir_agencies.add(ag)
            # Keep sample descriptions of non-SBIR awards (the follow-on signals)
            if desc and len(non_sbir_descriptions) < 5:
                # Truncate long descriptions
                if len(desc) > 200:
                    desc = desc[:200] + "..."
                non_sbir_descriptions.append(
                    f"{desc} ({ag}, {at}, ${amount:,.0f})"
                )

    return PIFederalAwardRecord(
        total_awards=len(results),
        total_funding=total_funding,
        agencies=sorted(agencies),
        award_types=sorted(award_types),
        date_range=(min(dates) if dates else None, max(dates) if dates else None),
        sbir_award_count=sbir_count,
        sbir_funding=sbir_funding,
        non_sbir_award_count=non_sbir_count,
        non_sbir_funding=non_sbir_funding,
        non_sbir_agencies=sorted(non_sbir_agencies),
        non_sbir_sample_descriptions=non_sbir_descriptions,
    )


def lookup_pi_external_data(
    awards: list[dict],
) -> dict[str, dict]:
    """Look up external data (patents, publications, ORCID, federal awards) for each PI.

    Returns a dict keyed by upper-cased PI name, with sub-keys:
    - "patents": PIPatentRecord | None
    - "publications": PIPublicationRecord | None
    - "orcid": ORCIDRecord | None
    - "federal_awards": PIFederalAwardRecord | None
    """
    # Collect unique PIs with their company context
    pis: dict[str, dict] = {}
    for a in awards:
        pi = str(a.get("PI Name", "")).strip()
        if not pi:
            continue
        key = pi.upper()
        if key not in pis:
            pis[key] = {
                "name": pi,
                "company": str(a.get("Company", "")).strip(),
                "uei": str(a.get("Company UEI", a.get("UEI", ""))).strip(),
            }

    results: dict[str, dict] = {}
    total = len(pis)

    for idx, (key, info) in enumerate(pis.items(), 1):
        name = info["name"]
        company = info["company"]
        uei = info["uei"] or None

        print(
            f"Looking up external data for PI {idx}/{total}: {name}...",
            file=sys.stderr,
        )

        patents = lookup_pi_patents(name, company)
        publications = lookup_pi_publications(name)
        orcid = lookup_pi_orcid(name)
        federal_awards = lookup_company_federal_awards(company, uei)

        results[key] = {
            "patents": patents,
            "publications": publications,
            "orcid": orcid,
            "federal_awards": federal_awards,
        }

    return results


# ---------------------------------------------------------------------------
# SAM.gov entity lookup (company diligence)
# ---------------------------------------------------------------------------


@dataclass
class SAMEntityRecord:
    """Key SAM.gov entity registration data for diligence."""

    uei: str
    legal_business_name: str
    dba_name: str | None
    registration_status: str | None
    expiration_date: str | None
    business_type: str | None
    entity_structure: str | None
    naics_codes: list[str]
    cage_code: str | None
    exclusion_status: str | None
    state: str | None
    congressional_district: str | None


def lookup_sam_entity(
    company_name: str,
    uei: str | None = None,
    cage: str | None = None,
) -> SAMEntityRecord | None:
    """Query SAM.gov Entity Information API for company registration data.

    Tries UEI first (exact match), then CAGE, then name search.
    Requires SAM_GOV_API_KEY environment variable.
    """
    api_key = os.environ.get("SAM_GOV_API_KEY", "")
    if not api_key:
        return None

    headers = {"X-Api-Key": api_key, "Accept": "application/json"}

    def _try_query(params: dict) -> dict | None:
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.get(SAM_GOV_API_URL, headers=headers, params=params)
                if resp.status_code != 200:
                    return None
                data = resp.json()
                results = data.get("entityData", data.get("results", []))
                if isinstance(results, list) and results:
                    return results[0]
                if isinstance(results, dict):
                    return results
        except Exception as e:
            print(f"SAM.gov API error: {e}", file=sys.stderr)
        return None

    entity = None

    # Try UEI first (most reliable)
    if uei:
        entity = _try_query({"ueiSAM": uei})

    # Try CAGE code
    if not entity and cage:
        entity = _try_query({"cageCode": cage})

    # Fall back to name search
    if not entity and company_name:
        entity = _try_query({"legalBusinessName": company_name, "registrationStatus": "A"})

    if not entity:
        return None

    # Extract fields — SAM.gov API nests data under various keys
    core = entity.get("entityRegistration", entity)
    address = entity.get("coreData", {}).get("physicalAddress", {})
    business_types = entity.get("coreData", {}).get("businessTypes", {})

    # Extract NAICS codes
    naics_list = entity.get("coreData", {}).get("naicsCodeList", [])
    if isinstance(naics_list, list):
        naics_codes = [
            str(n.get("naicsCode", "")) for n in naics_list if n.get("naicsCode")
        ]
    else:
        naics_codes = []

    return SAMEntityRecord(
        uei=core.get("ueiSAM", ""),
        legal_business_name=core.get("legalBusinessName", ""),
        dba_name=core.get("dbaName"),
        registration_status=core.get("registrationStatus"),
        expiration_date=core.get("registrationExpirationDate"),
        business_type=(
            business_types.get("businessTypeList", [{}])[0].get("businessType")
            if isinstance(business_types.get("businessTypeList"), list)
            and business_types.get("businessTypeList")
            else None
        ),
        entity_structure=core.get("entityStructureDesc"),
        naics_codes=naics_codes,
        cage_code=core.get("cageCode"),
        exclusion_status=core.get("exclusionStatusFlag"),
        state=address.get("stateOrProvinceCode"),
        congressional_district=address.get("congressionalDistrict"),
    )


def lookup_sam_entities(
    awards: list[dict],
) -> dict[str, SAMEntityRecord]:
    """Look up SAM.gov registration data for each unique company.

    Returns a dict keyed by upper-cased company name.
    """
    api_key = os.environ.get("SAM_GOV_API_KEY", "")
    if not api_key:
        print(
            "SAM_GOV_API_KEY not set — skipping SAM.gov entity lookups.",
            file=sys.stderr,
        )
        return {}

    companies: dict[str, dict] = {}
    for a in awards:
        name = str(a.get("Company", "")).strip()
        if not name:
            continue
        key = name.upper()
        if key not in companies:
            companies[key] = {
                "name": name,
                "uei": str(a.get("Company UEI", a.get("UEI", ""))).strip() or None,
                "cage": str(a.get("Company CAGE", a.get("CAGE", ""))).strip() or None,
            }

    results: dict[str, SAMEntityRecord] = {}
    total = len(companies)
    print(f"Looking up {total} companies on SAM.gov...", file=sys.stderr)

    for idx, (key, info) in enumerate(companies.items(), 1):
        if idx % 10 == 0 or idx == total:
            print(f"SAM.gov lookup {idx}/{total}...", file=sys.stderr)
        record = lookup_sam_entity(info["name"], info["uei"], info["cage"])
        if record:
            results[key] = record

    print(f"Found {len(results)}/{total} companies on SAM.gov", file=sys.stderr)
    return results


# ---------------------------------------------------------------------------
# ORCID API lookup (PI diligence)
# ---------------------------------------------------------------------------


@dataclass
class ORCIDRecord:
    """Key data from an ORCID researcher profile."""

    orcid_id: str
    given_name: str | None
    family_name: str | None
    affiliations: list[str]
    works_count: int
    sample_work_titles: list[str]
    funding_count: int
    keywords: list[str]


def lookup_pi_orcid(pi_name: str) -> ORCIDRecord | None:
    """Search the ORCID public API for a PI's researcher profile.

    Uses the expanded search endpoint to find by name, then fetches
    the full profile for works, affiliations, and funding.
    """
    first, last = _split_pi_name(pi_name)
    if not last:
        return None

    headers = {"Accept": "application/json"}

    try:
        # Step 1: Search for the researcher by name
        query = f"family-name:{last}"
        if first:
            query += f"+AND+given-names:{first}"

        with httpx.Client(timeout=30) as client:
            resp = client.get(
                f"{ORCID_API_URL}/expanded-search/",
                headers=headers,
                params={"q": query, "rows": 5},
            )
            if resp.status_code != 200:
                return None
            search_data = resp.json()

        results = search_data.get("expanded-result", [])
        if not results:
            return None

        # Pick the best match (first result)
        best = results[0]
        orcid_id = best.get("orcid-id", "")
        if not orcid_id:
            return None

        # Step 2: Fetch full profile
        with httpx.Client(timeout=30) as client:
            resp = client.get(
                f"{ORCID_API_URL}/{orcid_id}/record",
                headers=headers,
            )
            if resp.status_code != 200:
                return None
            profile = resp.json()

    except Exception as e:
        print(f"ORCID API error for {pi_name}: {e}", file=sys.stderr)
        return None

    # Extract affiliations
    affiliations: list[str] = []
    affiliation_groups = (
        profile.get("activities-summary", {})
        .get("employments", {})
        .get("affiliation-group", [])
    )
    for group in affiliation_groups[:10]:
        summaries = group.get("summaries", [])
        for s in summaries:
            emp = s.get("employment-summary", {})
            org = emp.get("organization", {})
            org_name = org.get("name", "")
            if org_name and org_name not in affiliations:
                affiliations.append(org_name)

    # Extract works (publications)
    works_group = (
        profile.get("activities-summary", {})
        .get("works", {})
        .get("group", [])
    )
    works_count = len(works_group)
    sample_titles: list[str] = []
    for wg in works_group[:5]:
        summaries = wg.get("work-summary", [])
        if summaries:
            title_obj = summaries[0].get("title", {})
            title_val = title_obj.get("title", {}).get("value", "")
            if title_val:
                sample_titles.append(title_val)

    # Extract funding
    funding_group = (
        profile.get("activities-summary", {})
        .get("fundings", {})
        .get("group", [])
    )
    funding_count = len(funding_group)

    # Extract keywords
    keywords_obj = profile.get("person", {}).get("keywords", {})
    keyword_list = keywords_obj.get("keyword", [])
    keywords = [
        kw.get("content", "") for kw in keyword_list[:10] if kw.get("content")
    ]

    return ORCIDRecord(
        orcid_id=orcid_id,
        given_name=best.get("given-names"),
        family_name=best.get("family-names"),
        affiliations=affiliations,
        works_count=works_count,
        sample_work_titles=sample_titles,
        funding_count=funding_count,
        keywords=keywords,
    )


# ---------------------------------------------------------------------------
# Solicitation topic lookup
# ---------------------------------------------------------------------------


@dataclass
class SolicitationTopic:
    """Solicitation topic details from SBIR.gov API."""

    topic_code: str
    solicitation_number: str
    title: str
    description: str | None
    agency: str | None
    program: str | None


def fetch_solicitation_topics(awards: list[dict]) -> dict[str, SolicitationTopic]:
    """Fetch solicitation topic titles and descriptions from SBIR.gov API.

    Queries the SBIR.gov solicitations endpoint for each unique topic code
    found in this week's awards. Returns a dict keyed by topic code.
    """
    # Collect unique topic codes
    topic_codes: dict[str, str] = {}  # topic_code -> solicitation_number
    for a in awards:
        tc = str(a.get("Topic Code", "")).strip()
        sol = str(a.get("Solicitation Number", "")).strip()
        if tc and tc not in topic_codes:
            topic_codes[tc] = sol

    if not topic_codes:
        return {}

    results: dict[str, SolicitationTopic] = {}
    total = len(topic_codes)
    print(f"Fetching {total} solicitation topics from SBIR.gov...", file=sys.stderr)

    # Query by solicitation year to reduce result sets.
    # Group topic codes by their solicitation number prefix to batch queries.
    sol_years: dict[int, list[str]] = {}
    for tc, sol in topic_codes.items():
        # Extract year from solicitation number (e.g. "SBIR-2023.1" -> 2023)
        year = None
        for part in sol.replace("-", " ").replace(".", " ").split():
            if part.isdigit() and len(part) == 4:
                year = int(part)
                break
        if year:
            sol_years.setdefault(year, []).append(tc)
        else:
            sol_years.setdefault(0, []).append(tc)

    for year, codes in sol_years.items():
        params: dict[str, str | int] = {"rows": 500, "start": 0}
        if year > 0:
            params["year"] = year

        try:
            with httpx.Client(timeout=30) as client:
                resp = client.get(
                    f"{SBIR_GOV_API_URL}/solicitations", params=params
                )
                if resp.status_code != 200:
                    print(
                        f"SBIR.gov API returned {resp.status_code} for year={year}",
                        file=sys.stderr,
                    )
                    continue
                data = resp.json()
        except Exception as e:
            print(f"SBIR.gov API error for year={year}: {e}", file=sys.stderr)
            continue

        topics = data if isinstance(data, list) else (
            data.get("results") or data.get("data") or []
        )

        codes_set = set(codes)
        for topic in topics:
            tc = topic.get("topicCode") or topic.get("topic_code") or ""
            if tc in codes_set and tc not in results:
                desc = topic.get("topicDescription") or topic.get("description")
                # Truncate very long descriptions for LLM context
                if desc and len(desc) > 3000:
                    desc = desc[:3000] + "..."
                results[tc] = SolicitationTopic(
                    topic_code=tc,
                    solicitation_number=(
                        topic.get("solicitationNumber")
                        or topic.get("solicitation_number")
                        or topic_codes.get(tc, "")
                    ),
                    title=topic.get("topicTitle") or topic.get("title") or "",
                    description=desc,
                    agency=topic.get("agency"),
                    program=topic.get("program"),
                )

    found = len(results)
    print(
        f"Fetched {found}/{total} solicitation topics from SBIR.gov",
        file=sys.stderr,
    )
    return results


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _escape_md_cell(value: str) -> str:
    """Escape a string for safe use inside a markdown table cell."""
    return value.replace("|", "\\|").replace("\n", " ").replace("\r", "")


def format_amount(amount_str: str) -> str:
    """Format dollar amount for display."""
    try:
        amount = float(str(amount_str).replace(",", "").replace("$", ""))
        if amount >= 1_000_000:
            return f"${amount / 1_000_000:.2f}M"
        if amount >= 1_000:
            return f"${amount / 1_000:.0f}K"
        return f"${amount:,.0f}"
    except (ValueError, AttributeError, TypeError):
        return str(amount_str) if amount_str else "N/A"


def _format_date(value) -> str:
    """Format a date value for display using the project's date parser."""
    parsed = _parse_date(value)
    if parsed:
        return parsed.isoformat()
    return str(value) if value else ""


def build_sbir_award_url(award: dict) -> str:
    """Build a link to the SBIR.gov award search page for this award."""
    contract = str(award.get("Contract", "")).strip()
    if contract:
        return f"{SBIR_AWARD_SEARCH_URL}/{quote(contract)}"
    company = str(award.get("Company", "")).strip()
    if company:
        return f"{SBIR_AWARD_SEARCH_URL}/{quote(company)}"
    return SBIR_AWARD_SEARCH_URL


def build_solicitation_url(award: dict) -> str | None:
    """Build a link to the SBIR.gov solicitation/topic page."""
    solicitation = str(award.get("Solicitation Number", "")).strip()
    topic_code = str(award.get("Topic Code", "")).strip()
    if solicitation:
        return f"{SBIR_SOLICITATION_URL}?keyword={quote(solicitation)}"
    if topic_code:
        return f"{SBIR_SOLICITATION_URL}?keyword={quote(topic_code)}"
    return None


def build_usaspending_url(award: dict) -> str | None:
    """Build a link to USAspending.gov search for this award's contract."""
    contract = str(award.get("Contract", "")).strip()
    if not contract:
        return None
    search_term = quote(contract)
    return f'{USASPENDING_SEARCH_URL}?form_fields={{"search_term":"{search_term}"}}'


# ---------------------------------------------------------------------------
# OpenAI integration
# ---------------------------------------------------------------------------


def _openai_request_with_retry(
    method: str,
    url: str,
    headers: dict,
    payload: dict,
    timeout: int = 120,
) -> httpx.Response | None:
    """Make an OpenAI API request with retry/backoff for 429 and 5xx errors."""
    import time

    for attempt in range(OPENAI_MAX_RETRIES + 1):
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.request(method, url, headers=headers, json=payload)
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt < OPENAI_MAX_RETRIES:
                    wait = OPENAI_RETRY_BACKOFF_BASE ** (attempt + 1)
                    print(
                        f"OpenAI API returned {resp.status_code}, retrying in {wait}s "
                        f"(attempt {attempt + 1}/{OPENAI_MAX_RETRIES})...",
                        file=sys.stderr,
                    )
                    time.sleep(wait)
                    continue
            resp.raise_for_status()
            return resp
        except httpx.HTTPStatusError:
            if attempt < OPENAI_MAX_RETRIES:
                continue
            print(f"OpenAI API error after {OPENAI_MAX_RETRIES} retries: {resp.status_code}", file=sys.stderr)
            return None
        except Exception as e:
            print(f"OpenAI API request error: {e}", file=sys.stderr)
            return None
    return None


def _openai_chat(
    api_key: str,
    system: str,
    user: str,
    model: str = OPENAI_MODEL,
    temperature: float = 0.3,
) -> str | None:
    """Call the OpenAI chat completions API. Returns the assistant message text."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    resp = _openai_request_with_retry("POST", OPENAI_CHAT_URL, headers, payload)
    if resp is None:
        return None
    try:
        return resp.json()["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError) as e:
        print(f"OpenAI Chat API unexpected response: {e}", file=sys.stderr)
        return None


def _openai_web_search(api_key: str, query: str) -> CompanyResearch | None:
    """Use the OpenAI Responses API with web_search_preview to research a company."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": OPENAI_MODEL,
        "tools": [{"type": "web_search_preview"}],
        "instructions": (
            "You are a research assistant gathering public information about "
            "companies that receive SBIR/STTR federal awards. Provide a concise "
            "2-3 sentence summary covering: what the company does, its size/stage, "
            "notable products or contracts, and any previous SBIR/STTR history. "
            "Cite your sources."
        ),
        "input": query,
    }
    resp = _openai_request_with_retry("POST", OPENAI_RESPONSES_URL, headers, payload, timeout=60)
    if resp is None:
        return None
    data = resp.json()

    summary_text = ""
    source_urls: list[str] = []

    for output_item in data.get("output", []):
        if output_item.get("type") == "message":
            for content_block in output_item.get("content", []):
                if content_block.get("type") == "output_text":
                    summary_text = content_block.get("text", "")
                    for annotation in content_block.get("annotations", []):
                        url = annotation.get("url", "")
                        if url and url not in source_urls:
                            source_urls.append(url)

    if not summary_text:
        return None

    return CompanyResearch(summary=summary_text, source_urls=source_urls)


def research_companies(
    api_key: str, awards: list[dict]
) -> dict[str, CompanyResearch]:
    """Research each unique awardee company via web search."""
    companies: dict[str, dict] = {}
    for a in awards:
        name = str(a.get("Company", "")).strip()
        if not name:
            continue
        key = name.upper()
        if key not in companies:
            companies[key] = {
                "name": name,
                "state": str(a.get("State", "")),
                "website": str(a.get("Company Website", "")),
            }

    results: dict[str, CompanyResearch] = {}
    # Cap the number of companies to research
    company_items = list(companies.items())
    if len(company_items) > MAX_COMPANIES_TO_RESEARCH:
        print(
            f"Capping company research at {MAX_COMPANIES_TO_RESEARCH} of {len(company_items)} companies",
            file=sys.stderr,
        )
        company_items = company_items[:MAX_COMPANIES_TO_RESEARCH]
    total = len(company_items)

    for idx, (key, info) in enumerate(company_items, 1):
        name = info["name"]
        state = info["state"]
        website = info["website"]

        query = (
            f"Find public information about {name}"
            + (f" based in {state}" if state else "")
            + ". They are an SBIR/STTR federal award recipient."
            + (f" Their website is {website}." if website else "")
            + " What does this company do? How large are they? "
            + "What is their technology focus? Any notable contracts or previous SBIR awards?"
        )

        print(f"Researching company {idx}/{total}: {name}...", file=sys.stderr)
        research = _openai_web_search(api_key, query)
        if research:
            results[key] = research

    return results


def _award_digest(
    award: dict,
    company_research: CompanyResearch | None = None,
    solicitation_topics: dict[str, SolicitationTopic] | None = None,
) -> str:
    """Build a compact text digest of an award for LLM context."""
    parts = [
        f"Title: {award.get('Award Title', 'N/A')}",
        f"Company: {award.get('Company', 'N/A')}",
        f"Agency: {award.get('Agency', 'N/A')}",
        f"Program: {award.get('Program', 'N/A')} {award.get('Phase', '')}",
        f"Amount: {award.get('Award Amount', 'N/A')}",
        f"State: {award.get('State', 'N/A')}",
        f"Date: {award.get('Proposal Award Date', 'N/A')}",
    ]
    abstract = str(award.get("Abstract", "")).strip()
    if abstract:
        if len(abstract) > 1500:
            abstract = abstract[:1500] + "..."
        parts.append(f"Abstract: {abstract}")
    topic_code = str(award.get("Topic Code", "")).strip()
    if topic_code:
        parts.append(f"Topic Code: {topic_code}")
    solicitation = str(award.get("Solicitation Number", "")).strip()
    if solicitation:
        parts.append(f"Solicitation: {solicitation}")
    solicitation_year = str(award.get("Solicitation Year", "")).strip()
    if solicitation_year:
        parts.append(f"Solicitation Year: {solicitation_year}")

    # Solicitation topic context (title + description from SBIR.gov API)
    if solicitation_topics and topic_code:
        topic = solicitation_topics.get(topic_code)
        if topic:
            if topic.title:
                parts.append(f"Solicitation Topic Title: {topic.title}")
            if topic.description:
                parts.append(
                    f"Solicitation Topic Description (government research need): "
                    f"{topic.description}"
                )

    contract = str(award.get("Contract", "")).strip()
    if contract:
        parts.append(f"Contract: {contract}")
        parts.append(
            f"USAspending Record: https://www.usaspending.gov/search"
            f'?form_fields={{"search_term":"{contract}"}}'
        )
    solicitation_url = build_solicitation_url(award)
    if solicitation_url:
        parts.append(f"Solicitation Reference: {solicitation_url}")
    if company_research:
        parts.append(f"Company Background (from web research): {company_research.summary}")
        if company_research.source_urls:
            parts.append(
                "Company Sources: " + ", ".join(company_research.source_urls[:5])
            )
    return "\n".join(parts)


def generate_weekly_synopsis(
    api_key: str,
    awards: list[dict],
    days: int,
    company_research: dict[str, CompanyResearch] | None = None,
    solicitation_topics: dict[str, SolicitationTopic] | None = None,
) -> str | None:
    """Generate a two-paragraph synopsis of all weekly award activity."""
    if not awards:
        return None

    total_amount = 0
    agencies: dict[str, int] = {}
    for a in awards:
        try:
            total_amount += float(
                str(a.get("Award Amount", "0")).replace(",", "").replace("$", "")
            )
        except (ValueError, AttributeError):
            pass
        ag = str(a.get("Agency", "Unknown"))
        agencies[ag] = agencies.get(ag, 0) + 1

    digests = []
    for i, a in enumerate(awards[:50]):
        cr = None
        if company_research:
            cr = company_research.get(str(a.get("Company", "")).strip().upper())
        digests.append(f"[{i+1}] {_award_digest(a, cr, solicitation_topics)}")
    digest_block = "\n\n".join(digests)
    if len(awards) > 50:
        digest_block += f"\n\n... and {len(awards) - 50} additional awards."

    system = (
        "You are an analyst writing a concise executive briefing about weekly "
        "SBIR/STTR federal small business innovation award activity. "
        "Write in a professional, informative tone. Do not use markdown headers. "
        "Do not use bullet points. Write exactly two paragraphs. "
        "Incorporate relevant context about the awardee companies when provided."
    )
    user = (
        f"Write a two-paragraph synopsis of this week's SBIR/STTR award activity.\n\n"
        f"Period: past {days} days\n"
        f"Total awards: {len(awards)}\n"
        f"Total funding: ${total_amount:,.0f}\n"
        f"Agencies: {json.dumps(agencies)}\n\n"
        f"Award details:\n{digest_block}"
    )

    print("Generating weekly synopsis via OpenAI...", file=sys.stderr)
    return _openai_chat(api_key, system, user)


def generate_award_descriptions(
    api_key: str,
    awards: list[dict],
    company_research: dict[str, CompanyResearch] | None = None,
    solicitation_topics: dict[str, SolicitationTopic] | None = None,
) -> dict[int, str]:
    """Generate a brief description for each award using batched API calls."""
    descriptions: dict[int, str] = {}
    if not awards:
        return descriptions

    # Cap the number of awards to describe
    awards_to_describe = awards
    if len(awards) > MAX_AWARDS_TO_DESCRIBE:
        print(
            f"Capping award descriptions at {MAX_AWARDS_TO_DESCRIBE} of {len(awards)} awards",
            file=sys.stderr,
        )
        awards_to_describe = awards[:MAX_AWARDS_TO_DESCRIBE]

    system = (
        "You summarize SBIR/STTR awards in plain language. "
        "For each award, write 3-4 sentences. The first 1-2 sentences should "
        "explain what the project does and why it matters — be specific about "
        "the technology and its intended application.\n\n"
        "When a solicitation topic description is provided, the final 1-2 "
        "sentences MUST assess the alignment between the award and the "
        "originating solicitation:\n"
        "- Does the award's abstract directly address the technical "
        "objectives laid out in the solicitation topic description?\n"
        "- Is the award tightly scoped to the solicitation's stated research "
        "need, or does it appear to address the topic tangentially or "
        "partially?\n"
        "- Are there aspects of the solicitation's requirements that the "
        "award abstract does not appear to cover?\n"
        "State the alignment clearly (e.g. 'This award directly addresses "
        "the solicitation's need for...' or 'While the solicitation sought "
        "X, this award focuses primarily on Y, which addresses only a "
        "portion of the stated need.'). Do not hedge — make a specific "
        "assessment based on the available text.\n\n"
        "If no solicitation topic description is available, skip the "
        "alignment assessment and focus on the technology, its application, "
        "and company context.\n\n"
        "Reference relevant company context (e.g. their expertise, previous "
        "work, or market position) when it adds value. Avoid generic filler.\n\n"
        "Respond with a JSON object mapping the award number (as a string key) "
        'to its description string. Example: {"1": "Description.", "2": "Description."}'
    )

    for batch_start in range(0, len(awards_to_describe), DESCRIPTION_BATCH_SIZE):
        batch = awards_to_describe[batch_start : batch_start + DESCRIPTION_BATCH_SIZE]
        digests = []
        for i, a in enumerate(batch):
            idx = batch_start + i + 1
            cr = None
            if company_research:
                cr = company_research.get(str(a.get("Company", "")).strip().upper())
            digests.append(f"[{idx}] {_award_digest(a, cr, solicitation_topics)}")

        user = (
            "Generate a description for each award below. Each description "
            "should convey the technology, its application, and — when "
            "solicitation topic data is provided — a specific assessment of "
            "how well the award aligns with the solicitation's stated "
            "research need. Respond ONLY with a JSON object.\n\n"
            + "\n\n".join(digests)
        )

        batch_label = f"{batch_start + 1}-{batch_start + len(batch)}"
        print(
            f"Generating descriptions for awards {batch_label} of {len(awards_to_describe)}...",
            file=sys.stderr,
        )
        raw = _openai_chat(api_key, system, user)
        if not raw:
            continue

        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()

        try:
            batch_descriptions = json.loads(text)
            for key, desc in batch_descriptions.items():
                descriptions[int(key) - 1] = desc
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Failed to parse description batch {batch_label}: {e}", file=sys.stderr)

    return descriptions


# ---------------------------------------------------------------------------
# Company & PI diligence
# ---------------------------------------------------------------------------

# Caps on diligence API calls (override via env vars)
MAX_COMPANIES_TO_DILIGENCE = int(os.environ.get("MAX_COMPANIES_TO_DILIGENCE", "50"))
MAX_PIS_TO_DILIGENCE = int(os.environ.get("MAX_PIS_TO_DILIGENCE", "50"))


def _company_history_digest(name: str, history: dict | None) -> str:
    """Format a company's historical SBIR record for LLM context."""
    if not history:
        return "No prior SBIR/STTR award history found in the dataset."
    parts = [
        f"Total historical SBIR/STTR awards: {history['total_awards']}",
        f"Phases achieved: {', '.join(history['phases']) or 'N/A'}",
        f"Agencies: {', '.join(history['agencies']) or 'N/A'}",
        f"Programs: {', '.join(history['programs']) or 'N/A'}",
        f"Total historical funding: ${history['total_funding']:,.0f}",
        f"Award date range: {history.get('earliest_date', 'N/A')} to {history.get('latest_date', 'N/A')}",
    ]
    if history.get("sample_titles"):
        parts.append("Sample award titles: " + "; ".join(history["sample_titles"]))
    return "\n".join(parts)


def _pi_history_digest(name: str, history: dict | None) -> str:
    """Format a PI's historical SBIR record for LLM context."""
    if not history:
        return "No prior SBIR/STTR award history found for this PI."
    parts = [
        f"Total historical SBIR/STTR awards as PI: {history['total_awards']}",
        f"Companies: {', '.join(history['companies']) or 'N/A'}",
        f"Phases: {', '.join(history['phases']) or 'N/A'}",
        f"Agencies: {', '.join(history['agencies']) or 'N/A'}",
        f"Total funding as PI: ${history['total_funding']:,.0f}",
        f"Date range: {history.get('earliest_date', 'N/A')} to {history.get('latest_date', 'N/A')}",
    ]
    if history.get("sample_titles"):
        parts.append("Sample award titles: " + "; ".join(history["sample_titles"]))
    return "\n".join(parts)


def _pi_external_digest(external: dict | None) -> str:
    """Format a PI's external data (patents, publications, ORCID, federal awards) for LLM context."""
    if not external:
        return "No external data available for this PI."

    parts = []

    # ORCID profile
    orcid: ORCIDRecord | None = external.get("orcid")
    if orcid:
        parts.append(f"ORCID ID: {orcid.orcid_id}")
        if orcid.affiliations:
            parts.append(f"ORCID affiliations: {', '.join(orcid.affiliations)}")
        parts.append(f"ORCID works count: {orcid.works_count}")
        parts.append(f"ORCID funding entries: {orcid.funding_count}")
        if orcid.keywords:
            parts.append(f"ORCID research keywords: {', '.join(orcid.keywords)}")
        if orcid.sample_work_titles:
            parts.append(
                "ORCID sample works: " + "; ".join(orcid.sample_work_titles)
            )
    else:
        parts.append("ORCID: No ORCID profile found for this researcher.")

    # Patents
    patents: PIPatentRecord | None = external.get("patents")
    if patents:
        parts.append(f"USPTO Patents as inventor: {patents.total_patents}")
        if patents.assignees:
            parts.append(f"Patent assignees: {', '.join(patents.assignees)}")
        if patents.date_range[0]:
            parts.append(f"Patent date range: {patents.date_range[0]} to {patents.date_range[1]}")
        if patents.sample_titles:
            parts.append("Sample patent titles: " + "; ".join(patents.sample_titles))
    else:
        parts.append("USPTO Patents: No patents found for this inventor name.")

    # Publications
    pubs: PIPublicationRecord | None = external.get("publications")
    if pubs:
        parts.append(f"Academic publications: {pubs.total_papers}")
        if pubs.h_index is not None:
            parts.append(f"h-index: {pubs.h_index}")
        parts.append(f"Total citations: {pubs.citation_count}")
        if pubs.affiliations:
            parts.append(f"Affiliations: {', '.join(pubs.affiliations)}")
        if pubs.sample_titles:
            parts.append("Sample paper titles: " + "; ".join(pubs.sample_titles))
    else:
        parts.append("Academic publications: No Semantic Scholar profile found.")

    # Federal awards (company-level) with SBIR vs non-SBIR breakdown
    fed: PIFederalAwardRecord | None = external.get("federal_awards")
    if fed:
        parts.append(f"Company federal awards (USAspending): {fed.total_awards} total")
        parts.append(f"Company total federal funding: ${fed.total_funding:,.0f}")
        parts.append(
            f"SBIR/STTR awards: {fed.sbir_award_count} "
            f"(${fed.sbir_funding:,.0f})"
        )
        parts.append(
            f"Non-SBIR federal awards (potential follow-on/Phase III): "
            f"{fed.non_sbir_award_count} (${fed.non_sbir_funding:,.0f})"
        )
        if fed.non_sbir_agencies:
            parts.append(
                f"Non-SBIR awarding agencies: {', '.join(fed.non_sbir_agencies)}"
            )
        if fed.non_sbir_sample_descriptions:
            parts.append(
                "Sample non-SBIR award descriptions (follow-on signals):"
            )
            for desc in fed.non_sbir_sample_descriptions:
                parts.append(f"  - {desc}")
        if fed.agencies:
            parts.append(f"All federal agencies: {', '.join(fed.agencies)}")
        if fed.award_types:
            parts.append(f"Award types: {', '.join(fed.award_types)}")
        if fed.date_range[0]:
            parts.append(f"Federal award date range: {fed.date_range[0]} to {fed.date_range[1]}")
    else:
        parts.append("Company federal awards: No USAspending records found.")

    return "\n".join(parts)


def generate_company_diligence(
    api_key: str,
    awards: list[dict],
    company_research: dict[str, CompanyResearch] | None = None,
    company_history: dict[str, dict] | None = None,
    sam_entities: dict[str, SAMEntityRecord] | None = None,
    company_federal_awards: dict[str, PIFederalAwardRecord] | None = None,
) -> dict[str, str]:
    """Generate a diligence paragraph for each unique awardee company.

    Combines web research, historical SBIR data, SAM.gov registration data,
    USAspending federal award data (with SBIR vs non-SBIR breakdown), and
    the current award context to produce a focused due-diligence assessment
    per company.

    Returns a dict keyed by upper-cased company name.
    """
    # Collect unique companies
    companies: dict[str, list[dict]] = {}
    for a in awards:
        name = str(a.get("Company", "")).strip()
        if not name:
            continue
        key = name.upper()
        companies.setdefault(key, []).append(a)

    company_items = list(companies.items())
    if len(company_items) > MAX_COMPANIES_TO_DILIGENCE:
        print(
            f"Capping company diligence at {MAX_COMPANIES_TO_DILIGENCE} "
            f"of {len(company_items)} companies",
            file=sys.stderr,
        )
        company_items = company_items[:MAX_COMPANIES_TO_DILIGENCE]

    system = (
        "You are a due-diligence analyst evaluating companies that receive "
        "SBIR/STTR federal innovation awards. Write exactly one paragraph "
        "(4-6 sentences) of diligence analysis for the company. Cover:\n"
        "1. Company background and technology focus\n"
        "2. SBIR track record — award volume, phase progression (Phase I→II→III "
        "indicates commercialization progress), agency diversity\n"
        "3. SAM.gov registration status — active registration, entity structure, "
        "business type, NAICS codes (industry classification), and any "
        "exclusion flags are important compliance signals. An expired or "
        "missing SAM registration is a red flag for federal contracting.\n"
        "4. Commercialization and follow-on signals — the strongest evidence "
        "of SBIR success is non-SBIR federal awards (contracts, grants) to "
        "the same company, which represent Phase III transitions where SBIR "
        "research led to production work. Also consider products, revenue, "
        "patents, or partnerships. A company with many SBIR awards but zero "
        "non-SBIR federal work may be an 'SBIR mill' that hasn't "
        "commercialized.\n"
        "5. Risk factors — e.g. sole reliance on SBIR funding, narrow agency "
        "base, lack of phase progression, SAM exclusions, no follow-on "
        "contracts, or limited public presence\n\n"
        "Be specific and analytical. Do not use bullet points or headers. "
        "Write in a professional, neutral tone. If information is limited, "
        "note that as a risk factor."
    )

    results: dict[str, str] = {}
    total = len(company_items)

    for idx, (key, co_awards) in enumerate(company_items, 1):
        display_name = co_awards[0].get("Company", key)
        state = str(co_awards[0].get("State", ""))

        # Build context
        context_parts = [f"Company: {display_name}"]
        if state:
            context_parts.append(f"State: {state}")

        # Current week's awards
        current_summaries = []
        for a in co_awards:
            current_summaries.append(
                f"- {a.get('Award Title', 'N/A')} | {a.get('Agency', '')} "
                f"{a.get('Program', '')} {a.get('Phase', '')} | "
                f"{format_amount(str(a.get('Award Amount', '')))}"
            )
        context_parts.append(
            f"Current week's awards ({len(co_awards)}):\n"
            + "\n".join(current_summaries)
        )

        # Historical SBIR data
        hist = company_history.get(key) if company_history else None
        context_parts.append(
            f"Historical SBIR record:\n{_company_history_digest(key, hist)}"
        )

        # Web research
        cr = company_research.get(key) if company_research else None
        if cr:
            context_parts.append(f"Web research summary:\n{cr.summary}")
            if cr.source_urls:
                context_parts.append(
                    "Sources: " + ", ".join(cr.source_urls[:5])
                )
        else:
            context_parts.append(
                "Web research: No web research available for this company."
            )

        # SAM.gov registration data
        sam = sam_entities.get(key) if sam_entities else None
        if sam:
            sam_parts = [
                f"SAM.gov UEI: {sam.uei}",
                f"Legal Business Name: {sam.legal_business_name}",
            ]
            if sam.dba_name:
                sam_parts.append(f"DBA Name: {sam.dba_name}")
            sam_parts.append(
                f"Registration Status: {sam.registration_status or 'Unknown'}"
            )
            if sam.expiration_date:
                sam_parts.append(f"Registration Expiration: {sam.expiration_date}")
            if sam.entity_structure:
                sam_parts.append(f"Entity Structure: {sam.entity_structure}")
            if sam.business_type:
                sam_parts.append(f"Business Type: {sam.business_type}")
            if sam.naics_codes:
                sam_parts.append(f"NAICS Codes: {', '.join(sam.naics_codes)}")
            if sam.cage_code:
                sam_parts.append(f"CAGE Code: {sam.cage_code}")
            if sam.exclusion_status:
                sam_parts.append(f"Exclusion Status: {sam.exclusion_status}")
            context_parts.append(
                f"SAM.gov registration data:\n" + "\n".join(sam_parts)
            )
        else:
            context_parts.append(
                "SAM.gov: No SAM.gov registration data found for this company. "
                "This may indicate the company is not registered as a federal "
                "contractor, or the lookup failed."
            )

        # USAspending federal awards with SBIR vs non-SBIR breakdown
        fed = company_federal_awards.get(key) if company_federal_awards else None
        if fed:
            fed_parts = [
                f"Total federal awards (USAspending): {fed.total_awards}",
                f"Total federal funding: ${fed.total_funding:,.0f}",
                f"SBIR/STTR awards: {fed.sbir_award_count} (${fed.sbir_funding:,.0f})",
                f"Non-SBIR federal awards (follow-on/Phase III signals): "
                f"{fed.non_sbir_award_count} (${fed.non_sbir_funding:,.0f})",
            ]
            if fed.non_sbir_agencies:
                fed_parts.append(
                    f"Non-SBIR awarding agencies: {', '.join(fed.non_sbir_agencies)}"
                )
            if fed.non_sbir_sample_descriptions:
                fed_parts.append("Sample non-SBIR awards:")
                for d in fed.non_sbir_sample_descriptions:
                    fed_parts.append(f"  - {d}")
            context_parts.append(
                "USAspending federal award data:\n" + "\n".join(fed_parts)
            )
        else:
            context_parts.append(
                "USAspending: No federal award records found for this company."
            )

        user = (
            "Write a one-paragraph due-diligence assessment for this "
            "SBIR/STTR awardee company.\n\n" + "\n\n".join(context_parts)
        )

        print(
            f"Generating company diligence {idx}/{total}: {display_name}...",
            file=sys.stderr,
        )
        result = _openai_chat(
            api_key, system, user,
            model=OPENAI_DILIGENCE_MODEL, temperature=0.4,
        )
        if result:
            results[key] = result

    return results


def generate_pi_diligence(
    api_key: str,
    awards: list[dict],
    pi_history: dict[str, dict] | None = None,
    company_research: dict[str, CompanyResearch] | None = None,
    pi_external_data: dict[str, dict] | None = None,
) -> dict[str, str]:
    """Generate a diligence paragraph for each unique Principal Investigator.

    Combines the PI's SBIR history, patent portfolio, academic publications,
    company federal award context, and web research to produce a comprehensive
    assessment.

    Returns a dict keyed by upper-cased PI name.
    """
    # Collect unique PIs
    pis: dict[str, list[dict]] = {}
    for a in awards:
        pi = str(a.get("PI Name", "")).strip()
        if not pi:
            continue
        key = pi.upper()
        pis.setdefault(key, []).append(a)

    pi_items = list(pis.items())
    if len(pi_items) > MAX_PIS_TO_DILIGENCE:
        print(
            f"Capping PI diligence at {MAX_PIS_TO_DILIGENCE} "
            f"of {len(pi_items)} PIs",
            file=sys.stderr,
        )
        pi_items = pi_items[:MAX_PIS_TO_DILIGENCE]

    system = (
        "You are a due-diligence analyst evaluating Principal Investigators "
        "(PIs) who lead SBIR/STTR federal innovation projects. Write exactly "
        "one paragraph (4-6 sentences) assessing the PI. Cover:\n"
        "1. The PI's SBIR track record — number of awards, phase progression, "
        "breadth of agencies and topics\n"
        "2. Continuity — have they stayed with one company or moved between "
        "organizations? Is their research focus consistent or scattered? "
        "Cross-reference ORCID affiliations with SBIR company history to "
        "verify consistency.\n"
        "3. IP and publication output — patents filed as inventor, academic "
        "publications, and ORCID profile data demonstrate research "
        "productivity and domain expertise. Note h-index and citation count "
        "when available. ORCID research keywords and funding entries help "
        "confirm domain alignment. If patents are assigned to different "
        "entities than the current company, note that.\n"
        "4. Follow-on and commercialization — non-SBIR federal awards "
        "(contracts, grants) to the PI's company are the strongest signal "
        "of successful SBIR commercialization. These represent Phase III "
        "transitions where SBIR research led to production contracts or "
        "operational deployment. Compare the non-SBIR award descriptions "
        "to the PI's SBIR research topics — thematic alignment confirms "
        "genuine technology transition. A company with only SBIR awards "
        "and no follow-on federal work may indicate research that hasn't "
        "transitioned.\n"
        "5. Current project context — what are they working on now and how "
        "does it relate to their history and expertise?\n\n"
        "Be specific and analytical. Do not use bullet points or headers. "
        "Write in a professional, neutral tone. If the PI has no prior "
        "history, note that this is their first known SBIR award."
    )

    results: dict[str, str] = {}
    total = len(pi_items)

    for idx, (key, pi_awards) in enumerate(pi_items, 1):
        display_name = pi_awards[0].get("PI Name", key)
        company = str(pi_awards[0].get("Company", ""))

        context_parts = [f"Principal Investigator: {display_name}"]
        if company:
            context_parts.append(f"Current company: {company}")

        # Current week's awards
        current_summaries = []
        for a in pi_awards:
            current_summaries.append(
                f"- {a.get('Award Title', 'N/A')} | {a.get('Company', '')} | "
                f"{a.get('Agency', '')} {a.get('Program', '')} {a.get('Phase', '')} | "
                f"{format_amount(str(a.get('Award Amount', '')))}"
            )
        context_parts.append(
            f"Current week's awards ({len(pi_awards)}):\n"
            + "\n".join(current_summaries)
        )

        # PI historical record
        hist = pi_history.get(key) if pi_history else None
        context_parts.append(
            f"Historical SBIR record as PI:\n{_pi_history_digest(key, hist)}"
        )

        # External data: patents, publications, federal awards
        ext = pi_external_data.get(key) if pi_external_data else None
        context_parts.append(
            f"External research data:\n{_pi_external_digest(ext)}"
        )

        # Company web research for context
        cr = None
        if company_research:
            cr = company_research.get(company.strip().upper())
        if cr:
            context_parts.append(
                f"Company context ({company}):\n{cr.summary}"
            )

        user = (
            "Write a one-paragraph assessment of this Principal Investigator's "
            "SBIR/STTR track record, research output, and current project.\n\n"
            + "\n\n".join(context_parts)
        )

        print(
            f"Generating PI diligence {idx}/{total}: {display_name}...",
            file=sys.stderr,
        )
        result = _openai_chat(
            api_key, system, user,
            model=OPENAI_DILIGENCE_MODEL, temperature=0.4,
        )
        if result:
            results[key] = result

    return results


# ---------------------------------------------------------------------------
# Markdown generation
# ---------------------------------------------------------------------------


def generate_markdown(
    awards: list[dict],
    days: int,
    synopsis: str | None = None,
    descriptions: dict[int, str] | None = None,
    company_research: dict[str, CompanyResearch] | None = None,
    freshness_warnings: list[str] | None = None,
    company_diligence: dict[str, str] | None = None,
    pi_diligence: dict[str, str] | None = None,
) -> str:
    """Generate markdown report from filtered awards."""
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=days)

    lines = []
    lines.append("# SBIR Weekly Awards Report")
    lines.append("")
    lines.append(
        f"**Period:** {cutoff.strftime('%B %d, %Y')} - {now.strftime('%B %d, %Y')}"
    )
    lines.append(f"**Total new awards:** {len(awards)}")
    lines.append("")

    # Data freshness warnings
    if freshness_warnings:
        lines.append("> **Data Freshness Warning**")
        lines.append(">")
        for w in freshness_warnings:
            lines.append(f"> - {w}")
        lines.append("")

    if not awards:
        lines.append("No new awards found for this period.")
        return "\n".join(lines)

    # Weekly synopsis at the very top
    if synopsis:
        lines.append(synopsis)
        lines.append("")

    # Summary statistics
    total_amount = 0
    agencies: dict[str, int] = {}
    programs: dict[str, int] = {}
    states: dict[str, int] = {}

    for a in awards:
        try:
            total_amount += float(
                str(a.get("Award Amount", "0")).replace(",", "").replace("$", "")
            )
        except (ValueError, AttributeError):
            pass
        agency = str(a.get("Agency", "Unknown"))
        agencies[agency] = agencies.get(agency, 0) + 1
        program = str(a.get("Program", "Unknown"))
        programs[program] = programs.get(program, 0) + 1
        state = str(a.get("State", ""))
        if state:
            states[state] = states.get(state, 0) + 1

    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Total Awards | {len(awards)} |")
    lines.append(f"| Total Funding | {format_amount(str(total_amount))} |")
    lines.append(
        f"| Avg Award Size | {format_amount(str(total_amount / len(awards)))} |"
    )
    lines.append(f"| Agencies | {len(agencies)} |")
    lines.append(f"| States | {len(states)} |")
    lines.append("")

    # Breakdown by agency
    lines.append("## By Agency")
    lines.append("")
    lines.append("| Agency | Awards |")
    lines.append("|--------|--------|")
    for agency, count in sorted(agencies.items(), key=lambda x: -x[1]):
        lines.append(f"| {_escape_md_cell(agency)} | {count} |")
    lines.append("")

    # Breakdown by program/phase
    lines.append("## By Program & Phase")
    lines.append("")
    lines.append("| Program | Phase | Awards |")
    lines.append("|---------|-------|--------|")
    program_phase: dict[tuple[str, str], int] = {}
    for a in awards:
        key = (str(a.get("Program", "Unknown")), str(a.get("Phase", "Unknown")))
        program_phase[key] = program_phase.get(key, 0) + 1
    for (program, phase), count in sorted(program_phase.items(), key=lambda x: -x[1]):
        lines.append(f"| {_escape_md_cell(program)} | {_escape_md_cell(phase)} | {count} |")
    lines.append("")

    # Individual awards
    lines.append("## Awards")
    lines.append("")

    for i, a in enumerate(awards):
        date = _format_date(a.get("Proposal Award Date", ""))
        company = str(a.get("Company", ""))
        title = str(a.get("Award Title", ""))
        agency = str(a.get("Agency", ""))
        program = str(a.get("Program", ""))
        phase = str(a.get("Phase", ""))
        amount = format_amount(str(a.get("Award Amount", "")))
        state = str(a.get("State", ""))
        contract = str(a.get("Contract", "")).strip()
        solicitation = str(a.get("Solicitation Number", "")).strip()
        topic_code = str(a.get("Topic Code", "")).strip()
        pi_name = str(a.get("PI Name", "")).strip()

        # Build links
        sbir_url = build_sbir_award_url(a)
        solicitation_url = build_solicitation_url(a)
        usaspending_url = build_usaspending_url(a)

        # Look up company research
        cr = None
        if company_research:
            cr = company_research.get(company.strip().upper())

        # Award header
        lines.append(f"### {i + 1}. {title}")
        lines.append("")
        lines.append(f"**{company}** | {agency} {program} {phase} | {amount} | {state} | {date}")
        lines.append("")

        # AI-generated description
        if descriptions and i in descriptions:
            lines.append(descriptions[i])
            lines.append("")

        # Company diligence paragraph
        if company_diligence:
            co_key = company.strip().upper()
            if co_key in company_diligence:
                lines.append(f"**Company Diligence — {company}:**")
                lines.append(company_diligence[co_key])
                lines.append("")

        # PI diligence paragraph
        if pi_diligence and pi_name:
            pi_key = pi_name.strip().upper()
            if pi_key in pi_diligence:
                lines.append(f"**Principal Investigator — {pi_name}:**")
                lines.append(pi_diligence[pi_key])
                lines.append("")

        # Details table
        lines.append("<details>")
        lines.append("<summary>Award details</summary>")
        lines.append("")
        lines.append("| Field | Value |")
        lines.append("|-------|-------|")
        lines.append(f"| **Company** | {_escape_md_cell(company)} |")
        lines.append(f"| **Award Date** | {date} |")
        lines.append(f"| **Amount** | {amount} |")
        lines.append(f"| **Agency** | {_escape_md_cell(agency)} |")
        lines.append(f"| **Program** | {_escape_md_cell(program)} |")
        lines.append(f"| **Phase** | {_escape_md_cell(phase)} |")
        if state:
            lines.append(f"| **State** | {_escape_md_cell(state)} |")
        if contract:
            lines.append(f"| **Contract** | `{_escape_md_cell(contract)}` |")
        if pi_name:
            lines.append(f"| **PI** | {_escape_md_cell(pi_name)} |")
        if solicitation:
            lines.append(f"| **Solicitation** | `{_escape_md_cell(solicitation)}` |")
        if topic_code:
            lines.append(f"| **Topic Code** | `{_escape_md_cell(topic_code)}` |")
        lines.append("")
        lines.append("</details>")
        lines.append("")

        # Reference links
        link_parts = [f"[SBIR.gov Award]({sbir_url})"]
        if solicitation_url:
            link_parts.append(f"[Solicitation]({solicitation_url})")
        if usaspending_url:
            link_parts.append(f"[USAspending]({usaspending_url})")
        if cr and cr.source_urls:
            for url in cr.source_urls[:3]:
                domain = url.split("//")[-1].split("/")[0].replace("www.", "")
                link_parts.append(f"[{domain}]({url})")

        lines.append("**References:** " + " | ".join(link_parts))
        lines.append("")

    lines.append(
        f"---\n*Generated on {now.strftime('%Y-%m-%d %H:%M UTC')} from "
        f"[SBIR.gov]({SBIR_AWARDS_URL}) bulk data.*"
    )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate weekly SBIR awards report")
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days to look back (default: 7)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output file path (default: stdout)",
    )
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="Skip AI-generated summaries even if OPENAI_API_KEY is set",
    )
    parser.add_argument(
        "--no-company-research",
        action="store_true",
        help="Skip web-based company research (still generates synopsis and descriptions)",
    )
    parser.add_argument(
        "--no-diligence",
        action="store_true",
        help="Skip company and PI diligence paragraphs",
    )
    args = parser.parse_args()

    awards, freshness_warnings = fetch_weekly_awards(days=args.days)

    # Generate AI content if API key is available
    synopsis = None
    descriptions = None
    company_info: dict[str, CompanyResearch] | None = None
    co_diligence: dict[str, str] | None = None
    pi_dilig: dict[str, str] | None = None
    api_key = os.environ.get("OPENAI_API_KEY", "")

    # Fetch solicitation topic context from SBIR.gov API (no API key needed)
    sol_topics = fetch_solicitation_topics(awards) if awards else None

    if api_key and not args.no_ai:
        if not args.no_company_research:
            company_info = research_companies(api_key, awards)
        synopsis = generate_weekly_synopsis(
            api_key, awards, args.days, company_info, sol_topics
        )
        descriptions = generate_award_descriptions(
            api_key, awards, company_info, sol_topics
        )

        if not args.no_diligence:
            # Build historical context for diligence
            print("Building historical company context...", file=sys.stderr)
            co_history = get_company_history(awards)
            print("Building historical PI context...", file=sys.stderr)
            pi_history = get_pi_history(awards)

            # SAM.gov entity registration data
            sam_data = lookup_sam_entities(awards)

            # USAspending federal awards per company (SBIR vs non-SBIR)
            print("Looking up company federal awards on USAspending...", file=sys.stderr)
            co_fed: dict[str, PIFederalAwardRecord] = {}
            co_names: dict[str, dict] = {}
            for a in awards:
                name = str(a.get("Company", "")).strip()
                if not name:
                    continue
                key = name.upper()
                if key not in co_names:
                    co_names[key] = {
                        "name": name,
                        "uei": str(a.get("Company UEI", a.get("UEI", ""))).strip() or None,
                    }
            for key, info in co_names.items():
                result = lookup_company_federal_awards(info["name"], info["uei"])
                if result:
                    co_fed[key] = result

            # Fetch external PI data (patents, publications, ORCID, federal awards)
            print("Looking up PI patents, publications, ORCID, and federal awards...", file=sys.stderr)
            pi_ext = lookup_pi_external_data(awards)

            co_diligence = generate_company_diligence(
                api_key, awards, company_info, co_history, sam_data, co_fed
            )
            pi_dilig = generate_pi_diligence(
                api_key, awards, pi_history, company_info, pi_ext
            )
    elif not api_key and not args.no_ai:
        print(
            "OPENAI_API_KEY not set - skipping AI summaries. "
            "Set the env var or use --no-ai to silence this message.",
            file=sys.stderr,
        )

    report = generate_markdown(
        awards,
        days=args.days,
        synopsis=synopsis,
        descriptions=descriptions,
        company_research=company_info,
        freshness_warnings=freshness_warnings,
        company_diligence=co_diligence,
        pi_diligence=pi_dilig,
    )

    if args.output:
        with open(args.output, "w") as f:
            f.write(report)
        print(f"Report written to {args.output} ({len(awards)} awards)", file=sys.stderr)
    else:
        print(report)


if __name__ == "__main__":
    main()
