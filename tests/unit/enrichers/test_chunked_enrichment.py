"""Tests for chunked enrichment processor."""

import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from src.enrichers.chunked_enrichment import (
    ChunkedEnricher,
    ChunkProgress,
    combine_enriched_chunks,
    create_dynamic_outputs_enrichment,
)
from src.exceptions import EnrichmentError


# ==================== Fixtures ====================

pytestmark = pytest.mark.fast
# Note: Fixtures (mock_enrichment_config, sample_sbir_df, sample_recipient_df)
# are now in tests/unit/enrichers/conftest.py and automatically available

from tests.utils.config_mocks import create_mock_pipeline_config


@pytest.fixture
def mock_config():
    """Mock configuration for testing."""

    config = create_mock_pipeline_config()
    # Ensure enrichment.performance exists with all required attributes
    if not hasattr(config, "enrichment"):
        config.enrichment = Mock()
    if not hasattr(config.enrichment, "performance"):
        config.enrichment.performance = Mock()
    # Set all required performance attributes
    config.enrichment.performance.chunk_size = 100
    config.enrichment.performance.memory_threshold_mb = 512
    config.enrichment.performance.timeout_seconds = 300
    config.enrichment.performance.high_confidence_threshold = 0.95
    config.enrichment.performance.low_confidence_threshold = 0.85
    config.enrichment.performance.enable_memory_monitoring = True
    config.enrichment.performance.enable_fuzzy_matching = True
    return config


@pytest.fixture
def temp_checkpoint_dir(tmp_path):
    """Temporary checkpoint directory."""
    checkpoint_dir = tmp_path / "checkpoints"
    checkpoint_dir.mkdir()
    return checkpoint_dir


# ==================== ChunkProgress Tests ====================


class TestChunkProgress:
    """Tests for ChunkProgress dataclass."""

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

    def test_total_chunks_calculation(self):
        """Test total chunks calculation."""
        progress = ChunkProgress(total_records=1000, chunk_size=100)
        assert progress.total_chunks == 10

        # Test with partial last chunk
        progress = ChunkProgress(total_records=1050, chunk_size=100)
        assert progress.total_chunks == 11

        # Test exact division
        progress = ChunkProgress(total_records=500, chunk_size=50)
        assert progress.total_chunks == 10

    def test_total_chunks_edge_cases(self):
        """Test total chunks calculation edge cases."""
        # Single record
        progress = ChunkProgress(total_records=1, chunk_size=100)
        assert progress.total_chunks == 1

        # Zero records
        progress = ChunkProgress(total_records=0, chunk_size=100)
        assert progress.total_chunks == 0

    def test_percent_complete(self):
        """Test percent complete calculation."""
        progress = ChunkProgress(total_records=1000, chunk_size=100)

        # 0% complete
        assert progress.percent_complete == 0.0

        # 50% complete
        progress.records_processed = 500
        assert progress.percent_complete == 50.0

        # 100% complete
        progress.records_processed = 1000
        assert progress.percent_complete == 100.0

    def test_percent_complete_zero_total(self):
        """Test percent complete with zero total records."""
        progress = ChunkProgress(total_records=0, chunk_size=100)
        assert progress.percent_complete == 0.0

    def test_elapsed_seconds(self):
        """Test elapsed seconds calculation."""
        # Create progress with known start time
        start_time = datetime.now() - timedelta(seconds=10)
        progress = ChunkProgress(total_records=1000, chunk_size=100)
        progress.start_time = start_time

        elapsed = progress.elapsed_seconds
        assert elapsed >= 10.0
        assert elapsed < 15.0  # Allow some tolerance

    def test_estimated_remaining_seconds(self):
        """Test estimated remaining time calculation."""
        progress = ChunkProgress(total_records=1000, chunk_size=100)
        progress.start_time = datetime.now() - timedelta(seconds=10)
        progress.records_processed = 500

        # Should estimate roughly 10 more seconds (50% done, took 10s)
        remaining = progress.estimated_remaining_seconds
        assert remaining >= 8.0
        assert remaining <= 12.0

    def test_estimated_remaining_seconds_no_progress(self):
        """Test estimated remaining with no progress."""
        progress = ChunkProgress(total_records=1000, chunk_size=100)
        assert progress.estimated_remaining_seconds == 0.0

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

        # Verify contents
        with open(checkpoint_path) as f:
            data = json.load(f)

        assert data["chunks_processed"] == 5
        assert data["records_processed"] == 500
        assert data["percent_complete"] == 50.0
        assert data["metadata"] == metadata
        assert "timestamp" in data
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

    def test_log_progress(self, capsys):
        """Test progress logging."""
        progress = ChunkProgress(total_records=1000, chunk_size=100)
        progress.chunks_processed = 5
        progress.records_processed = 500

        progress.log_progress()

        captured = capsys.readouterr()
        # Loguru writes to stderr
        assert "50.0%" in captured.err
        assert "500/1000 records" in captured.err
        assert "5/10 chunks" in captured.err


