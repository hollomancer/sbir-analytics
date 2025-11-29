"""Unit tests for quality dashboard generation.

Tests cover:
- DashboardMetrics dataclass
- Dashboard generation (with and without Plotly)
- Trend analysis dashboards
- Distribution dashboards
- Comparison dashboards
- Summary reports
"""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest


pytestmark = pytest.mark.fast

import pytest

from src.quality.dashboard import DashboardMetrics, QualityDashboard


pytestmark = pytest.mark.fast


@pytest.fixture
def sample_metrics():
    """Create sample dashboard metrics."""
    return DashboardMetrics(
        timestamp=datetime(2024, 1, 1, 12, 0, 0),
        match_rate=0.85,
        matched_records=850,
        total_records=1000,
        exact_matches=500,
        fuzzy_matches=350,
        unmatched_records=150,
        fuzzy_scores=[0.8, 0.85, 0.9, 0.95],
        match_methods={"exact": 500, "fuzzy": 350},
        by_phase={"phase1": 0.8, "phase2": 0.9},
    )


@pytest.fixture
def dashboard(tmp_path):
    """Create dashboard instance with temp output dir."""
    return QualityDashboard(output_dir=tmp_path / "dashboards")


@pytest.fixture
def metrics_history():
    """Create sample metrics history."""
    return [
        DashboardMetrics(
            timestamp=datetime(2024, 1, i, 12, 0, 0),
            match_rate=0.80 + i * 0.02,
            matched_records=800 + i * 20,
            total_records=1000,
            exact_matches=500,
            fuzzy_matches=300 + i * 20,
            unmatched_records=200 - i * 20,
            match_methods={"exact": 500, "fuzzy": 300 + i * 20},
        )
        for i in range(1, 6)
    ]


class TestDashboardMetrics:
    """Tests for DashboardMetrics dataclass."""

    def test_metrics_creation(self, sample_metrics):
        """Test metrics creation with all fields."""
        assert sample_metrics.match_rate == 0.85
        assert sample_metrics.matched_records == 850
        assert sample_metrics.total_records == 1000
        assert len(sample_metrics.fuzzy_scores) == 4
        assert sample_metrics.match_methods["exact"] == 500

    def test_metrics_optional_fields(self):
        """Test metrics with only required fields."""
        metrics = DashboardMetrics(
            timestamp=datetime.now(),
            match_rate=0.80,
            matched_records=800,
            total_records=1000,
            exact_matches=500,
            fuzzy_matches=300,
            unmatched_records=200,
        )

        assert metrics.fuzzy_scores is None
        assert metrics.match_methods is None


