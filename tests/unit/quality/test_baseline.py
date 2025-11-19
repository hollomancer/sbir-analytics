"""Unit tests for quality baseline management.

Tests cover:
- QualityBaseline dataclass serialization
- BaselineComparison calculations and reporting
- QualityBaselineManager operations
- Trend analysis and history tracking
"""

import json
from datetime import datetime

import pytest


pytestmark = pytest.mark.fast

from src.quality.baseline import BaselineComparison, QualityBaseline, QualityBaselineManager


pytestmark = pytest.mark.fast


@pytest.fixture
def sample_baseline():
    """Create a sample quality baseline."""
    return QualityBaseline(
        timestamp=datetime(2024, 1, 1, 12, 0, 0),
        match_rate=0.85,
        matched_records=850,
        total_records=1000,
        exact_matches=500,
        fuzzy_matches=350,
        run_id="run_001",
        processing_mode="standard",
        metadata={"version": "1.0"},
    )


@pytest.fixture
def improved_baseline():
    """Create an improved baseline for comparison."""
    return QualityBaseline(
        timestamp=datetime(2024, 1, 2, 12, 0, 0),
        match_rate=0.90,
        matched_records=900,
        total_records=1000,
        exact_matches=550,
        fuzzy_matches=350,
    )


@pytest.fixture
def regressed_baseline():
    """Create a regressed baseline for comparison."""
    return QualityBaseline(
        timestamp=datetime(2024, 1, 2, 12, 0, 0),
        match_rate=0.75,
        matched_records=750,
        total_records=1000,
        exact_matches=400,
        fuzzy_matches=350,
    )


@pytest.fixture
def baseline_manager(tmp_path):
    """Create a baseline manager with temp directory."""
    return QualityBaselineManager(baseline_dir=tmp_path / "baselines")


class TestQualityBaseline:
    """Tests for QualityBaseline dataclass."""

    def test_baseline_creation(self, sample_baseline):
        """Test baseline creation with all fields."""
        assert sample_baseline.match_rate == 0.85
        assert sample_baseline.matched_records == 850
        assert sample_baseline.run_id == "run_001"
        assert sample_baseline.metadata["version"] == "1.0"

    def test_baseline_to_dict(self, sample_baseline):
        """Test baseline serialization to dict."""
        data = sample_baseline.to_dict()

        assert data["match_rate"] == 0.85
        assert data["matched_records"] == 850
        assert data["timestamp"] == "2024-01-01T12:00:00"
        assert data["run_id"] == "run_001"
        assert data["metadata"]["version"] == "1.0"

    def test_baseline_from_dict(self, sample_baseline):
        """Test baseline deserialization from dict."""
        data = sample_baseline.to_dict()
        restored = QualityBaseline.from_dict(data)

        assert restored.match_rate == sample_baseline.match_rate
        assert restored.matched_records == sample_baseline.matched_records
        assert restored.timestamp == sample_baseline.timestamp
        assert restored.run_id == sample_baseline.run_id

    def test_baseline_roundtrip(self, sample_baseline):
        """Test serialization/deserialization roundtrip."""
        data = sample_baseline.to_dict()
        restored = QualityBaseline.from_dict(data)

        assert restored.to_dict() == data