# ==================== ChunkedEnricher Initialization Tests ====================


class TestChunkedEnricherInitialization:
    """Tests for ChunkedEnricher initialization."""

    @patch("src.enrichers.chunked_enrichment.get_config")
    def test_initialization(
        self, mock_get_config, mock_config, sample_sbir_df, sample_recipient_df
    ):
        """Test ChunkedEnricher initialization."""
        mock_get_config.return_value = mock_config

        enricher = ChunkedEnricher(
            sbir_df=sample_sbir_df,
            recipient_df=sample_recipient_df,
        )

        assert len(enricher.sbir_df) == 5
        assert len(enricher.recipient_df) == 4
        assert enricher.chunk_size == 100
        assert enricher.memory_threshold_mb == 512
        assert enricher.timeout_seconds == 300
        assert enricher.high_threshold == 0.95
        assert enricher.low_threshold == 0.85
        assert enricher.enable_memory_monitoring is True
        assert enricher.enable_fuzzy_matching is True
        assert enricher.progress.total_records == 5
        assert enricher.checkpoint_dir is None

    @patch("src.enrichers.chunked_enrichment.get_config")
    def test_initialization_with_checkpoint_dir(
        self, mock_get_config, mock_config, sample_sbir_df, sample_recipient_df, temp_checkpoint_dir
    ):
        """Test initialization with checkpoint directory."""
        mock_get_config.return_value = mock_config

        enricher = ChunkedEnricher(
            sbir_df=sample_sbir_df,
            recipient_df=sample_recipient_df,
            checkpoint_dir=temp_checkpoint_dir,
        )

        assert enricher.checkpoint_dir == temp_checkpoint_dir
        assert enricher.progress.checkpoint_dir == temp_checkpoint_dir

    @patch("src.enrichers.chunked_enrichment.get_config")
    def test_initialization_progress_tracking_disabled(
        self, mock_get_config, mock_config, sample_sbir_df, sample_recipient_df, temp_checkpoint_dir
    ):
        """Test initialization with progress tracking disabled."""
        mock_get_config.return_value = mock_config

        enricher = ChunkedEnricher(
            sbir_df=sample_sbir_df,
            recipient_df=sample_recipient_df,
            checkpoint_dir=temp_checkpoint_dir,
            enable_progress_tracking=False,
        )

        assert enricher.checkpoint_dir is None
        assert enricher.enable_progress_tracking is False


# ==================== Chunk Generation Tests ====================


