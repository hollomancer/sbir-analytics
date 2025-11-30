"""Tests for chunked enrichment module-level functions."""

from unittest.mock import Mock, patch

import pandas as pd
import pytest

from src.enrichers.chunked_enrichment import (
    combine_enriched_chunks,
    create_dynamic_outputs_enrichment,
)
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
    config.enrichment.performance.chunk_size = 2
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


class TestCombineEnrichedChunks:
    """Tests for combine_enriched_chunks function."""

    def test_combine_multiple_chunks(self, sample_sbir_df):
        """Test combining multiple enriched chunks."""
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

    def test_combine_empty_list(self):
        """Test combining empty list of chunks."""
        combined_df, metrics = combine_enriched_chunks([])

        assert len(combined_df) == 0
        assert "error" in metrics

    def test_combine_single_chunk(self, sample_sbir_df):
        """Test combining single chunk."""
        chunk = sample_sbir_df.copy()
        chunk["_usaspending_match_method"] = ["exact_uei"] * len(sample_sbir_df)

        combined_df, metrics = combine_enriched_chunks([chunk])

        assert len(combined_df) == 5
        assert metrics["chunks_combined"] == 1
        assert metrics["match_rate"] == 1.0

    def test_combine_all_unmatched(self, sample_sbir_df):
        """Test combining chunks with no matches."""
        chunk = sample_sbir_df.copy()
        chunk["_usaspending_match_method"] = [None] * len(sample_sbir_df)

        combined_df, metrics = combine_enriched_chunks([chunk])

        assert metrics["total_matched"] == 0
        assert metrics["match_rate"] == 0.0


class TestCreateDynamicOutputsEnrichment:
    """Tests for create_dynamic_outputs_enrichment generator."""

    @patch("src.enrichers.chunked_enrichment.get_config")
    @patch("src.enrichers.chunked_enrichment.enrich_sbir_with_usaspending")
    @patch("src.enrichers.chunked_enrichment.performance_monitor")
    def test_yields_chunk_tuples(
        self,
        mock_perf_monitor,
        mock_enrich,
        mock_get_config,
        mock_config,
        sample_sbir_df,
        sample_recipient_df,
    ):
        """Test generator yields (chunk_id, enriched_chunk) tuples."""
        mock_get_config.return_value = mock_config

        enriched_df = sample_sbir_df.copy()
        enriched_df["_usaspending_match_method"] = ["exact_uei"] * len(sample_sbir_df)
        mock_enrich.return_value = enriched_df

        results = list(create_dynamic_outputs_enrichment(sample_sbir_df, sample_recipient_df))

        assert len(results) == 3
        assert results[0][0] == 0
        assert results[1][0] == 1
        assert results[2][0] == 2
        assert isinstance(results[0][1], pd.DataFrame)

    @patch("src.enrichers.chunked_enrichment.get_config")
    @patch("src.enrichers.chunked_enrichment.enrich_sbir_with_usaspending")
    @patch("src.enrichers.chunked_enrichment.performance_monitor")
    def test_processes_all_records(
        self,
        mock_perf_monitor,
        mock_enrich,
        mock_get_config,
        mock_config,
        sample_sbir_df,
        sample_recipient_df,
    ):
        """Test all records are processed across chunks."""
        mock_get_config.return_value = mock_config

        enriched_df = sample_sbir_df.copy()
        enriched_df["_usaspending_match_method"] = ["exact_uei"] * len(sample_sbir_df)
        mock_enrich.return_value = enriched_df

        results = list(create_dynamic_outputs_enrichment(sample_sbir_df, sample_recipient_df))

        total_records = sum(len(chunk) for _, chunk in results)
        assert total_records == len(sample_sbir_df)
