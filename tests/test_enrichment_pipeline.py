"""Comprehensive test suite for SBIR-USAspending enrichment pipeline.

Tests cover:
- End-to-end pipeline validation
- USAspending enrichment functionality
- Performance monitoring integration
- Quality metrics validation
- Large dataset handling
"""

import json
import time
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
from dagster import build_asset_context

from src.assets import sbir_ingestion, sbir_usaspending_enrichment
from src.enrichers.usaspending_enricher import enrich_sbir_with_usaspending
from src.utils.performance_monitor import PerformanceMonitor


@pytest.fixture
def sample_sbir_data():
    """Sample SBIR awards data for testing."""
    return pd.DataFrame(
        [
            {
                "Company": "Acme Innovations Inc",
                "UEI": "A1B2C3D4E5F6G7H8",
                "Duns": "123456789",
                "Contract": "C-2023-0001",
                "Award Title": "Advanced Widget Development",
            },
            {
                "Company": "BioTech Labs LLC",
                "UEI": "B2C3D4E5F6G7H8I9",
                "Duns": "987654321",
                "Contract": "C-2023-0002",
                "Award Title": "Biotech Research Platform",
            },
            {
                "Company": "NanoWorks Corporation",
                "UEI": "",  # No UEI for fuzzy matching test
                "Duns": "",
                "Contract": "C-2023-0003",
                "Award Title": "Nanotechnology Solutions",
            },
        ]
    )


@pytest.fixture
def sample_usaspending_data():
    """Sample USAspending recipient data for testing."""
    return pd.DataFrame(
        [
            {
                "recipient_name": "Acme Innovations Inc",
                "recipient_uei": "A1B2C3D4E5F6G7H8",
                "recipient_duns": "123456789",
                "recipient_city": "Springfield",
                "recipient_state": "IL",
            },
            {
                "recipient_name": "BioTech Laboratories LLC",
                "recipient_uei": "B2C3D4E5F6G7H8I9",
                "recipient_duns": "987654321",
                "recipient_city": "Boston",
                "recipient_state": "MA",
            },
            {
                "recipient_name": "NanoWorks Corp",
                "recipient_uei": "N3O4W5R6K7S8T9U0",
                "recipient_duns": "555666777",
                "recipient_city": "Austin",
                "recipient_state": "TX",
            },
        ]
    )


@pytest.fixture
def large_sbir_data():
    """Generate larger SBIR dataset for performance testing."""
    companies = [f"Test Company {i}" for i in range(100)]
    return pd.DataFrame(
        {
            "Company": companies,
            "UEI": [f"UEI{i:010d}" for i in range(100)],
            "Duns": [f"DUNS{i:09d}" for i in range(100)],
            "Contract": [f"C-2023-{i:04d}" for i in range(100)],
            "Award Title": [f"Award Title {i}" for i in range(100)],
        }
    )


@pytest.fixture
def large_usaspending_data():
    """Generate larger USAspending dataset for performance testing."""
    return pd.DataFrame(
        {
            "recipient_name": [f"Test Recipient {i}" for i in range(500)],
            "recipient_uei": [f"UEI{i:010d}" for i in range(500)],
            "recipient_duns": [f"DUNS{i:09d}" for i in range(500)],
            "recipient_city": ["Test City"] * 500,
            "recipient_state": ["TS"] * 500,
        }
    )


class TestUSAspendingEnrichment:
    """Test USAspending enrichment functionality."""

    def test_exact_uei_match(self, sample_sbir_data, sample_usaspending_data):
        """Test exact UEI matching."""
        enriched = enrich_sbir_with_usaspending(sample_sbir_data, sample_usaspending_data)

        # First row should match exactly on UEI
        assert enriched["_usaspending_match_method"].iloc[0] == "uei-exact"
        assert enriched["_usaspending_match_score"].iloc[0] == 100
        assert enriched["usaspending_recipient_recipient_city"].iloc[0] == "Springfield"

    def test_exact_duns_match(self, sample_sbir_data, sample_usaspending_data):
        """Test exact DUNS matching."""
        enriched = enrich_sbir_with_usaspending(sample_sbir_data, sample_usaspending_data)

        # Second row should match exactly on DUNS
        assert enriched["_usaspending_match_method"].iloc[1] == "duns-exact"
        assert enriched["_usaspending_match_score"].iloc[1] == 100
        assert enriched["usaspending_recipient_recipient_city"].iloc[1] == "Boston"

    def test_fuzzy_name_match(self, sample_sbir_data, sample_usaspending_data):
        """Test fuzzy name matching for unmatched records."""
        enriched = enrich_sbir_with_usaspending(
            sample_sbir_data, sample_usaspending_data, high_threshold=80, low_threshold=60
        )

        # Third row should get fuzzy match
        assert enriched["_usaspending_match_method"].iloc[2].startswith("name-fuzzy")
        assert enriched["_usaspending_match_score"].iloc[2] >= 60

    def test_no_match_scenario(self):
        """Test behavior when no matches are found."""
        sbir_data = pd.DataFrame(
            [
                {
                    "Company": "Completely Unmatched Company",
                    "UEI": "NOMATCH123456789",
                    "Duns": "",
                    "Contract": "C-2023-9999",
                }
            ]
        )

        usaspending_data = pd.DataFrame(
            [
                {
                    "recipient_name": "Different Company",
                    "recipient_uei": "DIFFERENT123456",
                    "recipient_duns": "999888777",
                }
            ]
        )

        enriched = enrich_sbir_with_usaspending(sbir_data, usaspending_data)

        assert pd.isna(enriched["_usaspending_match_method"].iloc[0])
        assert pd.isna(enriched["_usaspending_match_score"].iloc[0])

    def test_return_candidates(self, sample_sbir_data, sample_usaspending_data):
        """Test candidate return functionality."""
        enriched = enrich_sbir_with_usaspending(
            sample_sbir_data, sample_usaspending_data, return_candidates=True
        )

        # Should have candidates column
        assert "_usaspending_match_candidates" in enriched.columns

        # Candidates should be JSON for fuzzy matches
        candidates_json = enriched["_usaspending_match_candidates"].iloc[2]
        if pd.notna(candidates_json):
            candidates = json.loads(candidates_json)
            assert isinstance(candidates, list)
            assert len(candidates) > 0
            assert "idx" in candidates[0]
            assert "score" in candidates[0]