class TestBaselineComparison:
    """Tests for BaselineComparison."""

    def test_comparison_no_regression(self, sample_baseline, improved_baseline):
        """Test comparison when quality improves."""
        comparison = BaselineComparison(
            baseline=sample_baseline,
            current=improved_baseline,
            match_rate_delta_percent=5.0,
            matched_records_delta=50,
            regression_severity="PASS",
        )

        assert comparison.has_regression is False
        assert comparison.regression_severity == "PASS"
        assert comparison.exceeded_threshold is False

    def test_comparison_with_regression(self, sample_baseline, regressed_baseline):
        """Test comparison when quality regresses."""
        comparison = BaselineComparison(
            baseline=sample_baseline,
            current=regressed_baseline,
            match_rate_delta_percent=-10.0,
            matched_records_delta=-100,
            regression_severity="FAILURE",
            exceeded_threshold=True,
        )

        assert comparison.has_regression is True
        assert comparison.regression_severity == "FAILURE"
        assert comparison.exceeded_threshold is True

    def test_regression_percent_change(self, sample_baseline, regressed_baseline):
        """Test regression percentage calculation."""
        comparison = BaselineComparison(
            baseline=sample_baseline,
            current=regressed_baseline,
            match_rate_delta_percent=-10.0,
            matched_records_delta=-100,
        )

        # (0.75 - 0.85) / 0.85 * 100 ≈ -11.76%
        assert comparison.regression_percent_change < 0
        assert abs(comparison.regression_percent_change + 11.76) < 0.1

    def test_comparison_to_dict(self, sample_baseline, improved_baseline):
        """Test comparison serialization to dict."""
        comparison = BaselineComparison(
            baseline=sample_baseline,
            current=improved_baseline,
            match_rate_delta_percent=5.0,
            matched_records_delta=50,
        )

        data = comparison.to_dict()

        assert "baseline" in data
        assert "current" in data
        assert data["match_rate_delta_percent"] == 5.0
        assert data["has_regression"] is False

    def test_comparison_to_markdown(self, sample_baseline, improved_baseline):
        """Test Markdown report generation."""
        comparison = BaselineComparison(
            baseline=sample_baseline,
            current=improved_baseline,
            match_rate_delta_percent=5.0,
            matched_records_delta=50,
            regression_severity="PASS",
        )

        markdown = comparison.to_markdown()

        assert "Quality Baseline Comparison" in markdown
        assert "PASS" in markdown
        assert "85.0%" in markdown
        assert "90.0%" in markdown

    def test_comparison_markdown_with_regression(self, sample_baseline, regressed_baseline):
        """Test Markdown report with regression warning."""
        comparison = BaselineComparison(
            baseline=sample_baseline,
            current=regressed_baseline,
            match_rate_delta_percent=-10.0,
            matched_records_delta=-100,
            regression_severity="FAILURE",
            exceeded_threshold=True,
            threshold_percent=5.0,
            regression_messages=["Match rate declined significantly"],
        )

        markdown = comparison.to_markdown()

        assert "FAILURE" in markdown
        assert "WARNING" in markdown
        assert "Match rate declined" in markdown


