"""Archive phase-transition analysis outputs to a dated directory.

The retired ``monthly-analysis.yml`` workflow published these files to
``s3://<bucket>/processed/phase_transition/<date>/`` after each run, giving the
analysis a dated history. GitHub artifacts expire, so without a replacement
that series would be lost. This regenerates the report the workflow produced,
then writes the same file set under the data root.
"""

import os
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path

from dagster import OpExecutionContext, job, op

from sbir_etl.reporting.phase_transition_analysis import generate_phase_transition_report

DATA_ROOT_ENV = "SBIR_ETL__PATHS__DATA_ROOT"
DEFAULT_DATA_ROOT = "data"
EPISTEMIC_TIER = "exploratory"

# Same file set the S3 publish step carried, relative to the repo root.
ARCHIVED_OUTPUTS = (
    "data/processed/phase_ii_awards.parquet",
    "data/processed/phase_ii_awards.checks.json",
    "data/processed/phase_iii_contracts.parquet",
    "data/processed/phase_iii_contracts.checks.json",
    "data/processed/phase_ii_iii_pairs.parquet",
    "data/processed/phase_ii_iii_pairs.checks.json",
    "data/processed/phase_transition_survival.parquet",
    "data/processed/phase_transition_survival.checks.json",
    "reports/phase_transition/phase_transition_report.json",
)


def _data_root() -> Path:
    return Path(os.getenv(DATA_ROOT_ENV, DEFAULT_DATA_ROOT))


@op
def generate_phase_transition_report_op(context: OpExecutionContext) -> float:
    """Produce the phase-transition report the retired workflow generated.

    `monthly_phase_transition` materializes the latency assets but does not
    write reports/phase_transition/phase_transition_report.json; without this
    step the archive would capture whatever stale report happened to be on
    disk. Returns the start time so the archive can require every file to be
    newer than it.
    """
    started = time.time()
    generate_phase_transition_report(
        Path("data/processed/phase_ii_awards.parquet"),
        Path("data/processed/phase_iii_contracts.parquet"),
        Path("data/processed/phase_ii_iii_pairs.parquet"),
        Path("data/processed/phase_transition_survival.parquet"),
        Path("reports/phase_transition"),
    )
    context.log.info("Generated exploratory, non-citable phase-transition report")
    context.add_output_metadata({"epistemic_tier": EPISTEMIC_TIER, "citable": False})
    return started


@op
def archive_phase_transition_outputs_op(context: OpExecutionContext, started: float) -> dict:
    """Copy the current analysis outputs into a dated archive directory.

    Copies rather than moves: the canonical paths stay where downstream
    consumers expect them, and the archive is an additional dated snapshot.

    Every expected output must exist and have been written by this run. A
    missing or stale file fails the op rather than producing an archive that
    silently mixes fresh parquet with an old report.
    """
    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    archive_dir = _data_root() / "processed" / "phase_transition" / "history" / date_str
    archive_dir.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    missing: list[str] = []
    stale: list[str] = []
    # Filesystem timestamps can round down relative to time.time(); allow a
    # small tolerance so a genuinely fresh file is never judged stale.
    cutoff = started - 2.0

    for rel in ARCHIVED_OUTPUTS:
        src = Path(rel)
        if not src.is_file():
            missing.append(rel)
            continue
        if src.stat().st_mtime < cutoff:
            stale.append(rel)
            continue
        shutil.copy2(src, archive_dir / src.name)
        copied.append(src.name)

    if missing or stale:
        raise FileNotFoundError(
            "Refusing to archive an incomplete or stale phase-transition snapshot. "
            f"Missing: {', '.join(missing) or 'none'}. "
            f"Not written by this run: {', '.join(stale) or 'none'}."
        )

    context.log.info(f"Archived {len(copied)} file(s) to {archive_dir}")
    context.add_output_metadata(
        {
            "archive_dir": str(archive_dir),
            "copied": len(copied),
            "epistemic_tier": EPISTEMIC_TIER,
            "citable": False,
        }
    )
    return {
        "archive_dir": str(archive_dir),
        "copied": copied,
        "epistemic_tier": EPISTEMIC_TIER,
        "citable": False,
    }


@job(
    name="phase_transition_archive_job",
    description="Archive phase-transition analysis outputs to a dated directory",
)
def phase_transition_archive_job():
    archive_phase_transition_outputs_op(generate_phase_transition_report_op())


__all__ = ["phase_transition_archive_job"]