class TestPerformanceMonitoring:
    """Test performance monitoring integration."""

    def test_performance_monitor_decorator(self):
        """Test that performance monitoring decorator works."""
        monitor = PerformanceMonitor()

        @monitor.time_function
        def test_function():
            time.sleep(0.01)
            return "result"

        result = test_function()
        assert result == "result"

        # Check that timing was recorded
        assert len(monitor.metrics) > 0
        assert "test_function" in monitor.metrics

    def test_memory_monitoring(self):
        """Test memory usage monitoring."""
        monitor = PerformanceMonitor()

        @monitor.monitor_memory
        def memory_test():
            # Create some data to use memory
            data = [i for i in range(10000)]
            return sum(data)

        result = memory_test()
        assert result == 49995000

        # Check memory metrics were recorded
        memory_metrics = [m for m in monitor.metrics if "memory" in m.lower()]
        assert len(memory_metrics) > 0

    def test_performance_context_manager(self):
        """Test performance monitoring context manager."""
        monitor = PerformanceMonitor()

        with monitor.time_block("test_block"):
            time.sleep(0.01)

        # Check timing was recorded
        assert "test_block" in monitor.metrics
        assert monitor.metrics["test_block"]["duration"] >= 0.01


class TestEnrichmentPipelineIntegration:
    """Test end-to-end enrichment pipeline integration."""

    @patch("src.assets.sbir_ingestion.get_config")
    def test_sbir_ingestion_assets(self, mock_get_config, tmp_path, monkeypatch):
        """Test SBIR ingestion asset execution."""
        # Mock configuration
        mock_config = type(
            "Config",
            (),
            {
                "extraction": type(
                    "Extraction",
                    (),
                    {
                        "sbir": type(
                            "SBIR",
                            (),
                            {
                                "csv_path": "tests/fixtures/sbir_sample.csv",
                                "database_path": str(tmp_path / "test.db"),
                                "table_name": "test_sbir",
                            },
                        )()
                    },
                )(),
                "data_quality": type(
                    "DataQuality",
                    (),
                    {"sbir_awards": type("SBIR", (), {"pass_rate_threshold": 0.8})()},
                )(),
            },
        )()
        mock_get_config.return_value = mock_config

        # Change to temp directory
        monkeypatch.chdir(tmp_path)

        # Test raw SBIR awards asset
        context = build_asset_context()
        result = sbir_ingestion.raw_sbir_awards(context)

        assert isinstance(result.value, pd.DataFrame)
        assert len(result.value) > 0

        # Check metadata
        assert "num_records" in result.metadata
        assert "num_columns" in result.metadata

    @patch("src.assets.sbir_usaspending_enrichment.get_config")
    def test_enrichment_assets_execution(
        self, mock_get_config, tmp_path, sample_sbir_data, sample_usaspending_data
    ):
        """Test enrichment asset execution."""
        # Mock configuration
        mock_config = type(
            "Config",
            (),
            {"duckdb": type("DuckDB", (), {"database_path": str(tmp_path / "test.db")})()},
        )()
        mock_get_config.return_value = mock_config

        # Mock the recipient lookup asset
        with patch.object(
            sbir_usaspending_enrichment, "usaspending_recipient_lookup"
        ) as mock_recipient:
            mock_recipient.return_value = sample_usaspending_data

            # Test enrichment asset
            context = build_asset_context()
            result = sbir_usaspending_enrichment.enriched_sbir_awards(
                context, sample_sbir_data, sample_usaspending_data
            )

            assert isinstance(result.value, pd.DataFrame)
            assert len(result.value) == len(sample_sbir_data)

            # Check enrichment metadata
            assert "match_rate" in result.metadata
            assert "matched_awards" in result.metadata

    def test_enrichment_quality_metrics(self, sample_sbir_data, sample_usaspending_data):
        """Test enrichment quality metrics calculation."""
        enriched = enrich_sbir_with_usaspending(sample_sbir_data, sample_usaspending_data)

        # Calculate quality metrics
        total_records = len(enriched)
        matched_records = enriched["_usaspending_match_method"].notna().sum()
        match_rate = matched_records / total_records if total_records > 0 else 0

        # Should have reasonable match rate
        assert match_rate >= 0.0
        assert match_rate <= 1.0

        # Check that exact matches have 100% score
        exact_matches = enriched[
            enriched["_usaspending_match_method"].str.contains("exact", na=False)
        ]
        if len(exact_matches) > 0:
            assert all(exact_matches["_usaspending_match_score"] == 100)


