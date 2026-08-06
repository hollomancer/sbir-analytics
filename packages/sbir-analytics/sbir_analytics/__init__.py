"""SBIR Analytics application package.

Epistemic tier: pipelines. Package default for deterministic orchestration
and materialization; asset modules that rank, score, or infer declare
exploratory per-file, and evidence-tier census machinery is governed by its
study contract under ``studies/``.

This package contains Dagster orchestration and application tools that should
not be part of the reusable sbir-etl library.
"""

EPISTEMIC_TIER = "pipelines"
