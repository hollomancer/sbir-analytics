# packages/sbir-analytics/sbir_analytics/assets/jobs/uspto_ai_job.py
"""
Dagster job that composes USPTO AI extraction assets into a single run.

Pipeline (intended order):
  1) raw_uspto_ai_extract             — stream raw files into DuckDB canonical table
  2) uspto_ai_deduplicate             — build deduplicated table keyed by grant_doc_num
  3) raw_uspto_ai_human_sample_extraction — write NDJSON sample for human evaluation

Notes:
- Execution order is determined by asset dependencies. These assets operate on DuckDB tables
  and do not declare direct Dagster dependencies, so Dagster may schedule them in parallel.
  Run this job with appropriate configuration or triggers to ensure extract precedes dedup
  and sample if your orchestration requires strict sequencing.
- Provide runtime configuration via Dagster run config (e.g., duckdb path, raw_dir, etc).
"""

from dagster import AssetSelection, define_asset_job


# Import the heavy asset module directly. The definitions profile decides
# whether this job module is imported, so the package-level environment gate
# must not change the job's selection.
from sbir_analytics.assets.uspto.ai_extraction import (
    raw_uspto_ai_extract,
    raw_uspto_ai_human_sample_extraction,
    uspto_ai_deduplicate,
)


uspto_ai_extraction_job = define_asset_job(
    name="uspto_ai_extraction_job",
    selection=AssetSelection.keys(
        raw_uspto_ai_extract.key,
        uspto_ai_deduplicate.key,
        raw_uspto_ai_human_sample_extraction.key,
    ),
    description=(
        "Materialize USPTO AI extraction -> deduplication -> sampling flow. "
        "Intended for end-to-end ingestion and human-eval preparation."
    ),
)


__all__ = ["uspto_ai_extraction_job"]