class TestChunkGeneration:
    """Tests for chunk generation."""

    @patch("src.enrichers.chunked_enrichment.get_config")
    def test_chunk_generator_single_chunk(
        self, mock_get_config, mock_config, sample_sbir_df, sample_recipient_df
    ):
        """Test chunk generator with data smaller than chunk size."""
        mock_get_config.return_value = mock_config
        mock_config.enrichment.performance.chunk_size = 100

        enricher = ChunkedEnricher(sample_sbir_df, sample_recipient_df)
        chunks = list(enricher.chunk_generator())

        assert len(chunks) == 1
        assert len(chunks[0]) == 5

    @patch("src.enrichers.chunked_enrichment.get_config")
    def test_chunk_generator_multiple_chunks(
        self, mock_get_config, mock_config, sample_recipient_df
    ):
        """Test chunk generator with multiple chunks."""
        # Create larger DataFrame
        large_df = pd.DataFrame(
            {
                "Award Number": [f"AWD{i:03d}" for i in range(250)],
                "Company": [f"Company {i}" for i in range(250)],
            }
        )

        mock_get_config.return_value = mock_config
        mock_config.enrichment.performance.chunk_size = 100

        enricher = ChunkedEnricher(large_df, sample_recipient_df)
        chunks = list(enricher.chunk_generator())

        assert len(chunks) == 3
        assert len(chunks[0]) == 100
        assert len(chunks[1]) == 100
        assert len(chunks[2]) == 50  # Partial last chunk

    @patch("src.enrichers.chunked_enrichment.get_config")
    def test_chunk_generator_exact_division(
        self, mock_get_config, mock_config, sample_recipient_df
    ):
        """Test chunk generator with exact division."""
        # Create DataFrame with exact multiple of chunk size
        df = pd.DataFrame(
            {
                "Award Number": [f"AWD{i:03d}" for i in range(200)],
                "Company": [f"Company {i}" for i in range(200)],
            }
        )

        mock_get_config.return_value = mock_config
        mock_config.enrichment.performance.chunk_size = 100

        enricher = ChunkedEnricher(df, sample_recipient_df)
        chunks = list(enricher.chunk_generator())

        assert len(chunks) == 2
        assert all(len(chunk) == 100 for chunk in chunks)

    @patch("src.enrichers.chunked_enrichment.get_config")
    def test_chunk_generator_empty_dataframe(self, mock_get_config, mock_config):
        """Test chunk generator with empty DataFrame."""
        empty_df = pd.DataFrame()
        mock_get_config.return_value = mock_config

        enricher = ChunkedEnricher(empty_df, empty_df)
        chunks = list(enricher.chunk_generator())

        assert len(chunks) == 0


# ==================== Single Chunk Enrichment Tests ====================


class TestEnrichChunk:
    """Tests for single chunk enrichment."""

    @patch("src.enrichers.chunked_enrichment.get_config")
    @patch("src.enrichers.chunked_enrichment.enrich_sbir_with_usaspending")
    @patch("src.enrichers.chunked_enrichment.performance_monitor")
    def test_enrich_chunk_success(
        self,
        mock_perf_monitor,
        mock_enrich,
        mock_get_config,
        mock_config,
        sample_sbir_df,
        sample_recipient_df,
    ):
        """Test successful chunk enrichment."""
        mock_get_config.return_value = mock_config

        # Mock enrichment to return only the chunk being processed
        def mock_enrich_func(chunk_df, *args, **kwargs):
            enriched = chunk_df.copy()
            # Add match method column based on chunk size
            enriched["_usaspending_match_method"] = ["exact_uei", "exact_uei", "fuzzy_name"][
                : len(chunk_df)
            ]
            return enriched

        mock_enrich.side_effect = mock_enrich_func

        # Mock performance monitor context

        enricher = ChunkedEnricher(sample_sbir_df, sample_recipient_df)
        result_df, metrics = enricher.enrich_chunk(sample_sbir_df.iloc[:3], chunk_num=1)

        assert len(result_df) == 3
        assert metrics["success"] is True
        assert metrics["chunk_num"] == 1
        assert metrics["chunk_size"] == 3
        assert metrics["records_matched"] == 2
        assert metrics["match_rate"] == pytest.approx(2 / 3)
        assert metrics["exact_matches"] == 2
        assert metrics["fuzzy_matches"] == 1
        assert "duration_seconds" in metrics

    @patch("src.enrichers.chunked_enrichment.get_config")
    @patch("src.enrichers.chunked_enrichment.enrich_sbir_with_usaspending")
    @patch("src.enrichers.chunked_enrichment.performance_monitor")
    def test_enrich_chunk_no_matches(
        self,
        mock_perf_monitor,
        mock_enrich,
        mock_get_config,
        mock_config,
        sample_sbir_df,
        sample_recipient_df,
    ):
        """Test chunk enrichment with no matches."""
        mock_get_config.return_value = mock_config

        # Mock enrichment with no matches
        enriched_df = sample_sbir_df.copy()
        enriched_df["_usaspending_match_method"] = [None, None, None, None, None]
        mock_enrich.return_value = enriched_df

        enricher = ChunkedEnricher(sample_sbir_df, sample_recipient_df)
        result_df, metrics = enricher.enrich_chunk(sample_sbir_df, chunk_num=0)

        assert metrics["records_matched"] == 0
        assert metrics["match_rate"] == 0.0
        assert metrics["exact_matches"] == 0
        assert metrics["fuzzy_matches"] == 0

    @patch("src.enrichers.chunked_enrichment.get_config")
    @patch("src.enrichers.chunked_enrichment.enrich_sbir_with_usaspending")
    @patch("src.enrichers.chunked_enrichment.performance_monitor")
    def test_enrich_chunk_error(
        self,
        mock_perf_monitor,
        mock_enrich,
        mock_get_config,
        mock_config,
        sample_sbir_df,
        sample_recipient_df,
    ):
        """Test chunk enrichment error handling."""
        mock_get_config.return_value = mock_config
        mock_enrich.side_effect = ValueError("Enrichment failed")

        enricher = ChunkedEnricher(sample_sbir_df, sample_recipient_df)

        with pytest.raises(ValueError, match="Enrichment failed"):
            enricher.enrich_chunk(sample_sbir_df, chunk_num=0)


