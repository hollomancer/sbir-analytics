"""Unit tests for enrichment checkpoint management."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from src.utils.enrichment_checkpoints import (
    CheckpointStore,
    EnrichmentCheckpoint,
)


@pytest.fixture
def checkpoint_store(tmp_path):
    """Create CheckpointStore for testing."""
    return CheckpointStore(parquet_path=tmp_path / "checkpoints.parquet")


@pytest.fixture
def sample_checkpoint():
    """Sample checkpoint for testing."""
    return EnrichmentCheckpoint(
        partition_id="partition_001",
        source="usaspending",
        last_processed_award_id="AWARD-050",
        last_success_timestamp=datetime.now(),
        records_processed=50,
        records_failed=2,
        records_total=100,
        checkpoint_timestamp=datetime.now(),
        metadata={"batch_number": 1},
    )


class TestEnrichmentCheckpoint:
    """Test EnrichmentCheckpoint dataclass."""

    def test_to_dict_serializes_datetimes(self, sample_checkpoint):
        """Test to_dict converts datetime to ISO string."""
        data = sample_checkpoint.to_dict()

        assert isinstance(data["last_success_timestamp"], str)
        assert isinstance(data["checkpoint_timestamp"], str)
        assert "T" in data["last_success_timestamp"]  # ISO format

    def test_from_dict_deserializes_datetimes(self, sample_checkpoint):
        """Test from_dict converts ISO string to datetime."""
        data = sample_checkpoint.to_dict()
        restored = EnrichmentCheckpoint.from_dict(data)

        assert isinstance(restored.last_success_timestamp, datetime)
        assert isinstance(restored.checkpoint_timestamp, datetime)
        assert restored.partition_id == sample_checkpoint.partition_id


class TestCheckpointStore:
    """Test CheckpointStore operations."""

    def test_save_and_load_checkpoint(self, checkpoint_store, sample_checkpoint):
        """Test saving and loading a checkpoint."""
        checkpoint_store.save_checkpoint(sample_checkpoint)

        loaded = checkpoint_store.load_checkpoint("partition_001", "usaspending")

        assert loaded is not None
        assert loaded.partition_id == sample_checkpoint.partition_id
        assert loaded.last_processed_award_id == sample_checkpoint.last_processed_award_id
        assert loaded.records_processed == sample_checkpoint.records_processed

    def test_save_checkpoint_updates_existing(self, checkpoint_store, sample_checkpoint):
        """Test saving updates existing checkpoint."""
        checkpoint_store.save_checkpoint(sample_checkpoint)

        # Update checkpoint
        updated = EnrichmentCheckpoint(
            partition_id="partition_001",
            source="usaspending",
            last_processed_award_id="AWARD-100",
            last_success_timestamp=datetime.now(),
            records_processed=100,
            records_failed=5,
            records_total=100,
            checkpoint_timestamp=datetime.now(),
            metadata={"batch_number": 2},
        )

        checkpoint_store.save_checkpoint(updated)

        loaded = checkpoint_store.load_checkpoint("partition_001", "usaspending")
        assert loaded.records_processed == 100
        assert loaded.last_processed_award_id == "AWARD-100"

    def test_load_all_returns_all_checkpoints(self, checkpoint_store):
        """Test load_all returns all saved checkpoints."""
        checkpoints = [
            EnrichmentCheckpoint(
                partition_id=f"partition_{i:03d}",
                source="usaspending",
                last_processed_award_id=f"AWARD-{i*10:03d}",
                last_success_timestamp=datetime.now(),
                records_processed=i * 10,
                records_failed=0,
                records_total=i * 10,
                checkpoint_timestamp=datetime.now(),
                metadata={},
            )
            for i in range(5)
        ]

        for checkpoint in checkpoints:
            checkpoint_store.save_checkpoint(checkpoint)

        df = checkpoint_store.load_all()
        assert len(df) == 5

    def test_load_checkpoint_returns_none_when_not_found(self, checkpoint_store):
        """Test load_checkpoint returns None for non-existent checkpoint."""
        result = checkpoint_store.load_checkpoint("nonexistent", "usaspending")
        assert result is None

    def test_delete_checkpoint(self, checkpoint_store, sample_checkpoint):
        """Test deleting a checkpoint."""
        checkpoint_store.save_checkpoint(sample_checkpoint)

        # Verify it exists
        assert checkpoint_store.load_checkpoint("partition_001", "usaspending") is not None

        # Delete it
        checkpoint_store.delete_checkpoint("partition_001", "usaspending")

        # Verify it's gone
        assert checkpoint_store.load_checkpoint("partition_001", "usaspending") is None

    def test_load_all_handles_missing_file(self, checkpoint_store):
        """Test load_all handles missing file gracefully."""
        # File doesn't exist yet
        df = checkpoint_store.load_all()
        assert len(df) == 0