class TestQualityBaselineManager:
    """Tests for QualityBaselineManager."""

    def test_manager_initialization(self, baseline_manager):
        """Test manager initialization creates directories."""
        assert baseline_manager.baseline_dir.exists()
        assert baseline_manager.baseline_file.parent.exists()

    def test_save_baseline(self, baseline_manager, sample_baseline):
        """Test saving baseline to file."""
        path = baseline_manager.save_baseline(sample_baseline)

        assert path.exists()
        assert path == baseline_manager.baseline_file

        # Verify content
        with open(path) as f:
            data = json.load(f)
        assert data["match_rate"] == 0.85

    def test_load_baseline(self, baseline_manager, sample_baseline):
        """Test loading baseline from file."""
        baseline_manager.save_baseline(sample_baseline)
        loaded = baseline_manager.load_baseline()

        assert loaded is not None
        assert loaded.match_rate == sample_baseline.match_rate
        assert loaded.matched_records == sample_baseline.matched_records

    def test_load_nonexistent_baseline(self, baseline_manager):
        """Test loading when no baseline exists."""
        loaded = baseline_manager.load_baseline()

        assert loaded is None

    def test_create_baseline_from_metrics(self, baseline_manager):
        """Test creating baseline from metrics."""
        baseline = baseline_manager.create_baseline_from_metrics(
            match_rate=0.80,
            matched_records=800,
            total_records=1000,
            exact_matches=500,
            fuzzy_matches=300,
            run_id="test_run",
            processing_mode="chunked",
            metadata={"test": "value"},
        )

        assert baseline.match_rate == 0.80
        assert baseline.matched_records == 800
        assert baseline.run_id == "test_run"
        assert baseline.metadata["test"] == "value"

    def test_compare_to_baseline_improvement(
        self, baseline_manager, sample_baseline, improved_baseline
    ):
        """Test comparison showing improvement."""
        baseline_manager.save_baseline(sample_baseline)

        comparison = baseline_manager.compare_to_baseline(improved_baseline)

        assert comparison.regression_severity == "PASS"
        assert comparison.has_regression is False
        assert comparison.match_rate_delta_percent > 0

    def test_compare_to_baseline_regression(
        self, baseline_manager, sample_baseline, regressed_baseline
    ):
        """Test comparison showing regression."""
        baseline_manager.save_baseline(sample_baseline)

        comparison = baseline_manager.compare_to_baseline(
            regressed_baseline, regression_threshold_percent=5.0
        )

        assert comparison.regression_severity in ["WARNING", "FAILURE"]
        assert comparison.has_regression is True
        assert comparison.match_rate_delta_percent < 0

    def test_compare_with_no_baseline(self, baseline_manager, sample_baseline):
        """Test comparison when no baseline exists."""
        comparison = baseline_manager.compare_to_baseline(sample_baseline)

        assert comparison.regression_severity == "PASS"
        assert "Initial baseline" in comparison.regression_messages[0]

    def test_compare_with_explicit_baseline(
        self, baseline_manager, sample_baseline, improved_baseline
    ):
        """Test comparison with explicitly provided baseline."""
        comparison = baseline_manager.compare_to_baseline(
            improved_baseline, baseline=sample_baseline
        )

        assert comparison.baseline == sample_baseline
        assert comparison.current == improved_baseline

    def test_history_tracking(self, baseline_manager, sample_baseline, improved_baseline):
        """Test that baselines are tracked in history."""
        baseline_manager.save_baseline(sample_baseline)
        baseline_manager.save_baseline(improved_baseline)

        history = baseline_manager.get_history()

        assert len(history) == 2
        assert history[0].match_rate == 0.90  # Most recent first
        assert history[1].match_rate == 0.85

    def test_history_with_limit(self, baseline_manager):
        """Test loading history with limit."""
        # Create 5 baselines
        for i in range(5):
            baseline = QualityBaseline(
                timestamp=datetime(2024, 1, i + 1),
                match_rate=0.80 + i * 0.02,
                matched_records=800,
                total_records=1000,
                exact_matches=500,
                fuzzy_matches=300,
            )
            baseline_manager.save_baseline(baseline)

        history = baseline_manager.get_history(limit=3)

        assert len(history) == 3
        # Most recent first
        assert history[0].timestamp.day == 5

    def test_calculate_trend_improving(self, baseline_manager):
        """Test trend calculation for improving quality."""
        # Create improving trend
        for i in range(5):
            baseline = QualityBaseline(
                timestamp=datetime(2024, 1, i + 1),
                match_rate=0.70 + i * 0.05,  # 0.70, 0.75, 0.80, 0.85, 0.90
                matched_records=700 + i * 50,
                total_records=1000,
                exact_matches=500,
                fuzzy_matches=300,
            )
            baseline_manager.save_baseline(baseline)

        trend = baseline_manager.calculate_trend(num_recent=5)

        assert trend["trend"] == "improving"
        assert trend["direction"] == "up"
        assert trend["baselines_analyzed"] == 5

    def test_calculate_trend_declining(self, baseline_manager):
        """Test trend calculation for declining quality."""
        # Create declining trend
        for i in range(5):
            baseline = QualityBaseline(
                timestamp=datetime(2024, 1, i + 1),
                match_rate=0.90 - i * 0.05,  # 0.90, 0.85, 0.80, 0.75, 0.70
                matched_records=900 - i * 50,
                total_records=1000,
                exact_matches=500,
                fuzzy_matches=300,
            )
            baseline_manager.save_baseline(baseline)

        trend = baseline_manager.calculate_trend(num_recent=5)

        assert trend["trend"] == "declining"
        assert trend["direction"] == "down"

    def test_calculate_trend_no_data(self, baseline_manager):
        """Test trend calculation with no historical data."""
        trend = baseline_manager.calculate_trend()

        assert trend["trend"] == "no_data"
        assert trend["direction"] == "unknown"
        assert trend["baselines_analyzed"] == 0