# ==================== Retry Logic Tests ====================


class TestRetryLogic:
    """Tests for retry logic."""

    @patch("src.enrichers.chunked_enrichment.get_config")
    @patch("time.sleep")
    def test_enrich_with_retry_success_first_attempt(
        self, mock_sleep, mock_get_config, mock_config, sample_sbir_df, sample_recipient_df
    ):
        """Test retry succeeds on first attempt."""
        mock_get_config.return_value = mock_config

        enricher = ChunkedEnricher(sample_sbir_df, sample_recipient_df)

        # Mock enrich_chunk to succeed
        enriched_df = sample_sbir_df.copy()
        enriched_df["_usaspending_match_method"] = ["exact_uei"] * len(sample_sbir_df)
        metrics = {"success": True, "chunk_num": 0}

        with patch.object(enricher, "enrich_chunk", return_value=(enriched_df, metrics)):
            result_df, result_metrics = enricher.enrich_with_retry(sample_sbir_df, chunk_num=0)

        assert result_metrics["success"] is True
        mock_sleep.assert_not_called()

    @patch("src.enrichers.chunked_enrichment.get_config")
    @patch("time.sleep")
    def test_enrich_with_retry_success_second_attempt(
        self, mock_sleep, mock_get_config, mock_config, sample_sbir_df, sample_recipient_df
    ):
        """Test retry succeeds on second attempt."""
        mock_get_config.return_value = mock_config

        enricher = ChunkedEnricher(sample_sbir_df, sample_recipient_df)

        enriched_df = sample_sbir_df.copy()
        enriched_df["_usaspending_match_method"] = ["exact_uei"] * len(sample_sbir_df)
        metrics = {"success": True, "chunk_num": 0}

        # Fail first, succeed second
        with patch.object(
            enricher,
            "enrich_chunk",
            side_effect=[ValueError("Temporary error"), (enriched_df, metrics)],
        ):
            result_df, result_metrics = enricher.enrich_with_retry(sample_sbir_df, chunk_num=0)

        assert result_metrics["success"] is True
        mock_sleep.assert_called_once_with(1)  # 2^0 = 1

    @patch("src.enrichers.chunked_enrichment.get_config")
    @patch("time.sleep")
    def test_enrich_with_retry_all_attempts_fail(
        self, mock_sleep, mock_get_config, mock_config, sample_sbir_df, sample_recipient_df
    ):
        """Test retry fails after max attempts."""
        mock_get_config.return_value = mock_config

        enricher = ChunkedEnricher(sample_sbir_df, sample_recipient_df)

        with patch.object(enricher, "enrich_chunk", side_effect=ValueError("Persistent error")):
            with pytest.raises(EnrichmentError, match="Failed to enrich chunk 0 after 3 attempts"):
                enricher.enrich_with_retry(sample_sbir_df, chunk_num=0, max_retries=3)

        # Should sleep with exponential backoff: 2^0=1, 2^1=2
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1)
        mock_sleep.assert_any_call(2)


# ==================== Progress Tracking Tests ====================


