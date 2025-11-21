"""Unit tests for performance alerts utilities."""

from datetime import datetime

import pytest


pytestmark = pytest.mark.fast

from src.utils.monitoring.alerts import Alert, AlertCollector, AlertSeverity


class TestAlert:
    """Tests for Alert dataclass."""

    def test_alert_creation(self):
        """Test creating an alert."""
        alert = Alert(
            timestamp=datetime(2024, 1, 15, 10, 30, 0),
            severity=AlertSeverity.WARNING,
            alert_type="performance_duration",
            message="Duration exceeded threshold",
            threshold_value=60.0,
            actual_value=75.0,
            metric_name="execution_time_seconds",
            delta_percent=25.0,
        )

        assert alert.severity == AlertSeverity.WARNING
        assert alert.alert_type == "performance_duration"
        assert alert.actual_value == 75.0

    def test_alert_to_dict(self):
        """Test alert serialization to dictionary."""
        alert = Alert(
            timestamp=datetime(2024, 1, 15, 10, 30, 0),
            severity=AlertSeverity.FAILURE,
            alert_type="quality_match_rate",
            message="Match rate below threshold",
            threshold_value=0.95,
            actual_value=0.85,
            metric_name="match_rate",
        )

        data = alert.to_dict()

        assert data["severity"] == "FAILURE"
        assert data["alert_type"] == "quality_match_rate"
        assert data["threshold_value"] == 0.95
        assert data["actual_value"] == 0.85
        assert "timestamp" in data
        assert isinstance(data["timestamp"], str)

    def test_alert_to_markdown(self):
        """Test alert formatting as Markdown."""
        alert = Alert(
            timestamp=datetime(2024, 1, 15, 10, 30, 0),
            severity=AlertSeverity.WARNING,
            alert_type="performance_memory",
            message="Memory usage exceeded threshold",
            threshold_value=1024.0,
            actual_value=1536.0,
            metric_name="peak_memory_mb",
            delta_percent=50.0,
        )

        markdown = alert.to_markdown()

        assert "WARNING" in markdown
        assert "performance memory" in markdown.lower()
        assert "1536.0" in markdown
        assert "50.0%" in markdown


class TestAlertCollector:
    """Tests for AlertCollector class."""

    @pytest.fixture
    def collector(self):
        """Create an AlertCollector instance."""
        return AlertCollector()

    def test_collector_initialization(self, collector):
        """Test AlertCollector initialization."""
        assert len(collector.alerts) == 0
        assert collector.asset_name is None
        assert collector.run_id is None

    def test_collector_with_asset_name(self):
        """Test AlertCollector initialization with asset name."""
        collector = AlertCollector(asset_name="test_asset", run_id="run_123")
        assert collector.asset_name == "test_asset"
        assert collector.run_id == "run_123"

    def test_check_duration_per_record_creates_alert(self, collector):
        """Test check_duration_per_record creates alert when threshold exceeded."""
        alert = collector.check_duration_per_record(
            total_duration_seconds=100.0,
            total_records=10,  # 10 seconds per record > 5 second threshold
            metric_name="test_metric",
        )

        assert alert is not None
        assert alert.severity == AlertSeverity.WARNING
        assert "duration" in alert.alert_type.lower()
        assert len(collector.alerts) == 1

    def test_check_duration_per_record_no_alert(self, collector):
        """Test check_duration_per_record doesn't create alert when under threshold."""
        alert = collector.check_duration_per_record(
            total_duration_seconds=10.0,
            total_records=10,  # 1 second per record < 5 second threshold
            metric_name="test_metric",
        )

        assert alert is None
        assert len(collector.alerts) == 0

    def test_check_duration_per_record_zero_records(self, collector):
        """Test check_duration_per_record handles zero records."""
        alert = collector.check_duration_per_record(
            total_duration_seconds=100.0,
            total_records=0,
            metric_name="test_metric",
        )

        assert alert is None

    def test_get_alerts_filters_by_severity(self, collector):
        """Test get_alerts filters by severity."""
        # Create alerts via check methods
        collector.check_duration_per_record(100.0, 10, "test")  # Creates WARNING
        collector.check_match_rate(0.5, "test")  # Creates FAILURE

        # Get all alerts
        all_alerts = collector.get_alerts()
        assert len(all_alerts) == 2

        # Get only warnings
        warnings = collector.get_alerts(AlertSeverity.WARNING)
        assert len(warnings) == 1
        assert warnings[0].severity == AlertSeverity.WARNING

        # Get only failures
        failures = collector.get_alerts(AlertSeverity.FAILURE)
        assert len(failures) == 1
        assert failures[0].severity == AlertSeverity.FAILURE

    def test_to_dict(self, collector):
        """Test serializing collector to dictionary."""
        collector.check_duration_per_record(100.0, 10, "test")

        data = collector.to_dict()

        assert "alerts" in data
        assert len(data["alerts"]) == 1
        assert isinstance(data["alerts"][0], dict)

    def test_check_memory_delta(self, collector):
        """Test check_memory_delta creates alert when threshold exceeded."""
        alert = collector.check_memory_delta(
            avg_memory_delta_mb=600.0,  # > 500MB threshold
            metric_name="test_memory",
        )

        assert alert is not None
        assert alert.severity == AlertSeverity.WARNING
        assert "memory" in alert.alert_type.lower()

    def test_check_match_rate(self, collector):
        """Test check_match_rate creates alert when below threshold."""
        alert = collector.check_match_rate(
            match_rate=0.65,  # < 0.70 threshold
            metric_name="test_match",
        )

        assert alert is not None
        assert alert.severity == AlertSeverity.FAILURE
        assert "match_rate" in alert.alert_type.lower()

