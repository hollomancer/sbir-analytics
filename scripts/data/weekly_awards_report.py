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
    python scripts/data/weekly_awards_report.py --debug
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
    from sbir_etl.utils.text_normalization import normalize_name as _normalize_name
    from sbir_etl.utils.text_normalization import pluralize_col_key as _pluralize_col_key
    from sbir_etl.validators.sbir_awards import validate_sbir_award_record as _validate_record

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

    _validate_record = None  # type: ignore[assignment]

    def _pluralize_col_key(col: str) -> str:  # type: ignore[misc]
        """Fallback pluralizer when sbir_etl is unavailable."""
        key = col.lower().replace(" ", "_")
        if key.endswith("y"):
            return key[:-1] + "ies"
        return key + "s"

    def _normalize_name(name, *, remove_suffixes=False, **_kwargs):  # type: ignore[misc]
        """Minimal fallback company name normalizer."""
        import re as _re

        if not name:
            return ""
        s = str(name).strip().lower()
        s = _re.sub(r"[^\w\s]", " ", s)
        if remove_suffixes:
            s = _re.sub(
                r"\b(incorporated|incorporation|inc|corp|corporation|llc|ltd|limited|co|company)\b",
                "",
                s,
            )
        else:
            s = _re.sub(r"\b(incorporated|incorporation)\b", "inc", s)
            s = _re.sub(r"\b(company|co)\b", "company", s)
            s = _re.sub(r"\b(limited|ltd)\b", "ltd", s)
        return _re.sub(r"\s+", " ", s).strip()

# Optional enricher imports — each degrades gracefully if unavailable.
try:
    from sbir_etl.extractors.solicitation import SolicitationExtractor

    _HAS_SOLICITATION_EXTRACTOR = True
except ImportError:
    _HAS_SOLICITATION_EXTRACTOR = False

try:
    from sbir_etl.enrichers.patentsview import PatentsViewClient, RateLimiter, parse_patent_record

    _HAS_PATENTS_CLIENT = True
except ImportError:
    _HAS_PATENTS_CLIENT = False
    parse_patent_record = None  # type: ignore[assignment]
    RateLimiter = None  # type: ignore[assignment, misc]

try:
    from sbir_etl.enrichers.inflation_adjuster import InflationAdjuster

    _HAS_INFLATION = True
except ImportError:
    _HAS_INFLATION = False

try:
    from sbir_etl.enrichers.congressional_district_resolver import CongressionalDistrictResolver

    _HAS_CONGRESS_RESOLVER = True
except ImportError:
    _HAS_CONGRESS_RESOLVER = False

try:
    from sbir_etl.enrichers.fiscal_bea_mapper import NAICSToBEAMapper

    _HAS_BEA_MAPPER = True
except ImportError:
    _HAS_BEA_MAPPER = False

try:
    from sbir_etl.enrichers.sync_wrappers import SyncSAMGovClient, SyncUSAspendingClient

    _HAS_SYNC_CLIENTS = True
except ImportError:
    _HAS_SYNC_CLIENTS = False

try:
    from sbir_etl.enrichers.fpds_atom import FPDSAtomClient

    _HAS_FPDS_CLIENT = True
except ImportError:
    _HAS_FPDS_CLIENT = False

try:
    from sbir_etl.enrichers.semantic_scholar import (
        PublicationRecord as _LibPublicationRecord,
        SemanticScholarClient,
    )

    _HAS_S2_CLIENT = True
except ImportError:
    _HAS_S2_CLIENT = False

try:
    from sbir_etl.enrichers.orcid_client import ORCIDClient, ORCIDRecord as _LibORCIDRecord

    _HAS_ORCID_CLIENT = True
except ImportError:
    _HAS_ORCID_CLIENT = False

try:
    from sbir_etl.enrichers.openai_client import OpenAIClient, WebSearchResult

    _HAS_OPENAI_CLIENT = True
except ImportError:
    _HAS_OPENAI_CLIENT = False


# ---------------------------------------------------------------------------
# Debug mode — toggled by --debug CLI flag
# ---------------------------------------------------------------------------

DEBUG = False

# Wall-clock budget per pipeline stage (seconds). Stages that exceed their
# budget skip remaining items and return partial results. Override via env var.
STAGE_TIMEOUT = int(os.environ.get("STAGE_TIMEOUT", "60"))

# Pipeline start time — set in main()
_pipeline_start: float = 0.0


def _stage_deadline(budget_seconds: int | None = None) -> float:
    """Return a monotonic deadline for the current pipeline stage."""
    import time
    return time.monotonic() + (budget_seconds or STAGE_TIMEOUT)


def _past_deadline(deadline: float) -> bool:
    """Check if we've exceeded the stage deadline."""
    import time
    return time.monotonic() > deadline


def _debug(msg: str) -> None:
    """Print a debug message to stderr when DEBUG mode is active."""
    if DEBUG:
        print(f"[DEBUG] {msg}", file=sys.stderr)


def _debug_response(label: str, resp: httpx.Response, body_preview_len: int = 500) -> None:
    """Log key details of an HTTP response in debug mode."""
    if not DEBUG:
        return
    # Use resp.content (bytes) to avoid decoding the full body into a string.
    # Only decode the sliced prefix for the preview.
    raw = resp.content
    encoding = resp.encoding or "utf-8"
    preview = raw[:body_preview_len].decode(encoding, errors="replace")
    # Collapse newlines/control chars so the log stays on one line.
    preview = preview.replace("\r", "").replace("\n", " ").replace("\t", " ")
    if len(raw) > body_preview_len:
        preview += "..."
    _debug(
        f"{label} — HTTP {resp.status_code} | "
        f"{len(raw)} bytes | preview: {preview}"
    )


# URL templates for external links
# SBIR.gov redesigned in 2025 — old /sbirsearch/ paths return 404.
# New site uses /awards?keyword= for search-based links.
SBIR_AWARD_SEARCH_URL = "https://www.sbir.gov/awards"
SBIR_SOLICITATION_URL = "https://www.sbir.gov/awards"
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
# PatentsView migrated to USPTO Open Data Portal (data.uspto.gov) March 2026
# ODP field-level Lucene queries (q=inventorNameText:"...") go to the base
# endpoint.  The /search sub-path only accepts free-text ``searchText``.
USPTO_ODP_PATENT_QUERY_URL = "https://data.uspto.gov/api/v1/patent/applications"
SEMANTIC_SCHOLAR_API_URL = "https://api.semanticscholar.org/graph/v1"
USASPENDING_API_URL = "https://api.usaspending.gov/api/v2"
SBIR_GOV_API_URL = "https://api.www.sbir.gov/public/api"
SAM_GOV_API_URL = "https://api.sam.gov/entity-information/v3/entities"
FPDS_ATOM_SEARCH_URL = "https://www.fpds.gov/ezsearch/LATEST"
ORCID_API_URL = "https://pub.orcid.org/v3.0"


# ---------------------------------------------------------------------------
# Rate limiters — shared across threads to prevent API throttling.
# Uses the library's thread-safe RateLimiter when available, with a minimal
# fallback that tracks nothing (effectively unlimited) when sbir_etl isn't
# installed.
# ---------------------------------------------------------------------------

def _make_rate_limiter(rpm: int) -> object:
    """Create a thread-safe rate limiter (library or no-op fallback)."""
    if RateLimiter is not None:
        return RateLimiter(rate_limit_per_minute=rpm)

    class _NoOpLimiter:
        def wait_if_needed(self) -> None:
            pass

    return _NoOpLimiter()


# USAspending: 120 req/min (matches library default)
_usaspending_limiter = _make_rate_limiter(120)
# Semantic Scholar: 100 req/min (default for unauthenticated)
_semantic_scholar_limiter = _make_rate_limiter(100)
# USPTO ODP: 60 req/min (conservative)
_uspto_limiter = _make_rate_limiter(60)
# SAM.gov: 60 req/min (matches library default)
_sam_gov_limiter = _make_rate_limiter(60)
# ORCID: 60 req/min (conservative)
_orcid_limiter = _make_rate_limiter(60)
# SBIR.gov API: 30 req/min (aggressive rate limiting observed)
_sbir_gov_limiter = _make_rate_limiter(30)


# Shared semaphore limiting total concurrent OpenAI API calls across all
# thread pools (company diligence + PI diligence run concurrently, each with
# up to 4 workers — without a cap that's 8 parallel LLM requests).
import threading as _threading

_openai_semaphore = _threading.Semaphore(int(os.environ.get("OPENAI_MAX_CONCURRENT", "4")))


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


# Source resolution and freshness checking — prefer shared library functions,
# fall back to inline implementations when sbir_etl is not installed.
try:
    from sbir_etl.utils.cloud_storage import (
        SbirAwardsSource as DataSource,
        check_sbir_data_freshness as _check_data_freshness_lib,
        resolve_sbir_awards_csv as _resolve_csv_path_lib,
    )

    def _resolve_csv_path() -> DataSource:
        source = _resolve_csv_path_lib(download_url=SBIR_AWARDS_URL)
        print(f"Resolved CSV: {source.path} (origin={source.origin})", file=sys.stderr)
        return source

    def _check_data_freshness(
        source: DataSource, max_award_date: str | None, days: int
    ) -> list[str]:
        return _check_data_freshness_lib(source, max_award_date, days)

except ImportError:
    from dataclasses import dataclass as _dataclass

    @_dataclass
    class DataSource:  # type: ignore[no-redef]
        """Metadata about the resolved CSV data source (fallback)."""
        path: Path
        origin: str
        s3_key_date: str | None = None

    def _resolve_csv_path() -> DataSource:  # type: ignore[misc]
        """Fallback source resolver for standalone operation."""
        print(f"S3 not available; downloading from {SBIR_AWARDS_URL}...", file=sys.stderr)
        with httpx.Client(timeout=600, follow_redirects=True) as client:
            response = client.get(SBIR_AWARDS_URL)
            response.raise_for_status()
        tmp = Path(tempfile.gettempdir()) / "sbir_weekly_award_data.csv"
        tmp.write_bytes(response.content)
        print(f"Downloaded {tmp.stat().st_size / 1024 / 1024:.1f} MB", file=sys.stderr)
        return DataSource(path=tmp, origin="download")

    def _check_data_freshness(  # type: ignore[misc]
        source: DataSource, max_award_date: str | None, days: int
    ) -> list[str]:
        """Fallback freshness checker for standalone operation."""
        warnings: list[str] = []
        now = datetime.now(UTC).replace(tzinfo=None)
        if source.s3_key_date:
            key_dt = _parse_date(source.s3_key_date)
            if key_dt:
                age = (now - datetime(key_dt.year, key_dt.month, key_dt.day)).days
                if age > days + 3:
                    warnings.append(
                        f"S3 data is {age} days old (key date: {source.s3_key_date}). "
                        f"The data-refresh workflow may have failed."
                    )
        if max_award_date:
            max_dt = _parse_date(max_award_date)
            if max_dt:
                data_age = (now - datetime(max_dt.year, max_dt.month, max_dt.day)).days
                if data_age > days + 14:
                    warnings.append(
                        f"Most recent award in data is from {max_award_date} "
                        f"({data_age} days ago). SBIR.gov bulk data may not have "
                        f"been updated recently."
                    )
        return warnings


def fetch_weekly_awards(
    days: int = 7,
) -> tuple[list[dict], list[str], DataSource, object | None, str | None]:
    """Load SBIR CSV and filter for awards in the past N days.

    When sbir_etl is installed, uses SbirDuckDBExtractor for fast
    columnar import and SQL-based date filtering.  Otherwise falls back
    to csv.DictReader with Python-level filtering.

    Returns (awards, freshness_warnings, source, extractor_or_None, table_or_None).
    The source/extractor/table can be reused for historical queries to avoid
    re-downloading and re-importing the ~376 MB CSV.
    """
    source = _resolve_csv_path()
    cutoff_str = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%d")

    extractor = None
    table = None

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

    return awards, freshness_warnings, source, extractor, table


# ---------------------------------------------------------------------------
# Data cleaning & deduplication
# ---------------------------------------------------------------------------

_FALLBACK_VALID_PHASES = {"Phase I", "Phase II", "Phase III"}


def _company_key(award: dict) -> str:
    """Return a normalized company key for grouping.

    Uses _normalized_company if the cleaning pass has run, otherwise
    falls back to upper-cased raw name.
    """
    norm = award.get("_normalized_company", "")
    if norm:
        return norm
    return str(award.get("Company", "")).strip().upper()


