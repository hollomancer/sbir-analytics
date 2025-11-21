"""Shared HTML template utilities for report generation.

This module provides reusable HTML generation utilities to ensure consistent
styling and structure across different report types (performance, statistical, etc.).
"""

from __future__ import annotations

from typing import Any


class HTMLReportBuilder:
    """Shared HTML report builder with consistent styling."""

    # Shared CSS styles
    CSS_STYLES = """
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
            color: #333;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        h1 {
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }
        h2 {
            color: #34495e;
            margin-top: 30px;
            margin-bottom: 15px;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
        }
        .status-badge {
            padding: 10px 20px;
            border-radius: 4px;
            color: white;
            font-weight: bold;
        }
        .status-pass {
            background-color: green;
        }
        .status-warning {
            background-color: orange;
        }
        .status-failure {
            background-color: red;
        }
        .timestamp {
            color: #7f8c8d;
            font-size: 14px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 20px;
        }
        th {
            background-color: #ecf0f1;
            padding: 12px;
            text-align: left;
            font-weight: 600;
            border-bottom: 2px solid #bdc3c7;
        }
        td {
            padding: 12px;
            border-bottom: 1px solid #ecf0f1;
        }
        tr:hover {
            background-color: #f9f9f9;
        }
        .metric-value {
            font-weight: 600;
            color: #2980b9;
        }
        .delta-positive {
            color: #e74c3c;
        }
        .delta-negative {
            color: #27ae60;
        }
        .delta-neutral {
            color: #95a5a6;
        }
        .alert {
            padding: 12px;
            margin-bottom: 15px;
            border-left: 4px solid;
            background-color: #f9f9f9;
        }
        .alert-failure {
            border-left-color: #e74c3c;
            background-color: #fadbd8;
        }
        .alert-warning {
            border-left-color: #f39c12;
            background-color: #fdebd0;
        }
        .metric-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .metric-card {
            background-color: #ecf0f1;
            padding: 20px;
            border-radius: 4px;
            border-left: 4px solid #3498db;
        }
        .metric-card-label {
            font-size: 12px;
            color: #7f8c8d;
            text-transform: uppercase;
            margin-bottom: 8px;
        }
        .metric-card-value {
            font-size: 24px;
            font-weight: bold;
            color: #2c3e50;
        }
        .footer {
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #ecf0f1;
            color: #95a5a6;
            font-size: 12px;
        }
    """

    @staticmethod
    def create_table(
        data: list[dict[str, Any]], headers: list[str], title: str | None = None
    ) -> str:
        """Generate HTML table with consistent styling.

        Args:
            data: List of dictionaries representing table rows
            headers: List of column header names
            title: Optional table title

        Returns:
            HTML table string

        Example:
            >>> data = [{"name": "A", "value": 1}, {"name": "B", "value": 2}]
            >>> HTMLReportBuilder.create_table(data, ["name", "value"], "Metrics")
            '<h2>Metrics</h2><table>...</table>'
        """
        html_parts = []
        if title:
            html_parts.append(f"<h2>{title}</h2>")

        html_parts.append("<table>")
        html_parts.append("<tr>")
        for header in headers:
            html_parts.append(f"<th>{header}</th>")
        html_parts.append("</tr>")

        for row in data:
            html_parts.append("<tr>")
            for header in headers:
                value = row.get(header, "")
                # Format value if it's a number
                if isinstance(value, (int, float)):
                    if isinstance(value, float):
                        value = f"{value:.2f}"
                    else:
                        value = f"{value:,}"
                html_parts.append(f'<td class="metric-value">{value}</td>')
            html_parts.append("</tr>")

        html_parts.append("</table>")
        return "\n".join(html_parts)

    @staticmethod
    def create_metric_card(label: str, value: str, delta: str | None = None) -> str:
        """Generate metric card HTML.

        Args:
            label: Metric label
            value: Metric value
            delta: Optional delta value (e.g., "+5.2%")

        Returns:
            HTML metric card string

        Example:
            >>> HTMLReportBuilder.create_metric_card("Duration", "10.5s", "+2.1%")
            '<div class="metric-card">...</div>'
        """
        html_parts = ['<div class="metric-card">']
        html_parts.append(f'<div class="metric-card-label">{label}</div>')
        html_parts.append(f'<div class="metric-card-value">{value}</div>')
        if delta:
            # Determine delta class based on sign
            delta_class = "delta-neutral"
            if delta.startswith("+"):
                delta_class = "delta-positive"
            elif delta.startswith("-"):
                delta_class = "delta-negative"
            html_parts.append(f'<div class="{delta_class}">{delta}</div>')
        html_parts.append("</div>")
        return "\n".join(html_parts)

    @staticmethod
    def create_metric_grid(cards: list[str]) -> str:
        """Generate metric grid container.

        Args:
            cards: List of metric card HTML strings

        Returns:
            HTML metric grid string
        """
        html_parts = ['<div class="metric-grid">']
        html_parts.extend(cards)
        html_parts.append("</div>")
        return "\n".join(html_parts)

    @staticmethod
    def create_status_badge(status: str) -> str:
        """Generate status badge HTML.

        Args:
            status: Status value ("PASS", "WARNING", "FAILURE")

        Returns:
            HTML status badge string
        """
        status_lower = status.upper()
        status_class = "status-pass"
        if status_lower == "WARNING":
            status_class = "status-warning"
        elif status_lower == "FAILURE":
            status_class = "status-failure"

        return f'<div class="status-badge {status_class}">{status}</div>'

    @staticmethod
    def create_alert(message: str, severity: str = "info") -> str:
        """Generate alert HTML.

        Args:
            message: Alert message
            severity: Alert severity ("info", "warning", "failure")

        Returns:
            HTML alert string
        """
        severity_class = "alert"
        if severity == "failure":
            severity_class = "alert-failure"
        elif severity == "warning":
            severity_class = "alert-warning"

        icon = "ℹ️"
        if severity == "failure":
            icon = "❌"
        elif severity == "warning":
            icon = "⚠️"

        return f'<div class="{severity_class}"><strong>{icon}</strong> {message}</div>'

    @staticmethod
    def create_report_layout(
        title: str, content: str, status: str = "PASS", timestamp: str | None = None
    ) -> str:
        """Generate full report HTML with consistent structure.

        Args:
            title: Report title
            content: Main report content HTML
            status: Report status ("PASS", "WARNING", "FAILURE")
            timestamp: Optional timestamp string

        Returns:
            Complete HTML report string

        Example:
            >>> content = "<p>Report content</p>"
            >>> HTMLReportBuilder.create_report_layout("My Report", content, "PASS")
            '<!DOCTYPE html>...'
        """
        status_badge = HTMLReportBuilder.create_status_badge(status)
        timestamp_html = f'<div class="timestamp">Generated: {timestamp}</div>' if timestamp else ""

        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
{HTMLReportBuilder.CSS_STYLES}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{title}</h1>
            {status_badge}
        </div>
        {timestamp_html}
        {content}
        <div class="footer">
            <p>Report Generated by SBIR-Analytics Pipeline</p>
        </div>
    </div>
</body>
</html>"""
        return html

    @staticmethod
    def create_header(title: str, status: str = "PASS", timestamp: str | None = None) -> str:
        """Generate report header section.

        Args:
            title: Report title
            status: Report status
            timestamp: Optional timestamp

        Returns:
            HTML header string
        """
        status_badge = HTMLReportBuilder.create_status_badge(status)
        timestamp_html = f'<div class="timestamp">Generated: {timestamp}</div>' if timestamp else ""

        return f"""<div class="header">
    <h1>{title}</h1>
    {status_badge}
</div>
{timestamp_html}"""