class TestProgressTracking:
    """Tests for progress tracking and checkpointing."""

    @patch("src.enrichers.chunked_enrichment.get_config")
    @patch("src.enrichers.chunked_enrichment.enrich_sbir_with_usaspending")
    @patch("src.enrichers.chunked_enrichment.performance_monitor")
    def test_process_all_chunks_updates_progress(
        self,
        mock_perf_monitor,
        mock_enrich,
        mock_get_config,
        mock_config,
        sample_sbir_df,
        sample_recipient_df,
    ):
        """Test process_all_chunks updates progress."""
        mock_get_config.return_value = mock_config
        mock_config.enrichment.performance.chunk_size = 2

        enriched_df = sample_sbir_df.copy()
        enriched_df["_usaspending_match_method"] = ["exact_uei"] * len(sample_sbir_df)
        mock_enrich.return_value = enriched_df

        enricher = ChunkedEnricher(sample_sbir_df, sample_recipient_df)

        chunks_processed = 0
        for _enriched_chunk, _metrics in enricher.process_all_chunks():
            chunks_processed += 1

        # 5 records / 2 chunk_size = 3 chunks
        assert enricher.progress.chunks_processed == 3
        assert enricher.progress.records_processed == 5
        assert chunks_processed == 3

    @patch("src.enrichers.chunked_enrichment.get_config")
    @patch("src.enrichers.chunked_enrichment.enrich_sbir_with_usaspending")
    @patch("src.enrichers.chunked_enrichment.performance_monitor")
    def test_process_all_chunks_saves_checkpoints(
        self,
        mock_perf_monitor,
        mock_enrich,
        mock_get_config,
        mock_config,
        sample_sbir_df,
        sample_recipient_df,
        temp_checkpoint_dir,
    ):
        """Test process_all_chunks saves checkpoints."""
        mock_get_config.return_value = mock_config
        mock_config.enrichment.performance.chunk_size = 2

        enriched_df = sample_sbir_df.copy()
        enriched_df["_usaspending_match_method"] = ["exact_uei"] * len(sample_sbir_df)
        mock_enrich.return_value = enriched_df

        enricher = ChunkedEnricher(
            sample_sbir_df,
            sample_recipient_df,
            checkpoint_dir=temp_checkpoint_dir,
            enable_progress_tracking=True,
        )

        list(enricher.process_all_chunks())

        # Should have 3 checkpoint files
        checkpoints = list(temp_checkpoint_dir.glob("checkpoint_*.json"))
        assert len(checkpoints) == 3


# ==================== DataFrame Processing Tests ====================


class TestDataFrameProcessing:
    """Tests for DataFrame processing methods."""

    @patch("src.enrichers.chunked_enrichment.get_config")
    @patch("src.enrichers.chunked_enrichment.enrich_sbir_with_usaspending")
    @patch("src.enrichers.chunked_enrichment.performance_monitor")
    def test_process_to_dataframe(
        self,
        mock_perf_monitor,
        mock_enrich,
        mock_get_config,
        mock_config,
        sample_sbir_df,
        sample_recipient_df,
    ):
        """Test process_to_dataframe combines chunks."""
        mock_get_config.return_value = mock_config
        mock_config.enrichment.performance.chunk_size = 2

        # Mock should return the chunk it receives (identity function)
        def enrich_chunk(sbir_df, recipient_df, transaction_df=None, **kwargs):
            enriched = sbir_df.copy()
            # Add match method based on chunk
            enriched["_usaspending_match_method"] = ["exact_uei"] * len(sbir_df)
            return enriched

        mock_enrich.side_effect = enrich_chunk

        enricher = ChunkedEnricher(sample_sbir_df, sample_recipient_df)
        combined_df, metrics = enricher.process_to_dataframe()

        assert len(combined_df) == 5
        assert metrics["total_records"] == 5
        assert metrics["chunks_processed"] == 3
        assert metrics["errors"] == []
        assert "total_duration_seconds" in metrics
        assert "records_per_second" in metrics

    @patch("src.enrichers.chunked_enrichment.get_config")
    def test_process_to_dataframe_empty(self, mock_get_config, mock_config):
        """Test process_to_dataframe with empty DataFrame."""
        mock_get_config.return_value = mock_config

        empty_df = pd.DataFrame()
        enricher = ChunkedEnricher(empty_df, empty_df)

        combined_df, metrics = enricher.process_to_dataframe()

        assert len(combined_df) == 0
        assert metrics["total_records"] == 0
        assert metrics["overall_match_rate"] == 0

    @patch("src.enrichers.chunked_enrichment.get_config")
    @patch("src.enrichers.chunked_enrichment.enrich_sbir_with_usaspending")
    @patch("src.enrichers.chunked_enrichment.performance_monitor")
    def test_process_streaming(
        self,
        mock_perf_monitor,
        mock_enrich,
        mock_get_config,
        mock_config,
        sample_sbir_df,
        sample_recipient_df,
    ):
        """Test process_streaming yields chunks."""
        mock_get_config.return_value = mock_config
        mock_config.enrichment.performance.chunk_size = 2

        enriched_df = sample_sbir_df.copy()
        enriched_df["_usaspending_match_method"] = ["exact_uei"] * len(sample_sbir_df)
        mock_enrich.return_value = enriched_df

        enricher = ChunkedEnricher(sample_sbir_df, sample_recipient_df)

        chunks = list(enricher.process_streaming())

        assert len(chunks) == 3
        assert len(chunks[0]) == 2
        assert len(chunks[1]) == 2
        assert len(chunks[2]) == 1