class TestQualityDashboard:
    """Tests for QualityDashboard class."""

    def test_dashboard_initialization(self, dashboard):
        """Test dashboard initialization."""
        assert dashboard.output_dir.exists()

    def test_dashboard_default_output_dir(self):
        """Test dashboard with default output directory."""
        dashboard = QualityDashboard()

        assert dashboard.output_dir == Path("reports/dashboards")

    def test_load_metrics_history(self, tmp_path, sample_metrics):
        """Test loading metrics history from file."""
        # Create history file
        history_file = tmp_path / "history.jsonl"
        with open(history_file, "w") as f:
            data = {
                "timestamp": sample_metrics.timestamp.isoformat(),
                "match_rate": sample_metrics.match_rate,
                "matched_records": sample_metrics.matched_records,
                "total_records": sample_metrics.total_records,
                "exact_matches": sample_metrics.exact_matches,
                "fuzzy_matches": sample_metrics.fuzzy_matches,
                "unmatched_records": sample_metrics.unmatched_records,
            }
            f.write(json.dumps(data) + "\n")

        dashboard = QualityDashboard(output_dir=tmp_path)
        metrics_list = dashboard.load_metrics_history(history_file)

        assert len(metrics_list) == 1
        assert metrics_list[0].match_rate == 0.85

    def test_load_metrics_history_with_limit(self, tmp_path):
        """Test loading history with limit."""
        history_file = tmp_path / "history.jsonl"
        with open(history_file, "w") as f:
            for i in range(10):
                data = {
                    "timestamp": datetime(2024, 1, i + 1).isoformat(),
                    "match_rate": 0.80,
                    "matched_records": 800,
                    "total_records": 1000,
                    "exact_matches": 500,
                    "fuzzy_matches": 300,
                    "unmatched_records": 200,
                }
                f.write(json.dumps(data) + "\n")

        dashboard = QualityDashboard(output_dir=tmp_path)
        metrics_list = dashboard.load_metrics_history(history_file, limit=5)

        assert len(metrics_list) == 5

    def test_load_metrics_nonexistent_file(self, tmp_path):
        """Test loading from non-existent file."""
        dashboard = QualityDashboard(output_dir=tmp_path)
        metrics_list = dashboard.load_metrics_history(tmp_path / "missing.jsonl")

        assert len(metrics_list) == 0

    @patch("src.quality.dashboard.PLOTLY_AVAILABLE", True)
    @patch("plotly.subplots.make_subplots")
    def test_generate_trend_dashboard_with_plotly(self, mock_subplots, dashboard, metrics_history):
        """Test trend dashboard generation with Plotly available."""
        mock_fig = Mock()
        mock_subplots.return_value = mock_fig

        output_file = dashboard.generate_trend_dashboard(metrics_history)

        assert output_file.exists()
        mock_fig.write_html.assert_called_once()

    @patch("src.quality.dashboard.PLOTLY_AVAILABLE", False)
    def test_generate_trend_dashboard_without_plotly(self, dashboard, metrics_history):
        """Test trend dashboard fallback without Plotly."""
        output_file = dashboard.generate_trend_dashboard(metrics_history)

        assert output_file.exists()
        # Should generate JSON file
        with open(output_file) as f:
            data = json.load(f)
        assert "metrics" in data

    def test_generate_trend_dashboard_empty_history(self, dashboard):
        """Test trend dashboard with empty history."""
        output_file = dashboard.generate_trend_dashboard([])

        assert "empty_dashboard" in str(output_file)

    @patch("src.quality.dashboard.PLOTLY_AVAILABLE", True)
    @patch("plotly.subplots.make_subplots")
    def test_generate_distribution_dashboard(self, mock_subplots, dashboard, sample_metrics):
        """Test distribution dashboard generation."""
        mock_fig = Mock()
        mock_subplots.return_value = mock_fig

        output_file = dashboard.generate_distribution_dashboard(sample_metrics)

        assert output_file.exists()
        mock_fig.write_html.assert_called_once()

    @patch("src.quality.dashboard.PLOTLY_AVAILABLE", False)
    def test_generate_distribution_dashboard_without_plotly(self, dashboard, sample_metrics):
        """Test distribution dashboard without Plotly."""
        output_file = dashboard.generate_distribution_dashboard(sample_metrics)

        assert output_file.exists()
        with open(output_file) as f:
            data = json.load(f)
        assert "metrics" in data

    @patch("src.quality.dashboard.PLOTLY_AVAILABLE", True)
    @patch("plotly.graph_objects.Figure")
    def test_generate_comparison_dashboard(self, mock_figure, dashboard):
        """Test comparison dashboard generation."""
        current = DashboardMetrics(
            timestamp=datetime.now(),
            match_rate=0.90,
            matched_records=900,
            total_records=1000,
            exact_matches=550,
            fuzzy_matches=350,
            unmatched_records=100,
        )
        baseline = DashboardMetrics(
            timestamp=datetime.now(),
            match_rate=0.85,
            matched_records=850,
            total_records=1000,
            exact_matches=500,
            fuzzy_matches=350,
            unmatched_records=150,
        )

        mock_fig = Mock()
        mock_figure.return_value = mock_fig

        output_file = dashboard.generate_comparison_dashboard(current, baseline)

        assert output_file.exists()
        mock_fig.write_html.assert_called_once()

    def test_generate_summary_report(self, dashboard, metrics_history):
        """Test Markdown summary report generation."""
        report_text, output_file = dashboard.generate_summary_report(metrics_history)

        assert output_file.exists()
        assert "Enrichment Quality Summary Report" in report_text
        assert "Current Metrics" in report_text
        assert "Historical Trends" in report_text

    def test_generate_summary_report_empty(self, dashboard):
        """Test summary report with empty history."""
        report_text, output_file = dashboard.generate_summary_report([])

        assert report_text == ""
        assert "empty_report" in str(output_file)

    def test_summary_report_recommendations(self, dashboard):
        """Test that summary report includes recommendations."""
        # Low match rate metrics
        low_metrics = [
            DashboardMetrics(
                timestamp=datetime.now(),
                match_rate=0.65,  # Below 70% threshold
                matched_records=650,
                total_records=1000,
                exact_matches=400,
                fuzzy_matches=250,
                unmatched_records=350,
            )
        ]

        report_text, _ = dashboard.generate_summary_report(low_metrics)

        assert "CRITICAL" in report_text
        assert "below 70%" in report_text

    def test_summary_report_trend_analysis(self, dashboard):
        """Test trend analysis in summary report."""
        # Create improving trend
        improving_metrics = [
            DashboardMetrics(
                timestamp=datetime(2024, 1, i),
                match_rate=0.70 + i * 0.05,
                matched_records=700 + i * 50,
                total_records=1000,
                exact_matches=400,
                fuzzy_matches=300,
                unmatched_records=300 - i * 50,
            )
            for i in range(1, 6)
        ]

        report_text, _ = dashboard.generate_summary_report(improving_metrics)

        # Trend should be positive
        assert "Trend" in report_text

    def test_json_dashboard_fallback(self, dashboard, sample_metrics):
        """Test JSON dashboard generation fallback."""
        output_file = dashboard._generate_json_dashboard(
            [sample_metrics], dashboard.output_dir / "test.json"
        )

        assert output_file.exists()
        with open(output_file) as f:
            data = json.load(f)

        assert "generated_at" in data
        assert "metrics" in data
        assert len(data["metrics"]) == 1
        assert data["metrics"][0]["match_rate"] == "85.0%"

    def test_dashboard_with_match_methods(self, dashboard):
        """Test dashboard generation with match method data."""
        metrics = DashboardMetrics(
            timestamp=datetime.now(),
            match_rate=0.85,
            matched_records=850,
            total_records=1000,
            exact_matches=500,
            fuzzy_matches=350,
            unmatched_records=150,
            match_methods={"exact": 500, "fuzzy_name": 200, "fuzzy_uei": 150},
        )

        report_text, _ = dashboard.generate_summary_report([metrics])

        assert "Match Method Distribution" in report_text
        assert "exact" in report_text
        assert "fuzzy_name" in report_text

    def test_dashboard_with_fuzzy_scores(self, dashboard):
        """Test dashboard handles fuzzy scores correctly."""
        metrics = DashboardMetrics(
            timestamp=datetime.now(),
            match_rate=0.85,
            matched_records=850,
            total_records=1000,
            exact_matches=500,
            fuzzy_matches=350,
            unmatched_records=150,
            fuzzy_scores=[0.7, 0.75, 0.8, 0.85, 0.9, 0.95],
        )

        # Should not raise error with fuzzy scores
        output_file = dashboard._generate_json_dashboard(
            [metrics], dashboard.output_dir / "test.json"
        )

        assert output_file.exists()