def clean_and_dedup_awards(awards: list[dict]) -> tuple[list[dict], dict]:
    """Validate, normalize, and deduplicate weekly awards.

    Uses the existing sbir_etl validation pipeline when available:
    - validate_sbir_award_record() for per-row validation (phase, amount,
      required fields, format checks, date consistency, etc.)
    - normalize_name() for company name normalization

    Falls back to basic checks when sbir_etl is not installed.

    Returns:
        (cleaned_awards, stats) where stats is a dict with counts.
    """
    import pandas as pd

    stats: dict = {
        "input": len(awards),
        "validation_errors": 0,
    }

    cleaned: list[dict] = []

    if _validate_record is not None:
        for i, a in enumerate(awards):
            row = pd.Series(a)
            issues = _validate_record(row, i)
            errors = [
                iss for iss in issues
                if (iss.severity.value if hasattr(iss.severity, "value") else iss.severity) == "error"
            ]
            if errors:
                stats["validation_errors"] += 1
                continue
            a["_normalized_company"] = _normalize_name(
                str(a.get("Company", "")), remove_suffixes=True
            )
            cleaned.append(a)
    else:
        # Minimal fallback when sbir_etl is not installed
        for a in awards:
            company = str(a.get("Company", "")).strip()
            if not company:
                stats["validation_errors"] += 1
                continue
            phase = str(a.get("Phase", "")).strip()
            if phase and phase not in _FALLBACK_VALID_PHASES:
                stats["validation_errors"] += 1
                continue
            a["_normalized_company"] = _normalize_name(
                company, remove_suffixes=True
            )
            cleaned.append(a)

    stats["output"] = len(cleaned)
    stats["total_removed"] = stats["input"] - stats["output"]

    if stats["total_removed"] > 0:
        print(
            f"Data cleaning: {stats['input']} -> {stats['output']} awards "
            f"({stats['validation_errors']} failed validation)",
            file=sys.stderr,
        )
    else:
        print(
            f"Data cleaning: {stats['input']} awards, all valid",
            file=sys.stderr,
        )

    return cleaned, stats


# ---------------------------------------------------------------------------
# Historical context (for diligence)
# ---------------------------------------------------------------------------


def _parse_date_safe(value) -> str | None:
    """Parse a date value and return ISO format string, or None."""
    parsed = _parse_date(value)
    return parsed.isoformat() if parsed else None


def _resolve_shared_extractor(
    source: DataSource | None = None,
) -> tuple[DataSource, object | None, str | None]:
    """Resolve a CSV path and optionally create a shared DuckDB extractor.

    Returns (source, extractor_or_None, table_name_or_None).
    """
    if source is None:
        source = _resolve_csv_path()

    extractor = None
    table = None
    if _HAS_SBIR_ETL and SbirDuckDBExtractor is not None:
        extractor = SbirDuckDBExtractor(
            csv_path=source.path,
            duckdb_path=":memory:",
            use_s3_first=False,
        )
        extractor.import_csv()
        table = extractor._table_identifier

    return source, extractor, table


# _pluralize_col_key is imported from sbir_etl.utils.text_normalization
# (with a fallback defined in the ImportError block above).


def _build_history_from_df(
    df,
    group_col: str,
    extra_set_cols: list[str] | None = None,
) -> dict[str, dict]:
    """Build history dicts from a DataFrame grouped by a column.

    Used by both company and PI history to avoid duplicating aggregation logic.
    """
    df = df.fillna("")
    history: dict[str, dict] = {}

    for group_key, group_df in df.groupby(group_col, sort=False):
        name = str(group_key).strip()
        if not name:
            continue

        phases = {v for v in group_df["Phase"].astype(str).str.strip() if v}
        agencies = {v for v in group_df["Agency"].astype(str).str.strip() if v}
        programs = {v for v in group_df["Program"].astype(str).str.strip() if v}

        total_funding = 0.0
        for val in group_df["Award Amount"].astype(str):
            try:
                total_funding += float(val.replace(",", "").replace("$", ""))
            except (ValueError, TypeError):
                pass

        parsed_dates = []
        for val in group_df["Proposal Award Date"].astype(str).str.strip():
            if val:
                iso = _parse_date_safe(val)
                if iso:
                    parsed_dates.append(iso)

        titles: list[str] = []
        for t in group_df["Award Title"].astype(str).str.strip():
            if t and t not in titles:
                titles.append(t)

        entry: dict = {
            "total_awards": len(group_df),
            "phases": sorted(phases),
            "agencies": sorted(agencies),
            "programs": sorted(programs),
            "total_funding": total_funding,
            "earliest_date": min(parsed_dates) if parsed_dates else None,
            "latest_date": max(parsed_dates) if parsed_dates else None,
            "sample_titles": titles[:5],
        }

        # Extra set columns (e.g. "Company" for PI history)
        if extra_set_cols:
            for col in extra_set_cols:
                col_key = _pluralize_col_key(col)
                entry[col_key] = sorted(
                    {v for v in group_df[col].astype(str).str.strip() if v}
                )

        history[name] = entry

    return history


def _build_history_from_csv(
    source: DataSource,
    target_names: set[str],
    key_field: str,
    extra_set_fields: list[str] | None = None,
) -> dict[str, dict]:
    """Build history dicts by streaming the CSV file.

    Streams the file line-by-line to avoid loading the entire CSV into memory.
    """
    import csv

    history: dict[str, dict] = {}
    with source.path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = str(row.get(key_field, "")).strip().upper()
            if name not in target_names:
                continue
            if name not in history:
                entry: dict = {
                    "total_awards": 0,
                    "phases": set(),
                    "agencies": set(),
                    "programs": set(),
                    "total_funding": 0.0,
                    "dates": [],
                    "sample_titles": [],
                }
                if extra_set_fields:
                    for ef in extra_set_fields:
                        entry[_pluralize_col_key(ef)] = set()
                history[name] = entry

            h = history[name]
            h["total_awards"] += 1
            for field, set_key in [("Phase", "phases"), ("Agency", "agencies"), ("Program", "programs")]:
                val = str(row.get(field, "")).strip()
                if val:
                    h[set_key].add(val)
            if extra_set_fields:
                for ef in extra_set_fields:
                    val = str(row.get(ef, "")).strip()
                    if val:
                        h[_pluralize_col_key(ef)].add(val)
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

    # Normalize sets to sorted lists and parse dates
    for name, h in history.items():
        raw_dates = h.pop("dates", [])
        parsed_dates = [_parse_date_safe(d) for d in raw_dates]
        parsed_dates = [d for d in parsed_dates if d]
        h["earliest_date"] = min(parsed_dates) if parsed_dates else None
        h["latest_date"] = max(parsed_dates) if parsed_dates else None
        for key in ["phases", "agencies", "programs"]:
            if isinstance(h[key], set):
                h[key] = sorted(h[key])
        if extra_set_fields:
            for ef in extra_set_fields:
                set_key = ef.lower().replace(" ", "_") + "s"
                if isinstance(h.get(set_key), set):
                    h[set_key] = sorted(h[set_key])

    return history


def get_company_history(
    awards: list[dict],
    source: DataSource | None = None,
    extractor: object | None = None,
    table: str | None = None,
) -> dict[str, dict]:
    """Extract historical SBIR award context per company from the full dataset.

    Accepts optional shared source/extractor/table to avoid redundant CSV
    downloads and DuckDB imports when called alongside get_pi_history().

    Returns a dict keyed by upper-cased company name.
    """
    company_names = {str(a.get("Company", "")).strip().upper() for a in awards}
    company_names.discard("")
    if not company_names:
        return {}

    if source is None:
        source, extractor, table = _resolve_shared_extractor()

    if extractor is not None and table is not None:
        # Build IN clause with escaped names
        escaped = [f"'{n.replace(chr(39), chr(39)+chr(39))}'" for n in sorted(company_names)]
        in_clause = ", ".join(escaped)
        query = (
            f'SELECT UPPER("Company") AS _group_key, "Phase", "Agency", '
            f'"Award Amount", "Proposal Award Date", "Award Title", "Program" '
            f"FROM {table} "
            f'WHERE UPPER("Company") IN ({in_clause}) '
            f'ORDER BY "Proposal Award Date" DESC'
        )
        df = extractor.duckdb_client.execute_query_df(query)
        if df.empty:
            return {}
        return _build_history_from_df(df, "_group_key")

    # Fallback: stream the CSV
    return _build_history_from_csv(source, company_names, "Company")


def get_pi_history(
    awards: list[dict],
    source: DataSource | None = None,
    extractor: object | None = None,
    table: str | None = None,
) -> dict[str, dict]:
    """Extract historical SBIR context per Principal Investigator.

    Accepts optional shared source/extractor/table to avoid redundant CSV
    downloads and DuckDB imports.

    Returns a dict keyed by upper-cased PI name.
    """
    pi_names = set()
    for a in awards:
        pi = str(a.get("PI Name", "")).strip().upper()
        if pi:
            pi_names.add(pi)

    if not pi_names:
        return {}

    if source is None:
        source, extractor, table = _resolve_shared_extractor()

    if extractor is not None and table is not None:
        escaped = [f"'{n.replace(chr(39), chr(39)+chr(39))}'" for n in sorted(pi_names)]
        in_clause = ", ".join(escaped)
        query = (
            f'SELECT UPPER("PI Name") AS _group_key, "Company", "Phase", "Agency", '
            f'"Award Amount", "Proposal Award Date", "Award Title", "Program" '
            f"FROM {table} "
            f'WHERE UPPER("PI Name") IN ({in_clause}) '
            f'ORDER BY "Proposal Award Date" DESC'
        )
        df = extractor.duckdb_client.execute_query_df(query)
        if df.empty:
            return {}
        return _build_history_from_df(df, "_group_key", extra_set_cols=["Company"])

    # Fallback: stream the CSV
    return _build_history_from_csv(source, pi_names, "PI Name", extra_set_fields=["Company"])


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
    """Query USPTO ODP for patents where the PI is a named inventor.

    Uses PatentsViewClient when available (rate limiting, caching, retry).
    Falls back to bare httpx calls otherwise.
    """
    first, last = _split_pi_name(pi_name)
    if not last:
        return None

    # Prefer PatentsViewClient — handles rate limiting and retry via tenacity
    if _HAS_PATENTS_CLIENT:
        _debug(f"Using PatentsViewClient for '{pi_name}'")
        try:
            client = PatentsViewClient()
            try:
                # Query by company name to get patents, then we'll have all
                # inventor/assignee data in the results
                patents = client.query_patents_by_assignee(
                    company_name=company_name or last,
                    max_patents=100,
                )
            finally:
                if hasattr(client, "close"):
                    client.close()
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
                d = p.get("grant_date") or p.get("patent_date", "")
                if d:
                    dates.append(d)

            return PIPatentRecord(
                total_patents=len(patents),
                sample_titles=titles,
                assignees=sorted(assignees),
                date_range=(min(dates) if dates else None, max(dates) if dates else None),
            )
        except Exception as e:
            _debug(f"PatentsViewClient error for '{pi_name}': {e}, falling back")

    # Fallback: bare httpx call to USPTO ODP
    api_key = os.environ.get("USPTO_ODP_API_KEY", "")
    headers: dict[str, str] = {}
    if api_key:
        headers["X-API-KEY"] = api_key

    # ODP uses ``searchText`` for free-text queries (not Lucene ``q``).
    # Combine inventor name and company into a single search string.
    search_terms = f"{first} {last}".strip() if first else last
    if company_name:
        search_terms += f" {company_name}"

    params = {
        "searchText": search_terms,
        "offset": 0,
        "limit": 100,
    }

    _debug(f"USPTO ODP query for '{pi_name}': GET {USPTO_ODP_PATENT_QUERY_URL} params={params}")
    try:
        _uspto_limiter.wait_if_needed()
        with httpx.Client(timeout=30) as client:
            resp = client.get(USPTO_ODP_PATENT_QUERY_URL, headers=headers, params=params)
            _debug_response(f"USPTO ODP [{pi_name}]", resp)
            if resp.status_code != 200:
                print(
                    f"USPTO ODP API returned {resp.status_code} for {pi_name}",
                    file=sys.stderr,
                )
                return None
            data = resp.json()
    except Exception as e:
        print(f"USPTO ODP API error for {pi_name}: {e}", file=sys.stderr)
        return None

    records = data.get("patentFileWrapperDataBag", [])
    _debug(f"USPTO ODP [{pi_name}]: {len(records)} patent records returned")
    if not records:
        return None

    titles = []
    assignees: set[str] = set()
    dates: list[str] = []

    for raw_record in records:
        # Use shared parser when available, inline fallback otherwise
        if parse_patent_record is not None:
            parsed = parse_patent_record(raw_record)
            title = parsed.get("patent_title", "")
            org = parsed.get("assignee_organization", "")
            grant_date = parsed.get("grant_date", "")
        else:
            metadata = raw_record.get("applicationMetaData", {}) or {}
            title = raw_record.get("inventionTitle") or metadata.get("inventionTitle") or ""
            org = ""
            for a in (raw_record.get("assignees", []) or []):
                if isinstance(a, dict):
                    org = a.get("assigneeName") or a.get("orgName") or ""
                    break
            if not org:
                org = raw_record.get("assigneeName") or metadata.get("assigneeName") or ""
            grant_date = metadata.get("grantDate") or raw_record.get("grantDate") or ""

        if title and title not in titles and len(titles) < 5:
            titles.append(title)
        if org:
            assignees.add(org)
        if grant_date:
            dates.append(grant_date)

    return PIPatentRecord(
        total_patents=len(records),
        sample_titles=titles,
        assignees=sorted(assignees),
        date_range=(min(dates) if dates else None, max(dates) if dates else None),
    )


