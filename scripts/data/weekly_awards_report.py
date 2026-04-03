#!/usr/bin/env python3
"""Generate a weekly SBIR awards report in markdown.

Downloads the SBIR bulk CSV from SBIR.gov and filters for awards
whose Proposal Award Date falls within the past 7 days, then outputs a
markdown summary with links to SBIR.gov, solicitations, and USAspending.

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
import csv
import io
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, UTC
from urllib.parse import quote

import requests

SBIR_AWARDS_URL = "https://data.www.sbir.gov/mod_awarddatapublic/award_data.csv"

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
# Parsing and URL helpers
# ---------------------------------------------------------------------------


def parse_award_date(date_str: str) -> datetime | None:
    """Parse award date from CSV, trying common formats."""
    if not date_str or not date_str.strip():
        return None
    date_str = date_str.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S", "%m/%d/%y"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


def fetch_weekly_awards(days: int = 7) -> list[dict]:
    """Download SBIR CSV and filter for awards in the past N days."""
    print(f"Downloading SBIR awards from {SBIR_AWARDS_URL}...", file=sys.stderr)

    response = requests.get(SBIR_AWARDS_URL, timeout=600)
    response.raise_for_status()

    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)

    reader = csv.DictReader(io.StringIO(response.text))
    awards = []
    for row in reader:
        award_date = parse_award_date(row.get("Proposal Award Date", ""))
        if award_date and award_date >= cutoff:
            awards.append(row)

    # Sort by date descending, then by amount descending
    def sort_key(a):
        dt = parse_award_date(a.get("Proposal Award Date", "")) or datetime.min
        try:
            amount = float(a.get("Award Amount", "0").replace(",", "").replace("$", ""))
        except (ValueError, AttributeError):
            amount = 0
        return (-dt.timestamp(), -amount)

    awards.sort(key=sort_key)
    return awards


def format_amount(amount_str: str) -> str:
    """Format dollar amount for display."""
    try:
        amount = float(amount_str.replace(",", "").replace("$", ""))
        if amount >= 1_000_000:
            return f"${amount / 1_000_000:.2f}M"
        if amount >= 1_000:
            return f"${amount / 1_000:.0f}K"
        return f"${amount:,.0f}"
    except (ValueError, AttributeError):
        return amount_str or "N/A"


def build_sbir_award_url(award: dict) -> str:
    """Build a link to the SBIR.gov award search page for this award."""
    contract = award.get("Contract", "").strip()
    if contract:
        return f"{SBIR_AWARD_SEARCH_URL}/{quote(contract)}"
    company = award.get("Company", "").strip()
    if company:
        return f"{SBIR_AWARD_SEARCH_URL}/{quote(company)}"
    return SBIR_AWARD_SEARCH_URL


def build_solicitation_url(award: dict) -> str | None:
    """Build a link to the SBIR.gov solicitation/topic page."""
    solicitation = award.get("Solicitation Number", "").strip()
    topic_code = award.get("Topic Code", "").strip()
    if solicitation:
        return f"{SBIR_SOLICITATION_URL}?keyword={quote(solicitation)}"
    if topic_code:
        return f"{SBIR_SOLICITATION_URL}?keyword={quote(topic_code)}"
    return None


def build_usaspending_url(award: dict) -> str | None:
    """Build a link to USAspending.gov search for this award's contract."""
    contract = award.get("Contract", "").strip()
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
    """Use the OpenAI Responses API with web_search_preview to research a company.

    Returns a CompanyResearch with a text summary and source URLs extracted
    from the response annotations.
    """
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

    # Extract text and source URLs from the response
    summary_text = ""
    source_urls: list[str] = []

    for output_item in data.get("output", []):
        if output_item.get("type") == "message":
            for content_block in output_item.get("content", []):
                if content_block.get("type") == "output_text":
                    summary_text = content_block.get("text", "")
                    # Extract URLs from annotations
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
    """Research each unique awardee company via web search.

    Returns a dict mapping normalized company name to CompanyResearch.
    Results are cached per company so duplicates aren't searched twice.
    """
    # Collect unique companies with their state and website for better search
    companies: dict[str, dict] = {}
    for a in awards:
        name = a.get("Company", "").strip()
        if not name:
            continue
        key = name.upper()
        if key not in companies:
            companies[key] = {
                "name": name,
                "state": a.get("State", ""),
                "website": a.get("Company Website", ""),
            }

    results: dict[str, CompanyResearch] = {}
    total = len(companies)

    for idx, (key, info) in enumerate(companies.items(), 1):
        name = info["name"]
        state = info["state"]
        website = info["website"]

        # Build a targeted search query
        query_parts = [f'"{name}"']
        if state:
            query_parts.append(state)
        query_parts.append("SBIR company")
        if website:
            query_parts.append(f"site:{website}")

        query = (
            f"Find public information about {name}"
            + (f" based in {state}" if state else "")
            + ". They are an SBIR/STTR federal award recipient."
            + (f" Their website is {website}." if website else "")
            + " What does this company do? How large are they? "
            + "What is their technology focus? Any notable contracts or previous SBIR awards?"
        )

        print(
            f"Researching company {idx}/{total}: {name}...",
            file=sys.stderr,
        )
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
    abstract = award.get("Abstract", "").strip()
    if abstract:
        if len(abstract) > 1500:
            abstract = abstract[:1500] + "..."
        parts.append(f"Abstract: {abstract}")
    topic_code = award.get("Topic Code", "").strip()
    if topic_code:
        parts.append(f"Topic Code: {topic_code}")
    solicitation = award.get("Solicitation Number", "").strip()
    if solicitation:
        parts.append(f"Solicitation: {solicitation}")
    solicitation_year = award.get("Solicitation Year", "").strip()
    if solicitation_year:
        parts.append(f"Solicitation Year: {solicitation_year}")
    contract = award.get("Contract", "").strip()
    if contract:
        parts.append(f"Contract: {contract}")
        parts.append(
            f"USAspending Record: https://www.usaspending.gov/search"
            f'?form_fields={{"search_term":"{contract}"}}'
        )
    solicitation_url = build_solicitation_url(award)
    if solicitation_url:
        parts.append(f"Solicitation Reference: {solicitation_url}")

    # Include company research if available
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
                a.get("Award Amount", "0").replace(",", "").replace("$", "")
            )
        except (ValueError, AttributeError):
            pass
        ag = a.get("Agency", "Unknown")
        agencies[ag] = agencies.get(ag, 0) + 1

    # Include up to 50 award digests for context
    digests = []
    for i, a in enumerate(awards[:50]):
        cr = None
        if company_research:
            cr = company_research.get(a.get("Company", "").strip().upper())
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
    """Generate a brief description for each award using batched API calls.

    The LLM receives each award's abstract, solicitation context,
    USAspending reference, and company web research so the description
    is informed by the full award context.

    Returns a dict mapping award index (0-based) to description text.
    """
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
                cr = company_research.get(a.get("Company", "").strip().upper())
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

        # Strip markdown code fences if present
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()

        try:
            batch_descriptions = json.loads(text)
            for key, desc in batch_descriptions.items():
                descriptions[int(key) - 1] = desc  # convert to 0-based
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
                a.get("Award Amount", "0").replace(",", "").replace("$", "")
            )
        except (ValueError, AttributeError):
            pass
        agency = a.get("Agency", "Unknown")
        agencies[agency] = agencies.get(agency, 0) + 1
        program = a.get("Program", "Unknown")
        programs[program] = programs.get(program, 0) + 1
        state = a.get("State", "Unknown")
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
        key = (a.get("Program", "Unknown"), a.get("Phase", "Unknown"))
        program_phase[key] = program_phase.get(key, 0) + 1
    for (program, phase), count in sorted(program_phase.items(), key=lambda x: -x[1]):
        lines.append(f"| {program} | {phase} | {count} |")
    lines.append("")

    # Individual awards
    lines.append("## Awards")
    lines.append("")

    for i, a in enumerate(awards):
        date = a.get("Proposal Award Date", "")
        company = a.get("Company", "")
        title = a.get("Award Title", "")
        agency = a.get("Agency", "")
        program = a.get("Program", "")
        phase = a.get("Phase", "")
        amount = format_amount(a.get("Award Amount", ""))
        state = a.get("State", "")
        contract = a.get("Contract", "").strip()
        solicitation = a.get("Solicitation Number", "").strip()
        topic_code = a.get("Topic Code", "").strip()
        pi_name = a.get("PI Name", "").strip()

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

        # Reference links — award, solicitation, USAspending, and company sources
        link_parts = [f"[SBIR.gov Award]({sbir_url})"]
        if solicitation_url:
            link_parts.append(f"[Solicitation]({solicitation_url})")
        if usaspending_url:
            link_parts.append(f"[USAspending]({usaspending_url})")
        if cr and cr.source_urls:
            for url in cr.source_urls[:3]:
                # Derive a short label from the domain
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

    awards = fetch_weekly_awards(days=args.days)

    # Generate AI content if API key is available
    synopsis = None
    descriptions = None
    company_info: dict[str, CompanyResearch] | None = None
    api_key = os.environ.get("OPENAI_API_KEY", "")

    if api_key and not args.no_ai:
        # Step 1: Research companies via web search
        company_info = research_companies(api_key, awards)

        # Step 2: Generate synopsis (with company context)
        synopsis = generate_weekly_synopsis(api_key, awards, args.days, company_info)

        # Step 3: Generate per-award descriptions (with company context)
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
    )

    if args.output:
        with open(args.output, "w") as f:
            f.write(report)
        print(f"Report written to {args.output} ({len(awards)} awards)", file=sys.stderr)
    else:
        print(report)


if __name__ == "__main__":
    main()