# ==================== Checkpoint Management Tests ====================


class TestCheckpointManagement:
    """Tests for checkpoint loading and resumption."""

    @patch("src.enrichers.chunked_enrichment.get_config")
    def test_load_last_checkpoint_no_directory(
        self, mock_get_config, mock_config, sample_sbir_df, sample_recipient_df
    ):
        """Test load_last_checkpoint with no directory."""
        mock_get_config.return_value = mock_config

        enricher = ChunkedEnricher(sample_sbir_df, sample_recipient_df)
        result = enricher.load_last_checkpoint()

        assert result is None

    @patch("src.enrichers.chunked_enrichment.get_config")
    def test_load_last_checkpoint_empty_directory(
        self, mock_get_config, mock_config, sample_sbir_df, sample_recipient_df, temp_checkpoint_dir
    ):
        """Test load_last_checkpoint with empty directory."""
        mock_get_config.return_value = mock_config

        enricher = ChunkedEnricher(
            sample_sbir_df, sample_recipient_df, checkpoint_dir=temp_checkpoint_dir
        )
        result = enricher.load_last_checkpoint()

        assert result is None

    @patch("src.enrichers.chunked_enrichment.get_config")
    def test_load_last_checkpoint_success(
        self, mock_get_config, mock_config, sample_sbir_df, sample_recipient_df, temp_checkpoint_dir
    ):
        """Test successful checkpoint loading."""
        mock_get_config.return_value = mock_config

        # Create checkpoint files
        checkpoint1 = temp_checkpoint_dir / "checkpoint_0001.json"
        checkpoint2 = temp_checkpoint_dir / "checkpoint_0002.json"

        checkpoint1.write_text(json.dumps({"chunks_processed": 1, "records_processed": 100}))
        checkpoint2.write_text(json.dumps({"chunks_processed": 2, "records_processed": 200}))

        enricher = ChunkedEnricher(
            sample_sbir_df, sample_recipient_df, checkpoint_dir=temp_checkpoint_dir
        )
        result = enricher.load_last_checkpoint()

        # Should load most recent checkpoint
        assert result["chunks_processed"] == 2
        assert result["records_processed"] == 200

    @patch("src.enrichers.chunked_enrichment.get_config")
    def test_resume_from_checkpoint(
        self, mock_get_config, mock_config, sample_sbir_df, sample_recipient_df, temp_checkpoint_dir
    ):
        """Test resume from checkpoint."""
        mock_get_config.return_value = mock_config

        enricher = ChunkedEnricher(
            sample_sbir_df, sample_recipient_df, checkpoint_dir=temp_checkpoint_dir
        )

        checkpoint_data = {
            "chunks_processed": 5,
            "records_processed": 500,
            "timestamp": datetime.now().isoformat(),
        }

        resume_chunk = enricher.resume_from_checkpoint(checkpoint_data)

        assert resume_chunk == 5
        assert enricher.progress.chunks_processed == 5
        assert enricher.progress.records_processed == 500
        assert enricher.progress.last_checkpoint is not None

    @patch("src.enrichers.chunked_enrichment.get_config")
    def test_clear_checkpoints(
        self, mock_get_config, mock_config, sample_sbir_df, sample_recipient_df, temp_checkpoint_dir
    ):
        """Test checkpoint cleanup."""
        mock_get_config.return_value = mock_config

        # Create checkpoint files
        for i in range(3):
            checkpoint = temp_checkpoint_dir / f"checkpoint_{i:04d}.json"
            checkpoint.write_text(json.dumps({"test": "data"}))

        enricher = ChunkedEnricher(
            sample_sbir_df, sample_recipient_df, checkpoint_dir=temp_checkpoint_dir
        )
        enricher.clear_checkpoints()

        # All checkpoints should be removed
        checkpoints = list(temp_checkpoint_dir.glob("checkpoint_*.json"))
        assert len(checkpoints) == 0