def lookup_pi_publications(pi_name: str) -> PIPublicationRecord | None:
    """Query Semantic Scholar for the PI's publication history.

    Uses :class:`SemanticScholarClient` when the library is available;
    falls back to inline httpx calls for standalone operation.
    """
    first, last = _split_pi_name(pi_name)
    if not last:
        return None

    search_query = f"{first} {last}".strip()

    if _HAS_S2_CLIENT:
        with SemanticScholarClient(rate_limiter=_semantic_scholar_limiter) as s2:
            try:
                rec = s2.lookup_author(search_query)
            except Exception as e:
                print(f"Semantic Scholar API error for {pi_name}: {e}", file=sys.stderr)
                return None
        if rec is None:
            return None
        return PIPublicationRecord(
            total_papers=rec.total_papers,
            h_index=rec.h_index,
            citation_count=rec.citation_count,
            sample_titles=rec.sample_titles,
            affiliations=rec.affiliations,
        )

    # Inline fallback for standalone operation
    s2_api_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "")
    headers: dict[str, str] = {}
    if s2_api_key:
        headers["x-api-key"] = s2_api_key

    import time

    try:
        search_data = None
        with httpx.Client(timeout=30, headers=headers) as client:
            for attempt in range(3):
                _semantic_scholar_limiter.wait_if_needed()
                resp = client.get(
                    f"{SEMANTIC_SCHOLAR_API_URL}/author/search",
                    params={"query": search_query, "limit": 5},
                )
                if resp.status_code == 429:
                    time.sleep(2 ** (attempt + 1))
                    continue
                if resp.status_code != 200:
                    return None
                search_data = resp.json()
                break
        if search_data is None:
            return None
        authors = search_data.get("data", [])
        if not authors:
            return None
        author_id = authors[0].get("authorId")
        if not author_id:
            return None

        author_data = None
        with httpx.Client(timeout=30, headers=headers) as client:
            for attempt in range(3):
                _semantic_scholar_limiter.wait_if_needed()
                resp = client.get(
                    f"{SEMANTIC_SCHOLAR_API_URL}/author/{author_id}",
                    params={"fields": "name,hIndex,citationCount,affiliations,papers.title,papers.year"},
                )
                if resp.status_code == 429:
                    time.sleep(2 ** (attempt + 1))
                    continue
                if resp.status_code != 200:
                    return None
                author_data = resp.json()
                break
        if author_data is None:
            return None
    except Exception as e:
        print(f"Semantic Scholar API error for {pi_name}: {e}", file=sys.stderr)
        return None

    papers = author_data.get("papers", [])
    return PIPublicationRecord(
        total_papers=len(papers),
        h_index=author_data.get("hIndex"),
        citation_count=author_data.get("citationCount", 0),
        sample_titles=[p["title"] for p in papers[:5] if p.get("title")],
        affiliations=author_data.get("affiliations", []) or [],
    )


def _is_sbir_award_type(description: str, cfda: str) -> bool:
    """Identify SBIR/STTR awards using ALN numbers and description keywords.

    Delegates to :func:`sbir_etl.models.sbir_identification.classify_sbir_award`
    when the library is available; falls back to a minimal inline heuristic.
    """
    try:
        from sbir_etl.models.sbir_identification import classify_sbir_award

        result = classify_sbir_award(cfda_number=cfda, description=description)
        return result is not None
    except ImportError:
        pass

    # Fallback for standalone operation
    _sbir_alns = {
        "10.212", "12.910", "12.911", "81.049", "43.002", "43.003",
        "47.041", "47.084", "66.511", "66.512", "97.077", "20.701",
        "84.133",
        "93.855", "93.856", "93.859", "93.837", "93.847", "93.853",
        "93.865", "93.866", "93.867", "93.879", "93.242", "93.273",
        "93.279", "93.395", "93.393", "93.394", "93.396", "93.399",
    }
    if cfda and cfda.strip() in _sbir_alns:
        return True
    desc_upper = description.upper()
    if "SBIR" in desc_upper or "STTR" in desc_upper:
        return True
    if "SMALL BUSINESS INNOVATION RESEARCH" in desc_upper:
        return True
    if "SMALL BUSINESS TECHNOLOGY TRANSFER" in desc_upper:
        return True
    return False


def _usaspending_autocomplete(company_name: str) -> dict[str, str] | None:
    """Use USAspending recipient autocomplete for fuzzy company name matching.

    Generates name variations (abbreviation expansion, punctuation normalization,
    suffix removal) and tries each against the autocomplete endpoint until a match
    with a UEI or resolved name is found.

    Based on sbir_etl.enrichers.company_categorization._fuzzy_match_recipient
    but uses synchronous httpx to avoid async dependencies.
    """
    import re as _re

    if not company_name or not company_name.strip():
        return None

    # Generate name variations, ordered most-to-least specific
    abbreviations = {
        r"\bIntl\.?\b": "International",
        r"\bInt'l\.?\b": "International",
        r"\bInc\.?\b": "Incorporated",
        r"\bCorp\.?\b": "Corporation",
        r"\bLtd\.?\b": "Limited",
        r"\bLLC\.?\b": "Limited Liability Company",
        r"\bTech\.?\b": "Technology",
        r"\bMfg\.?\b": "Manufacturing",
        r"\bSvcs\.?\b": "Services",
        r"\bDev\.?\b": "Development",
    }

    variations: list[str] = [company_name.strip()]

    # Expand abbreviations
    expanded = company_name
    for pattern, replacement in abbreviations.items():
        expanded = _re.sub(pattern, replacement, expanded, flags=_re.IGNORECASE)
    if expanded != company_name:
        variations.append(expanded.strip())

    # Normalize punctuation
    normalized = expanded.replace("/", " AND ").replace("&", " AND ")
    normalized = _re.sub(r"\s+", " ", normalized).strip()
    if normalized not in variations:
        variations.append(normalized)

    # Remove legal suffixes for broadest match
    base = _re.sub(
        r",?\s*(Inc\.?|Incorporated|LLC|Ltd\.?|Limited|Corp\.?|Corporation|Company|Co\.?)$",
        "", normalized, flags=_re.IGNORECASE,
    ).strip().rstrip(",").strip()
    if base and base not in variations and len(base) >= 10:
        variations.append(base)

    # Add uppercase versions (USAspending often stores uppercase)
    upper_vars = [v.upper() for v in variations[:2] if v.upper() != v]
    variations = variations[:2] + upper_vars + variations[2:]

    # Deduplicate preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for v in variations:
        key = v.lower()
        if key not in seen and len(v) >= 5:
            seen.add(key)
            unique.append(v)

    _debug(f"USAspending autocomplete: {len(unique)} name variations for '{company_name}'")

    best_candidate = None

    # Use shared sync client when available (gets rate limiting + retry from
    # the library); fall back to raw httpx for standalone operation.
    if _HAS_SYNC_CLIENTS:
        usa = SyncUSAspendingClient()
        try:
            for idx, name in enumerate(unique, 1):
                try:
                    _usaspending_limiter.wait_if_needed()
                    data = usa.autocomplete_recipient(name, limit=5)
                    results = data.get("results", [])
                    if not results:
                        continue
                    match = results[0]
                    matched_name = match.get("legal_business_name", "")
                    matched_uei = match.get("uei")
                    if matched_uei and str(matched_uei).strip().lower() not in ("", "nan", "none"):
                        _debug(
                            f"USAspending autocomplete matched '{company_name}' "
                            f"(variation {idx}: '{name}') → '{matched_name}' UEI={matched_uei}"
                        )
                        return {"uei": matched_uei, "name": matched_name}
                    if matched_name and best_candidate is None:
                        best_candidate = {"uei": matched_uei, "name": matched_name}
                except Exception:
                    continue
        finally:
            usa.close()
    else:
        with httpx.Client(timeout=15) as client:
            for idx, name in enumerate(unique, 1):
                try:
                    _usaspending_limiter.wait_if_needed()
                    resp = client.post(
                        f"{USASPENDING_API_URL}/autocomplete/recipient/",
                        json={"search_text": name, "limit": 5},
                    )
                    if resp.status_code != 200:
                        continue
                    results = resp.json().get("results", [])
                    if not results:
                        continue
                    match = results[0]
                    matched_name = match.get("legal_business_name", "")
                    matched_uei = match.get("uei")
                    if matched_uei and str(matched_uei).strip().lower() not in ("", "nan", "none"):
                        _debug(
                            f"USAspending autocomplete matched '{company_name}' "
                            f"(variation {idx}: '{name}') → '{matched_name}' UEI={matched_uei}"
                        )
                        return {"uei": matched_uei, "name": matched_name}
                    if matched_name and best_candidate is None:
                        best_candidate = {"uei": matched_uei, "name": matched_name}
                except Exception:
                    continue

    if best_candidate:
        _debug(f"USAspending autocomplete: best candidate for '{company_name}' → '{best_candidate['name']}' (no UEI)")
        return best_candidate

    _debug(f"USAspending autocomplete: no match for '{company_name}' after {len(unique)} variations")
    return None


def _usaspending_search(
    company_name: str,
    search_text: str,
    label: str,
) -> list[dict] | None:
    """Execute USAspending spending_by_award searches for a company.

    Makes separate requests for contracts and grants/other (USAspending
    requires award_type_codes from a single group per request), then
    merges the results.

    Returns the combined results list on success, or None on error.
    """
    fields = [
        "Award ID",
        "Recipient Name",
        "Award Amount",
        "Awarding Agency",
        "Award Type",
        "Start Date",
        "Description",
        "CFDA Number",
    ]
    # USAspending requires award_type_codes from one group only.
    # The API enforces these groups: contracts (A-D), grants (02-05),
    # direct_payments (06, 10), loans (07-09), other (11).
    type_groups = [
        ("contracts", ["A", "B", "C", "D"]),
        ("grants", ["02", "03", "04", "05"]),
        ("direct_payments", ["06", "10"]),
        ("loans", ["07", "08", "09"]),
        ("other", ["11"]),
    ]

    all_results: list[dict] = []
    _debug(
        f"USAspending query for '{company_name}' ({label}='{search_text}'): "
        f"POST /search/spending_by_award/"
    )

    if _HAS_SYNC_CLIENTS:
        usa = SyncUSAspendingClient()
        try:
            for group_name, codes in type_groups:
                try:
                    _usaspending_limiter.wait_if_needed()
                    data = usa.search_awards(
                        filters={
                            "award_type_codes": codes,
                            "recipient_search_text": [search_text],
                        },
                        fields=fields,
                        limit=50,
                    )
                    group_results = data.get("results", [])
                    _debug(f"USAspending [{company_name} via {label}/{group_name}]: {len(group_results)} results")
                    all_results.extend(group_results)
                except Exception as e:
                    _debug(f"USAspending [{company_name}] {label}/{group_name} error: {e}")
                    continue
        finally:
            usa.close()
    else:
        try:
            with httpx.Client(timeout=30) as client:
                for group_name, codes in type_groups:
                    _usaspending_limiter.wait_if_needed()
                    payload = {
                        "filters": {
                            "award_type_codes": codes,
                            "recipient_search_text": [search_text],
                        },
                        "fields": fields,
                        "page": 1,
                        "limit": 50,
                        "sort": "Award Amount",
                        "order": "desc",
                    }
                    resp = client.post(
                        f"{USASPENDING_API_URL}/search/spending_by_award/",
                        json=payload,
                    )
                    if resp.status_code != 200:
                        _debug(f"USAspending [{company_name}] {label}/{group_name} returned {resp.status_code}")
                        continue
                    data = resp.json()
                    group_results = data.get("results", [])
                    _debug(f"USAspending [{company_name} via {label}/{group_name}]: {len(group_results)} results")
                    all_results.extend(group_results)
        except Exception as e:
            _debug(f"USAspending [{company_name}] {label} error: {e}")
            return None

    _debug(f"USAspending [{company_name} via {label}]: {len(all_results)} total results")
    return all_results if all_results else None


