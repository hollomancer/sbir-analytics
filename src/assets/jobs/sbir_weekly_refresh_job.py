"""SBIR weekly refresh job for Dagster Cloud execution.

This job replaces the container-based Lambda functions (ingestion-checks, load-neo4j)
with a unified Dagster job that can be triggered from Step Functions or scheduled.
"""

from dagster import AssetSelection, define_asset_job

# Job that runs the full SBIR weekly refresh pipeline:
# 1. Extract and validate SBIR awards (raw_sbir_awards, validated_sbir_awards, sbir_validation_report)
# 2. Load validated awards into Neo4j (neo4j_sbir_awards)
sbir_weekly_refresh_job = define_asset_job(
    name="sbir_weekly_refresh_job",
    selection=AssetSelection.keys(
        "raw_sbir_awards",
        "validated_sbir_awards",
        "sbir_validation_report",
        "neo4j_sbir_awards",
    ),
    description="Weekly SBIR data refresh: extract, validate, and load awards into Neo4j",
)