# ==================== Progress Metadata Tests ====================


class TestProgressMetadata:
    """Tests for progress metadata."""

    @patch("src.enrichers.chunked_enrichment.get_config")
    def test_get_progress_metadata(
        self, mock_get_config, mock_config, sample_sbir_df, sample_recipient_df
    ):
        """Test get_progress_metadata returns complete info."""
        mock_get_config.return_value = mock_config

        enricher = ChunkedEnricher(sample_sbir_df, sample_recipient_df)
        enricher.progress.records_processed = 250
        enricher.progress.chunks_processed = 2

        # Mock attributes referenced in get_progress_metadata
        enricher.memory_pressure_warnings = 1
        enricher.chunk_size_reductions = 0
        enricher.chunks_spilled = 0
        enricher.current_chunk_size = 100

        metadata = enricher.get_progress_metadata()

        assert metadata["progress_records_processed"] == 250
        assert metadata["progress_total_records"] == 5
        assert metadata["progress_chunks_processed"] == 2
        assert metadata["progress_resumable"] is False
        assert "progress_elapsed_seconds" in metadata
        assert "progress_estimated_remaining_seconds" in metadata


# ==================== Memory Estimation Tests ====================


class TestMemoryEstimation:
    """Tests for memory usage estimation."""

    def test_estimate_memory_usage(self):
        """Test memory usage estimation."""
        estimates = ChunkedEnricher.estimate_memory_usage(
            sbir_records=10000,
            recipient_records=5000,
            chunk_size=1000,
        )

        assert "sbir_memory_mb" in estimates
        assert "recipient_memory_mb" in estimates
        assert "chunk_working_memory_mb" in estimates
        assert "peak_memory_mb" in estimates
        assert estimates["chunk_size"] == 1000

        # Verify calculations (rough estimates)
        assert estimates["sbir_memory_mb"] == pytest.approx(10000 / 1024)
        assert estimates["recipient_memory_mb"] == pytest.approx(5000 / 1024)

    def test_estimate_memory_usage_small_dataset(self):
        """Test memory estimation for small dataset."""
        estimates = ChunkedEnricher.estimate_memory_usage(
            sbir_records=100,
            recipient_records=50,
            chunk_size=10,
        )

        assert estimates["sbir_memory_mb"] > 0
        assert estimates["recipient_memory_mb"] > 0
        assert estimates["chunk_working_memory_mb"] > 0


# ==================== Module Functions Tests ====================


class TestModuleFunctions:
    """Tests for module-level functions."""

    @patch("src.enrichers.chunked_enrichment.get_config")
    @patch("src.enrichers.chunked_enrichment.enrich_sbir_with_usaspending")
    @patch("src.enrichers.chunked_enrichment.performance_monitor")
    def test_create_dynamic_outputs_enrichment(
        self,
        mock_perf_monitor,
        mock_enrich,
        mock_get_config,
        mock_config,
        sample_sbir_df,
        sample_recipient_df,
    ):
        """Test create_dynamic_outputs_enrichment generator."""
        mock_get_config.return_value = mock_config
        mock_config.enrichment.performance.chunk_size = 2

        enriched_df = sample_sbir_df.copy()
        enriched_df["_usaspending_match_method"] = ["exact_uei"] * len(sample_sbir_df)
        mock_enrich.return_value = enriched_df

        results = list(create_dynamic_outputs_enrichment(sample_sbir_df, sample_recipient_df))

        # Should yield (chunk_id, enriched_chunk) tuples
        assert len(results) == 3
        assert results[0][0] == 0  # First chunk ID
        assert results[1][0] == 1  # Second chunk ID
        assert results[2][0] == 2  # Third chunk ID
        assert isinstance(results[0][1], pd.DataFrame)

    def test_combine_enriched_chunks(self, sample_sbir_df):
        """Test combine_enriched_chunks function."""
        chunk1 = sample_sbir_df.iloc[:2].copy()
        chunk1["_usaspending_match_method"] = ["exact_uei", "fuzzy_name"]

        chunk2 = sample_sbir_df.iloc[2:].copy()
        chunk2["_usaspending_match_method"] = ["exact_uei", None, "exact_uei"]

        combined_df, metrics = combine_enriched_chunks([chunk1, chunk2])

        assert len(combined_df) == 5
        assert metrics["total_records"] == 5
        assert metrics["total_matched"] == 4
        assert metrics["match_rate"] == pytest.approx(0.8)
        assert metrics["chunks_combined"] == 2

    def test_combine_enriched_chunks_empty(self):
        """Test combine_enriched_chunks with empty list."""
        combined_df, metrics = combine_enriched_chunks([])

        assert len(combined_df) == 0
        assert "error" in metrics

    def test_combine_enriched_chunks_single_chunk(self, sample_sbir_df):
        """Test combine_enriched_chunks with single chunk."""
        chunk = sample_sbir_df.copy()
        chunk["_usaspending_match_method"] = ["exact_uei"] * len(sample_sbir_df)

        combined_df, metrics = combine_enriched_chunks([chunk])

        assert len(combined_df) == 5
        assert metrics["chunks_combined"] == 1


