"""Unit tests for HTMLReportBuilder utility."""

import pytest

from src.utils.reporting.formats.html_templates import HTMLReportBuilder


class TestHTMLReportBuilder:
    """Test HTMLReportBuilder utility methods."""

    def test_create_table_basic(self):
        """Test creating a basic HTML table."""
        data = [{"name": "A", "value": 1}, {"name": "B", "value": 2}]
        headers = ["name", "value"]
        result = HTMLReportBuilder.create_table(data, headers)
        assert "<table>" in result
        assert "<th>name</th>" in result
        assert "<th>value</th>" in result
        assert "<td class=\"metric-value\">A</td>" in result
        assert "<td class=\"metric-value\">1</td>" in result

    def test_create_table_with_title(self):
        """Test creating a table with title."""
        data = [{"name": "A", "value": 1}]
        headers = ["name", "value"]
        result = HTMLReportBuilder.create_table(data, headers, title="Test Table")
        assert "<h2>Test Table</h2>" in result
        assert "<table>" in result

    def test_create_table_number_formatting(self):
        """Test that numbers are formatted correctly in tables."""
        data = [{"value": 1000.5}, {"value": 2000}]
        headers = ["value"]
        result = HTMLReportBuilder.create_table(data, headers)
        assert "1,000.50" in result or "1000.50" in result
        assert "2,000" in result

    def test_create_metric_card_basic(self):
        """Test creating a basic metric card."""
        result = HTMLReportBuilder.create_metric_card("Duration", "10.5s")
        assert "metric-card" in result
        assert "Duration" in result
        assert "10.5s" in result

    def test_create_metric_card_with_delta(self):
        """Test creating a metric card with delta."""
        result = HTMLReportBuilder.create_metric_card("Duration", "10.5s", "+2.1%")
        assert "10.5s" in result
        assert "+2.1%" in result
        assert "delta-positive" in result

    def test_create_metric_card_negative_delta(self):
        """Test creating a metric card with negative delta."""
        result = HTMLReportBuilder.create_metric_card("Duration", "10.5s", "-2.1%")
        assert "delta-negative" in result

    def test_create_metric_grid(self):
        """Test creating a metric grid."""
        cards = [
            HTMLReportBuilder.create_metric_card("A", "1"),
            HTMLReportBuilder.create_metric_card("B", "2"),
        ]
        result = HTMLReportBuilder.create_metric_grid(cards)
        assert "metric-grid" in result
        assert "A" in result
        assert "B" in result

    def test_create_status_badge_pass(self):
        """Test creating a PASS status badge."""
        result = HTMLReportBuilder.create_status_badge("PASS")
        assert "status-badge" in result
        assert "status-pass" in result
        assert "PASS" in result

    def test_create_status_badge_warning(self):
        """Test creating a WARNING status badge."""
        result = HTMLReportBuilder.create_status_badge("WARNING")
        assert "status-warning" in result
        assert "WARNING" in result

    def test_create_status_badge_failure(self):
        """Test creating a FAILURE status badge."""
        result = HTMLReportBuilder.create_status_badge("FAILURE")
        assert "status-failure" in result
        assert "FAILURE" in result

    def test_create_alert_info(self):
        """Test creating an info alert."""
        result = HTMLReportBuilder.create_alert("Test message", "info")
        assert "alert" in result
        assert "Test message" in result
        assert "ℹ️" in result

    def test_create_alert_warning(self):
        """Test creating a warning alert."""
        result = HTMLReportBuilder.create_alert("Test warning", "warning")
        assert "alert-warning" in result
        assert "⚠️" in result

    def test_create_alert_failure(self):
        """Test creating a failure alert."""
        result = HTMLReportBuilder.create_alert("Test failure", "failure")
        assert "alert-failure" in result
        assert "❌" in result

    def test_create_report_layout_basic(self):
        """Test creating a basic report layout."""
        content = "<p>Test content</p>"
        result = HTMLReportBuilder.create_report_layout("Test Report", content)
        assert "<!DOCTYPE html>" in result
        assert "Test Report" in result
        assert "Test content" in result
        assert "container" in result

    def test_create_report_layout_with_status(self):
        """Test creating a report layout with status."""
        content = "<p>Test</p>"
        result = HTMLReportBuilder.create_report_layout("Test", content, status="WARNING")
        assert "status-warning" in result

    def test_create_report_layout_with_timestamp(self):
        """Test creating a report layout with timestamp."""
        content = "<p>Test</p>"
        result = HTMLReportBuilder.create_report_layout(
            "Test", content, timestamp="2024-01-01T00:00:00"
        )
        assert "2024-01-01T00:00:00" in result

    def test_create_header(self):
        """Test creating a report header."""
        result = HTMLReportBuilder.create_header("Test Title", "PASS", "2024-01-01")
        assert "Test Title" in result
        assert "status-pass" in result
        assert "2024-01-01" in result

