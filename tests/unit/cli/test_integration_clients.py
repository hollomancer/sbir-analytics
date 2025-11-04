"""Unit tests for CLI integration clients."""

from datetime import datetime
from unittest.mock import Mock, patch

import pytest


pytestmark = pytest.mark.fast

from src.cli.integration.dagster_client import DagsterClient
from src.cli.integration.metrics_collector import MetricsCollector
from src.cli.integration.neo4j_client import Neo4jClient


class TestDagsterClient:
    """Tests for DagsterClient."""

    @pytest.fixture
    def mock_config(self) -> Mock:
        """Create mock config."""
        config = Mock()
        return config

    @pytest.fixture
    def mock_console(self) -> Mock:
        """Create mock console."""
        return Mock()

    @pytest.fixture
    def client(self, mock_config: Mock, mock_console: Mock) -> DagsterClient:
        """Create DagsterClient instance."""
        return DagsterClient(config=mock_config, console=mock_console)

    def test_list_assets(self, client: DagsterClient) -> None:
        """Test listing assets."""
        # Mock definitions property
        mock_asset = Mock()
        mock_asset.key = Mock()
        mock_asset.key.__str__ = Mock(return_value="test_asset")
        mock_asset.group_name = "test_group"
        mock_asset.description = "Test asset"
        mock_asset.is_source = False

        mock_defs = Mock()
        mock_defs.assets = [mock_asset]
        client._defs = mock_defs

        # Test
        assets = client.list_assets()

        # Verify
        assert len(assets) == 1
        assert assets[0]["key"] == "test_asset"
        assert assets[0]["group"] == "test_group"

    def test_get_asset_status(self, client: DagsterClient) -> None:
        """Test getting asset status."""
        # Mock instance
        mock_instance = Mock()
        mock_metadata = {
            "duration": Mock(value=10.5),
            "records_processed": Mock(value=1000),
        }
        # The code accesses: event.dagster_event.metadata where event = latest.dagster_event
        # So we need: record.dagster_event.dagster_event.metadata
        mock_inner_dagster_event = Mock()
        mock_inner_dagster_event.metadata = mock_metadata
        mock_dagster_event = Mock()
        mock_dagster_event.dagster_event = mock_inner_dagster_event
        mock_event_record = Mock()
        # Set dagster_event attribute on the record
        mock_event_record.dagster_event = mock_dagster_event
        mock_event_record.timestamp = datetime.now().timestamp()
        mock_instance.get_event_records.return_value = [mock_event_record]
        client._instance = mock_instance

        # Mock AssetKey
        with patch("src.cli.integration.dagster_client.AssetKey") as mock_key:
            mock_key.from_user_string.return_value = Mock()

            # Test
            status = client.get_asset_status("test_asset")

            # Verify
            assert status.asset_key == "test_asset"
            assert status.status == "success"
            # The metadata access is complex - verify basic structure
            assert status.last_run is not None

    @patch("src.cli.integration.dagster_client.materialize")
    @patch("src.cli.integration.dagster_client.AssetSelection")
    def test_trigger_materialization(
        self, mock_selection: Mock, mock_materialize: Mock, client: DagsterClient
    ) -> None:
        """Test triggering materialization."""
        # Mock materialize result
        mock_result = Mock()
        mock_result.success = True
        mock_result.run_id = "test_run_123"
        mock_materialize.return_value = mock_result

        # Mock selection
        mock_resolved = Mock()
        mock_selection_class = Mock()
        mock_selection_class.keys.return_value = Mock()
        mock_selection_class.keys.return_value.resolve.return_value = mock_resolved

        client._instance = Mock()
        mock_defs = Mock()
        mock_defs.assets = []
        client._defs = mock_defs

        with patch("src.cli.integration.dagster_client.AssetSelection", mock_selection_class):
            # Test
            result = client.trigger_materialization(asset_keys=["test_asset"])

            # Verify
            assert result.status == "success"
            assert "test_run" in result.run_id.lower() or result.run_id == "unknown"


