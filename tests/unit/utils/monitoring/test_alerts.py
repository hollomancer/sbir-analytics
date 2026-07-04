"""Unit tests for performance alerts utilities."""

import dataclasses
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest


pytestmark = pytest.mark.fast

from sbir_etl.utils.monitoring.alerts import (
    Alert,
    AlertCollector,
    AlertSeverity,
    Caveat,
    ProvenanceEntry,
)


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


class TestCaveat:
    """Tests for Caveat dataclass."""

    def _caveat(self, **overrides):
        defaults = {
            "timestamp": datetime(2026, 7, 2, 15, 32, 4, tzinfo=UTC),
            "dimension": "validity",
            "metric_name": "sbir_awards_pass_rate",
            "observed_value": 0.972,
            "expected_value": 0.99,
            "description": "Pass rate below floor.",
            "impact": "Cohort counts under-report.",
        }
        defaults.update(overrides)
        return Caveat(**defaults)

    def test_caveat_is_frozen(self):
        caveat = self._caveat()
        with pytest.raises(dataclasses.FrozenInstanceError):
            caveat.observed_value = 0.5  # type: ignore[misc]

    def test_caveat_to_dict_roundtrip(self):
        caveat = self._caveat(asset_name="validated_sbir_awards", run_id="r1")
        data = caveat.to_dict()
        assert data["dimension"] == "validity"
        assert data["observed_value"] == 0.972
        assert data["expected_value"] == 0.99
        assert data["asset_name"] == "validated_sbir_awards"
        assert data["run_id"] == "r1"
        # timestamp is ISO string
        assert isinstance(data["timestamp"], str)
        json.dumps(data)  # must be JSON-serializable


class TestProvenanceEntry:
    """Tests for ProvenanceEntry dataclass."""

    def _entry(self, **overrides):
        defaults = {
            "source_id": "sbir_gov_bulk_download",
            "location": "s3://bucket/key.csv",
            "retrieved_at": datetime(2026, 7, 2, 14, 58, 12, tzinfo=UTC),
            "sha256": None,
            "row_count": 540123,
            "extractor_module": "sbir_etl.extractors.sbir",
            "hash_omitted_reason": "streaming s3 source",
        }
        defaults.update(overrides)
        return ProvenanceEntry(**defaults)

    def test_provenance_is_frozen(self):
        entry = self._entry()
        with pytest.raises(dataclasses.FrozenInstanceError):
            entry.row_count = 0  # type: ignore[misc]

    def test_provenance_to_dict_roundtrip(self):
        entry = self._entry(sha256="abc123", hash_omitted_reason=None)
        data = entry.to_dict()
        assert data["source_id"] == "sbir_gov_bulk_download"
        assert data["sha256"] == "abc123"
        assert data["hash_omitted_reason"] is None
        assert data["row_count"] == 540123
        assert isinstance(data["retrieved_at"], str)
        json.dumps(data)


class TestEmitCaveat:
    """Tests for AlertCollector.emit_caveat."""

    def test_emit_caveat_appends_to_caveats_not_alerts(self):
        collector = AlertCollector(asset_name="a", run_id="r")
        caveat = collector.emit_caveat(
            dimension="validity",
            metric_name="m",
            observed_value=1,
            expected_value=0,
            description="d",
            impact="i",
        )
        assert len(collector.caveats) == 1
        assert collector.caveats[0] is caveat
        assert len(collector.alerts) == 0

    def test_emit_caveat_stamps_asset_and_run(self):
        collector = AlertCollector(asset_name="asset_x", run_id="run_x")
        caveat = collector.emit_caveat(
            dimension="completeness",
            metric_name="m",
            observed_value=1,
            expected_value=0,
            description="d",
            impact="i",
        )
        assert caveat.asset_name == "asset_x"
        assert caveat.run_id == "run_x"

    def test_emit_caveat_rejects_invalid_dimension(self):
        collector = AlertCollector()
        with pytest.raises(ValueError, match="Invalid dimension"):
            collector.emit_caveat(
                dimension="not_a_dimension",  # type: ignore[arg-type]
                metric_name="m",
                observed_value=1,
                expected_value=0,
                description="d",
                impact="i",
            )

    def test_emit_caveat_accepts_all_four_dimensions(self):
        collector = AlertCollector()
        for dim in ("accuracy", "completeness", "consistency", "validity"):
            collector.emit_caveat(
                dimension=dim,  # type: ignore[arg-type]
                metric_name=f"m_{dim}",
                observed_value=1,
                expected_value=0,
                description="d",
                impact="i",
            )
        assert len(collector.caveats) == 4


