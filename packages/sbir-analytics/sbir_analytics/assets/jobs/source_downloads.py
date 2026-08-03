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
    """Fetch the keyless, structurally validated SAM Public V2 snapshot."""
    import pandas as pd

    from scripts.data.download_sam_gov import (
        PARQUET_NAME,
        _download_bulk_extract,
        _write_local,
    )

    df: pd.DataFrame | None = _download_bulk_extract()
    if df is None or df.empty:
        raise ValueError("SAM.gov Public V2 bulk download returned no validated entity records")

    path = _write_local(
        df,
        _data_root() / "raw" / "sam_gov",
        name=PARQUET_NAME,
    )
    context.add_output_metadata({"rows": len(df), "path": str(path), "partial": False})
    return {"rows": len(df), "path": str(path), "partial": False}


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


MIN_PLAUSIBLE_DOWNLOAD_BYTES = 1024 * 1024


def _guard_html_shell(path: Path) -> None:
    """Reject an HTML error page saved under a data filename.

    Anonymous downloads from data.uspto.gov ended 2026-06-18 and now return a
    small HTML shell with HTTP 200 rather than the file, so a plain stream
    download succeeds while writing garbage. Fail loudly instead.
    """
    size = path.stat().st_size
    if size < MIN_PLAUSIBLE_DOWNLOAD_BYTES:
        head = path.read_bytes()[:512].lstrip().lower()
        if head.startswith(b"<!doctype html") or head.startswith(b"<html"):
            path.unlink(missing_ok=True)
            raise ValueError(
                f"USPTO returned an HTML page rather than data for {path.name}. "
                f"The endpoint requires an API key (USPTO_ODP_API_KEY) or the "
                f"browser download path."
            )
        raise ValueError(f"USPTO download implausibly small ({size} bytes): {path}")


def _extract_assignment_archives(context: OpExecutionContext, assignment_dir: Path) -> list[str]:
    """Extract the downloaded .csv.zip archives so downstream assets see them.

    The raw USPTO assets discover .csv/.dta/.parquet, so a directory of
    .csv.zip archives is invisible to them. Each archive is extracted to a
    temporary directory and moved into place, so a failure part-way never
    leaves a truncated .csv where a complete one is expected.
    """
    import tempfile
    import zipfile

    extracted: list[str] = []
    for archive in sorted(assignment_dir.glob("*.zip")):
        with (
            zipfile.ZipFile(archive) as zf,
            tempfile.TemporaryDirectory(dir=assignment_dir) as staging,
        ):
            zf.extractall(staging)
            for member in Path(staging).rglob("*"):
                if not member.is_file():
                    continue
                member.replace(assignment_dir / member.name)
                extracted.append(member.name)
    context.log.info(f"Extracted {len(extracted)} assignment file(s) from archives")
    return extracted


@op
def download_uspto_op(context: OpExecutionContext) -> dict:
    """Fetch the three USPTO datasets the pipeline consumes.

    Mirrors what the retired data-refresh.yml workflow fetched:
    PatentsView ``patent``, the AI patents dataset, and patent assignments.
    Assignments go through browser automation because the USPTO portal no
    longer serves them to a plain HTTP client.
    """
    import asyncio

    from scripts.data.download_uspto import (
        PATENTSVIEW_PRODUCT,
        PATENTSVIEW_TABLES,
        USPTO_AI_PATENT_URL,
        create_session_with_retries,
        download_odp_file,
        stream_download,
    )

    dest_dir = _data_root() / "raw" / "uspto"
    dest_dir.mkdir(parents=True, exist_ok=True)

    api_key = os.environ.get("USPTO_ODP_API_KEY", "")
    results: dict[str, dict] = {}
    session = create_session_with_retries()

    # 1: PatentsView patent table, via the ODP presigned-URL mint flow.
    if not api_key:
        raise ValueError(
            "USPTO_ODP_API_KEY is not set. PatentsView downloads have required a "
            "key since 2026-06-18; add it to .env.server."
        )

    pv_dest = dest_dir / "patentsview_patent.zip"
    context.log.info("Downloading PatentsView patent table")
    results["patentsview_patent"] = download_odp_file(
        f"{PATENTSVIEW_PRODUCT}/{PATENTSVIEW_TABLES['patent']}", api_key, pv_dest, session
    )
    _guard_html_shell(pv_dest)
    results["patentsview_patent"]["path"] = str(pv_dest)

    # 2: AI patents, served from a direct URL rather than the ODP product API.
    ai_dest = dest_dir / "ai_patent_dataset.zip"
    context.log.info("Downloading AI patents dataset")
    results["ai_patents"] = stream_download(USPTO_AI_PATENT_URL, ai_dest, session)
    _guard_html_shell(ai_dest)
    results["ai_patents"]["path"] = str(ai_dest)

    # 3: assignments, which need a real browser session.
    from scripts.data.download_uspto_browser import download_assignments

    context.log.info("Downloading patent assignments via browser automation")
    assignment_dir = dest_dir / "assignments"
    assignment_results = asyncio.run(download_assignments(output_dir=assignment_dir))

    # download_assignments records per-file failures instead of raising, so the
    # op would otherwise succeed with a partial assignment set.
    failed = [r for r in assignment_results if r.get("error")]
    if failed:
        raise RuntimeError(
            "USPTO assignment download failed for "
            + ", ".join(f"{r.get('file')}: {r['error']}" for r in failed)
        )
    if not assignment_results:
        raise RuntimeError("USPTO assignment download produced no files")

    extracted = _extract_assignment_archives(context, assignment_dir)
    results["assignments"] = {"files": assignment_results, "extracted": extracted}

    context.add_output_metadata(
        {
            "datasets": list(results),
            "assignment_files": len(assignment_results),
            "dest_dir": str(dest_dir),
        }
    )
    return results


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