# ==================== Edge Cases and Error Handling ====================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.slow
    @patch("src.enrichers.chunked_enrichment.get_config")
    @patch("src.enrichers.chunked_enrichment.enrich_sbir_with_usaspending")
    @patch("src.enrichers.chunked_enrichment.performance_monitor")
    def test_process_all_chunks_with_error(
        self,
        mock_perf_monitor,
        mock_enrich,
        mock_get_config,
        mock_config,
        sample_sbir_df,
        sample_recipient_df,
        temp_checkpoint_dir,
    ):
        """Test process_all_chunks handles errors."""
        mock_get_config.return_value = mock_config
        mock_config.enrichment.performance.chunk_size = 2

        # Fail on second chunk
        enriched_df = sample_sbir_df.copy()
        enriched_df["_usaspending_match_method"] = ["exact_uei"] * len(sample_sbir_df)
        mock_enrich.side_effect = [enriched_df, ValueError("Chunk error"), enriched_df]

        enricher = ChunkedEnricher(
            sample_sbir_df, sample_recipient_df, checkpoint_dir=temp_checkpoint_dir
        )

        with pytest.raises(EnrichmentError):
            list(enricher.process_all_chunks())

        # Should have saved error checkpoint
        assert len(enricher.progress.errors) > 0

    @patch("src.enrichers.chunked_enrichment.get_config")
    def test_chunk_progress_with_checkpoint_io_error(
        self, mock_get_config, mock_config, sample_sbir_df, sample_recipient_df, tmp_path
    ):
        """Test checkpoint save handles IO errors gracefully."""
        mock_get_config.return_value = mock_config

        # Create read-only checkpoint directory
        checkpoint_dir = tmp_path / "readonly"
        checkpoint_dir.mkdir()
        checkpoint_dir.chmod(0o444)

        progress = ChunkProgress(
            total_records=1000,
            chunk_size=100,
            checkpoint_dir=checkpoint_dir,
        )

        # Should handle permission error gracefully
        try:
            progress.save_checkpoint({"test": "data"})
        except PermissionError:
            pass  # Expected on some systems
        finally:
            # Restore permissions for cleanup
            checkpoint_dir.chmod(0o755)

    @patch("src.enrichers.chunked_enrichment.get_config")
    def test_load_checkpoint_corrupt_json(
        self, mock_get_config, mock_config, sample_sbir_df, sample_recipient_df, temp_checkpoint_dir
    ):
        """Test load_last_checkpoint handles corrupt JSON."""
        mock_get_config.return_value = mock_config

        # Create corrupt checkpoint
        corrupt_checkpoint = temp_checkpoint_dir / "checkpoint_0001.json"
        corrupt_checkpoint.write_text("{invalid json")

        enricher = ChunkedEnricher(
            sample_sbir_df, sample_recipient_df, checkpoint_dir=temp_checkpoint_dir
        )
        result = enricher.load_last_checkpoint()

        # Should return None on error
        assert result is None
