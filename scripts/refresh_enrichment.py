#!/usr/bin/env python3
"""CLI utility for refreshing enrichment data.

Allows operators to request ad-hoc refresh windows or replays of failed slices.
"""

import sys
from datetime import datetime
from pathlib import Path


# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import typer
from loguru import logger
from typer import Option

from src.config.loader import get_config
from src.utils.enrichment_freshness import FreshnessStore


app = typer.Typer(help="USAspending enrichment refresh utility")


@app.command()
def refresh_usaspending(
    award_ids: str = Option(
        None, "--award-ids", help="Comma-separated list of award IDs to refresh"
    ),
    cohort: str = Option(
        None,
        "--cohort",
        help="Award cohort (e.g., year like '2023' or date range like '2023-01-01:2023-12-31')",
    ),
    window_days: int = Option(
        None,
        "--window",
        help="Number of days to look back for stale awards (overrides SLA from config)",
    ),
    stale_only: bool = Option(False, "--stale-only", help="Only refresh awards that are stale"),
    force: bool = Option(False, "--force", help="Force refresh even if not stale"),
    dry_run: bool = Option(
        False, "--dry-run", help="Show what would be refreshed without executing"
    ),
) -> None:
    """Refresh USAspending enrichment for specified awards.

    Examples:
        # Refresh specific awards
        python scripts/refresh_enrichment.py refresh-usaspending --award-ids "AWARD-001,AWARD-002"

        # Refresh all stale awards
        python scripts/refresh_enrichment.py refresh-usaspending --stale-only

        # Refresh awards from 2023
        python scripts/refresh_enrichment.py refresh-usaspending --cohort 2023

        # Force refresh all awards in date range
        python scripts/refresh_enrichment.py refresh-usaspending --cohort "2023-01-01:2023-12-31" --force
    """
    config = get_config()
    source = "usaspending"
    refresh_config = config.enrichment_refresh.usaspending

    store = FreshnessStore()

    # Determine which awards to refresh
    award_ids_list: list[str] | None = None
    if award_ids:
        award_ids_list = [aid.strip() for aid in award_ids.split(",")]

    if stale_only:
        sla_days = window_days or refresh_config.sla_staleness_days
        stale_records = store.get_stale_records(source, sla_days)
        award_ids_list = [r.award_id for r in stale_records]
        logger.info(f"Found {len(award_ids_list)} stale awards")

    if cohort:
        # Parse cohort - could be year or date range
        # For now, simple implementation - could be enhanced
        if ":" in cohort:
            start_str, end_str = cohort.split(":", 1)
            start_date = datetime.fromisoformat(start_str)
            end_date = datetime.fromisoformat(end_str)
            logger.info(f"Cohort date range: {start_date} to {end_date}")
            # TODO: Filter awards by date range
        else:
            year = int(cohort)
            logger.info(f"Cohort year: {year}")
            # TODO: Filter awards by year

    if dry_run:
        logger.info("DRY RUN MODE - No changes will be made")
        if award_ids_list:
            logger.info(f"Would refresh {len(award_ids_list)} awards: {award_ids_list[:10]}...")
        else:
            logger.info("No awards specified for refresh")
        return

    # For now, this is a placeholder that shows what would be done
    # In production, this would trigger the Dagster job with appropriate config
    logger.info("Refresh functionality requires Dagster job execution")
    logger.info("To refresh via Dagster, run:")
    logger.info("  dagster job execute usaspending_iterative_enrichment_job -c config/dev.yaml")
    if award_ids_list:
        logger.info(f"  With award_ids: {award_ids_list[:5]}...")


@app.command()
def list_stale(
    source: str = Option("usaspending", "--source", help="Enrichment source name"),
    sla_days: int = Option(None, "--sla-days", help="SLA staleness threshold in days"),
) -> None:
    """List stale awards that need refresh.

    Args:
        source: Enrichment source name
        sla_days: SLA staleness threshold (uses config default if not specified)
    """
    config = get_config()
    if sla_days is None:
        sla_days = config.enrichment_refresh.usaspending.sla_staleness_days

    store = FreshnessStore()
    stale_records = store.get_stale_records(source, sla_days)

    logger.info(f"Found {len(stale_records)} stale {source} records (SLA: {sla_days} days)")

    for record in stale_records[:20]:  # Show first 20
        age_days = (
            (datetime.now() - record.last_success_at).total_seconds() / 86400
            if record.last_success_at
            else float("inf")
        )
        logger.info(
            f"  {record.award_id}: last success {age_days:.1f} days ago "
            f"(status: {record.status.value})"
        )

    if len(stale_records) > 20:
        logger.info(f"... and {len(stale_records) - 20} more")


@app.command()
def stats(
    source: str = Option("usaspending", "--source", help="Enrichment source name"),
) -> None:
    """Show enrichment freshness statistics.

    Args:
        source: Enrichment source name
    """
    config = get_config()
    sla_days = config.enrichment_refresh.usaspending.sla_staleness_days

    store = FreshnessStore()
    df = store.load_all()

    if df.empty:
        logger.info("No freshness records found")
        return

    df_source = df[df["source"] == source] if "source" in df.columns else df

    total = len(df_source)
    successful = (
        len(df_source[df_source["status"] == "success"]) if "status" in df_source.columns else 0
    )
    stale_records = store.get_stale_records(source, sla_days)
    stale_count = len(stale_records)

    logger.info(f"Freshness Statistics for {source}:")
    logger.info(f"  Total records: {total}")
    logger.info(f"  Successful: {successful}")
    logger.info(f"  Stale (>{sla_days} days): {stale_count}")
    logger.info(f"  Coverage: {successful/total*100:.1f}%" if total > 0 else "  Coverage: N/A")


def main() -> None:
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
