"""Generate the weekly SBIR awards report on this host.

The retired ``weekly.yml`` workflow ran ``scripts/data/weekly_awards_report.py``
every Monday at 12:00 UTC, posted the markdown to the job summary and kept it as
a 30-day artifact. Artifacts expire, so the weekly series was never durable.
This runs the same script and writes each report to a dated directory under the
data root instead, matching what ``phase_transition_archive`` does for the
monthly analysis.
"""

import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from dagster import OpExecutionContext, job, op

DATA_ROOT_ENV = "SBIR_ETL__PATHS__DATA_ROOT"
DEFAULT_DATA_ROOT = "data"

# The workflow's `days` input, which defaulted to 7 and was only ever overridden
# for a manual backfill.
LOOKBACK_DAYS_ENV = "SBIR_ETL__REPORTS__WEEKLY_AWARDS_DAYS"
DEFAULT_LOOKBACK_DAYS = "7"


def _data_root() -> Path:
    return Path(os.getenv(DATA_ROOT_ENV, DEFAULT_DATA_ROOT))


@op
def generate_weekly_awards_report_op(context: OpExecutionContext) -> dict:
    """Run the report script and store its markdown under a dated directory."""
    days = os.getenv(LOOKBACK_DAYS_ENV, DEFAULT_LOOKBACK_DAYS)
    report_date = datetime.now(UTC).strftime("%Y-%m-%d")
    output_dir = _data_root() / "reports" / "weekly_awards" / report_date
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "weekly-awards.md"

    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "scripts/data/weekly_awards_report.py",
            "--days",
            days,
            "--output",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        context.log.error(result.stderr[-4000:])
        raise RuntimeError(f"weekly_awards_report.py failed with exit code {result.returncode}")

    # The script exits 0 even when it writes nothing useful, so require output
    # rather than trusting the exit code — an empty report is a silent failure
    # of exactly the kind that let the retired workflow rot unnoticed.
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise FileNotFoundError(f"Report script wrote no report to {output_path}")

    size = output_path.stat().st_size
    context.log.info(f"Wrote {size} bytes to {output_path}")
    context.add_output_metadata({"report_path": str(output_path), "bytes": size, "days": days})
    return {"report_path": str(output_path), "bytes": size}


@job(
    name="weekly_awards_report_job",
    description="Generate the weekly SBIR awards report to a dated directory",
)
def weekly_awards_report_job():
    generate_weekly_awards_report_op()


__all__ = ["weekly_awards_report_job"]
