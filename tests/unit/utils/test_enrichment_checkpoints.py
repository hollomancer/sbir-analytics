"""Unit tests for enrichment checkpoint management.

Tests cover:
- EnrichmentCheckpoint dataclass
- Checkpoint serialization/deserialization
- CheckpointStore initialization
- Checkpoint save/load operations
- Checkpoint updates
- Multiple checkpoint management
- Edge cases (empty data, missing files)
"""

from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from src.utils.enrichment_checkpoints import CheckpointStore, EnrichmentCheckpoint


pytestmark = pytest.mark.fast


@pytest.fixture
def sample_checkpoint():
    """Create a sample checkpoint."""
    return EnrichmentCheckpoint(
        partition_id="partition_001",
        source="usaspending",
        last_processed_award_id="AWARD-12345",
        last_success_timestamp=datetime(2024, 1, 1, 12, 0, 0),
        records_processed=1000,
        records_failed=10,
        records_total=1010,
        checkpoint_timestamp=datetime(2024, 1, 1, 12, 30, 0),
        metadata={"version": "1.0", "mode": "incremental"},
    )


@pytest.fixture
def checkpoint_store(tmp_path):
    """Create a checkpoint store with temp path."""
    return CheckpointStore(parquet_path=tmp_path / "checkpoints.parquet")


class TestEnrichmentCheckpoint:
    """Tests for EnrichmentCheckpoint dataclass."""

    def test_checkpoint_creation(self, sample_checkpoint):
        """Test creating a checkpoint."""
        assert sample_checkpoint.partition_id == "partition_001"
        assert sample_checkpoint.source == "usaspending"
        assert sample_checkpoint.records_processed == 1000
        assert sample_checkpoint.records_failed == 10
        assert sample_checkpoint.metadata["version"] == "1.0"

    def test_checkpoint_to_dict(self, sample_checkpoint):
        """Test converting checkpoint to dictionary."""
        data = sample_checkpoint.to_dict()

        assert isinstance(data, dict)
        assert data["partition_id"] == "partition_001"
        assert data["source"] == "usaspending"
        assert data["records_processed"] == 1000

        # Datetime should be converted to ISO string
        assert isinstance(data["last_success_timestamp"], str)
        assert isinstance(data["checkpoint_timestamp"], str)

        # Metadata should be JSON string
        assert isinstance(data["metadata"], str)
        assert '"version"' in data["metadata"]

    def test_checkpoint_from_dict(self, sample_checkpoint):
        """Test creating checkpoint from dictionary."""
        data = sample_checkpoint.to_dict()
        restored = EnrichmentCheckpoint.from_dict(data)

        assert restored.partition_id == sample_checkpoint.partition_id
        assert restored.source == sample_checkpoint.source
        assert restored.records_processed == sample_checkpoint.records_processed
        assert restored.metadata == sample_checkpoint.metadata

    def test_checkpoint_roundtrip(self, sample_checkpoint):
        """Test serialization/deserialization roundtrip."""
        data = sample_checkpoint.to_dict()
        restored = EnrichmentCheckpoint.from_dict(data)
        data2 = restored.to_dict()

        assert data == data2

    def test_checkpoint_with_none_values(self):
        """Test checkpoint with None values."""
        checkpoint = EnrichmentCheckpoint(
            partition_id="partition_002",
            source="test",
            last_processed_award_id=None,
            last_success_timestamp=None,
            records_processed=0,
            records_failed=0,
            records_total=0,
            checkpoint_timestamp=datetime.now(),
            metadata={},
        )

        data = checkpoint.to_dict()
        restored = EnrichmentCheckpoint.from_dict(data)

        assert restored.last_processed_award_id is None
        assert restored.last_success_timestamp is None

    def test_checkpoint_with_empty_metadata(self):
        """Test checkpoint with empty metadata."""
        checkpoint = EnrichmentCheckpoint(
            partition_id="partition_003",
            source="test",
            last_processed_award_id="AWARD-999",
            last_success_timestamp=datetime.now(),
            records_processed=100,
            records_failed=0,
            records_total=100,
            checkpoint_timestamp=datetime.now(),
            metadata={},
        )

        data = checkpoint.to_dict()

        assert data["metadata"] == "{}"

        restored = EnrichmentCheckpoint.from_dict(data)
        assert restored.metadata == {}


