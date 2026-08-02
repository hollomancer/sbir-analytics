"""Source-data download jobs that run on the always-on server.

These replace the GitHub Actions `data-refresh.yml` workflow. Actions runners
cannot reach the Mac mini (tailnet-only, no self-hosted runner), so the host
that stores the data is the host that fetches it.

Each op wraps the corresponding `scripts/` downloader, which writes to the
local data root by default. Destinations come from the config paths so the
server profile's SSD bind mounts are honoured without hardcoding them here.

Schedules for these jobs default to STOPPED. Per the Mac mini runbook, an
operator confirms a manual run succeeds on this host before enabling one.
"""

import os
from pathlib import Path

from dagster import OpExecutionContext, job, op

DATA_ROOT_ENV = "SBIR_ETL__PATHS__DATA_ROOT"
DEFAULT_DATA_ROOT = "data"


def _data_root() -> Path:
    return Path(os.getenv(DATA_ROOT_ENV, DEFAULT_DATA_ROOT))


@op
def download_sbir_awards_op(context: OpExecutionContext) -> dict:
    """Fetch the SBIR.gov awards CSV, keeping a dated vintage."""
    from scripts.data.download_sbir import download_sbir_awards

    result = download_sbir_awards(_data_root() / "raw" / "sbir")
    context.log.info(
        f"SBIR awards: changed={result['changed']} path={result['path']} "
        f"sha256={result['sha256'][:16]}"
    )
    context.add_output_metadata(
        {"changed": result["changed"], "path": result["path"], "sha256": result["sha256"]}
    )
    return result


@op
def download_sam_gov_op(context: OpExecutionContext) -> dict:
    """Fetch SAM.gov entity records as parquet.

    Requires SAM_GOV_API_KEY. Keys expire roughly every 60 days, so a failure
    here is usually a rotation prompt rather than a transient error.
    """
    import pandas as pd

    from scripts.data.download_sam_gov import (
        MIN_CANONICAL_ROW_COUNT,
        PARQUET_NAME,
        PARQUET_NAME_PARTIAL,
        _download_bulk_extract,
        _write_local,
    )

    api_key = os.environ.get("SAM_GOV_API_KEY", "")
    if not api_key:
        raise ValueError(
            "SAM_GOV_API_KEY is not set. Obtain a key from "
            "https://sam.gov -> Account -> API Keys and add it to .env.server."
        )

    df: pd.DataFrame = _download_bulk_extract(api_key)
    if df is None or df.empty:
        raise ValueError("SAM.gov returned no entity records")

    partial = len(df) < MIN_CANONICAL_ROW_COUNT
    if partial:
        context.log.warning(
            f"Only {len(df):,} rows (below {MIN_CANONICAL_ROW_COUNT:,}); "
            f"writing as partial so the canonical dataset is not overwritten"
        )

    path = _write_local(
        df,
        _data_root() / "raw" / "sam_gov",
        name=PARQUET_NAME_PARTIAL if partial else PARQUET_NAME,
    )
    context.add_output_metadata({"rows": len(df), "path": str(path), "partial": partial})
    return {"rows": len(df), "path": str(path), "partial": partial}


@op
def download_usaspending_op(context: OpExecutionContext) -> dict:
    """Fetch the USAspending database dump.

    This is the long pole: the dump is large, the op may run for hours, and it
    resumes from a sidecar checkpoint if interrupted. It checks free space
    before downloading rather than failing late on a full volume.
    """
    from scripts.usaspending.download_database import download_local

    result = download_local(_data_root() / "usaspending")
    context.log.info(f"USAspending: status={result['status']} path={result['path']}")
    context.add_output_metadata(
        {"status": result["status"], "path": result["path"], "size": result["size"]}
    )
    return result


@op
def download_uspto_op(context: OpExecutionContext) -> dict:
    """Fetch the USPTO patent assignments dataset."""
    from scripts.data.download_uspto import (
        USPTO_ASSIGNMENT_URL,
        create_session_with_retries,
        stream_download,
    )

    dest_dir = _data_root() / "raw" / "uspto"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / "patent_assignments.zip"

    result = stream_download(USPTO_ASSIGNMENT_URL, dest_path, create_session_with_retries())
    context.log.info(f"USPTO: {dest_path} ({result['size'] / 1024 / 1024:.1f} MB)")
    context.add_output_metadata(
        {"path": str(dest_path), "size": result["size"], "sha256": result["sha256"]}
    )
    return {"path": str(dest_path), **result}


@job(
    name="sbir_awards_download_job",
    description="Download the SBIR.gov awards CSV to local storage",
)
def sbir_awards_download_job():
    download_sbir_awards_op()


@job(
    name="sam_gov_download_job",
    description="Download SAM.gov entity records to local storage",
)
def sam_gov_download_job():
    download_sam_gov_op()


@job(
    name="usaspending_download_job",
    description="Download the USAspending database dump to local storage",
)
def usaspending_download_job():
    download_usaspending_op()


@job(
    name="uspto_download_job",
    description="Download USPTO patent assignments to local storage",
)
def uspto_download_job():
    download_uspto_op()


__all__ = [
    "sam_gov_download_job",
    "sbir_awards_download_job",
    "usaspending_download_job",
    "uspto_download_job",
]