def lookup_company_federal_awards(
    company_name: str,
    uei: str | None = None,
) -> PIFederalAwardRecord | None:
    """Query USAspending for all federal awards to the PI's company.

    Tries UEI first (most reliable), then falls back to company name search.
    Separates SBIR/STTR awards from non-SBIR federal work. Non-SBIR
    contracts and grants to a company with SBIR history are the strongest
    signal of successful commercialization / Phase III transition.
    """
    if not company_name:
        return None

    # Cascading lookup: UEI → exact name → fuzzy autocomplete match
    results = None
    if uei:
        results = _usaspending_search(company_name, uei, "UEI")
    if not results:
        results = _usaspending_search(company_name, company_name, "name")
    if not results:
        # Fuzzy match: try USAspending autocomplete with name variations
        match = _usaspending_autocomplete(company_name)
        if match:
            search_key = match["uei"] if match.get("uei") else match["name"]
            label = "autocomplete-UEI" if match.get("uei") else "autocomplete-name"
            results = _usaspending_search(company_name, search_key, label)
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
    company_federal_awards: dict[str, PIFederalAwardRecord] | None = None,
) -> dict[str, dict]:
    """Look up external data (patents, publications, ORCID, federal awards) for each PI.

    If company_federal_awards is provided, reuses those results instead of
    re-querying USAspending for each PI's company.

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
                "company_key": _company_key(a),
            }

    results: dict[str, dict] = {}
    total = len(pis)

    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _lookup_single_pi(key: str, info: dict) -> tuple[str, dict]:
        name = info["name"]
        company = info["company"]
        uei = info["uei"] or None

        # Run the 3 independent API calls concurrently per PI
        with ThreadPoolExecutor(max_workers=3) as inner:
            patent_future = inner.submit(lookup_pi_patents, name, company)
            pub_future = inner.submit(lookup_pi_publications, name)
            orcid_future = inner.submit(lookup_pi_orcid, name)

            patents = patent_future.result()
            publications = pub_future.result()
            orcid_rec = orcid_future.result()

        # Reuse company federal awards if already fetched, else query fresh
        fed = None
        if company_federal_awards is not None:
            fed = company_federal_awards.get(info["company_key"])
        if fed is None and company_federal_awards is None:
            fed = lookup_company_federal_awards(company, uei)

        return key, {
            "patents": patents,
            "publications": publications,
            "orcid": orcid_rec,
            "federal_awards": fed,
        }

    # Process PIs concurrently (capped at 4 to respect API rate limits)
    deadline = _stage_deadline()
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(_lookup_single_pi, key, info): (key, info)
            for key, info in pis.items()
        }
        done = 0
        for future in as_completed(futures):
            if _past_deadline(deadline):
                print(
                    f"PI external data stage timeout ({STAGE_TIMEOUT}s) — "
                    f"completed {done}/{total}, skipping remainder",
                    file=sys.stderr,
                )
                executor.shutdown(wait=False, cancel_futures=True)
                break
            done += 1
            key, info = futures[future]
            try:
                pi_key, pi_data = future.result(timeout=10)
                results[pi_key] = pi_data
                print(
                    f"Completed PI external data {done}/{total}: {info['name']}",
                    file=sys.stderr,
                )
            except Exception as e:
                print(
                    f"PI external data error for {info['name']}: {e}",
                    file=sys.stderr,
                )

    return results


# ---------------------------------------------------------------------------
# USAspending recipient profile (company context)
# ---------------------------------------------------------------------------


@dataclass
class USARecipientProfile:
    """Key data from a USAspending recipient profile."""

    recipient_id: str
    name: str
    uei: str | None
    parent_name: str | None
    parent_uei: str | None
    location_state: str | None
    location_congressional_district: str | None
    business_types: list[str]
    total_transaction_amount: float
    total_transactions: int


def lookup_usaspending_recipient(
    company_name: str,
    uei: str | None = None,
) -> USARecipientProfile | None:
    """Look up a company's USAspending recipient profile.

    Two-step: POST /recipient/ to find the hash ID, then GET /recipient/{id}/
    for the full profile. Tries UEI first, then company name.
    """
    if not company_name:
        return None

    # Step 1: Find the recipient hash ID
    search_terms = []
    if uei:
        search_terms.append(uei)
    search_terms.append(company_name)

    recipient_id = None

    if _HAS_SYNC_CLIENTS:
        usa = SyncUSAspendingClient()
        try:
            for term in search_terms:
                _debug(f"USAspending recipient search: keyword='{term}'")
                try:
                    _usaspending_limiter.wait_if_needed()
                    results = usa.search_recipients(term, limit=5)
                    if results:
                        recipient_id = results[0].get("id")
                        _debug(
                            f"USAspending recipient matched '{term}' → "
                            f"'{results[0].get('name')}' id={recipient_id}"
                        )
                        break
                except Exception as e:
                    _debug(f"USAspending recipient search error for '{term}': {e}")
                    continue

            if not recipient_id:
                _debug(f"USAspending recipient: no match for '{company_name}'")
                return None

            # Step 2: Fetch the full profile
            _debug(f"USAspending recipient profile: GET /recipient/{recipient_id}/?year=all")
            try:
                _usaspending_limiter.wait_if_needed()
                profile = usa.get_recipient_profile(recipient_id)
            except Exception as e:
                _debug(f"USAspending recipient profile error: {e}")
                return None
            if not profile:
                return None
        finally:
            usa.close()
    else:
        for term in search_terms:
            _debug(f"USAspending recipient search: keyword='{term}'")
            try:
                _usaspending_limiter.wait_if_needed()
                with httpx.Client(timeout=15) as client:
                    resp = client.post(
                        f"{USASPENDING_API_URL}/recipient/",
                        json={"keyword": term, "limit": 5},
                    )
                    if resp.status_code != 200:
                        _debug(f"USAspending recipient search returned {resp.status_code}")
                        continue
                    data = resp.json()
                    results = data.get("results", [])
                    if results:
                        recipient_id = results[0].get("id")
                        _debug(
                            f"USAspending recipient matched '{term}' → "
                            f"'{results[0].get('name')}' id={recipient_id}"
                        )
                        break
            except Exception as e:
                _debug(f"USAspending recipient search error for '{term}': {e}")
                continue

        if not recipient_id:
            _debug(f"USAspending recipient: no match for '{company_name}'")
            return None

        _debug(f"USAspending recipient profile: GET /recipient/{recipient_id}/?year=all")
        try:
            _usaspending_limiter.wait_if_needed()
            with httpx.Client(timeout=15) as client:
                resp = client.get(
                    f"{USASPENDING_API_URL}/recipient/{recipient_id}/",
                    params={"year": "all"},
                )
                if resp.status_code != 200:
                    _debug(f"USAspending recipient profile returned {resp.status_code}")
                    return None
                profile = resp.json()
        except Exception as e:
            _debug(f"USAspending recipient profile error: {e}")
            return None

    location = profile.get("location") or {}

    return USARecipientProfile(
        recipient_id=recipient_id,
        name=profile.get("name") or company_name,
        uei=profile.get("uei"),
        parent_name=profile.get("parent_name"),
        parent_uei=profile.get("parent_uei"),
        location_state=location.get("state_code"),
        location_congressional_district=location.get("congressional_code"),
        business_types=profile.get("business_types") or [],
        total_transaction_amount=float(profile.get("total_transaction_amount") or 0),
        total_transactions=int(profile.get("total_transactions") or 0),
    )


def lookup_usaspending_recipients(
    awards: list[dict],
) -> dict[str, USARecipientProfile]:
    """Look up USAspending recipient profiles for each unique company.

    Returns a dict keyed by upper-cased company name.
    """
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
            }

    results: dict[str, USARecipientProfile] = {}
    total = len(companies)
    deadline = _stage_deadline(60)  # lighter budget — profile lookups are fast
    print(f"Looking up {total} recipient profiles on USAspending...", file=sys.stderr)

    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _lookup_one(item: tuple[str, dict]) -> tuple[str, USARecipientProfile | None]:
        key, info = item
        return key, lookup_usaspending_recipient(info["name"], info["uei"])

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(_lookup_one, item): item for item in companies.items()}
        for future in as_completed(futures):
            if _past_deadline(deadline):
                print(
                    f"USAspending recipient stage timeout — "
                    f"completed {len(results)}/{total}, skipping remainder",
                    file=sys.stderr,
                )
                executor.shutdown(wait=False, cancel_futures=True)
                break
            try:
                key, profile = future.result(timeout=10)
                if profile:
                    results[key] = profile
            except Exception as e:
                item = futures[future]
                print(
                    f"Warning: USAspending recipient lookup failed for {item[0]}: {e}",
                    file=sys.stderr,
                )

    print(f"Found {len(results)}/{total} recipient profiles on USAspending", file=sys.stderr)
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

    entity = None

    if _HAS_SYNC_CLIENTS:
        sam = SyncSAMGovClient()
        try:
            # Try UEI first (most reliable)
            if uei:
                _debug(f"SAM.gov [{company_name}]: lookup by UEI={uei}")
                try:
                    _sam_gov_limiter.wait_if_needed()
                    entity = sam.get_entity_by_uei(uei)
                except Exception as e:
                    _debug(f"SAM.gov [{company_name}]: UEI lookup error: {e}")

            # Try CAGE code
            if not entity and cage:
                _debug(f"SAM.gov [{company_name}]: lookup by CAGE={cage}")
                try:
                    _sam_gov_limiter.wait_if_needed()
                    entity = sam.get_entity_by_cage(cage)
                except Exception as e:
                    _debug(f"SAM.gov [{company_name}]: CAGE lookup error: {e}")

            # Fall back to name search
            if not entity and company_name:
                _debug(f"SAM.gov [{company_name}]: name search")
                try:
                    _sam_gov_limiter.wait_if_needed()
                    results = sam.search_entities(
                        legal_business_name=company_name,
                        registration_status="A",
                        limit=1,
                    )
                    entity = results[0] if results else None
                except Exception as e:
                    _debug(f"SAM.gov [{company_name}]: name search error: {e}")
        finally:
            sam.close()
    else:
        headers = {"X-Api-Key": api_key, "Accept": "application/json"}

        def _try_query(params: dict) -> dict | None:
            _debug(f"SAM.gov query for '{company_name}': GET {SAM_GOV_API_URL} params={params}")
            import time

            for attempt in range(3):
                try:
                    _sam_gov_limiter.wait_if_needed()
                    with httpx.Client(timeout=30) as client:
                        resp = client.get(SAM_GOV_API_URL, headers=headers, params=params)
                        _debug_response(f"SAM.gov [{company_name}]", resp)
                        if resp.status_code == 429:
                            wait = 2 ** (attempt + 1)
                            _debug(f"SAM.gov [{company_name}]: rate limited, retrying in {wait}s")
                            time.sleep(wait)
                            continue
                        if resp.status_code != 200:
                            return None
                        data = resp.json()
                        results = data.get("entityData", data.get("results", []))
                        result_count = len(results) if isinstance(results, list) else (1 if results else 0)
                        _debug(f"SAM.gov [{company_name}]: {result_count} entities in response")
                        if isinstance(results, list) and results:
                            return results[0]
                        if isinstance(results, dict):
                            return results
                        return None
                except Exception as e:
                    if attempt < 2:
                        wait = 2 ** (attempt + 1)
                        _debug(f"SAM.gov [{company_name}]: request error ({e}), retrying in {wait}s")
                        time.sleep(wait)
                        continue
                    print(f"SAM.gov API error: {e}", file=sys.stderr)
                    return None
            return None

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
        # Always log — helps diagnose silent failures in CI
        methods_tried = []
        if uei:
            methods_tried.append(f"UEI={uei}")
        if cage:
            methods_tried.append(f"CAGE={cage}")
        methods_tried.append(f"name='{company_name}'")
        print(
            f"SAM.gov: no entity found for {company_name} "
            f"(tried: {', '.join(methods_tried)})",
            file=sys.stderr,
        )
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
    deadline = _stage_deadline()
    print(f"Looking up {total} companies on SAM.gov...", file=sys.stderr)

    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _lookup_one(item: tuple[str, dict]) -> tuple[str, SAMEntityRecord | None]:
        key, info = item
        return key, lookup_sam_entity(info["name"], info["uei"], info["cage"])

    # Cap at 3 workers to respect SAM.gov 60 req/min rate limit
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(_lookup_one, item): item for item in companies.items()}
        for future in as_completed(futures):
            if _past_deadline(deadline):
                print(
                    f"SAM.gov stage timeout ({STAGE_TIMEOUT}s) — "
                    f"completed {len(results)}/{total}, skipping remainder",
                    file=sys.stderr,
                )
                executor.shutdown(wait=False, cancel_futures=True)
                break
            try:
                key, record = future.result(timeout=10)
                if record:
                    results[key] = record
            except Exception as e:
                item = futures[future]
                print(
                    f"Warning: SAM.gov entity lookup failed for {item[0]}: {e}",
                    file=sys.stderr,
                )

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

    Uses :class:`ORCIDClient` when the library is available;
    falls back to inline httpx calls for standalone operation.
    """
    first, last = _split_pi_name(pi_name)
    if not last:
        return None

    if _HAS_ORCID_CLIENT:
        with ORCIDClient(rate_limiter=_orcid_limiter) as orcid:
            try:
                rec = orcid.lookup(pi_name)
            except Exception as e:
                print(f"ORCID API error for {pi_name}: {e}", file=sys.stderr)
                return None
        if rec is None:
            return None
        return ORCIDRecord(
            orcid_id=rec.orcid_id,
            given_name=rec.given_name,
            family_name=rec.family_name,
            affiliations=rec.affiliations,
            works_count=rec.works_count,
            sample_work_titles=rec.sample_work_titles,
            funding_count=rec.funding_count,
            keywords=rec.keywords,
        )

    # Inline fallback for standalone operation
    headers = {"Accept": "application/json"}
    orcid_token = os.environ.get("ORCID_ACCESS_TOKEN", "")
    if orcid_token:
        headers["Authorization"] = f"Bearer {orcid_token}"

    try:
        query = f"family-name:{last}"
        if first:
            query += f" AND given-names:{first}"

        _orcid_limiter.wait_if_needed()
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
        best = results[0]
        orcid_id = best.get("orcid-id", "")
        if not orcid_id:
            return None

        _orcid_limiter.wait_if_needed()
        with httpx.Client(timeout=30) as client:
            resp = client.get(f"{ORCID_API_URL}/{orcid_id}/record", headers=headers)
            if resp.status_code != 200:
                return None
            profile = resp.json()
    except Exception as e:
        print(f"ORCID API error for {pi_name}: {e}", file=sys.stderr)
        return None

    affiliations: list[str] = []
    for group in (profile.get("activities-summary", {}).get("employments", {}).get("affiliation-group", []))[:10]:
        for s in group.get("summaries", []):
            org_name = s.get("employment-summary", {}).get("organization", {}).get("name", "")
            if org_name and org_name not in affiliations:
                affiliations.append(org_name)

    works_group = profile.get("activities-summary", {}).get("works", {}).get("group", [])
    sample_titles = []
    for wg in works_group[:5]:
        summaries = wg.get("work-summary", [])
        if summaries:
            title_val = summaries[0].get("title", {}).get("title", {}).get("value", "")
            if title_val:
                sample_titles.append(title_val)

    funding_group = profile.get("activities-summary", {}).get("fundings", {}).get("group", [])
    keyword_list = profile.get("person", {}).get("keywords", {}).get("keyword", [])
    keywords = [kw.get("content", "") for kw in keyword_list[:10] if kw.get("content")]

    return ORCIDRecord(
        orcid_id=orcid_id,
        given_name=best.get("given-names"),
        family_name=best.get("family-names"),
        affiliations=affiliations,
        works_count=len(works_group),
        sample_work_titles=sample_titles,
        funding_count=len(funding_group),
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

    Uses SolicitationExtractor when available (tenacity retry, pagination,
    keyword search, awards fallback). Falls back to hand-rolled queries
    otherwise.
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

    def _parse_year(sol: str) -> int | None:
        for part in sol.replace("-", " ").replace(".", " ").split():
            if part.isdigit() and len(part) == 4:
                return int(part)
        return None

    def _make_topic(tc: str, sol_num: str, topic: dict) -> SolicitationTopic:
        desc = topic.get("topicDescription") or topic.get("description")
        if desc and len(str(desc)) > 3000:
            desc = str(desc)[:3000] + "..."
        return SolicitationTopic(
            topic_code=tc,
            solicitation_number=(
                topic.get("solicitationNumber")
                or topic.get("solicitation_number")
                or sol_num
            ),
            title=topic.get("topicTitle") or topic.get("title") or "",
            description=str(desc) if desc else None,
            agency=topic.get("agency"),
            program=topic.get("program"),
        )

    # --- Path A: SolicitationExtractor (tenacity retry + all query modes) ---
    if _HAS_SOLICITATION_EXTRACTOR:
        _debug("Using SolicitationExtractor")
        try:
            extractor = SolicitationExtractor()
            try:
                # Group topic codes by year
                sol_years: dict[int, list[str]] = {}
                no_year_codes: list[tuple[str, str]] = []
                for tc, sol in topic_codes.items():
                    year = _parse_year(sol)
                    if year:
                        sol_years.setdefault(year, []).append(tc)
                    else:
                        no_year_codes.append((tc, sol))

                # Step 1: Year-based batch queries
                import pandas as pd

                all_topics = pd.DataFrame()
                for year in sol_years:
                    df = extractor.extract_topics(year=year, max_results=1000)
                    if not df.empty:
                        all_topics = pd.concat([all_topics, df], ignore_index=True)

                if not all_topics.empty:
                    all_topics = extractor.deduplicate_topics(all_topics)
                    codes_set = set(topic_codes.keys())
                    for _, row in all_topics.iterrows():
                        tc = str(row.get("topic_code", "")).strip()
                        if tc in codes_set and tc not in results:
                            results[tc] = _make_topic(tc, topic_codes.get(tc, ""), row.to_dict())

                # Step 2: Keyword search for no-year codes
                for tc, sol in no_year_codes:
                    if tc in results:
                        continue
                    keyword = sol if sol else tc
                    topics = extractor.query_by_keyword(keyword)
                    for topic in topics:
                        found_tc = topic.get("topicCode") or topic.get("topic_code") or ""
                        if found_tc == tc:
                            results[tc] = _make_topic(tc, sol, topic)
                            break

                # Step 3: Awards fallback for anything still missing
                missing = [tc for tc in topic_codes if tc not in results]
                if missing:
                    _debug(f"Awards fallback for {len(missing)} missing topic codes")
                    for tc in missing:
                        fallback = extractor.query_awards_for_topic(tc)
                        if fallback:
                            results[tc] = SolicitationTopic(
                                topic_code=tc,
                                solicitation_number=topic_codes.get(tc, ""),
                                title=fallback.get("title", ""),
                                description=(
                                    str(fallback["description"])[:3000] + "..."
                                    if fallback.get("description") and len(str(fallback["description"])) > 3000
                                    else fallback.get("description")
                                ),
                                agency=fallback.get("agency"),
                                program=fallback.get("program"),
                            )

                print(f"SolicitationExtractor found {len(results)}/{total} topics", file=sys.stderr)
            finally:
                extractor.close()
            return results
        except Exception as e:
            print(f"SolicitationExtractor error: {e}, falling back to manual queries", file=sys.stderr)

    # --- Path B: Inline httpx fallback (standalone mode) ---
    sol_years_fb: dict[int, list[str]] = {}
    no_year_codes_fb: list[tuple[str, str]] = []
    for tc, sol in topic_codes.items():
        year = _parse_year(sol)
        if year:
            sol_years_fb.setdefault(year, []).append(tc)
        else:
            no_year_codes_fb.append((tc, sol))

    import time

    for tc, sol in no_year_codes_fb:
        keyword = sol if sol else tc
        try:
            _sbir_gov_limiter.wait_if_needed()
            with httpx.Client(timeout=30) as client:
                resp = client.get(f"{SBIR_GOV_API_URL}/solicitations", params={"rows": 25, "start": 0, "keyword": keyword})
                if resp.status_code == 429:
                    time.sleep(3)
                    _sbir_gov_limiter.wait_if_needed()
                    resp = client.get(f"{SBIR_GOV_API_URL}/solicitations", params={"rows": 25, "start": 0, "keyword": keyword})
                if resp.status_code != 200:
                    continue
                data = resp.json()
        except Exception:
            continue
        topics = data if isinstance(data, list) else (data.get("results") or data.get("data") or [])
        for topic in topics:
            found_tc = topic.get("topicCode") or topic.get("topic_code") or ""
            if found_tc == tc and tc not in results:
                results[tc] = _make_topic(tc, sol, topic)
                break

    for year, codes in sol_years_fb.items():
        data = None
        for attempt in range(3):
            try:
                _sbir_gov_limiter.wait_if_needed()
                with httpx.Client(timeout=30) as client:
                    resp = client.get(f"{SBIR_GOV_API_URL}/solicitations", params={"rows": 500, "start": 0, "year": year})
                    if resp.status_code == 429:
                        time.sleep(2 ** (attempt + 1))
                        continue
                    if resp.status_code != 200:
                        break
                    data = resp.json()
                    break
            except Exception:
                break
        if data is None:
            continue
        topics = data if isinstance(data, list) else (data.get("results") or data.get("data") or [])
        codes_set = set(codes)
        for topic in topics:
            tc = topic.get("topicCode") or topic.get("topic_code") or ""
            if tc in codes_set and tc not in results:
                results[tc] = _make_topic(tc, topic_codes.get(tc, ""), topic)

    found = len(results)
    print(f"Fetched {found}/{total} solicitation topics from SBIR.gov", file=sys.stderr)

    # Awards fallback for missing codes
    missing_codes = [tc for tc in topic_codes if tc not in results]
    if missing_codes:
        print(f"Falling back to SBIR.gov awards API for {len(missing_codes)} missing topic codes...", file=sys.stderr)
        time.sleep(2)
        for tc in missing_codes:
            try:
                _sbir_gov_limiter.wait_if_needed()
                with httpx.Client(timeout=30) as client:
                    resp = client.get(f"{SBIR_GOV_API_URL}/awards", params={"keyword": tc, "rows": 5, "start": 0})
                    if resp.status_code == 429:
                        time.sleep(3)
                        resp = client.get(f"{SBIR_GOV_API_URL}/awards", params={"keyword": tc, "rows": 5, "start": 0})
                        if resp.status_code != 200:
                            continue
                    elif resp.status_code != 200:
                        continue
                    data = resp.json()
            except Exception:
                continue
            award_list = data if isinstance(data, list) else (data.get("results") or data.get("data") or [])
            for award in award_list:
                award_tc = award.get("topicCode") or award.get("topic_code") or ""
                if award_tc != tc:
                    continue
                title = award.get("topicTitle") or award.get("topic_title") or award.get("awardTitle") or award.get("award_title") or ""
                desc = award.get("topicDescription") or award.get("topic_description") or award.get("abstract") or award.get("Abstract") or None
                if desc and len(desc) > 3000:
                    desc = desc[:3000] + "..."
                if title or desc:
                    results[tc] = SolicitationTopic(
                        topic_code=tc, solicitation_number=topic_codes.get(tc, ""),
                        title=title, description=desc, agency=award.get("agency"), program=award.get("program"),
                    )
                    break
        fallback_found = len(results) - found
        print(f"Fallback recovered {fallback_found}/{len(missing_codes)} topic descriptions from awards API", file=sys.stderr)

    return results


# ---------------------------------------------------------------------------
# Reference link verification
# ---------------------------------------------------------------------------


def verify_reference_links(
    awards: list[dict],
    company_research: dict[str, CompanyResearch] | None = None,
) -> dict[str, list[dict]]:
    """Verify that constructed reference links return valid HTTP responses.

    Performs HTTP HEAD requests on a sample of each link type to check
    for broken URLs. Returns a summary dict with results per link type.

    Only runs in --debug mode to avoid slowing down normal report generation.
    """
    link_checks: dict[str, list[dict]] = {
        "sbir_award": [],
        "solicitation": [],
        "usaspending": [],
        "company_research": [],
    }

    # Check a sample of up to 5 awards to avoid excessive requests
    sample = awards[:5] if len(awards) > 5 else awards

    with httpx.Client(timeout=10, follow_redirects=True) as client:
        for a in sample:
            title = str(a.get("Award Title", ""))[:60]

            # SBIR.gov award link
            sbir_url = build_sbir_award_url(a)
            try:
                resp = client.head(sbir_url)
                link_checks["sbir_award"].append({
                    "url": sbir_url, "status": resp.status_code, "award": title,
                })
            except Exception as e:
                link_checks["sbir_award"].append({
                    "url": sbir_url, "status": f"error: {e}", "award": title,
                })

            # Solicitation link
            sol_url = build_solicitation_url(a)
            if sol_url:
                try:
                    resp = client.head(sol_url)
                    link_checks["solicitation"].append({
                        "url": sol_url, "status": resp.status_code, "award": title,
                    })
                except Exception as e:
                    link_checks["solicitation"].append({
                        "url": sol_url, "status": f"error: {e}", "award": title,
                    })

            # USAspending link
            usa_url = build_usaspending_url(a)
            if usa_url:
                try:
                    resp = client.head(usa_url)
                    link_checks["usaspending"].append({
                        "url": usa_url, "status": resp.status_code, "award": title,
                    })
                except Exception as e:
                    link_checks["usaspending"].append({
                        "url": usa_url, "status": f"error: {e}", "award": title,
                    })

        # Check company research source URLs (sample)
        if company_research:
            checked_urls: set[str] = set()
            for cr in list(company_research.values())[:3]:
                for url in cr.source_urls[:2]:
                    if url in checked_urls:
                        continue
                    checked_urls.add(url)
                    try:
                        resp = client.head(url)
                        link_checks["company_research"].append({
                            "url": url, "status": resp.status_code,
                        })
                    except Exception as e:
                        link_checks["company_research"].append({
                            "url": url, "status": f"error: {e}",
                        })

    return link_checks


def _print_link_verification_report(link_checks: dict[str, list[dict]]) -> None:
    """Print link verification results to stderr."""
    print("\n[DEBUG] === Reference Link Verification ===", file=sys.stderr)
    for link_type, checks in link_checks.items():
        if not checks:
            print(f"[DEBUG] {link_type}: no links to check", file=sys.stderr)
            continue
        ok = sum(1 for c in checks if isinstance(c["status"], int) and c["status"] < 400)
        broken = [c for c in checks if not (isinstance(c["status"], int) and c["status"] < 400)]
        print(
            f"[DEBUG] {link_type}: {ok}/{len(checks)} OK",
            file=sys.stderr,
        )
        for b in broken:
            award_info = f" (award: {b['award']})" if "award" in b else ""
            print(
                f"[DEBUG]   BROKEN: {b['url']} -> {b['status']}{award_info}",
                file=sys.stderr,
            )


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
        url = f"{SBIR_AWARD_SEARCH_URL}?keyword={quote(contract)}"
        _debug(f"SBIR award URL (contract='{contract}'): {url}")
        return url
    company = str(award.get("Company", "")).strip()
    if company:
        url = f"{SBIR_AWARD_SEARCH_URL}?keyword={quote(company)}"
        _debug(f"SBIR award URL (company='{company}', no contract): {url}")
        return url
    _debug("SBIR award URL: no contract or company — using base URL")
    return SBIR_AWARD_SEARCH_URL


def build_solicitation_url(award: dict) -> str | None:
    """Build a link to the SBIR.gov solicitation/topic page."""
    solicitation = str(award.get("Solicitation Number", "")).strip()
    topic_code = str(award.get("Topic Code", "")).strip()
    if solicitation:
        url = f"{SBIR_SOLICITATION_URL}?keyword={quote(solicitation)}"
        _debug(f"Solicitation URL (sol='{solicitation}'): {url}")
        return url
    if topic_code:
        url = f"{SBIR_SOLICITATION_URL}?keyword={quote(topic_code)}"
        _debug(f"Solicitation URL (topic='{topic_code}', no sol number): {url}")
        return url
    _debug(f"Solicitation URL: no solicitation number or topic code for '{award.get('Award Title', 'N/A')}'")
    return None


def build_usaspending_url(award: dict) -> str | None:
    """Build a link to USAspending.gov search for this award's contract."""
    contract = str(award.get("Contract", "")).strip()
    if not contract:
        _debug(f"USAspending URL: no contract number for '{award.get('Award Title', 'N/A')}'")
        return None
    search_term = quote(contract)
    url = f'{USASPENDING_SEARCH_URL}?form_fields={{"search_term":"{search_term}"}}'
    _debug(f"USAspending URL (contract='{contract}'): {url}")
    return url


# ---------------------------------------------------------------------------
# OpenAI integration
# ---------------------------------------------------------------------------


# Lazy-initialized OpenAI client — created on first use when the library is
# available.  Shares the concurrency semaphore with the fallback path.
_openai_client_instance: object | None = None


def _get_openai_client(api_key: str) -> object | None:
    """Return (and cache) an OpenAIClient if the library is installed."""
    global _openai_client_instance  # noqa: PLW0603
    if not _HAS_OPENAI_CLIENT:
        return None
    if _openai_client_instance is None:
        _openai_client_instance = OpenAIClient(
            api_key=api_key,
            max_concurrent=int(os.environ.get("OPENAI_MAX_CONCURRENT", "4")),
            model=OPENAI_MODEL,
        )
    return _openai_client_instance


def _openai_request_with_retry(
    method: str,
    url: str,
    headers: dict,
    payload: dict,
    timeout: int = 120,
) -> httpx.Response | None:
    """Fallback: make an OpenAI API request with retry/backoff."""
    import time

    for attempt in range(OPENAI_MAX_RETRIES + 1):
        try:
            _openai_semaphore.acquire()
            try:
                with httpx.Client(timeout=timeout) as client:
                    resp = client.request(method, url, headers=headers, json=payload)
            finally:
                _openai_semaphore.release()
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt < OPENAI_MAX_RETRIES:
                    wait = OPENAI_RETRY_BACKOFF_BASE ** (attempt + 1)
                    time.sleep(wait)
                    continue
            resp.raise_for_status()
            return resp
        except httpx.HTTPStatusError:
            if attempt < OPENAI_MAX_RETRIES:
                continue
            return None
        except Exception:
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
    _debug(
        f"OpenAI chat: model={model} temp={temperature} "
        f"system_len={len(system)} user_len={len(user)}"
    )

    # Prefer library client (has its own retry + semaphore)
    oai = _get_openai_client(api_key)
    if oai is not None:
        result = oai.chat(system, user, model=model, temperature=temperature)
        if result:
            _debug(f"OpenAI chat response: {len(result)} chars")
        return result

    # Inline fallback
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
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
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        usage = data.get("usage", {})
        _debug(
            f"OpenAI chat response: {len(content)} chars | "
            f"tokens: prompt={usage.get('prompt_tokens', '?')} "
            f"completion={usage.get('completion_tokens', '?')} "
            f"total={usage.get('total_tokens', '?')}"
        )
        return content
    except (KeyError, IndexError) as e:
        print(f"OpenAI Chat API unexpected response: {e}", file=sys.stderr)
        return None


def _openai_web_search(api_key: str, query: str) -> CompanyResearch | None:
    """Use the OpenAI Responses API with web_search_preview to research a company."""
    _debug(f"OpenAI web search: query='{query[:200]}'")

    # Prefer library client
    oai = _get_openai_client(api_key)
    if oai is not None:
        result = oai.web_search(query)
        if result is None:
            return None
        return CompanyResearch(summary=result.summary, source_urls=result.source_urls)

    # Inline fallback
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
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
        key = _company_key(a)
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

    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _research_single(item: tuple[str, dict]) -> tuple[str, CompanyResearch | None]:
        key, info = item
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
        return key, _openai_web_search(api_key, query)

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(_research_single, item): item
            for item in company_items
        }
        done = 0
        for future in as_completed(futures):
            done += 1
            key_info = futures[future]
            name = key_info[1]["name"]
            try:
                key, research = future.result()
                if research:
                    results[key] = research
                print(f"Completed company research {done}/{total}: {name}", file=sys.stderr)
            except Exception as e:
                print(f"Company research error for {name}: {e}", file=sys.stderr)

    return results