class TestRecordProvenance:
    """Tests for AlertCollector.record_provenance."""

    def test_record_provenance_appends(self):
        collector = AlertCollector()
        entry = collector.record_provenance(
            source_id="src",
            location="/path/to/file.csv",
            row_count=100,
            extractor_module="mod",
            sha256="deadbeef",
        )
        assert len(collector.provenance) == 1
        assert collector.provenance[0] is entry

    def test_record_provenance_defaults_retrieved_at(self):
        collector = AlertCollector()
        before = datetime.now(UTC)
        entry = collector.record_provenance(
            source_id="src",
            location="/p",
            row_count=1,
            extractor_module="m",
            sha256="abc",
        )
        after = datetime.now(UTC)
        assert before <= entry.retrieved_at <= after

    def test_record_provenance_null_hash_requires_reason(self):
        collector = AlertCollector()
        with pytest.raises(ValueError, match="hash_omitted_reason"):
            collector.record_provenance(
                source_id="src",
                location="/p",
                row_count=1,
                extractor_module="m",
                sha256=None,
            )

    def test_record_provenance_null_hash_with_reason_ok(self):
        collector = AlertCollector()
        entry = collector.record_provenance(
            source_id="src",
            location="s3://b/k",
            row_count=1,
            extractor_module="m",
            sha256=None,
            hash_omitted_reason="s3 streaming",
        )
        assert entry.sha256 is None
        assert entry.hash_omitted_reason == "s3 streaming"


class TestSaveManifest:
    """Tests for AlertCollector.save_manifest."""

    def _emit(self, collector, metric_name):
        collector.emit_caveat(
            dimension="validity",
            metric_name=metric_name,
            observed_value=1,
            expected_value=0,
            description=f"desc {metric_name}",
            impact=f"impact {metric_name}",
        )

    def test_save_manifest_writes_valid_json(self, tmp_path: Path):
        collector = AlertCollector(asset_name="a", run_id="run1")
        self._emit(collector, "m1")
        collector.record_provenance(
            source_id="src",
            location="/p",
            row_count=1,
            extractor_module="mod",
            sha256="abc",
        )
        out = tmp_path / "sub" / "run1.json"

        manifest = collector.save_manifest(out)

        assert out.exists()
        assert manifest["asset_name"] == "a"
        assert manifest["run_id"] == "run1"
        assert len(manifest["caveats"]) == 1
        assert len(manifest["provenance"]) == 1
        assert manifest["resolved_caveats"] == []
        assert manifest["framework_reference"] == "GAO-20-283G"

        with open(out) as f:
            on_disk = json.load(f)
        assert on_disk["asset_name"] == "a"
        assert on_disk["caveats"][0]["metric_name"] == "m1"

    def test_save_manifest_creates_parent_dirs(self, tmp_path: Path):
        deep = tmp_path / "a" / "b" / "c" / "manifest.json"
        collector = AlertCollector()
        collector.save_manifest(deep)
        assert deep.exists()

    def test_resolved_caveats_populated_from_prior_manifest(self, tmp_path: Path):
        # Run 1: emit m1 and m2
        c1 = AlertCollector(asset_name="a", run_id="run1")
        self._emit(c1, "m1")
        self._emit(c1, "m2")
        c1.save_manifest(tmp_path / "run1.json")

        # Run 2: emit only m2 -> m1 should appear in resolved_caveats
        c2 = AlertCollector(asset_name="a", run_id="run2")
        self._emit(c2, "m2")
        manifest = c2.save_manifest(tmp_path / "run2.json")

        assert len(manifest["caveats"]) == 1
        assert manifest["caveats"][0]["metric_name"] == "m2"
        assert len(manifest["resolved_caveats"]) == 1
        assert manifest["resolved_caveats"][0]["metric_name"] == "m1"
        # Resolved carries the full prior caveat dict (design open-question #3).
        assert manifest["resolved_caveats"][0]["description"] == "desc m1"
        assert manifest["resolved_caveats"][0]["impact"] == "impact m1"

    def test_identical_reruns_produce_empty_resolved(self, tmp_path: Path):
        c1 = AlertCollector(asset_name="a", run_id="run1")
        self._emit(c1, "m1")
        c1.save_manifest(tmp_path / "run1.json")

        c2 = AlertCollector(asset_name="a", run_id="run2")
        self._emit(c2, "m1")
        manifest = c2.save_manifest(tmp_path / "run2.json")

        assert manifest["resolved_caveats"] == []

    def test_empty_prior_directory_produces_empty_resolved(self, tmp_path: Path):
        collector = AlertCollector()
        self._emit(collector, "m1")
        manifest = collector.save_manifest(tmp_path / "run1.json")
        assert manifest["resolved_caveats"] == []

    def test_rewrite_same_path_does_not_self_resolve(self, tmp_path: Path):
        # Writing to the same path twice: the exclude logic should prevent
        # the caveats from the first write showing up as "resolved" in the second.
        out = tmp_path / "run1.json"
        c1 = AlertCollector(asset_name="a", run_id="run1")
        self._emit(c1, "m1")
        c1.save_manifest(out)

        c2 = AlertCollector(asset_name="a", run_id="run1")
        # No caveats emitted this time
        manifest = c2.save_manifest(out)
        # The excluded file is the one being written, so no prior candidate exists.
        assert manifest["resolved_caveats"] == []
