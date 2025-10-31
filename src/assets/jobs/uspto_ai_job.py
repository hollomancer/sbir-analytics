# sbir-etl/src/assets/jobs/uspto_ai_job.py
"""
Dagster job that composes USPTO AI extraction assets into a single run.

Pipeline (intended order):
  1) uspto_ai_extract_to_duckdb      — stream raw files into DuckDB canonical table
  2) uspto_ai_deduplicate            — build deduplicated table keyed by grant_doc_num
  3) uspto_ai_human_sample_extraction— write NDJSON sample for human evaluation

Notes:
- Execution order is determined by asset dependencies. These assets operate on DuckDB tables
  and do not declare direct Dagster dependencies, so Dagster may schedule them in parallel.
  Run this job with appropriate configuration or triggers to ensure extract precedes dedup
  and sample if your orchestration requires strict sequencing.
- Provide runtime configuration via Dagster run config (e.g., duckdb path, raw_dir, etc).
"""

from dagster import AssetSelection, build_assets_job

# Import the USPTO AI asset definitions. These are expected to be defined in:
#   src.assets.uspto_ai_extraction_assets
try:
    from src.assets.uspto_assets import (  # type: ignore
        uspto_ai_deduplicate,
        uspto_ai_extract_to_duckdb,
        uspto_ai_human_sample_extraction,
    )
except Exception:  # pragma: no cover - defensive import for repository load-time
    uspto_ai_extract_to_duckdb = None  # type: ignore
    uspto_ai_deduplicate = None  # type: ignore
    uspto_ai_human_sample_extraction = None  # type: ignore


# Compose the USPTO AI extraction job.
# When assets import successfully, expose a real job that targets the three assets.
# Otherwise, expose a placeholder job so repository load is resilient in constrained environments.
if (
    uspto_ai_extract_to_duckdb is not None
    and uspto_ai_deduplicate is not None
    and uspto_ai_human_sample_extraction is not None
):
    uspto_ai_extraction_job = build_assets_job(
        name="uspto_ai_extraction_job",
        assets=[
            uspto_ai_extract_to_duckdb,
            uspto_ai_deduplicate,
            uspto_ai_human_sample_extraction,
        ],
        selection=AssetSelection.keys(
            uspto_ai_extract_to_duckdb.key,
            uspto_ai_deduplicate.key,  # type: ignore[attr-defined]
            uspto_ai_human_sample_extraction.key,  # type: ignore[attr-defined]
        ),
        description=(
            "Materialize USPTO AI extraction -> deduplication -> sampling flow. "
            "Intended for end-to-end ingestion and human-eval preparation."
        ),
    )
else:
    uspto_ai_extraction_job = build_assets_job(
        name="uspto_ai_extraction_job_placeholder",
        assets=[],
        description="Placeholder job (USPTO AI assets unavailable at import time).",
    )


__all__ = ["uspto_ai_extraction_job"]