def _fetch_fpds_descriptions(
    contract_ids: list[str],
) -> dict[str, str]:
    """Fetch contract descriptions from FPDS Atom Feed (public, no API key).

    Uses :class:`FPDSAtomClient` when the library is available; falls back
    to inline httpx + XML parsing for standalone operation.

    Only accepts contract PIIDs — assistance FAINs (e.g. DE-*) are not
    indexed in FPDS and should be filtered out before calling this function.
    """
    if not contract_ids:
        return {}

    _debug(f"FPDS: querying {len(contract_ids)} contract IDs")

    if _HAS_FPDS_CLIENT:
        with FPDSAtomClient(rate_limiter=_usaspending_limiter) as fpds:
            try:
                results = fpds.get_descriptions(contract_ids)
            except Exception as e:
                print(f"FPDS error: {e}", file=sys.stderr)
                results = {}
        _debug(f"FPDS: {len(results)}/{len(contract_ids)} descriptions found")
        return results

    # Inline fallback for standalone operation (no sbir_etl)
    import time as _t
    import xml.etree.ElementTree as ET

    results: dict[str, str] = {}
    try:
        with httpx.Client(timeout=30) as client:
            for cid in contract_ids:
                if cid in results:
                    continue
                query = f'PIID:"{cid}" OR REF_IDV_PIID:"{cid}"'
                for attempt in range(3):
                    try:
                        _usaspending_limiter.wait_if_needed()
                        resp = client.get(
                            FPDS_ATOM_SEARCH_URL,
                            params={"q": query, "s": 0, "num": 1},
                        )
                        if resp.status_code in (429, 500, 502, 503, 504):
                            wait = 2 ** (attempt + 1)
                            _debug(f"FPDS [{cid}] returned {resp.status_code}, retrying in {wait}s")
                            _t.sleep(wait)
                            continue
                        if resp.status_code != 200:
                            break

                        root = ET.fromstring(resp.text)
                        ns = {"atom": "http://www.w3.org/2005/Atom"}
                        entry = root.find("atom:entry", ns)
                        if entry is None:
                            break

                        content_el = entry.find("atom:content", ns)
                        desc = None
                        if content_el is not None:
                            for local_name in ("descriptionOfContractRequirement", "description"):
                                for el in content_el.iter():
                                    tag = el.tag.split("}", 1)[-1] if "}" in el.tag else el.tag
                                    if tag == local_name and el.text:
                                        desc = el.text.strip()
                                        break
                                if desc:
                                    break
                        if not desc:
                            title_el = entry.find("atom:title", ns)
                            if title_el is not None and title_el.text:
                                desc = title_el.text.strip()
                        if desc:
                            if len(desc) > 500:
                                desc = desc[:500] + "..."
                            results[cid] = desc
                        break
                    except (httpx.HTTPError, ET.ParseError, UnicodeDecodeError) as e:
                        _t.sleep(2 ** (attempt + 1))
    except Exception as e:
        print(f"FPDS fallback error: {e}", file=sys.stderr)

    _debug(f"FPDS: {len(results)}/{len(contract_ids)} descriptions found")
    return results


