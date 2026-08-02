"""Archive phase-transition analysis outputs to a dated directory.

The retired ``monthly-analysis.yml`` workflow published these files to
``s3://<bucket>/processed/phase_transition/<date>/`` after each run, giving the
analysis a dated history. GitHub artifacts expire, so without a replacement
that series would be lost. This writes the same set under the data root.
"""

import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

from dagster import OpExecutionContext, job, op

DATA_ROOT_ENV = "SBIR_ETL__PATHS__DATA_ROOT"
DEFAULT_DATA_ROOT = "data"

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
def archive_phase_transition_outputs_op(context: OpExecutionContext) -> dict:
    """Copy the current analysis outputs into a dated archive directory.

    Copies rather than moves: the canonical paths stay where downstream
    consumers expect them, and the archive is an additional dated snapshot.
    """
    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    archive_dir = _data_root() / "processed" / "phase_transition" / "history" / date_str
    archive_dir.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    missing: list[str] = []
    for rel in ARCHIVED_OUTPUTS:
        src = Path(rel)
        if not src.is_file():
            missing.append(rel)
            continue
        shutil.copy2(src, archive_dir / src.name)
        copied.append(src.name)

    if missing:
        context.log.warning(
            f"{len(missing)} expected output(s) absent, archived without them: {', '.join(missing)}"
        )
    if not copied:
        raise FileNotFoundError(
            "No phase-transition outputs found to archive. Expected files under "
            "data/processed and reports/phase_transition; run the analysis first."
        )

    context.log.info(f"Archived {len(copied)} file(s) to {archive_dir}")
    context.add_output_metadata(
        {"archive_dir": str(archive_dir), "copied": len(copied), "missing": len(missing)}
    )
    return {"archive_dir": str(archive_dir), "copied": copied, "missing": missing}


@job(
    name="phase_transition_archive_job",
    description="Archive phase-transition analysis outputs to a dated directory",
)
def phase_transition_archive_job():
    archive_phase_transition_outputs_op()


__all__ = ["phase_transition_archive_job"]
