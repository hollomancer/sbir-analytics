"""Tests for ChunkedEnricher initialization and core functionality."""

from unittest.mock import Mock, patch

import pandas as pd
import pytest

from src.enrichers.chunked_enrichment import ChunkedEnricher
from tests.utils.config_mocks import create_mock_pipeline_config


pytestmark = pytest.mark.fast


@pytest.fixture
def mock_config():
    """Mock configuration for testing."""
    config = create_mock_pipeline_config()
    if not hasattr(config, "enrichment"):
        config.enrichment = Mock()
    if not hasattr(config.enrichment, "performance"):
        config.enrichment.performance = Mock()
    config.enrichment.performance.chunk_size = 100
    config.enrichment.performance.memory_threshold_mb = 512
    config.enrichment.performance.timeout_seconds = 300
    config.enrichment.performance.high_confidence_threshold = 0.95
    config.enrichment.performance.low_confidence_threshold = 0.85
    config.enrichment.performance.enable_memory_monitoring = True
    config.enrichment.performance.enable_fuzzy_matching = True
    return config


@pytest.fixture
def sample_sbir_df():
    """Sample SBIR DataFrame."""
    return pd.DataFrame(
        {
            "award_id": [f"AWD-{i}" for i in range(5)],
            "company_name": [f"Company {i}" for i in range(5)],
            "company_uei": [f"UEI{i:09d}" for i in range(5)],
        }
    )


@pytest.fixture
def sample_recipient_df():
    """Sample recipient DataFrame."""
    return pd.DataFrame(
        {
            "recipient_name": ["Acme Corp", "TechStart Inc"],
            "recipient_uei": ["UEI000000001", "UEI000000002"],
        }
    )


@pytest.fixture
def temp_checkpoint_dir(tmp_path):
    """Temporary checkpoint directory."""
    checkpoint_dir = tmp_path / "checkpoints"
    checkpoint_dir.mkdir()
    return checkpoint_dir


class TestChunkedEnricherInitialization:
    """Tests for ChunkedEnricher initialization."""

    @patch("src.enrichers.chunked_enrichment.get_config")
    def test_initialization(
        self, mock_get_config, mock_config, sample_sbir_df, sample_recipient_df
    ):
        """Test ChunkedEnricher initialization."""
        mock_get_config.return_value = mock_config

        enricher = ChunkedEnricher(sample_sbir_df, sample_recipient_df)

        assert enricher.sbir_df is not None
        assert enricher.recipient_df is not None
        assert enricher.chunk_size == 100
        assert enricher.progress is not None
        assert enricher.progress.total_records == 5

    @patch("src.enrichers.chunked_enrichment.get_config")
    def test_initialization_with_checkpoint_dir(
        self, mock_get_config, mock_config, sample_sbir_df, sample_recipient_df, temp_checkpoint_dir
    ):
        """Test initialization with checkpoint directory."""
        mock_get_config.return_value = mock_config

        enricher = ChunkedEnricher(
            sample_sbir_df, sample_recipient_df, checkpoint_dir=temp_checkpoint_dir
        )

        assert enricher.progress.checkpoint_dir == temp_checkpoint_dir

    @patch("src.enrichers.chunked_enrichment.get_config")
    def test_initialization_with_custom_chunk_size(
        self, mock_get_config, mock_config, sample_sbir_df, sample_recipient_df
    ):
        """Test initialization with custom chunk size."""
        mock_get_config.return_value = mock_config

        enricher = ChunkedEnricher(sample_sbir_df, sample_recipient_df, chunk_size=50)

        assert enricher.chunk_size == 50


class TestChunkGeneration:
    """Tests for chunk generation."""

    @patch("src.enrichers.chunked_enrichment.get_config")
    def test_generate_chunks(
        self, mock_get_config, mock_config, sample_sbir_df, sample_recipient_df
    ):
        """Test chunk generation."""
        mock_get_config.return_value = mock_config
        mock_config.enrichment.performance.chunk_size = 2

        enricher = ChunkedEnricher(sample_sbir_df, sample_recipient_df)
        chunks = list(enricher.generate_chunks())

        assert len(chunks) == 3
        assert len(chunks[0]) == 2
        assert len(chunks[1]) == 2
        assert len(chunks[2]) == 1

    @patch("src.enrichers.chunked_enrichment.get_config")
    def test_generate_chunks_single_chunk(
        self, mock_get_config, mock_config, sample_sbir_df, sample_recipient_df
    ):
        """Test chunk generation with single chunk."""
        mock_get_config.return_value = mock_config
        mock_config.enrichment.performance.chunk_size = 100

        enricher = ChunkedEnricher(sample_sbir_df, sample_recipient_df)
        chunks = list(enricher.generate_chunks())

        assert len(chunks) == 1
        assert len(chunks[0]) == 5


class TestMemoryEstimation:
    """Tests for memory usage estimation."""

    @pytest.mark.parametrize(
        "sbir_records,recipient_records,chunk_size",
        [
            (10000, 5000, 1000),
            (100, 50, 10),
            (1000000, 500000, 10000),
        ],
        ids=["medium", "small", "large"],
    )
    def test_estimate_memory_usage(self, sbir_records, recipient_records, chunk_size):
        """Test memory usage estimation."""
        estimates = ChunkedEnricher.estimate_memory_usage(
            sbir_records=sbir_records,
            recipient_records=recipient_records,
            chunk_size=chunk_size,
        )

        assert "sbir_memory_mb" in estimates
        assert "recipient_memory_mb" in estimates
        assert "chunk_working_memory_mb" in estimates
        assert "peak_memory_mb" in estimates
        assert estimates["chunk_size"] == chunk_size
        assert estimates["sbir_memory_mb"] > 0
        assert estimates["recipient_memory_mb"] > 0


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
        enricher.memory_pressure_warnings = 1
        enricher.chunk_size_reductions = 0
        enricher.chunks_spilled = 0
        enricher.current_chunk_size = 100

        metadata = enricher.get_progress_metadata()

        assert metadata["progress_records_processed"] == 250
        assert metadata["progress_total_records"] == 5
        assert metadata["progress_chunks_processed"] == 2
        assert "progress_elapsed_seconds" in metadata