class TestCheckpointStoreInitialization:
    """Tests for CheckpointStore initialization."""

    def test_init_default_path(self):
        """Test initialization with default path."""
        store = CheckpointStore()

        assert store.parquet_path == Path("data/state/enrichment_checkpoints.parquet")

    def test_init_custom_path(self, tmp_path):
        """Test initialization with custom path."""
        custom_path = tmp_path / "custom_checkpoints.parquet"
        store = CheckpointStore(parquet_path=custom_path)

        assert store.parquet_path == custom_path

    def test_init_creates_directory(self, tmp_path):
        """Test that initialization creates parent directory."""
        checkpoint_path = tmp_path / "nested" / "path" / "checkpoints.parquet"
        CheckpointStore(parquet_path=checkpoint_path)

        assert checkpoint_path.parent.exists()


class TestCheckpointStoreSaveLoad:
    """Tests for checkpoint save and load operations."""

    def test_save_checkpoint(self, checkpoint_store, sample_checkpoint):
        """Test saving a checkpoint."""
        checkpoint_store.save_checkpoint(sample_checkpoint)

        # Verify file was created
        assert checkpoint_store.parquet_path.exists()

        # Verify can load it back
        loaded = checkpoint_store.load_checkpoint("partition_001", "usaspending")

        assert loaded is not None
        assert loaded.partition_id == "partition_001"
        assert loaded.records_processed == 1000

    def test_load_nonexistent_checkpoint(self, checkpoint_store):
        """Test loading checkpoint that doesn't exist."""
        loaded = checkpoint_store.load_checkpoint("nonexistent", "source")

        assert loaded is None

    def test_load_checkpoint_from_empty_store(self, checkpoint_store):
        """Test loading when no checkpoints exist."""
        loaded = checkpoint_store.load_checkpoint("partition_001", "usaspending")

        assert loaded is None

    def test_save_multiple_checkpoints(self, checkpoint_store):
        """Test saving multiple different checkpoints."""
        checkpoint1 = EnrichmentCheckpoint(
            partition_id="partition_001",
            source="usaspending",
            last_processed_award_id="AWARD-001",
            last_success_timestamp=datetime.now(),
            records_processed=100,
            records_failed=0,
            records_total=100,
            checkpoint_timestamp=datetime.now(),
            metadata={},
        )

        checkpoint2 = EnrichmentCheckpoint(
            partition_id="partition_002",
            source="sam_gov",
            last_processed_award_id="AWARD-002",
            last_success_timestamp=datetime.now(),
            records_processed=200,
            records_failed=0,
            records_total=200,
            checkpoint_timestamp=datetime.now(),
            metadata={},
        )

        checkpoint_store.save_checkpoint(checkpoint1)
        checkpoint_store.save_checkpoint(checkpoint2)

        # Both should be loadable
        loaded1 = checkpoint_store.load_checkpoint("partition_001", "usaspending")
        loaded2 = checkpoint_store.load_checkpoint("partition_002", "sam_gov")

        assert loaded1 is not None
        assert loaded2 is not None
        assert loaded1.records_processed == 100
        assert loaded2.records_processed == 200

    def test_update_existing_checkpoint(self, checkpoint_store, sample_checkpoint):
        """Test updating an existing checkpoint."""
        # Save initial checkpoint
        checkpoint_store.save_checkpoint(sample_checkpoint)

        # Update and save again
        sample_checkpoint.records_processed = 2000
        sample_checkpoint.last_processed_award_id = "AWARD-99999"
        checkpoint_store.save_checkpoint(sample_checkpoint)

        # Load and verify update
        loaded = checkpoint_store.load_checkpoint("partition_001", "usaspending")

        assert loaded.records_processed == 2000
        assert loaded.last_processed_award_id == "AWARD-99999"

    def test_load_all_empty(self, checkpoint_store):
        """Test loading all checkpoints when none exist."""
        df = checkpoint_store.load_all()

        assert isinstance(df, pd.DataFrame)
        assert df.empty

    def test_load_all_with_checkpoints(self, checkpoint_store):
        """Test loading all checkpoints."""
        checkpoint1 = EnrichmentCheckpoint(
            partition_id="partition_001",
            source="usaspending",
            last_processed_award_id="AWARD-001",
            last_success_timestamp=datetime.now(),
            records_processed=100,
            records_failed=0,
            records_total=100,
            checkpoint_timestamp=datetime.now(),
            metadata={},
        )

        checkpoint2 = EnrichmentCheckpoint(
            partition_id="partition_002",
            source="usaspending",
            last_processed_award_id="AWARD-002",
            last_success_timestamp=datetime.now(),
            records_processed=200,
            records_failed=0,
            records_total=200,
            checkpoint_timestamp=datetime.now(),
            metadata={},
        )

        checkpoint_store.save_checkpoint(checkpoint1)
        checkpoint_store.save_checkpoint(checkpoint2)

        df = checkpoint_store.load_all()

        assert len(df) == 2
        assert "partition_id" in df.columns
        assert "source" in df.columns

    def test_save_all(self, checkpoint_store):
        """Test saving all checkpoints DataFrame."""
        df = pd.DataFrame({
            "partition_id": ["p1", "p2"],
            "source": ["s1", "s2"],
            "last_processed_award_id": ["A1", "A2"],
            "last_success_timestamp": [datetime.now(), datetime.now()],
            "records_processed": [100, 200],
            "records_failed": [1, 2],
            "records_total": [101, 202],
            "checkpoint_timestamp": [datetime.now(), datetime.now()],
            "metadata": ["{}", "{}"],
        })

        checkpoint_store.save_all(df)

        assert checkpoint_store.parquet_path.exists()

        loaded_df = checkpoint_store.load_all()
        assert len(loaded_df) == 2


