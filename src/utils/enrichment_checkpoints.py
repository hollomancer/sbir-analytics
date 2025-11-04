"""Checkpoint management for enrichment refresh operations.

Provides persistence layer for checkpoint state to enable resume functionality
when refresh runs are interrupted.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger


@dataclass
class EnrichmentCheckpoint:
    """Checkpoint state for a refresh operation."""

    partition_id: str
    source: str
    last_processed_award_id: str | None
    last_success_timestamp: datetime | None
    records_processed: int
    records_failed: int
    records_total: int
    checkpoint_timestamp: datetime
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Convert checkpoint to dictionary for serialization."""
        import json

        data = asdict(self)
        # Convert datetime to ISO string
        # Convert metadata dict to JSON string for Parquet compatibility
        for key, value in data.items():
            if isinstance(value, datetime):
                data[key] = value.isoformat()
            elif key == "metadata" and isinstance(value, dict):
                # Convert dict to JSON string for Parquet compatibility (handles empty dicts)
                data[key] = json.dumps(value) if value else "{}"
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EnrichmentCheckpoint:
        """Create checkpoint from dictionary."""
        import json

        # Convert ISO strings to datetime
        # Convert metadata JSON string back to dict
        for key in ["last_success_timestamp", "checkpoint_timestamp"]:
            if key in data and data[key] and isinstance(data[key], str):
                data[key] = datetime.fromisoformat(data[key])
        if "metadata" in data and isinstance(data["metadata"], str):
            # Parse JSON string back to dict
            data["metadata"] = json.loads(data["metadata"]) if data["metadata"] else {}
        return cls(**data)


class CheckpointStore:
    """Store for managing enrichment refresh checkpoints."""

    def __init__(self, parquet_path: Path | str | None = None):
        """Initialize checkpoint store.

        Args:
            parquet_path: Path to Parquet file for persistence.
                         Defaults to data/state/enrichment_checkpoints.parquet
        """
        if parquet_path is None:
            parquet_path = Path("data/state/enrichment_checkpoints.parquet")
        self.parquet_path = Path(parquet_path)
        self.parquet_path.parent.mkdir(parents=True, exist_ok=True)

    def save_checkpoint(self, checkpoint: EnrichmentCheckpoint) -> None:
        """Save or update a checkpoint.

        Args:
            checkpoint: Checkpoint to save
        """
        df = self.load_all()

        # Create DataFrame from checkpoint
        checkpoint_dict = checkpoint.to_dict()
        new_row = pd.DataFrame([checkpoint_dict])

        # Check if checkpoint exists (by partition_id + source)
        if not df.empty:
            mask = (df["partition_id"] == checkpoint.partition_id) & (
                df["source"] == checkpoint.source
            )
            if mask.any():
                # Update existing checkpoint - replace the entire row
                # Find the index of the matching row
                idx = df[mask].index[0]
                # Update all columns from new_row
                for col in new_row.columns:
                    df.loc[idx, col] = new_row[col].iloc[0]
            else:
                # Append new checkpoint
                df = pd.concat([df, new_row], ignore_index=True)
        else:
            df = new_row

        self.save_all(df)
        logger.debug(f"Saved checkpoint: {checkpoint.partition_id} ({checkpoint.source})")

    def load_checkpoint(self, partition_id: str, source: str) -> EnrichmentCheckpoint | None:
        """Load a specific checkpoint.

        Args:
            partition_id: Partition identifier
            source: Enrichment source name

        Returns:
            Checkpoint or None if not found
        """
        df = self.load_all()
        if df.empty:
            return None

        mask = (df["partition_id"] == partition_id) & (df["source"] == source)
        if not mask.any():
            return None

        row = df[mask].iloc[0]
        checkpoint_dict = row.to_dict()
        # Ensure metadata is handled correctly (it's stored as JSON string)
        if "metadata" in checkpoint_dict and isinstance(checkpoint_dict["metadata"], str):
            import json

            checkpoint_dict["metadata"] = json.loads(checkpoint_dict["metadata"]) if checkpoint_dict["metadata"] else {}
        return EnrichmentCheckpoint.from_dict(checkpoint_dict)

    def load_all(self) -> pd.DataFrame:
        """Load all checkpoints.

        Returns:
            DataFrame with all checkpoints
        """
        if not self.parquet_path.exists():
            return pd.DataFrame()

        try:
            df = pd.read_parquet(self.parquet_path)
            # Convert datetime columns
            for col in ["last_success_timestamp", "checkpoint_timestamp"]:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col])
            # metadata is stored as JSON string, keep as string for now
            # (will be parsed in from_dict)
            return df
        except Exception as e:
            logger.error(f"Failed to load checkpoints: {e}")
            return pd.DataFrame()

    def save_all(self, df: pd.DataFrame) -> None:
        """Save all checkpoints.

        Args:
            df: DataFrame with all checkpoints
        """
        try:
            self.parquet_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(self.parquet_path, index=False, engine="pyarrow")
        except Exception as e:
            logger.error(f"Failed to save checkpoints: {e}")
            raise

    def delete_checkpoint(self, partition_id: str, source: str) -> None:
        """Delete a checkpoint.

        Args:
            partition_id: Partition identifier
            source: Enrichment source name
        """
        df = self.load_all()
        if df.empty:
            return

        mask = ~((df["partition_id"] == partition_id) & (df["source"] == source))
        df = df[mask]
        self.save_all(df)