def fetch_usaspending_contract_descriptions(
    awards: list[dict],
) -> dict[str, str]:
    """Fetch contract descriptions from USAspending for awards with contract numbers.

    Returns a dict keyed by contract number with the award description text.
    Used as supplementary LLM context when solicitation topic data is unavailable.
    """
    import time as _t

    # Use shared award-ID classification when available, inline fallback otherwise.
    try:
        from sbir_etl.enrichers.usaspending.client import build_award_type_groups
    except ImportError:
        import re as _re

        def build_award_type_groups(ids):  # type: ignore[misc]
            piids, fains, unknown = [], [], []
            seen: set[str] = set()
            for raw in ids:
                s = raw.strip()
                if not s or s in seen:
                    continue
                seen.add(s)
                if _re.match(r"^DE-", s, _re.IGNORECASE):
                    fains.append(s)
                elif _re.match(r"^[A-Z]{2}\d", s):
                    piids.append(s)
                else:
                    unknown.append(s)
            groups = []
            if piids:
                groups.append((piids, "contracts", ["A", "B", "C", "D"]))
            if fains:
                groups.append((fains, "assistance", ["02", "03", "04", "05"]))
            for uid in unknown:
                groups.append(([uid], "contracts", ["A", "B", "C", "D"]))
                groups.append(([uid], "assistance", ["02", "03", "04", "05"]))
            return groups

    raw_ids = [str(a.get("Contract", "")).strip() for a in awards]
    raw_ids = [c for c in raw_ids if c]
    if not raw_ids:
        return {}

    requests_to_make = build_award_type_groups(raw_ids)
    all_ids = list({aid for ids, _, _ in requests_to_make for aid in ids})

    _debug(f"USAspending contract desc: {len(all_ids)} IDs in {len(requests_to_make)} groups")
    print(
        f"Fetching {len(all_ids)} contract descriptions from USAspending...",
        file=sys.stderr,
    )
    results: dict[str, str] = {}
    # Track IDs from groups that failed at the API level (503, 422, etc.)
    # so the FPDS fallback only fires for actual USAspending outages.
    failed_ids: set[str] = set()

    desc_fields = ["Award ID", "Description", "Awarding Agency", "Award Type"]

    def _extract_descriptions(data: dict) -> None:
        """Extract descriptions from a USAspending response into results."""
        for r in data.get("results", []):
            aid = str(r.get("Award ID", "")).strip()
            desc = str(r.get("Description", "")).strip()
            if aid and desc and aid not in results:
                if len(desc) > 500:
                    desc = desc[:500] + "..."
                results[aid] = desc

    if _HAS_SYNC_CLIENTS:
        usa = SyncUSAspendingClient()
        try:
            for ids, group_name, codes in requests_to_make:
                quoted = [f'"{c}"' for c in ids]
                filters = {"award_ids": quoted, "award_type_codes": codes}
                _debug(
                    f"USAspending contract desc: {group_name} "
                    f"({len(ids)} IDs: {ids[:3]})"
                )
                data = None
                # Try spending_by_award, then spending_by_transaction
                # USAspending requires a 'sort' field; use the appropriate
                # default for each endpoint.
                _sort_for_method = {
                    "search_awards": "Award Amount",
                    "search_transactions": "Transaction Amount",
                }
                for method in ("search_awards", "search_transactions"):
                    try:
                        _usaspending_limiter.wait_if_needed()
                        data = getattr(usa, method)(
                            filters=filters,
                            fields=desc_fields,
                            limit=len(ids),
                            sort=_sort_for_method.get(method, "Award Amount"),
                            order="desc",
                        )
                        break
                    except Exception as e:
                        _debug(f"USAspending {method}/{group_name} failed: {e}")
                        continue
                if data is None:
                    failed_ids.update(ids)
                    continue
                _extract_descriptions(data)
        except Exception as e:
            failed_ids.update(cid for cid in all_ids if cid not in results)
            print(f"USAspending contract desc error: {e}", file=sys.stderr)
        finally:
            usa.close()
    else:
        try:
            with httpx.Client(timeout=30) as client:
                for ids, group_name, codes in requests_to_make:
                    quoted = [f'"{c}"' for c in ids]
                    # USAspending requires 'sort'; map each endpoint to its
                    # default sort field.
                    endpoints = [
                        ("search/spending_by_award", "Award Amount"),
                        ("search/spending_by_transaction", "Transaction Amount"),
                    ]
                    _debug(
                        f"USAspending contract desc: {group_name} "
                        f"({len(ids)} IDs: {ids[:3]})"
                    )
                    data = None
                    for endpoint, sort_field in endpoints:
                        payload = {
                            "filters": {
                                "award_ids": quoted,
                                "award_type_codes": codes,
                            },
                            "fields": desc_fields,
                            "page": 1,
                            "limit": len(ids),
                            "sort": sort_field,
                            "order": "desc",
                        }
                        for attempt in range(2):
                            _usaspending_limiter.wait_if_needed()
                            resp = client.post(
                                f"{USASPENDING_API_URL}/{endpoint}/",
                                json=payload,
                            )
                            if resp.status_code in (429, 500, 502, 503, 504):
                                wait = 2 ** (attempt + 1)
                                _debug(
                                    f"USAspending {endpoint}/{group_name} "
                                    f"returned {resp.status_code}, retrying in {wait}s"
                                )
                                _t.sleep(wait)
                                continue
                            if resp.status_code != 200:
                                _debug(
                                    f"USAspending {endpoint}/{group_name} "
                                    f"returned {resp.status_code}"
                                )
                                break
                            data = resp.json()
                            break
                        if data is not None:
                            break
                        _debug(
                            f"USAspending {endpoint} failed for {group_name}, "
                            f"trying next endpoint"
                        )
                    if data is None:
                        failed_ids.update(ids)
                        continue
                    _extract_descriptions(data)
        except Exception as e:
            failed_ids.update(cid for cid in all_ids if cid not in results)
            print(f"USAspending contract desc error: {e}", file=sys.stderr)

    # FPDS Atom Feed fallback for contract PIIDs that failed at USAspending.
    # FPDS only indexes procurement contracts (PIIDs), not assistance FAINs
    # (e.g. DE-* DOE awards), so we filter to contract-type IDs only.
    import re as _re_fallback
    fpds_eligible = [
        cid for cid in failed_ids
        if cid not in results and not _re_fallback.match(r"^DE-", cid, _re_fallback.IGNORECASE)
    ]
    if fpds_eligible:
        _debug(
            f"USAspending failed for {len(failed_ids)} IDs, "
            f"{len(fpds_eligible)} eligible for FPDS fallback"
        )
        print(
            f"Falling back to FPDS for {len(fpds_eligible)} missing contract descriptions...",
            file=sys.stderr,
        )
        fpds_results = _fetch_fpds_descriptions(fpds_eligible)
        if fpds_results:
            results.update(fpds_results)
            print(
                f"FPDS fallback recovered {len(fpds_results)}/{len(fpds_eligible)} descriptions",
                file=sys.stderr,
            )

    if not results and all_ids:
        print(
            f"Contract descriptions: 0 results for {len(all_ids)} award IDs "
            f"from USAspending + FPDS (sample: {all_ids[:3]})",
            file=sys.stderr,
        )

    _debug(f"Contract descriptions: {len(results)}/{len(all_ids)} found (USAspending + FPDS)")
    print(
        f"Fetched {len(results)}/{len(all_ids)} contract descriptions (USAspending + FPDS fallback)",
        file=sys.stderr,
    )
    return results


