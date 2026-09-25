"""Dagster job for NIH RePORTER iterative enrichment.

No sensor and no schedule. Keep enrichment_refresh.nih_reporter.enabled false
until a hand run succeeds.
"""

from dagster import AssetSelection, define_asset_job


nih_reporter_iterative_enrichment_job = define_asset_job(
    name="nih_reporter_iterative_enrichment_job",
    selection=AssetSelection.keys(
        "nih_reporter_freshness_ledger",
        "stale_nih_reporter_awards",
        "nih_reporter_refresh_batch",
    ),
    description=(
        "NIH RePORTER iterative enrichment: identify unseen or stale SBIR.gov "
        "NIH/HHS awards and refresh exact project_num + FY lookups"
    ),
)
