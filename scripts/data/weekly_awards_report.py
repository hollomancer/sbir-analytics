#!/usr/bin/env python3
"""Generate a weekly SBIR awards report in markdown.

Downloads the SBIR bulk CSV from SBIR.gov and filters for awards
whose Proposal Award Date falls within the past 7 days, then outputs a
markdown summary with links to SBIR.gov, solicitations, and USAspending.

Usage:
    python scripts/data/weekly_awards_report.py
    python scripts/data/weekly_awards_report.py --days 14 --output report.md
"""

import argparse
import csv
import io
import sys
from datetime import datetime, timedelta, UTC
from urllib.parse import quote

import requests

SBIR_AWARDS_URL = "https://data.www.sbir.gov/mod_awarddatapublic/award_data.csv"

# URL templates for external links
SBIR_AWARD_SEARCH_URL = "https://www.sbir.gov/sbirsearch/award/all"
SBIR_SOLICITATION_URL = "https://www.sbir.gov/sbirsearch/topic/default"
USASPENDING_SEARCH_URL = "https://www.usaspending.gov/search"


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
    """Build a link to the SBIR.gov award search page for this award.

    Uses the contract number as a keyword search on SBIR.gov's award listing.
    """
    contract = award.get("Contract", "").strip()
    if contract:
        return f"{SBIR_AWARD_SEARCH_URL}/{quote(contract)}"
    # Fall back to company name search
    company = award.get("Company", "").strip()
    if company:
        return f"{SBIR_AWARD_SEARCH_URL}/{quote(company)}"
    return SBIR_AWARD_SEARCH_URL


def build_solicitation_url(award: dict) -> str | None:
    """Build a link to the SBIR.gov solicitation/topic page.

    Links to the SBIR.gov topic search using the solicitation number.
    Returns None if no solicitation info is available.
    """
    solicitation = award.get("Solicitation Number", "").strip()
    topic_code = award.get("Topic Code", "").strip()

    if solicitation:
        return f"{SBIR_SOLICITATION_URL}?keyword={quote(solicitation)}"
    if topic_code:
        return f"{SBIR_SOLICITATION_URL}?keyword={quote(topic_code)}"
    return None


def build_usaspending_url(award: dict) -> str | None:
    """Build a link to USAspending.gov search for this award's contract.

    Returns None if no contract number is available.
    """
    contract = award.get("Contract", "").strip()
    if not contract:
        return None
    search_term = quote(contract)
    return f'{USASPENDING_SEARCH_URL}?form_fields={{"search_term":"{search_term}"}}'


def generate_markdown(awards: list[dict], days: int) -> str:
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

    # Summary statistics
    total_amount = 0
    agencies: dict[str, int] = {}
    programs: dict[str, int] = {}
    phases: dict[str, int] = {}
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
        phase = a.get("Phase", "Unknown")
        phases[phase] = phases.get(phase, 0) + 1
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

    # Awards list with links
    lines.append("## Awards")
    lines.append("")

    for i, a in enumerate(awards, 1):
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

        # Award header with title linked to SBIR.gov
        lines.append(f"### {i}. [{title}]({sbir_url})")
        lines.append("")

        # Details table
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

        # Links
        link_parts = [f"[SBIR.gov Award]({sbir_url})"]
        if solicitation_url:
            link_parts.append(f"[Solicitation]({solicitation_url})")
        if usaspending_url:
            link_parts.append(f"[USAspending]({usaspending_url})")

        lines.append("")
        lines.append(" | ".join(link_parts))
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
    args = parser.parse_args()

    awards = fetch_weekly_awards(days=args.days)
    report = generate_markdown(awards, days=args.days)

    if args.output:
        with open(args.output, "w") as f:
            f.write(report)
        print(f"Report written to {args.output} ({len(awards)} awards)", file=sys.stderr)
    else:
        print(report)


if __name__ == "__main__":
    main()
