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

import requests

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

# Batch size for per-award descriptions (awards per API call)
DESCRIPTION_BATCH_SIZE = 10


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
    response = requests.get(SBIR_AWARDS_URL, timeout=600)
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
# Formatting helpers
# ---------------------------------------------------------------------------


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


def _openai_chat(api_key: str, system: str, user: str) -> str | None:
    """Call the OpenAI chat completions API. Returns the assistant message text."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": OPENAI_MODEL,
        "temperature": 0.3,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    try:
        resp = requests.post(
            OPENAI_CHAT_URL, headers=headers, json=payload, timeout=120
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"OpenAI Chat API error: {e}", file=sys.stderr)
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
    try:
        resp = requests.post(
            OPENAI_RESPONSES_URL, headers=headers, json=payload, timeout=60
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"OpenAI Responses API error for web search: {e}", file=sys.stderr)
        return None

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
    total = len(companies)

    for idx, (key, info) in enumerate(companies.items(), 1):
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


def _award_digest(award: dict, company_research: CompanyResearch | None = None) -> str:
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
        digests.append(f"[{i+1}] {_award_digest(a, cr)}")
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
) -> dict[int, str]:
    """Generate a brief description for each award using batched API calls."""
    descriptions: dict[int, str] = {}
    if not awards:
        return descriptions

    system = (
        "You summarize SBIR/STTR awards in plain language. "
        "For each award, write 2-3 sentences explaining what the project does "
        "and why it matters. Use the abstract, solicitation context, "
        "associated federal spending data, and company background research "
        "to inform your description. Reference relevant company context "
        "(e.g. their expertise, previous work, or market position) when it "
        "adds value. Be specific about the technology and its intended "
        "application. Avoid generic filler.\n\n"
        "Respond with a JSON object mapping the award number (as a string key) "
        'to its description string. Example: {"1": "Description.", "2": "Description."}'
    )

    for batch_start in range(0, len(awards), DESCRIPTION_BATCH_SIZE):
        batch = awards[batch_start : batch_start + DESCRIPTION_BATCH_SIZE]
        digests = []
        for i, a in enumerate(batch):
            idx = batch_start + i + 1
            cr = None
            if company_research:
                cr = company_research.get(str(a.get("Company", "")).strip().upper())
            digests.append(f"[{idx}] {_award_digest(a, cr)}")

        user = (
            "Generate a brief plain-language description for each award below. "
            "Each description should convey the technology, its application, "
            "the significance of the federal investment, and relevant company "
            "context. Respond ONLY with a JSON object.\n\n" + "\n\n".join(digests)
        )

        batch_label = f"{batch_start + 1}-{batch_start + len(batch)}"
        print(
            f"Generating descriptions for awards {batch_label} of {len(awards)}...",
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
# Markdown generation
# ---------------------------------------------------------------------------


def generate_markdown(
    awards: list[dict],
    days: int,
    synopsis: str | None = None,
    descriptions: dict[int, str] | None = None,
    company_research: dict[str, CompanyResearch] | None = None,
    freshness_warnings: list[str] | None = None,
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
        lines.append(f"| {agency} | {count} |")
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
        lines.append(f"| {program} | {phase} | {count} |")
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
            cr = company_research.get(company.upper())

        # Award header
        lines.append(f"### {i + 1}. {title}")
        lines.append("")
        lines.append(f"**{company}** | {agency} {program} {phase} | {amount} | {state} | {date}")
        lines.append("")

        # AI-generated description
        if descriptions and i in descriptions:
            lines.append(descriptions[i])
            lines.append("")

        # Details table
        lines.append("<details>")
        lines.append("<summary>Award details</summary>")
        lines.append("")
        lines.append("| Field | Value |")
        lines.append("|-------|-------|")
        lines.append(f"| **Company** | {company} |")
        lines.append(f"| **Award Date** | {date} |")
        lines.append(f"| **Amount** | {amount} |")
        lines.append(f"| **Agency** | {agency} |")
        lines.append(f"| **Program** | {program} |")
        lines.append(f"| **Phase** | {phase} |")
        if state:
            lines.append(f"| **State** | {state} |")
        if contract:
            lines.append(f"| **Contract** | `{contract}` |")
        if pi_name:
            lines.append(f"| **PI** | {pi_name} |")
        if solicitation:
            lines.append(f"| **Solicitation** | `{solicitation}` |")
        if topic_code:
            lines.append(f"| **Topic Code** | `{topic_code}` |")
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
    args = parser.parse_args()

    awards, freshness_warnings = fetch_weekly_awards(days=args.days)

    # Generate AI content if API key is available
    synopsis = None
    descriptions = None
    company_info: dict[str, CompanyResearch] | None = None
    api_key = os.environ.get("OPENAI_API_KEY", "")

    if api_key and not args.no_ai:
        company_info = research_companies(api_key, awards)
        synopsis = generate_weekly_synopsis(api_key, awards, args.days, company_info)
        descriptions = generate_award_descriptions(api_key, awards, company_info)
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
    )

    if args.output:
        with open(args.output, "w") as f:
            f.write(report)
        print(f"Report written to {args.output} ({len(awards)} awards)", file=sys.stderr)
    else:
        print(report)


if __name__ == "__main__":
    main()