def _award_digest(
    award: dict,
    company_research: CompanyResearch | None = None,
    solicitation_topics: dict[str, SolicitationTopic] | None = None,
    usaspending_descriptions: dict[str, str] | None = None,
    sam_entities: dict[str, SAMEntityRecord] | None = None,
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
    has_sol_topic = False
    if solicitation_topics and topic_code:
        topic = solicitation_topics.get(topic_code)
        if topic:
            has_sol_topic = True
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

    # Supplementary context from USAspending and SAM.gov when solicitation
    # topic data is unavailable — gives the LLM program/industry context.
    if not has_sol_topic:
        if usaspending_descriptions and contract:
            usa_desc = usaspending_descriptions.get(contract)
            if usa_desc:
                parts.append(
                    f"USAspending contract description (supplementary context): {usa_desc}"
                )
        company = str(award.get("Company", "")).strip()
        if sam_entities and company:
            sam = sam_entities.get(company.upper())
            if sam and sam.naics_codes:
                parts.append(
                    f"Company NAICS codes (industry classification from SAM.gov): "
                    f"{', '.join(sam.naics_codes)}"
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
    usaspending_descriptions: dict[str, str] | None = None,
    sam_entities: dict[str, SAMEntityRecord] | None = None,
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
            cr = company_research.get(_company_key(a))
        digests.append(
            f"[{i+1}] {_award_digest(a, cr, solicitation_topics, usaspending_descriptions, sam_entities)}"
        )
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
    usaspending_descriptions: dict[str, str] | None = None,
    sam_entities: dict[str, SAMEntityRecord] | None = None,
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
                cr = company_research.get(_company_key(a))
            digests.append(
                f"[{idx}] {_award_digest(a, cr, solicitation_topics, usaspending_descriptions, sam_entities)}"
            )

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
    usa_recipients: dict[str, USARecipientProfile] | None = None,
    congressional_districts: dict[str, str] | None = None,
    bea_sectors: dict[str, str] | None = None,
) -> dict[str, str]:
    """Generate a diligence paragraph for each unique awardee company.

    Combines web research, historical SBIR data, SAM.gov registration data,
    USAspending federal award data (with SBIR vs non-SBIR breakdown), and
    the current award context to produce a focused due-diligence assessment
    per company.

    Returns a dict keyed by upper-cased company name.
    """
    # Collect unique companies (grouped by normalized name)
    companies: dict[str, list[dict]] = {}
    for a in awards:
        name = str(a.get("Company", "")).strip()
        if not name:
            continue
        key = _company_key(a)
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

    def _build_and_generate(idx: int, key: str, co_awards: list[dict]) -> tuple[str, str | None]:
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

        # USAspending recipient profile (business types, parent company, totals)
        rcp = usa_recipients.get(key) if usa_recipients else None
        if rcp:
            rcp_parts = [
                f"USAspending recipient name: {rcp.name}",
            ]
            if rcp.parent_name:
                rcp_parts.append(f"Parent company: {rcp.parent_name}")
            if rcp.business_types:
                rcp_parts.append(f"Business types: {', '.join(rcp.business_types)}")
            rcp_parts.append(
                f"Total federal award history: {rcp.total_transactions} awards, "
                f"${rcp.total_transaction_amount:,.0f}"
            )
            if rcp.location_state:
                rcp_parts.append(f"State: {rcp.location_state}")
            if rcp.location_congressional_district:
                rcp_parts.append(f"Congressional district: {rcp.location_state}-{rcp.location_congressional_district}")
            context_parts.append(
                "USAspending recipient profile:\n" + "\n".join(rcp_parts)
            )

        # Congressional district (from ZIP code resolution)
        # Try both _company_key and raw upper name since dicts may use either
        if congressional_districts:
            district = congressional_districts.get(key) or congressional_districts.get(display_name.upper())
            if district:
                context_parts.append(f"Congressional district: {district}")

        # BEA sector classification (from SAM.gov NAICS codes)
        # SAM entities may be keyed by raw upper name
        if not sam and sam_entities:
            sam = sam_entities.get(display_name.upper())
        if bea_sectors and sam:
            sector_parts = []
            for naics in (sam.naics_codes or [])[:3]:
                sector = bea_sectors.get(naics)
                if sector:
                    sector_parts.append(f"NAICS {naics} → {sector}")
            if sector_parts:
                context_parts.append(
                    "BEA economic sectors: " + "; ".join(sector_parts)
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
        return key, result

    from concurrent.futures import ThreadPoolExecutor, as_completed

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(_build_and_generate, idx, key, co_awards): key
            for idx, (key, co_awards) in enumerate(company_items, 1)
        }
        for future in as_completed(futures):
            try:
                key, result = future.result()
                if result:
                    results[key] = result
            except Exception as e:
                print(f"Company diligence error for {futures[future]}: {e}", file=sys.stderr)

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

    def _build_and_generate_pi(idx: int, key: str, pi_awards: list[dict]) -> tuple[str, str | None]:
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
            cr = company_research.get(
                _normalize_name(company, remove_suffixes=True) or company.strip().upper()
            )
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
        return key, result

    from concurrent.futures import ThreadPoolExecutor, as_completed

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(_build_and_generate_pi, idx, key, pi_awards): key
            for idx, (key, pi_awards) in enumerate(pi_items, 1)
        }
        for future in as_completed(futures):
            try:
                key, result = future.result()
                if result:
                    results[key] = result
            except Exception as e:
                print(f"PI diligence error for {futures[future]}: {e}", file=sys.stderr)

    return results


# ---------------------------------------------------------------------------
# Enrichment helpers (inflation, congressional districts, BEA sectors)
# ---------------------------------------------------------------------------


def enrich_with_inflation(awards: list[dict], base_year: int | None = None) -> dict[str, float]:
    """Compute an inflation-adjusted total using InflationAdjuster.

    Returns a dict containing:
    - 'adjusted_total': the sum of inflation-adjusted award amounts
    - 'base_year': the dollar year used for the adjustment

    Returns an empty dict if inflation support is unavailable or fails.
    """
    if not _HAS_INFLATION:
        return {}

    import pandas as pd

    try:
        adjuster = InflationAdjuster(
            config={"base_year": base_year or 2024}
        )
        df = pd.DataFrame(awards)
        # Map column names to what InflationAdjuster expects
        if "Award Amount" in df.columns:
            df["award_amount"] = (
                df["Award Amount"]
                .astype(str)
                .str.replace(",", "")
                .str.replace("$", "")
            )
            df["award_amount"] = pd.to_numeric(df["award_amount"], errors="coerce").fillna(0)
        if "Proposal Award Date" in df.columns:
            df["award_date"] = df["Proposal Award Date"]

        enriched = adjuster.adjust_awards_dataframe(df)
        adjusted_col = "fiscal_adjusted_amount"
        if adjusted_col in enriched.columns:
            adjusted_total = enriched[adjusted_col].sum()
            base = enriched.get("fiscal_base_year", pd.Series([2024])).iloc[0]
            _debug(f"Inflation adjustment: ${adjusted_total:,.0f} in {base} dollars")
            return {
                "adjusted_total": float(adjusted_total),
                "base_year": int(base),
            }
    except Exception as e:
        _debug(f"InflationAdjuster error: {e}")

    return {}


def resolve_congressional_districts(awards: list[dict]) -> dict[str, str]:
    """Resolve congressional districts for each unique company.

    Returns a dict keyed by upper-cased company name → "ST-DD" district string.
    """
    if not _HAS_CONGRESS_RESOLVER:
        return {}

    results: dict[str, str] = {}
    resolver = CongressionalDistrictResolver(method="auto")

    seen: dict[str, dict] = {}
    for a in awards:
        name = str(a.get("Company", "")).strip()
        if not name:
            continue
        key = name.upper()
        if key not in seen:
            seen[key] = {
                "zip": str(a.get("Zip", "")).strip()[:5],
                "state": str(a.get("State", "")).strip(),
                "city": str(a.get("City", "")).strip(),
                "address": str(a.get("Address1", "")).strip(),
            }

    _debug(f"Resolving congressional districts for {len(seen)} companies")
    for key, info in seen.items():
        if not info["zip"]:
            continue
        try:
            result = resolver.resolve_single_address(
                address=info["address"] or None,
                city=info["city"] or None,
                state=info["state"] or None,
                zip_code=info["zip"],
            )
            if result and result.congressional_district:
                results[key] = result.congressional_district
        except Exception:
            continue

    _debug(f"Congressional districts resolved: {len(results)}/{len(seen)}")
    return results