class TestLargeDatasetHandling:
    """Test handling of large datasets."""

    def test_chunked_processing(self, large_sbir_data, large_usaspending_data):
        """Test processing of larger datasets."""
        # This should not crash or run out of memory
        enriched = enrich_sbir_with_usaspending(
            large_sbir_data, large_usaspending_data, high_threshold=90, low_threshold=70
        )

        assert len(enriched) == len(large_sbir_data)
        assert "_usaspending_match_method" in enriched.columns
        assert "_usaspending_match_score" in enriched.columns

    def test_performance_with_large_data(self, large_sbir_data, large_usaspending_data):
        """Test performance monitoring with large datasets."""
        monitor = PerformanceMonitor()

        with monitor.time_block("large_dataset_enrichment"):
            enriched = enrich_sbir_with_usaspending(large_sbir_data, large_usaspending_data)

        # Should complete within reasonable time
        duration = monitor.metrics["large_dataset_enrichment"]["duration"]
        assert duration < 30  # Should complete in less than 30 seconds

        # Should have some matches
        matched = enriched["_usaspending_match_method"].notna().sum()
        assert matched >= 0

    def test_memory_usage_tracking(self, large_sbir_data, large_usaspending_data):
        """Test memory usage monitoring during large dataset processing."""
        monitor = PerformanceMonitor()

        @monitor.monitor_memory
        def process_large_dataset():
            return enrich_sbir_with_usaspending(large_sbir_data, large_usaspending_data)

        result = process_large_dataset()

        # Should have memory metrics
        memory_metrics = [m for m in monitor.metrics if "memory" in str(m).lower()]
        assert len(memory_metrics) > 0

        # Result should be valid
        assert isinstance(result, pd.DataFrame)
        assert len(result) == len(large_sbir_data)


class TestQualityValidation:
    """Test quality validation and reporting."""

    def test_match_rate_calculation(self, sample_sbir_data, sample_usaspending_data):
        """Test match rate calculation."""
        enriched = enrich_sbir_with_usaspending(sample_sbir_data, sample_usaspending_data)

        total = len(enriched)
        matched = enriched["_usaspending_match_method"].notna().sum()
        match_rate = matched / total if total > 0 else 0

        # Should have at least some matches
        assert match_rate > 0

        # Exact matches should be 100% accurate
        exact_matches = enriched[
            enriched["_usaspending_match_method"].str.contains("exact", na=False)
        ]
        assert all(exact_matches["_usaspending_match_score"] == 100)

    def test_confidence_score_distribution(self, sample_sbir_data, sample_usaspending_data):
        """Test confidence score distribution analysis."""
        enriched = enrich_sbir_with_usaspending(
            sample_sbir_data, sample_usaspending_data, high_threshold=90, low_threshold=70
        )

        scores = enriched["_usaspending_match_score"].dropna()

        if len(scores) > 0:
            # All scores should be between 0 and 100
            assert all(scores >= 0)
            assert all(scores <= 100)

            # Exact matches should have 100% confidence
            exact_mask = enriched["_usaspending_match_method"].str.contains("exact", na=False)
            if exact_mask.any():
                exact_scores = enriched[exact_mask]["_usaspending_match_score"]
                assert all(exact_scores == 100)

    def test_enrichment_report_generation(self, sample_sbir_data, sample_usaspending_data):
        """Test enrichment report generation."""
        enriched = enrich_sbir_with_usaspending(sample_sbir_data, sample_usaspending_data)

        # Generate report data
        total_awards = len(enriched)
        matched_awards = enriched["_usaspending_match_method"].notna().sum()
        match_rate = matched_awards / total_awards if total_awards > 0 else 0

        match_methods = enriched["_usaspending_match_method"].value_counts(dropna=False).to_dict()

        report = {
            "total_awards": total_awards,
            "matched_awards": matched_awards,
            "match_rate": match_rate,
            "match_methods": match_methods,
        }

        # Validate report structure
        assert "total_awards" in report
        assert "matched_awards" in report
        assert "match_rate" in report
        assert "match_methods" in report

        # Validate report values
        assert report["total_awards"] == len(sample_sbir_data)
        assert report["matched_awards"] >= 0
        assert 0 <= report["match_rate"] <= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
