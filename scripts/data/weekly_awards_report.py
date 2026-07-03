#!/usr/bin/env python3
"""Generate a weekly SBIR awards report in markdown.

Thin CLI over :mod:`sbir_etl.reporting.weekly` (see
specs/archive & specs/weekly-awards-report-refactor for the extraction
history). Downloads the SBIR bulk CSV (from S3 if available, else direct
from SBIR.gov), filters for awards whose Proposal Award Date falls within
the past N days, and renders a markdown summary with links to SBIR.gov,
solicitations, and USAspending.

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
import os
import sys

from sbir_etl.reporting.weekly.debug import set_debug
from sbir_etl.reporting.weekly.orchestrator import WeeklyAwardsReportBuilder


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
        help="Enable verbose debug output for API calls, LLM context, and "
        "URL construction (to stderr)",
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

    if args.debug:
        set_debug(True)
        print(
            "[DEBUG] Debug mode enabled — verbose API diagnostics will appear on stderr",
            file=sys.stderr,
        )

    builder = WeeklyAwardsReportBuilder(
        days=args.days,
        no_ai=args.no_ai,
        no_company_research=args.no_company_research,
        no_diligence=args.no_diligence,
        skip_sbir_api=args.skip_sbir_api,
        timeout=args.timeout,
        api_key=os.environ.get("OPENAI_API_KEY", ""),
    )
    report = builder.run()

    if args.output:
        with open(args.output, "w") as f:
            f.write(report)
        # Award count lives in the report header; reparsing it here isn't worth
        # it — point at the file instead.
        print(f"Report written to {args.output}", file=sys.stderr)
    else:
        print(report)


if __name__ == "__main__":
    main()