def map_naics_to_bea_sectors(naics_codes: list[str]) -> dict[str, str]:
    """Map NAICS codes to BEA sector names.

    Returns a dict keyed by NAICS code → BEA sector name.
    """
    if not _HAS_BEA_MAPPER:
        return {}

    try:
        mapper = NAICSToBEAMapper(
            crosswalk_path=None,  # Will use fallback YAML
            fallback_config_path="config/fiscal/naics_bea_mappings.yaml",
        )
    except Exception as e:
        _debug(f"NAICSToBEAMapper init error: {e}")
        return {}

    results: dict[str, str] = {}
    for code in naics_codes:
        try:
            mappings = mapper.map_naics_to_bea(code)
            if mappings:
                # Take the highest-weight mapping
                best = max(mappings, key=lambda m: m.allocation_weight)
                results[code] = best.bea_sector_name
        except Exception:
            continue

    _debug(f"NAICS→BEA mapped: {len(results)}/{len(naics_codes)}")
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
    inflation_data: dict[str, float] | None = None,
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
    if inflation_data and "adjusted_total" in inflation_data:
        base_yr = inflation_data.get("base_year", 2024)
        lines.append(
            f"| Inflation-Adjusted Total ({base_yr}$) | "
            f"{format_amount(str(inflation_data['adjusted_total']))} |"
        )
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
            cr = company_research.get(
                _normalize_name(company, remove_suffixes=True) or company.strip().upper()
            )

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
            co_key = _normalize_name(company, remove_suffixes=True) or company.strip().upper()
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
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable verbose debug output for API calls, LLM context, and URL construction (to stderr)",
    )
    parser.add_argument(
        "--skip-sbir-api",
        action="store_true",
        default=os.environ.get("SKIP_SBIR_API", "").lower() in ("1", "true", "yes"),
        help="Skip SBIR.gov API calls (solicitation topics + awards fallback). "
        "Useful when the API is down or rate-limiting. Also settable via SKIP_SBIR_API=1 env var.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=int(os.environ.get("REPORT_TIMEOUT", "720")),
        help="Hard pipeline timeout in seconds (default: 720 = 12 min). "
        "Skips remaining enrichment when exceeded. Also settable via REPORT_TIMEOUT env var.",
    )
    args = parser.parse_args()

    global DEBUG  # noqa: PLW0603
    if args.debug:
        DEBUG = True
        print("[DEBUG] Debug mode enabled — verbose API diagnostics will appear on stderr", file=sys.stderr)

    import time as _time

    global _pipeline_start  # noqa: PLW0603
    _pipeline_start = _time.monotonic()
    pipeline_deadline = _pipeline_start + args.timeout

    def _pipeline_expired() -> bool:
        return _time.monotonic() > pipeline_deadline

    awards, freshness_warnings, shared_source, shared_ext, shared_table = (
        fetch_weekly_awards(days=args.days)
    )
    _debug(f"Fetched {len(awards)} raw awards (freshness_warnings={freshness_warnings})")

    # Clean, validate, and deduplicate
    awards, cleaning_stats = clean_and_dedup_awards(awards)
    _debug(f"After cleaning: {len(awards)} awards | stats={cleaning_stats}")
    if DEBUG and awards:
        sample = awards[0]
        _debug(f"Sample award keys: {list(sample.keys())}")
        _debug(
            f"Sample award: Company='{sample.get('Company')}' "
            f"Contract='{sample.get('Contract')}' "
            f"Solicitation='{sample.get('Solicitation Number')}' "
            f"Topic='{sample.get('Topic Code')}'"
        )

    # Generate AI content if API key is available
    synopsis = None
    descriptions = None
    company_info: dict[str, CompanyResearch] | None = None
    co_diligence: dict[str, str] | None = None
    pi_dilig: dict[str, str] | None = None
    api_key = os.environ.get("OPENAI_API_KEY", "")

    from concurrent.futures import ThreadPoolExecutor, as_completed

    # --- Stage 1: Parallel API fetches (solicitation topics + USAspending + SAM) ---
    sol_topics = None
    usa_descs: dict[str, str] | None = None
    usa_recipients: dict[str, USARecipientProfile] | None = None
    sam_data: dict[str, SAMEntityRecord] | None = None
    if awards:
        fetch_futures: dict = {}
        with ThreadPoolExecutor(max_workers=4) as fetch_pool:
            if not args.skip_sbir_api:
                fetch_futures["sol_topics"] = fetch_pool.submit(
                    fetch_solicitation_topics, awards
                )
            else:
                print("Skipping SBIR.gov API calls (--skip-sbir-api)", file=sys.stderr)

            # Government data APIs (USAspending, SAM.gov) are independent of AI —
            # always fetch when awards exist so enrichment data (BEA sectors,
            # congressional districts, recipient profiles) is available regardless
            # of whether AI descriptions are generated.
            fetch_futures["usa_descs"] = fetch_pool.submit(
                fetch_usaspending_contract_descriptions, awards
            )
            fetch_futures["usa_recipients"] = fetch_pool.submit(
                lookup_usaspending_recipients, awards
            )
            fetch_futures["sam_data"] = fetch_pool.submit(
                lookup_sam_entities, awards
            )

            # Collect results
            for name, future in fetch_futures.items():
                try:
                    result = future.result()
                    if name == "sol_topics":
                        sol_topics = result
                    elif name == "usa_descs":
                        usa_descs = result
                    elif name == "usa_recipients":
                        usa_recipients = result
                    elif name == "sam_data":
                        sam_data = result
                except Exception as e:
                    print(f"Warning: {name} fetch failed: {e}", file=sys.stderr)

    # Local enrichments (no network I/O except congressional district Census fallback)
    inflation_data: dict[str, float] = {}
    congressional: dict[str, str] = {}
    bea_sectors: dict[str, str] = {}
    if awards:
        inflation_data = enrich_with_inflation(awards)
        # BEA sector mapping from SAM.gov NAICS codes (local YAML lookup)
        if sam_data:
            all_naics: list[str] = []
            for sam_rec in sam_data.values():
                for code in (sam_rec.naics_codes or []):
                    if code and code not in all_naics:
                        all_naics.append(code)
            bea_sectors = map_naics_to_bea_sectors(all_naics)
    # Congressional district resolution may call Census API — only when AI is enabled
    if awards and api_key and not args.no_ai:
        congressional = resolve_congressional_districts(awards)

    if api_key and not args.no_ai:
        # --- Stage 2: Company research (parallelized within) ---
        if not args.no_company_research and not _pipeline_expired():
            company_info = research_companies(api_key, awards)
        if _pipeline_expired():
            print(
                f"Pipeline timeout ({args.timeout}s) — skipping remaining AI enrichment",
                file=sys.stderr,
            )
        else:
            # --- Stage 3: Synopsis + descriptions in parallel ---
            with ThreadPoolExecutor(max_workers=2) as ai_pool:
                synopsis_future = ai_pool.submit(
                    generate_weekly_synopsis,
                    api_key, awards, args.days, company_info, sol_topics,
                    usa_descs, sam_data,
                )
                desc_future = ai_pool.submit(
                    generate_award_descriptions,
                    api_key, awards, company_info, sol_topics,
                    usa_descs, sam_data,
                )
                try:
                    synopsis = synopsis_future.result()
                except Exception as e:
                    print(f"Warning: synopsis generation failed: {e}", file=sys.stderr)
                try:
                    descriptions = desc_future.result()
                except Exception as e:
                    print(f"Warning: description generation failed: {e}", file=sys.stderr)

        if not args.no_diligence and not _pipeline_expired():
            # Reuse the source/extractor/table from fetch_weekly_awards() to
            # avoid re-downloading and re-importing the ~376 MB CSV.
            # Build history sequentially — both use the same DuckDB connection
            # which is not thread-safe for concurrent queries.
            print("Building historical context...", file=sys.stderr)
            co_history = get_company_history(
                awards, shared_source, shared_ext, shared_table
            )
            pi_history = get_pi_history(
                awards, shared_source, shared_ext, shared_table
            )

            # SAM.gov entity data was already fetched above for LLM context;
            # reuse sam_data for diligence.

            # --- Stage 5: Company federal awards (already parallelized) ---
            print("Looking up company federal awards on USAspending...", file=sys.stderr)
            co_fed: dict[str, PIFederalAwardRecord] = {}
            co_names: dict[str, dict] = {}
            for a in awards:
                name = str(a.get("Company", "")).strip()
                if not name:
                    continue
                key = _company_key(a)
                if key not in co_names:
                    co_names[key] = {
                        "name": name,
                        "uei": str(a.get("Company UEI", a.get("UEI", ""))).strip() or None,
                    }

            def _lookup_co_fed(item: tuple[str, dict]) -> tuple[str, PIFederalAwardRecord | None]:
                k, info = item
                return k, lookup_company_federal_awards(info["name"], info["uei"])

            co_fed_deadline = _stage_deadline()
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {
                    executor.submit(_lookup_co_fed, item): item
                    for item in co_names.items()
                }
                for future in as_completed(futures):
                    if _past_deadline(co_fed_deadline):
                        print(
                            f"USAspending stage timeout ({STAGE_TIMEOUT}s) — "
                            f"completed {len(co_fed)}/{len(co_names)}, skipping remainder",
                            file=sys.stderr,
                        )
                        executor.shutdown(wait=False, cancel_futures=True)
                        break
                    try:
                        key, result = future.result(timeout=10)
                        if result:
                            co_fed[key] = result
                    except Exception:
                        pass
            print(
                f"Found federal awards for {len(co_fed)}/{len(co_names)} companies",
                file=sys.stderr,
            )

            # Fetch external PI data (patents, publications, ORCID).
            # Reuse co_fed to avoid duplicate USAspending calls per company.
            pi_ext: dict[str, dict] = {}
            if not _pipeline_expired():
                print("Looking up PI patents, publications, and ORCID...", file=sys.stderr)
                pi_ext = lookup_pi_external_data(awards, co_fed)

            # --- Stage 6: Company + PI diligence in parallel ---
            if not _pipeline_expired():
                with ThreadPoolExecutor(max_workers=2) as dilig_pool:
                    co_dilig_future = dilig_pool.submit(
                        generate_company_diligence,
                        api_key, awards, company_info, co_history, sam_data, co_fed,
                        usa_recipients, congressional, bea_sectors,
                    )
                    pi_dilig_future = dilig_pool.submit(
                        generate_pi_diligence,
                        api_key, awards, pi_history, company_info, pi_ext,
                    )
                    try:
                        co_diligence = co_dilig_future.result()
                    except Exception as e:
                        print(f"Warning: company diligence failed: {e}", file=sys.stderr)
                    try:
                        pi_dilig = pi_dilig_future.result()
                    except Exception as e:
                        print(f"Warning: PI diligence failed: {e}", file=sys.stderr)

            if _pipeline_expired():
                elapsed = int(_time.monotonic() - _pipeline_start)
                print(
                    f"Pipeline timeout ({args.timeout}s) at {elapsed}s — "
                    f"generating report with partial enrichment",
                    file=sys.stderr,
                )
    elif not api_key and not args.no_ai:
        print(
            "OPENAI_API_KEY not set - skipping AI summaries. "
            "Set the env var or use --no-ai to silence this message.",
            file=sys.stderr,
        )

    # Print debug summary of all data collection results before report generation
    if DEBUG:
        print("\n" + "=" * 72, file=sys.stderr)
        print("[DEBUG] === API Data Collection Summary ===", file=sys.stderr)
        print(f"[DEBUG] Awards loaded: {len(awards)}", file=sys.stderr)
        print(f"[DEBUG] Freshness warnings: {len(freshness_warnings) if freshness_warnings else 0}", file=sys.stderr)
        print(
            f"[DEBUG] Solicitation topics fetched: "
            f"{len(sol_topics) if sol_topics else 0}",
            file=sys.stderr,
        )
        print(
            f"[DEBUG] Company research results: "
            f"{len(company_info) if company_info else 0}",
            file=sys.stderr,
        )
        print(
            f"[DEBUG] USAspending contract descriptions: "
            f"{len(usa_descs) if usa_descs else 0}",
            file=sys.stderr,
        )
        print(
            f"[DEBUG] SAM.gov entity records: "
            f"{len(sam_data) if sam_data else 0}",
            file=sys.stderr,
        )
        print(
            f"[DEBUG] USAspending recipient profiles: "
            f"{len(usa_recipients) if usa_recipients else 0}",
            file=sys.stderr,
        )
        print(f"[DEBUG] Synopsis generated: {'yes' if synopsis else 'no'}", file=sys.stderr)
        print(
            f"[DEBUG] Award descriptions generated: "
            f"{len(descriptions) if descriptions else 0}",
            file=sys.stderr,
        )
        print(
            f"[DEBUG] Company diligence paragraphs: "
            f"{len(co_diligence) if co_diligence else 0}",
            file=sys.stderr,
        )
        print(
            f"[DEBUG] PI diligence paragraphs: "
            f"{len(pi_dilig) if pi_dilig else 0}",
            file=sys.stderr,
        )
        # Show which awards have all reference link components
        missing_contracts = sum(1 for a in awards if not str(a.get("Contract", "")).strip())
        missing_sol = sum(
            1 for a in awards
            if not str(a.get("Solicitation Number", "")).strip()
            and not str(a.get("Topic Code", "")).strip()
        )
        print(f"[DEBUG] Awards missing Contract (no USAspending link): {missing_contracts}/{len(awards)}", file=sys.stderr)
        print(f"[DEBUG] Awards missing Solicitation+Topic (no solicitation link): {missing_sol}/{len(awards)}", file=sys.stderr)
        # Verify reference links with HTTP HEAD requests
        if awards:
            link_checks = verify_reference_links(awards, company_info)
            _print_link_verification_report(link_checks)
        print("=" * 72 + "\n", file=sys.stderr)

    report = generate_markdown(
        awards,
        days=args.days,
        synopsis=synopsis,
        descriptions=descriptions,
        company_research=company_info,
        freshness_warnings=freshness_warnings,
        company_diligence=co_diligence,
        pi_diligence=pi_dilig,
        inflation_data=inflation_data,
    )

    if args.output:
        with open(args.output, "w") as f:
            f.write(report)
        print(f"Report written to {args.output} ({len(awards)} awards)", file=sys.stderr)
    else:
        print(report)


if __name__ == "__main__":
    main()