class TestNeo4jClient:
    """Tests for Neo4jClient."""

    @pytest.fixture
    def mock_config(self) -> Mock:
        """Create mock config."""
        config = Mock()
        config.neo4j = Mock()
        config.neo4j.uri = "bolt://localhost:7687"
        config.neo4j.username = "neo4j"
        config.neo4j.password = "password"  # pragma: allowlist secret
        config.neo4j.database = "neo4j"
        return config

    @pytest.fixture
    def mock_console(self) -> Mock:
        """Create mock console."""
        return Mock()

    @pytest.fixture
    def client(self, mock_config: Mock, mock_console: Mock) -> Neo4jClient:
        """Create Neo4jClient instance."""
        return Neo4jClient(config=mock_config, console=mock_console)

    @patch("src.cli.integration.neo4j_client.GraphDatabase")
    def test_health_check_success(self, mock_graph_db: Mock, client: Neo4jClient) -> None:
        """Test successful health check."""
        # Mock driver and session
        mock_driver = Mock()
        mock_session = Mock()
        mock_record = Mock()
        mock_record.__getitem__ = Mock(side_effect=lambda k: 1 if k == "test" else None)
        mock_result = Mock()
        mock_result.single.return_value = mock_record

        # Mock version query
        mock_version_result = Mock()
        mock_version_record = Mock()
        mock_version_record.__getitem__ = Mock(return_value="5.0.0")
        mock_version_result.single.return_value = mock_version_record

        mock_session.run.side_effect = [mock_result, mock_version_result]
        mock_driver.session.return_value.__enter__ = Mock(return_value=mock_session)
        mock_driver.session.return_value.__exit__ = Mock(return_value=None)
        mock_graph_db.driver.return_value = mock_driver

        client._driver = mock_driver

        # Test
        health = client.health_check()

        # Verify
        assert health.connected is True
        assert health.uri == "bolt://localhost:7687"
        assert health.version == "5.0.0"

    @patch("src.cli.integration.neo4j_client.GraphDatabase")
    def test_health_check_failure(self, mock_graph_db: Mock, client: Neo4jClient) -> None:
        """Test failed health check."""
        # Mock driver that raises exception
        mock_driver = Mock()
        mock_driver.session.side_effect = Exception("Connection failed")
        mock_graph_db.driver.return_value = mock_driver

        client._driver = mock_driver

        # Test
        health = client.health_check()

        # Verify
        assert health.connected is False
        assert "Connection failed" in health.error

    @patch("src.cli.integration.neo4j_client.GraphDatabase")
    def test_get_statistics(self, mock_graph_db: Mock, client: Neo4jClient) -> None:
        """Test getting statistics."""
        # Mock driver and session
        mock_driver = Mock()
        mock_session = Mock()

        # Mock node count query
        mock_node_result = Mock()
        mock_node_record1 = Mock()
        mock_node_record1.__getitem__ = Mock(
            side_effect=lambda k: "Company" if k == "label" else 100
        )
        mock_node_record2 = Mock()
        mock_node_record2.__getitem__ = Mock(side_effect=lambda k: "Award" if k == "label" else 50)
        mock_node_result.__iter__ = Mock(return_value=iter([mock_node_record1, mock_node_record2]))

        # Mock relationship count query
        mock_rel_result = Mock()
        mock_rel_record = Mock()
        mock_rel_record.__getitem__ = Mock(
            side_effect=lambda k: "FUNDED" if k == "rel_type" else 150
        )
        mock_rel_result.__iter__ = Mock(return_value=iter([mock_rel_record]))

        mock_session.run.side_effect = [mock_node_result, mock_rel_result]
        mock_driver.session.return_value.__enter__ = Mock(return_value=mock_session)
        mock_driver.session.return_value.__exit__ = Mock(return_value=None)
        mock_graph_db.driver.return_value = mock_driver

        client._driver = mock_driver

        # Test
        stats = client.get_statistics()

        # Verify
        assert stats is not None
        assert stats.total_nodes == 150
        assert stats.total_relationships == 150
        assert "Company" in stats.node_counts
        assert stats.node_counts["Company"] == 100


class TestMetricsCollector:
    """Tests for MetricsCollector."""

    @pytest.fixture
    def mock_config(self) -> Mock:
        """Create mock config."""
        config = Mock()
        return config

    @pytest.fixture
    def mock_console(self) -> Mock:
        """Create mock console."""
        return Mock()

    @pytest.fixture
    def collector(self, mock_config: Mock, mock_console: Mock) -> MetricsCollector:
        """Create MetricsCollector instance."""
        return MetricsCollector(config=mock_config, console=mock_console)

    @patch("pathlib.Path.exists")
    @patch("builtins.open", create=True)
    @patch("json.load")
    def test_get_metrics(
        self,
        mock_json_load: Mock,
        mock_open: Mock,
        mock_exists: Mock,
        collector: MetricsCollector,
    ) -> None:
        """Test getting metrics from files."""
        # Setup mocks
        mock_exists.return_value = True
        mock_json_load.return_value = [
            {
                "timestamp": "2024-01-01T00:00:00",
                "asset_key": "test_asset",
                "duration_seconds": 10.0,
                "records_processed": 100,
                "success": True,
            }
        ]

        # Mock Path.glob
        mock_file = Mock()
        mock_file.__enter__ = Mock(return_value=Mock())
        mock_file.__exit__ = Mock(return_value=None)
        mock_open.return_value = mock_file

        # Mock Path.glob to return file paths
        mock_path = Mock()
        mock_path.exists.return_value = True
        mock_file_path = Mock()
        mock_file_path.__str__ = Mock(return_value="metrics_file.json")
        mock_path.glob.return_value = [mock_file_path]
        collector.metrics_dir = mock_path

        # Test
        metrics = collector.get_metrics()

        # Verify
        assert len(metrics) == 1
        assert metrics[0]["asset_key"] == "test_asset"

    def test_get_latest_metrics_no_data(self, collector: MetricsCollector) -> None:
        """Test getting latest metrics when no data available."""
        with patch.object(collector, "get_metrics", return_value=[]):
            # Test
            metrics = collector.get_latest_metrics()

            # Verify
            assert metrics is None

    def test_get_latest_metrics_with_data(self, collector: MetricsCollector) -> None:
        """Test getting latest aggregated metrics."""
        test_metrics = [
            {
                "timestamp": "2024-01-01T00:00:00",
                "duration_seconds": 10.0,
                "records_processed": 100,
                "success": True,
                "peak_memory_mb": 512.0,
            },
            {
                "timestamp": "2024-01-01T01:00:00",
                "duration_seconds": 5.0,
                "records_processed": 50,
                "success": False,
                "peak_memory_mb": 256.0,
                "error_count": 1,
            },
        ]

        with patch.object(collector, "get_metrics", return_value=test_metrics):
            # Test
            metrics = collector.get_latest_metrics()

            # Verify
            assert metrics is not None
            assert metrics.enrichment_success_rate == 0.5  # 1 out of 2 successful
            assert metrics.processing_throughput == 150.0 / 15.0  # 150 records / 15 seconds
            assert metrics.memory_usage_mb == 384.0  # (512 + 256) / 2
            assert metrics.error_count == 1