class TestCheckpointStoreFiltering:
    """Tests for checkpoint filtering and querying."""

    def test_get_checkpoints_by_source(self, checkpoint_store):
        """Test retrieving checkpoints by source."""
        # Create checkpoints for different sources
        for i in range(3):
            checkpoint = EnrichmentCheckpoint(
                partition_id=f"partition_{i:03d}",
                source="usaspending",
                last_processed_award_id=f"AWARD-{i}",
                last_success_timestamp=datetime.now(),
                records_processed=100 * (i + 1),
                records_failed=0,
                records_total=100 * (i + 1),
                checkpoint_timestamp=datetime.now(),
                metadata={},
            )
            checkpoint_store.save_checkpoint(checkpoint)

        for i in range(2):
            checkpoint = EnrichmentCheckpoint(
                partition_id=f"partition_{i:03d}",
                source="sam_gov",
                last_processed_award_id=f"AWARD-{i}",
                last_success_timestamp=datetime.now(),
                records_processed=50 * (i + 1),
                records_failed=0,
                records_total=50 * (i + 1),
                checkpoint_timestamp=datetime.now(),
                metadata={},
            )
            checkpoint_store.save_checkpoint(checkpoint)

        df = checkpoint_store.load_all()
        usaspending_checkpoints = df[df["source"] == "usaspending"]
        sam_gov_checkpoints = df[df["source"] == "sam_gov"]

        assert len(usaspending_checkpoints) == 3
        assert len(sam_gov_checkpoints) == 2


class TestCheckpointStoreEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_checkpoint_with_large_metadata(self, checkpoint_store):
        """Test checkpoint with large metadata."""
        large_metadata = {f"key_{i}": f"value_{i}" for i in range(100)}

        checkpoint = EnrichmentCheckpoint(
            partition_id="partition_large",
            source="test",
            last_processed_award_id="AWARD-LARGE",
            last_success_timestamp=datetime.now(),
            records_processed=1000,
            records_failed=0,
            records_total=1000,
            checkpoint_timestamp=datetime.now(),
            metadata=large_metadata,
        )

        checkpoint_store.save_checkpoint(checkpoint)
        loaded = checkpoint_store.load_checkpoint("partition_large", "test")

        assert loaded is not None
        assert len(loaded.metadata) == 100

    def test_checkpoint_with_special_characters(self, checkpoint_store):
        """Test checkpoint with special characters in metadata."""
        special_metadata = {
            "description": 'Test with "quotes" and \'apostrophes\'',
            "path": "C:\\Users\\Test\\Documents",
            "unicode": "Café résumé",
        }

        checkpoint = EnrichmentCheckpoint(
            partition_id="partition_special",
            source="test",
            last_processed_award_id="AWARD-SPECIAL",
            last_success_timestamp=datetime.now(),
            records_processed=100,
            records_failed=0,
            records_total=100,
            checkpoint_timestamp=datetime.now(),
            metadata=special_metadata,
        )

        checkpoint_store.save_checkpoint(checkpoint)
        loaded = checkpoint_store.load_checkpoint("partition_special", "test")

        assert loaded is not None
        assert loaded.metadata["description"] == special_metadata["description"]

    def test_delete_checkpoint(self, checkpoint_store, sample_checkpoint):
        """Test deleting a checkpoint."""
        checkpoint_store.save_checkpoint(sample_checkpoint)

        # Delete by filtering and saving
        df = checkpoint_store.load_all()
        df_filtered = df[
            ~((df["partition_id"] == "partition_001") & (df["source"] == "usaspending"))
        ]
        checkpoint_store.save_all(df_filtered)

        loaded = checkpoint_store.load_checkpoint("partition_001", "usaspending")
        assert loaded is None


class TestCheckpointStoreWorkflow:
    """Integration tests for complete checkpoint workflows."""

    def test_incremental_refresh_workflow(self, checkpoint_store):
        """Test complete incremental refresh workflow."""
        # Initial run
        initial_checkpoint = EnrichmentCheckpoint(
            partition_id="partition_001",
            source="usaspending",
            last_processed_award_id="AWARD-100",
            last_success_timestamp=datetime(2024, 1, 1),
            records_processed=100,
            records_failed=0,
            records_total=100,
            checkpoint_timestamp=datetime(2024, 1, 1),
            metadata={"batch": "1"},
        )
        checkpoint_store.save_checkpoint(initial_checkpoint)

        # Resume run - load checkpoint
        loaded = checkpoint_store.load_checkpoint("partition_001", "usaspending")
        assert loaded.last_processed_award_id == "AWARD-100"

        # Process more data
        loaded.last_processed_award_id = "AWARD-200"
        loaded.records_processed = 200
        loaded.records_total = 200
        loaded.checkpoint_timestamp = datetime(2024, 1, 2)
        loaded.metadata = {"batch": "2"}

        checkpoint_store.save_checkpoint(loaded)

        # Verify update
        final = checkpoint_store.load_checkpoint("partition_001", "usaspending")
        assert final.last_processed_award_id == "AWARD-200"
        assert final.records_processed == 200
        assert final.metadata["batch"] == "2"

    def test_multiple_source_management(self, checkpoint_store):
        """Test managing checkpoints for multiple sources."""
        sources = ["usaspending", "sam_gov", "fpds"]

        for source in sources:
            checkpoint = EnrichmentCheckpoint(
                partition_id="partition_001",
                source=source,
                last_processed_award_id=f"{source.upper()}-001",
                last_success_timestamp=datetime.now(),
                records_processed=100,
                records_failed=0,
                records_total=100,
                checkpoint_timestamp=datetime.now(),
                metadata={"source": source},
            )
            checkpoint_store.save_checkpoint(checkpoint)

        # Verify all sources are saved
        for source in sources:
            loaded = checkpoint_store.load_checkpoint("partition_001", source)
            assert loaded is not None
            assert loaded.source == source
