#!/usr/bin/env python3
"""Backfill enrichment freshness metadata for existing enriched awards.

Scans existing enriched awards and initializes freshness records with
last_success_at from existing enrichment timestamps and payload_hash from
current enriched data.
"""

import sys
from pathlib import Path


# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import hashlib
import json
from datetime import datetime
from typing import Any

import pandas as pd
from loguru import logger

from src.models.enrichment import EnrichmentFreshnessRecord, EnrichmentStatus
from src.utils.enrichment_freshness import FreshnessStore


def compute_enrichment_hash(enriched_data: dict[str, Any]) -> str:
    """Compute hash of enriched data payload.

    Args:
        enriched_data: Dictionary of enriched fields

    Returns:
        SHA256 hash as hex string
    """
    # Filter to only USAspending-related fields
    usaspending_fields = {
        k: v
        for k, v in enriched_data.items()
        if k.startswith("usaspending_") or k.startswith("recipient_") or k == "naics_code"
    }

    if not usaspending_fields:
        return ""

    # Sort keys for deterministic hashing
    json_str = json.dumps(usaspending_fields, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(json_str.encode("utf-8")).hexdigest()


def extract_enrichment_timestamp(enriched_row: pd.Series) -> datetime | None:
    """Extract enrichment timestamp from enriched award row.

    Args:
        enriched_row: Row from enriched awards DataFrame

    Returns:
        Enrichment timestamp or None if not found
    """
    # Check for common timestamp fields
    timestamp_fields = [
        "_enrichment_timestamp",
        "enrichment_timestamp",
        "_usaspending_enriched_at",
        "usaspending_enriched_at",
        "fiscal_naics_timestamp",
    ]

    for field in timestamp_fields:
        if field in enriched_row.index and pd.notna(enriched_row[field]):
            try:
                ts = enriched_row[field]
                if isinstance(ts, str):
                    return datetime.fromisoformat(ts.replace("Z", "+00:00"))
                elif isinstance(ts, datetime):
                    return ts
                elif isinstance(ts, pd.Timestamp):
                    return ts.to_pydatetime()
            except Exception as e:
                logger.debug(f"Failed to parse timestamp from {field}: {e}")

    # Fallback: use current time if enrichment seems present (has usaspending fields)
    if any(
        col.startswith("usaspending_") or col.startswith("recipient_") for col in enriched_row.index
    ):
        return datetime.now()

    return None


def backfill_freshness_records(
    enriched_awards_path: Path | str,
    source: str = "usaspending",
    dry_run: bool = False,
) -> int:
    """Backfill freshness records from existing enriched awards.

    Args:
        enriched_awards_path: Path to enriched awards Parquet/CSV file
        source: Enrichment source name (default: "usaspending")
        dry_run: If True, don't save records, just report what would be created

    Returns:
        Number of freshness records created/updated
    """
    enriched_path = Path(enriched_awards_path)
    if not enriched_path.exists():
        logger.error(f"Enriched awards file not found: {enriched_path}")
        return 0

    logger.info(f"Loading enriched awards from {enriched_path}")

    # Load enriched awards
    try:
        if enriched_path.suffix == ".parquet":
            enriched_df = pd.read_parquet(enriched_path)
        else:
            enriched_df = pd.read_csv(enriched_path)
    except Exception as e:
        logger.error(f"Failed to load enriched awards: {e}")
        return 0

    logger.info(f"Loaded {len(enriched_df)} enriched awards")

    # Initialize freshness store
    store = FreshnessStore()

    # Identify award ID column
    award_id_col = None
    for col in ["award_id", "Award_ID", "id", "ID"]:
        if col in enriched_df.columns:
            award_id_col = col
            break

    if not award_id_col:
        logger.error("Could not find award ID column in enriched data")
        return 0

    records_created = 0

    # Process each award
    for idx, row in enriched_df.iterrows():
        award_id = str(row[award_id_col])

        # Check if enrichment data exists for this source
        enrichment_present = False
        if source == "usaspending":
            # Check for USAspending enrichment fields
            enrichment_present = any(
                col.startswith("usaspending_")
                or col.startswith("recipient_")
                or col == "_usaspending_match_method"
                for col in row.index
                if pd.notna(row.get(col))
            )

        if not enrichment_present:
            continue

        # Extract enrichment timestamp
        enrichment_timestamp = extract_enrichment_timestamp(row)

        # Compute payload hash from enriched data
        enriched_data = row.to_dict()
        payload_hash = compute_enrichment_hash(enriched_data)

        # Create freshness record
        freshness_record = EnrichmentFreshnessRecord(
            award_id=award_id,
            source=source,
            last_attempt_at=enrichment_timestamp or datetime.now(),
            last_success_at=enrichment_timestamp,
            payload_hash=payload_hash if payload_hash else None,
            status=EnrichmentStatus.SUCCESS if enrichment_timestamp else EnrichmentStatus.PENDING,
            attempt_count=1 if enrichment_timestamp else 0,
            success_count=1 if enrichment_timestamp else 0,
            metadata={
                "backfilled": True,
                "backfilled_at": datetime.now().isoformat(),
            },
        )

        if not dry_run:
            store.save_record(freshness_record)
        records_created += 1

        if (idx + 1) % 1000 == 0:
            logger.info(f"Processed {idx + 1} awards...")

    logger.info(f"{'Would create' if dry_run else 'Created'} {records_created} freshness records")
    return records_created


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Backfill enrichment freshness metadata")
    parser.add_argument(
        "--enriched-awards",
        type=str,
        default="data/processed/enriched_awards.csv",
        help="Path to enriched awards file (CSV or Parquet)",
    )
    parser.add_argument(
        "--source",
        type=str,
        default="usaspending",
        help="Enrichment source name (default: usaspending)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't save records, just report what would be created",
    )

    args = parser.parse_args()

    logger.info("Starting freshness metadata backfill")
    logger.info(f"Enriched awards: {args.enriched_awards}")
    logger.info(f"Source: {args.source}")
    logger.info(f"Dry run: {args.dry_run}")

    records_created = backfill_freshness_records(
        enriched_awards_path=args.enriched_awards,
        source=args.source,
        dry_run=args.dry_run,
    )

    logger.info(f"Backfill complete: {records_created} records")
    return 0


if __name__ == "__main__":
    sys.exit(main())
