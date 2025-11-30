"""Tests for ChunkProgress dataclass and progress tracking."""

import json
from datetime import datetime, timedelta

import pytest

from src.enrichers.chunked_enrichment import ChunkProgress


pytestmark = pytest.mark.fast


@pytest.fixture
def temp_checkpoint_dir(tmp_path):
    """Temporary checkpoint directory."""
    checkpoint_dir = tmp_path / "checkpoints"
    checkpoint_dir.mkdir()
    return checkpoint_dir


class TestChunkProgressInit:
    """Tests for ChunkProgress initialization."""

    def test_initialization(self):
        """Test ChunkProgress initialization."""
        progress = ChunkProgress(total_records=1000, chunk_size=100)

        assert progress.total_records == 1000
        assert progress.chunk_size == 100
        assert progress.chunks_processed == 0
        assert progress.records_processed == 0
        assert isinstance(progress.start_time, datetime)
        assert progress.last_checkpoint is None
        assert progress.errors == []
        assert progress.checkpoint_dir is None


class TestChunkProgressCalculations:
    """Tests for ChunkProgress calculations."""

    @pytest.mark.parametrize(
        "total,chunk_size,expected",
        [
            (1000, 100, 10),
            (1050, 100, 11),
            (500, 50, 10),
            (1, 100, 1),
            (0, 100, 0),
        ],
        ids=["exact", "partial", "exact_50", "single", "zero"],
    )
    def test_total_chunks_calculation(self, total, chunk_size, expected):
        """Test total chunks calculation."""
        progress = ChunkProgress(total_records=total, chunk_size=chunk_size)
        assert progress.total_chunks == expected

    @pytest.mark.parametrize(
        "total,processed,expected",
        [
            (1000, 0, 0.0),
            (1000, 500, 50.0),
            (1000, 1000, 100.0),
            (0, 0, 0.0),
        ],
        ids=["zero_pct", "half", "complete", "zero_total"],
    )
    def test_percent_complete(self, total, processed, expected):
        """Test percent complete calculation."""
        progress = ChunkProgress(total_records=total, chunk_size=100)
        progress.records_processed = processed
        assert progress.percent_complete == expected

    def test_elapsed_seconds(self):
        """Test elapsed seconds calculation."""
        start_time = datetime.now() - timedelta(seconds=10)
        progress = ChunkProgress(total_records=1000, chunk_size=100)
        progress.start_time = start_time

        elapsed = progress.elapsed_seconds
        assert 10.0 <= elapsed < 15.0

    def test_estimated_remaining_seconds(self):
        """Test estimated remaining time calculation."""
        progress = ChunkProgress(total_records=1000, chunk_size=100)
        progress.start_time = datetime.now() - timedelta(seconds=10)
        progress.records_processed = 500

        remaining = progress.estimated_remaining_seconds
        assert 8.0 <= remaining <= 12.0

    def test_estimated_remaining_seconds_no_progress(self):
        """Test estimated remaining with no progress."""
        progress = ChunkProgress(total_records=1000, chunk_size=100)
        assert progress.estimated_remaining_seconds == 0.0


class TestChunkProgressCheckpoints:
    """Tests for ChunkProgress checkpoint functionality."""

    def test_save_checkpoint_no_directory(self):
        """Test checkpoint save with no directory."""
        progress = ChunkProgress(total_records=1000, chunk_size=100)
        result = progress.save_checkpoint({"test": "data"})
        assert result is None

    def test_save_checkpoint_success(self, temp_checkpoint_dir):
        """Test successful checkpoint save."""
        progress = ChunkProgress(
            total_records=1000,
            chunk_size=100,
            checkpoint_dir=temp_checkpoint_dir,
        )
        progress.chunks_processed = 5
        progress.records_processed = 500

        metadata = {"test_key": "test_value"}
        checkpoint_path = progress.save_checkpoint(metadata)

        assert checkpoint_path is not None
        assert checkpoint_path.exists()
        assert checkpoint_path.name == "checkpoint_0005.json"

        with open(checkpoint_path) as f:
            data = json.load(f)

        assert data["chunks_processed"] == 5
        assert data["records_processed"] == 500
        assert data["percent_complete"] == 50.0
        assert data["metadata"] == metadata
        assert progress.last_checkpoint is not None

    def test_save_checkpoint_creates_directory(self, tmp_path):
        """Test checkpoint save creates directory if needed."""
        checkpoint_dir = tmp_path / "new_checkpoints"
        assert not checkpoint_dir.exists()

        progress = ChunkProgress(
            total_records=1000,
            chunk_size=100,
            checkpoint_dir=checkpoint_dir,
        )

        checkpoint_path = progress.save_checkpoint({})
        assert checkpoint_dir.exists()
        assert checkpoint_path.exists()

    def test_log_progress(self):
        """Test progress logging doesn't crash."""
        progress = ChunkProgress(total_records=1000, chunk_size=100)
        progress.chunks_processed = 5
        progress.records_processed = 500
        progress.log_progress()

        assert progress.records_processed == 500
