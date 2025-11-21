"""Unit tests for enrichment metrics utilities."""

from datetime import datetime

import pytest


pytestmark = pytest.mark.fast

from src.utils.enrichment_metrics import EnrichmentFreshnessMetrics


class TestEnrichmentFreshnessMetrics:
    """Tests for EnrichmentFreshnessMetrics class."""

    def test_init_calculates_derived_metrics(self):
        """Test that initialization calculates derived metrics."""
        metrics = EnrichmentFreshnessMetrics(
            source="test_source",
            total_records=100,
            within_sla=80,
            stale_count=20,
            success_count=90,
            failed_count=10,
            unchanged_count=5,
            attempt_count=100,
            api_calls=100,
            api_errors=5,
            sla_days=30,
        )

        assert metrics.coverage_rate == 0.8  # 80/100
        assert metrics.success_rate == 0.9  # 90/100
        assert metrics.staleness_rate == 0.2  # 20/100
        assert metrics.error_rate == 0.05  # 5/100
        assert metrics.unchanged_rate == 0.05  # 5/100

    def test_init_handles_zero_denominators(self):
        """Test that initialization handles zero denominators gracefully."""
        metrics = EnrichmentFreshnessMetrics(
            source="test_source",
            total_records=0,
            within_sla=0,
            stale_count=0,
            success_count=0,
            failed_count=0,
            unchanged_count=0,
            attempt_count=0,
            api_calls=0,
            api_errors=0,
            sla_days=30,
        )

        assert metrics.coverage_rate == 0.0
        assert metrics.success_rate == 0.0
        assert metrics.staleness_rate == 0.0
        assert metrics.error_rate == 0.0
        assert metrics.unchanged_rate == 0.0

    def test_to_dict_serializes_all_fields(self):
        """Test that to_dict includes all fields."""
        metrics = EnrichmentFreshnessMetrics(
            source="test_source",
            total_records=100,
            within_sla=80,
            stale_count=20,
            success_count=90,
            failed_count=10,
            unchanged_count=5,
            attempt_count=100,
            api_calls=100,
            api_errors=5,
            sla_days=30,
        )

        data = metrics.to_dict()

        assert data["source"] == "test_source"
        assert "timestamp" in data
        assert data["sla_days"] == 30
        assert "records" in data
        assert "rates" in data
        assert "api" in data

    def test_timestamp_is_iso_format(self):
        """Test that timestamp is in ISO format."""
        metrics = EnrichmentFreshnessMetrics(
            source="test",
            total_records=10,
            within_sla=8,
            stale_count=2,
            success_count=9,
            failed_count=1,
            unchanged_count=0,
            attempt_count=10,
            api_calls=10,
            api_errors=0,
            sla_days=30,
        )

        # Should be able to parse as ISO datetime
        datetime.fromisoformat(metrics.timestamp)

