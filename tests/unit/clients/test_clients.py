"""Unit tests for sbir_analytics.clients (DagsterClient, MetricsCollector, re-exports)."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

pytestmark = pytest.mark.fast


# ---------------------------------------------------------------------------
# DagsterClient
# ---------------------------------------------------------------------------


class TestDagsterClient:
    @pytest.fixture
    def client(self):
        from sbir_analytics.clients import DagsterClient

        config = Mock()
        return DagsterClient(config=config)

    def test_list_assets_empty(self, client):
        mock_defs = Mock()
        mock_defs.assets = None
        client._defs = mock_defs

        assert client.list_assets() == []

    def test_list_assets(self, client):
        mock_asset = Mock()
        mock_asset.key = Mock(__str__=Mock(return_value="raw_awards"))
        mock_asset.group_name = "ingestion"
        mock_asset.description = "Raw awards"
        mock_asset.is_source = False

        mock_defs = Mock()
        mock_defs.assets = [mock_asset]
        client._defs = mock_defs

        assets = client.list_assets()
        assert len(assets) == 1
        assert assets[0]["key"] == "raw_awards"
        assert assets[0]["group"] == "ingestion"

    def test_get_asset_status_not_started(self, client):
        mock_instance = Mock()
        mock_instance.get_event_records.return_value = []
        client._instance = mock_instance

        status = client.get_asset_status("missing_asset")
        assert status.status == "not_started"
        assert status.asset_key == "missing_asset"

    def test_get_asset_status_success(self, client):
        mock_record = Mock()
        mock_record.timestamp = datetime.now().timestamp()
        mock_record.dagster_event = Mock()
        mock_record.dagster_event.dagster_event = Mock()
        mock_record.dagster_event.dagster_event.metadata = {}

        mock_instance = Mock()
        mock_instance.get_event_records.return_value = [mock_record]
        client._instance = mock_instance

        status = client.get_asset_status("my_asset")
        assert status.status == "success"
        assert status.last_run is not None

    def test_get_asset_status_exception(self, client):
        mock_instance = Mock()
        mock_instance.get_event_records.side_effect = RuntimeError("db error")
        client._instance = mock_instance

        status = client.get_asset_status("broken_asset")
        assert status.status == "unknown"

    def test_trigger_materialization_requires_keys_or_groups(self, client):
        with pytest.raises(ValueError, match="Must specify"):
            client.trigger_materialization()

    def test_list_recent_runs_empty(self, client):
        mock_instance = Mock()
        mock_instance.get_runs.return_value = []
        client._instance = mock_instance

        assert client.list_recent_runs() == []

    def test_get_run_status_not_found(self, client):
        mock_instance = Mock()
        mock_instance.get_run_by_id.return_value = None
        client._instance = mock_instance

        result = client.get_run_status("nonexistent")
        assert result["status"] == "not_found"


# ---------------------------------------------------------------------------
# MetricsCollector
# ---------------------------------------------------------------------------


class TestMetricsCollector:
    @pytest.fixture
    def collector_with_data(self, tmp_path):
        from sbir_analytics.clients import MetricsCollector

        config = Mock()
        collector = MetricsCollector(config=config)
        metrics_dir = tmp_path / "metrics"
        metrics_dir.mkdir()
        collector.reports_dir = tmp_path
        collector.metrics_dir = metrics_dir

        # Write two metric files
        now = datetime.now()
        for i, success in enumerate([True, False]):
            data = {
                "timestamp": (now - timedelta(hours=i)).isoformat(),
                "records_processed": 100 * (i + 1),
                "duration_seconds": 10.0 * (i + 1),
                "error_count": 0 if success else 1,
                "peak_memory_mb": 50.0,
                "success": success,
                "asset_group": "enrichment" if i == 0 else "ingestion",
            }
            (metrics_dir / f"metric_{i}.json").write_text(json.dumps(data))

        return collector

    def test_get_metrics_all(self, collector_with_data):
        metrics = collector_with_data.get_metrics()
        assert len(metrics) == 2

    def test_get_metrics_by_group(self, collector_with_data):
        metrics = collector_with_data.get_metrics(asset_group="enrichment")
        assert len(metrics) == 1
        assert metrics[0]["asset_group"] == "enrichment"

    def test_get_metrics_by_date(self, collector_with_data):
        future = datetime.now() + timedelta(days=1)
        metrics = collector_with_data.get_metrics(start_date=future)
        assert len(metrics) == 0

    def test_get_latest_metrics(self, collector_with_data):
        latest = collector_with_data.get_latest_metrics()
        assert latest is not None
        assert latest.enrichment_success_rate == 0.5  # 1 of 2 succeeded
        assert latest.error_count == 1
        assert latest.processing_throughput > 0

    def test_get_latest_metrics_empty(self, tmp_path):
        from sbir_analytics.clients import MetricsCollector

        config = Mock()
        collector = MetricsCollector(config=config)
        collector.metrics_dir = tmp_path / "empty"
        assert collector.get_latest_metrics() is None

    def test_get_asset_group_metrics(self, collector_with_data):
        metrics = collector_with_data.get_asset_group_metrics("ingestion")
        assert len(metrics) == 1


# ---------------------------------------------------------------------------
# Re-exports from sbir-graph
# ---------------------------------------------------------------------------


class TestReExports:
    def test_neo4j_classes_importable(self):
        from sbir_analytics.clients import Neo4jClient, Neo4jConfig, Neo4jHealthStatus, Neo4jStatistics

        # Verify they're the actual sbir-graph classes
        from sbir_graph.loaders.neo4j.client import Neo4jClient as GraphClient

        assert Neo4jClient is GraphClient

    def test_all_exports(self):
        from sbir_analytics import clients

        expected = {
            "AssetStatus", "DagsterClient", "MetricsCollector",
            "Neo4jClient", "Neo4jConfig", "Neo4jHealthStatus",
            "Neo4jStatistics", "PipelineMetrics", "RunResult",
        }
        assert expected.issubset(set(clients.__all__))
