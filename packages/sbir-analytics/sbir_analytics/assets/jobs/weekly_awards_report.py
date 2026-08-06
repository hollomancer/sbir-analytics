"""Generate the weekly SBIR awards report on this host.

The retired ``weekly.yml`` workflow ran ``scripts/data/weekly_awards_report.py``
every Monday at 12:00 UTC, posted the markdown to the job summary and kept it as
a 30-day artifact. Artifacts expire, so the weekly series was never durable.
This calls the existing package API and writes each report to a dated directory
under the data root, matching what ``phase_transition_archive`` does for the
monthly analysis. The report is exploratory and rendered with a non-citable
notice.
"""

import os
from datetime import UTC, datetime
from pathlib import Path

from dagster import OpExecutionContext, job, op

from sbir_etl.reporting.weekly.orchestrator import WeeklyAwardsReportBuilder

DATA_ROOT_ENV = "SBIR_ETL__PATHS__DATA_ROOT"
DEFAULT_DATA_ROOT = "data"
EPISTEMIC_TIER = "exploratory"

# The workflow's `days` input, which defaulted to 7 and was only ever overridden
# for a manual backfill.
LOOKBACK_DAYS_ENV = "SBIR_ETL__REPORTS__WEEKLY_AWARDS_DAYS"
DEFAULT_LOOKBACK_DAYS = "7"


def _data_root() -> Path:
    return Path(os.getenv(DATA_ROOT_ENV, DEFAULT_DATA_ROOT))


@op
def generate_weekly_awards_report_op(context: OpExecutionContext) -> dict:
    """Build the report through its package API and store dated markdown."""
    days = int(os.getenv(LOOKBACK_DAYS_ENV, DEFAULT_LOOKBACK_DAYS))
    report_date = datetime.now(UTC).strftime("%Y-%m-%d")
    output_dir = _data_root() / "reports" / "weekly_awards" / report_date
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "weekly-awards.md"

    report = WeeklyAwardsReportBuilder(
        days=days,
        skip_sbir_api=os.getenv("SKIP_SBIR_API", "").lower() in {"1", "true", "yes"},
        timeout=int(os.getenv("REPORT_TIMEOUT", "720")),
        api_key=os.getenv("OPENAI_API_KEY", ""),
    ).run()
    output_path.write_text(report)
    # Require output because an empty report is a silent failure of exactly the
    # kind that let the retired workflow rot unnoticed.
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise FileNotFoundError(f"Report script wrote no report to {output_path}")

    size = output_path.stat().st_size
    context.log.info(f"Wrote {size} bytes to {output_path}")
    context.add_output_metadata(
        {
            "report_path": str(output_path),
            "bytes": size,
            "days": days,
            "epistemic_tier": EPISTEMIC_TIER,
            "citable": False,
        }
    )
    return {
        "report_path": str(output_path),
        "bytes": size,
        "epistemic_tier": EPISTEMIC_TIER,
        "citable": False,
    }


@job(
    name="weekly_awards_report_job",
    description="Generate the weekly SBIR awards report to a dated directory",
)
def weekly_awards_report_job():
    generate_weekly_awards_report_op()


__all__ = ["weekly_awards_report_job"]
