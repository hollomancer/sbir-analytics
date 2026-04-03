#!/usr/bin/env python3
"""Generate a weekly SBIR awards report in markdown.

Downloads the SBIR bulk CSV from SBIR.gov and filters for awards
whose Award Date falls within the past 7 days, then outputs a
markdown summary.

Usage:
    python scripts/data/weekly_awards_report.py
    python scripts/data/weekly_awards_report.py --days 14 --output report.md
"""

import argparse
import csv
import io
import sys
from datetime import datetime, timedelta, UTC

import requests

SBIR_AWARDS_URL = "https://data.www.sbir.gov/mod_awarddatapublic/award_data.csv"


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
        award_date = parse_award_date(row.get("Award Date", ""))
        if award_date and award_date >= cutoff:
            awards.append(row)

    # Sort by date descending, then by amount descending
    def sort_key(a):
        dt = parse_award_date(a.get("Award Date", "")) or datetime.min
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


def generate_markdown(awards: list[dict], days: int) -> str:
    """Generate markdown report from filtered awards."""
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=days)

    lines = []
    lines.append(f"# SBIR Weekly Awards Report")
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
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
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

    # Awards table
    lines.append("## Awards")
    lines.append("")
    lines.append("| Date | Company | Award Title | Agency | Program | Phase | Amount | State |")
    lines.append("|------|---------|-------------|--------|---------|-------|--------|-------|")

    for a in awards:
        date = a.get("Award Date", "")
        company = a.get("Company", "")
        title = a.get("Award Title", "")
        # Truncate long titles for table readability
        if len(title) > 80:
            title = title[:77] + "..."
        agency = a.get("Agency", "")
        program = a.get("Program", "")
        phase = a.get("Phase", "")
        amount = format_amount(a.get("Award Amount", ""))
        state = a.get("State", "")
        lines.append(
            f"| {date} | {company} | {title} | {agency} | {program} | {phase} | {amount} | {state} |"
        )

    lines.append("")
    lines.append(
        f"---\n*Generated on {now.strftime('%Y-%m-%d %H:%M UTC')} from [SBIR.gov](https://www.sbir.gov) bulk data.*"
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
