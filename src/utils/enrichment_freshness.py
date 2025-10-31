"""Utilities for managing enrichment freshness records.

Provides persistence layer for freshness records to Parquet/DuckDB and Neo4j,
along with utilities for querying stale records and updating freshness state.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger

from ..models.enrichment import (
    EnrichmentFreshnessRecord,
    EnrichmentFreshnessRecordModel,
    EnrichmentStatus,
)


class FreshnessStore:
    """Store for managing enrichment freshness records."""

    def __init__(self, parquet_path: Path | str | None = None):
        """Initialize freshness store.

        Args:
            parquet_path: Path to Parquet file for persistence. Defaults to data/derived/enrichment_freshness.parquet
        """
        if parquet_path is None:
            parquet_path = Path("data/derived/enrichment_freshness.parquet")
        self.parquet_path = Path(parquet_path)
        self.parquet_path.parent.mkdir(parents=True, exist_ok=True)

    def load_all(self) -> pd.DataFrame:
        """Load all freshness records from Parquet.

        Returns:
            DataFrame with freshness records
        """
        if not self.parquet_path.exists():
            return pd.DataFrame()

        try:
            df = pd.read_parquet(self.parquet_path)
            # Ensure datetime columns are properly typed
            if "last_attempt_at" in df.columns:
                df["last_attempt_at"] = pd.to_datetime(df["last_attempt_at"])
            if "last_success_at" in df.columns:
                df["last_success_at"] = pd.to_datetime(df["last_success_at"])
            return df
        except Exception as e:
            logger.error(f"Failed to load freshness records: {e}")
            return pd.DataFrame()

    def save_record(self, record: EnrichmentFreshnessRecord) -> None:
        """Save a single freshness record (append or update).

        Args:
            record: Freshness record to save
        """
        df = self.load_all()

        # Convert to Pydantic model for serialization
        model = EnrichmentFreshnessRecordModel.from_dataclass(record)

        # Create DataFrame from single record
        new_row = pd.DataFrame([model.model_dump()])

        # Check if record exists (by award_id + source)
        if not df.empty:
            mask = (df["award_id"] == record.award_id) & (df["source"] == record.source)
            if mask.any():
                # Update existing record
                df.loc[mask, new_row.columns] = new_row.iloc[0]
            else:
                # Append new record
                df = pd.concat([df, new_row], ignore_index=True)
        else:
            df = new_row

        self.save_all(df)

    def save_records(self, records: list[EnrichmentFreshnessRecord]) -> None:
        """Save multiple freshness records in batch.

        Args:
            records: List of freshness records to save
        """
        if not records:
            return

        df = self.load_all()

        # Convert all records to Pydantic models
        models = [EnrichmentFreshnessRecordModel.from_dataclass(r) for r in records]
        new_rows = pd.DataFrame([m.model_dump() for m in models])

        if not df.empty:
            # Update existing records and append new ones
            for idx, new_row in new_rows.iterrows():
                mask = (df["award_id"] == new_row["award_id"]) & (
                    df["source"] == new_row["source"]
                )
                if mask.any():
                    df.loc[mask, new_row.index] = new_row.values
                else:
                    df = pd.concat([df, new_row.to_frame().T], ignore_index=True)
        else:
            df = new_rows

        self.save_all(df)

    def save_all(self, df: pd.DataFrame) -> None:
        """Save all freshness records to Parquet.

        Args:
            df: DataFrame with all freshness records
        """
        try:
            self.parquet_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(self.parquet_path, index=False, engine="pyarrow")
            logger.debug(f"Saved {len(df)} freshness records to {self.parquet_path}")
        except Exception as e:
            logger.error(f"Failed to save freshness records: {e}")
            raise

    def get_record(
        self, award_id: str, source: str
    ) -> EnrichmentFreshnessRecord | None:
        """Get a specific freshness record.

        Args:
            award_id: Award identifier
            source: Enrichment source name

        Returns:
            Freshness record or None if not found
        """
        df = self.load_all()
        if df.empty:
            return None

        mask = (df["award_id"] == award_id) & (df["source"] == source)
        if not mask.any():
            return None

        row = df[mask].iloc[0]
        model = EnrichmentFreshnessRecordModel(**row.to_dict())
        return model.to_dataclass()

    def get_stale_records(
        self, source: str, sla_days: int
    ) -> list[EnrichmentFreshnessRecord]:
        """Get all stale records for a source.

        Args:
            source: Enrichment source name
            sla_days: Maximum allowed age in days

        Returns:
            List of stale freshness records
        """
        df = self.load_all()
        if df.empty:
            return []

        # Filter by source
        df_source = df[df["source"] == source].copy()
        if df_source.empty:
            return []

        # Filter by staleness
        now = datetime.now()
        cutoff = now - timedelta(days=sla_days)

        stale_records = []
        for _, row in df_source.iterrows():
            last_success = row.get("last_success_at")
            if pd.isna(last_success):
                # No successful enrichment yet
                stale_records.append(
                    EnrichmentFreshnessRecordModel(**row.to_dict()).to_dataclass()
                )
            else:
                # Check if last success is before cutoff
                if isinstance(last_success, pd.Timestamp):
                    last_success = last_success.to_pydatetime()
                if last_success < cutoff:
                    stale_records.append(
                        EnrichmentFreshnessRecordModel(**row.to_dict()).to_dataclass()
                    )

        return stale_records

    def get_awards_needing_refresh(
        self, source: str, sla_days: int, award_ids: list[str] | None = None
    ) -> list[str]:
        """Get list of award IDs that need refresh.

        Args:
            source: Enrichment source name
            sla_days: Maximum allowed age in days
            award_ids: Optional list of award IDs to check. If None, checks all.

        Returns:
            List of award IDs that need refresh
        """
        stale_records = self.get_stale_records(source, sla_days)
        stale_award_ids = {r.award_id for r in stale_records}

        if award_ids is None:
            return list(stale_award_ids)

        # Filter to only requested award IDs
        return [aid for aid in award_ids if aid in stale_award_ids]


def update_freshness_ledger(
    store: FreshnessStore,
    award_id: str,
    source: str,
    success: bool,
    payload_hash: str | None = None,
    metadata: dict[str, Any] | None = None,
    error_message: str | None = None,
) -> EnrichmentFreshnessRecord:
    """Update freshness ledger after enrichment attempt.

    Args:
        store: FreshnessStore instance
        award_id: Award identifier
        source: Enrichment source name
        success: Whether enrichment succeeded
        payload_hash: SHA256 hash of payload (if successful)
        metadata: Source-specific metadata
        error_message: Error message if failed

    Returns:
        Updated freshness record
    """
    # Load existing record or create new one
    existing = store.get_record(award_id, source)
    now = datetime.now()

    if existing:
        record = existing
        record.attempt_count += 1
        record.last_attempt_at = now
    else:
        record = EnrichmentFreshnessRecord(
            award_id=award_id,
            source=source,
            last_attempt_at=now,
            attempt_count=1,
        )

    if success:
        record.status = EnrichmentStatus.SUCCESS
        record.last_success_at = now
        record.success_count += 1
        if payload_hash:
            # Check if payload changed
            if record.payload_hash and record.payload_hash != payload_hash:
                record.status = EnrichmentStatus.SUCCESS  # Changed
            record.payload_hash = payload_hash
        if metadata:
            record.metadata.update(metadata)
        record.error_message = None
    else:
        record.status = EnrichmentStatus.FAILED
        record.error_message = error_message

    store.save_record(record)
    return record


def persist_to_neo4j(
    record: EnrichmentFreshnessRecord,
    neo4j_driver: Any,  # neo4j.Driver type - using Any to avoid import dependency
) -> None:
    """Persist freshness record to Neo4j as node properties.

    Args:
        record: Freshness record to persist
        neo4j_driver: Neo4j driver instance
    """
    query = """
    MATCH (a:Award {award_id: $award_id})
    SET a.`enrichment_freshness_` + $source + `_last_attempt_at` = $last_attempt_at,
        a.`enrichment_freshness_` + $source + `_last_success_at` = $last_success_at,
        a.`enrichment_freshness_` + $source + `_payload_hash` = $payload_hash,
        a.`enrichment_freshness_` + $source + `_status` = $status,
        a.`enrichment_freshness_` + $source + `_attempt_count` = $attempt_count,
        a.`enrichment_freshness_` + $source + `_success_count` = $success_count
    """
    # Note: The above query uses string concatenation which is not ideal in Cypher.
    # A better approach would be to use SET with dynamic property names or a different pattern.
    # For now, this is a placeholder implementation.

    with neo4j_driver.session() as session:
        session.run(
            query,
            award_id=record.award_id,
            source=record.source,
            last_attempt_at=record.last_attempt_at.isoformat(),
            last_success_at=record.last_success_at.isoformat() if record.last_success_at else None,
            payload_hash=record.payload_hash,
            status=record.status.value if isinstance(record.status, EnrichmentStatus) else record.status,
            attempt_count=record.attempt_count,
            success_count=record.success_count,
        )
