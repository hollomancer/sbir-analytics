#!/usr/bin/env python3
"""Analyze historical performance metrics and trends.

This script provides utilities to:
- Archive benchmark and quality metrics with timestamps
- Query historical metrics across time ranges
- Detect performance trends and anomalies
- Generate trend reports and visualizations
- Compare metrics across different time periods

Usage:
    # Archive current metrics
    python scripts/analyze_performance_history.py --archive

    # Query metrics for last 7 days
    python scripts/analyze_performance_history.py --query --days 7

    # Generate trend report
    python scripts/analyze_performance_history.py --trend-report --output report.md

    # List all archived metrics
    python scripts/analyze_performance_history.py --list
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from loguru import logger


class PerformanceMetricsArchive:
    """Manage historical performance metrics storage and retrieval."""

    def __init__(
        self,
        benchmarks_dir: Path = Path("reports/benchmarks"),
        quality_dir: Path = Path("reports/quality"),
        archive_dir: Path = Path("reports/archive"),
    ):
        """Initialize archive manager.

        Args:
            benchmarks_dir: Directory for benchmark metrics
            quality_dir: Directory for quality metrics
            archive_dir: Directory for archived metrics
        """
        self.benchmarks_dir = benchmarks_dir
        self.quality_dir = quality_dir
        self.archive_dir = archive_dir

        # Create directories if needed
        self.benchmarks_dir.mkdir(parents=True, exist_ok=True)
        self.quality_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

    def archive_current_metrics(self) -> dict[str, Path]:
        """Archive current benchmark and quality metrics with timestamp.

        Returns:
            Dictionary with archived file paths
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archived = {}

        # Archive latest benchmark if it exists
        latest_benchmark = self._find_latest_file(self.benchmarks_dir, "benchmark_*.json")
        if latest_benchmark:
            archive_path = self.archive_dir / f"benchmark_{timestamp}.json"
            self._copy_with_metadata(latest_benchmark, archive_path)
            archived["benchmark"] = archive_path
            logger.info(f"Archived benchmark: {archive_path}")

        # Archive latest quality report if it exists
        latest_quality = self._find_latest_file(self.quality_dir, "*.json")
        if latest_quality:
            archive_path = self.archive_dir / f"quality_{timestamp}.json"
            self._copy_with_metadata(latest_quality, archive_path)
            archived["quality"] = archive_path
            logger.info(f"Archived quality report: {archive_path}")

        return archived

    def query_metrics(
        self,
        days: int = 7,
        metric_type: str = "benchmark",
    ) -> list[tuple[Path, dict[str, Any]]]:
        """Query historical metrics within time range.

        Args:
            days: Number of days to look back (default: 7)
            metric_type: Type of metrics to query (benchmark, quality, or all)

        Returns:
            List of (file_path, metrics) tuples sorted by timestamp
        """
        cutoff_time = datetime.now() - timedelta(days=days)
        results = []

        # Determine which directories to search
        search_dirs = []
        if metric_type in ("benchmark", "all"):
            search_dirs.append(self.archive_dir)
        if metric_type in ("quality", "all"):
            search_dirs.append(self.archive_dir)

        # Search for matching files
        for search_dir in search_dirs:
            if not search_dir.exists():
                continue

            pattern = f"{metric_type}_*.json" if metric_type != "all" else "*.json"

            for file_path in sorted(search_dir.glob(pattern)):
                try:
                    # Extract timestamp from filename
                    timestamp = self._extract_timestamp(file_path.name)
                    if not timestamp:
                        continue

                    if timestamp < cutoff_time:
                        continue

                    # Load metrics
                    with open(file_path) as f:
                        metrics = json.load(f)

                    results.append((file_path, metrics))

                except Exception as e:
                    logger.warning(f"Failed to load metrics from {file_path}: {e}")

        return results

    def analyze_trends(
        self,
        metrics_list: list[tuple[Path, dict[str, Any]]],
    ) -> dict[str, Any]:
        """Analyze performance trends from historical metrics.

        Args:
            metrics_list: List of (file_path, metrics) tuples

        Returns:
            Trend analysis dictionary
        """
        if not metrics_list:
            return {}

        # Extract time-series data
        timestamps = []
        durations = []
        memories = []
        match_rates = []
        throughputs = []

        for file_path, metrics in metrics_list:
            try:
                timestamp = self._extract_timestamp(file_path.name)
                if not timestamp:
                    continue

                timestamps.append(timestamp)

                # Extract performance metrics
                perf = metrics.get("performance_metrics", {})
                if perf:
                    durations.append(perf.get("total_duration_seconds", 0))
                    memories.append(perf.get("peak_memory_mb", 0))
                    throughputs.append(perf.get("records_per_second", 0))

                # Extract quality metrics
                stats = metrics.get("enrichment_stats", {})
                if stats:
                    match_rates.append(stats.get("match_rate", 0))

            except Exception as e:
                logger.warning(f"Failed to extract metrics from {file_path}: {e}")

        # Calculate statistics
        trend_analysis = {
            "run_count": len(metrics_list),
            "time_period": {
                "start": timestamps[0].isoformat() if timestamps else None,
                "end": timestamps[-1].isoformat() if timestamps else None,
            },
        }

        # Duration trend
        if durations:
            trend_analysis["duration"] = {
                "min": min(durations),
                "max": max(durations),
                "avg": sum(durations) / len(durations),
                "latest": durations[-1],
                "trend": self._calculate_trend(durations),
                "change_percent": self._calculate_change_percent(durations[0], durations[-1]),
            }

        # Memory trend
        if memories:
            trend_analysis["memory"] = {
                "min": min(memories),
                "max": max(memories),
                "avg": sum(memories) / len(memories),
                "latest": memories[-1],
                "trend": self._calculate_trend(memories),
                "change_percent": self._calculate_change_percent(memories[0], memories[-1]),
            }

        # Throughput trend
        if throughputs:
            trend_analysis["throughput"] = {
                "min": min(throughputs),
                "max": max(throughputs),
                "avg": sum(throughputs) / len(throughputs),
                "latest": throughputs[-1],
                "trend": self._calculate_trend(throughputs),
                "change_percent": self._calculate_change_percent(
                    throughputs[-1], throughputs[0]
                ),  # Inverted (higher is better)
            }

        # Match rate trend
        if match_rates:
            trend_analysis["match_rate"] = {
                "min": min(match_rates),
                "max": max(match_rates),
                "avg": sum(match_rates) / len(match_rates),
                "latest": match_rates[-1],
                "trend": self._calculate_trend(match_rates),
                "change_percent": self._calculate_change_percent(match_rates[0], match_rates[-1]),
            }

        return trend_analysis

    def generate_trend_report(
        self,
        metrics_list: list[tuple[Path, dict[str, Any]]],
        output_path: Path | None = None,
    ) -> str:
        """Generate markdown trend report.

        Args:
            metrics_list: List of (file_path, metrics) tuples
            output_path: Optional path to save report

        Returns:
            Markdown report text
        """
        trend_analysis = self.analyze_trends(metrics_list)

        if not trend_analysis:
            report = "# Performance Trend Report\n\nNo metrics available for analysis.\n"
        else:
            report = self._format_trend_report(trend_analysis)

        # Save if path provided
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w") as f:
                f.write(report)
            logger.info(f"Trend report saved to {output_path}")

        return report

    def list_archived_metrics(self) -> list[dict[str, Any]]:
        """List all archived metrics files with metadata.

        Returns:
            List of file info dictionaries
        """
        files = []

        if not self.archive_dir.exists():
            return files

        for file_path in sorted(self.archive_dir.glob("*.json"), reverse=True):
            try:
                timestamp = self._extract_timestamp(file_path.name)
                file_size = file_path.stat().st_size

                # Try to load and get metrics count
                with open(file_path) as f:
                    data = json.load(f)

                file_info = {
                    "filename": file_path.name,
                    "path": str(file_path),
                    "timestamp": timestamp.isoformat() if timestamp else None,
                    "size_kb": round(file_size / 1024, 2),
                    "type": "benchmark" if "benchmark" in file_path.name else "quality",
                }

                # Add metrics summary
                if "performance_metrics" in data:
                    perf = data["performance_metrics"]
                    file_info["duration_seconds"] = perf.get("total_duration_seconds")
                    file_info["match_rate"] = data.get("enrichment_stats", {}).get("match_rate")

                files.append(file_info)

            except Exception as e:
                logger.warning(f"Failed to read {file_path}: {e}")

        return files

    @staticmethod
    def _find_latest_file(directory: Path, pattern: str) -> Path | None:
        """Find the most recently modified file matching pattern.

        Args:
            directory: Directory to search
            pattern: Glob pattern to match

        Returns:
            Path to latest matching file or None
        """
        if not directory.exists():
            return None

        files = list(directory.glob(pattern))
        if not files:
            return None

        return max(files, key=lambda p: p.stat().st_mtime)

    @staticmethod
    def _copy_with_metadata(src: Path, dst: Path) -> None:
        """Copy file with metadata preservation.

        Args:
            src: Source file path
            dst: Destination file path
        """
        with open(src) as f:
            data = json.load(f)

        # Add archive metadata
        data["archived_at"] = datetime.now().isoformat()
        data["archived_from"] = str(src)

        with open(dst, "w") as f:
            json.dump(data, f, indent=2)

    @staticmethod
    def _extract_timestamp(filename: str) -> datetime | None:
        """Extract timestamp from filename.

        Args:
            filename: Filename to parse

        Returns:
            Extracted datetime or None
        """
        # Handle benchmark_YYYYMMDD_HHMMSS.json format
        # Handle quality_YYYYMMDD_HHMMSS.json format
        try:
            # Extract YYYYMMDD_HHMMSS portion
            parts = filename.replace(".json", "").split("_")
            if len(parts) >= 3:
                date_part = parts[-2]  # YYYYMMDD
                time_part = parts[-1]  # HHMMSS

                if len(date_part) == 8 and len(time_part) == 6:
                    datetime_str = f"{date_part}_{time_part}"
                    return datetime.strptime(datetime_str, "%Y%m%d_%H%M%S")
        except Exception:
            pass

        return None

    @staticmethod
    def _calculate_trend(values: list[float]) -> str:
        """Determine if trend is improving or degrading.

        Args:
            values: List of metric values (earlier to later)

        Returns:
            "improving", "degrading", or "stable"
        """
        if len(values) < 2:
            return "stable"

        # For most metrics, lower is better (duration, memory)
        # For throughput/match_rate, higher is better (handled by caller)
        first = values[0]
        last = values[-1]
        change = (last - first) / first if first != 0 else 0

        if change < -0.05:  # 5% improvement
            return "improving"
        elif change > 0.05:  # 5% degradation
            return "degrading"
        else:
            return "stable"

    @staticmethod
    def _calculate_change_percent(earlier: float, later: float) -> float:
        """Calculate percentage change from earlier to later value.

        Args:
            earlier: Earlier value
            later: Later value

        Returns:
            Percentage change (positive = increase)
        """
        if earlier == 0:
            return 0.0

        return round(((later - earlier) / earlier) * 100, 1)

    @staticmethod
    def _format_trend_report(trend_analysis: dict[str, Any]) -> str:
        """Format trend analysis as markdown.

        Args:
            trend_analysis: Analysis dictionary from analyze_trends()

        Returns:
            Markdown formatted report
        """
        lines = [
            "# Performance Trend Report",
            "",
            f"**Period:** {trend_analysis['time_period']['start']} to {trend_analysis['time_period']['end']}",
            f"**Runs Analyzed:** {trend_analysis['run_count']}",
            "",
        ]

        # Duration section
        if "duration" in trend_analysis:
            d = trend_analysis["duration"]
            lines.extend(
                [
                    "## Duration Trend",
                    "",
                    f"- **Latest:** {d['latest']:.2f}s",
                    f"- **Average:** {d['avg']:.2f}s",
                    f"- **Range:** {d['min']:.2f}s - {d['max']:.2f}s",
                    f"- **Trend:** {d['trend']} ({d['change_percent']:+.1f}%)",
                    "",
                ]
            )

        # Memory section
        if "memory" in trend_analysis:
            m = trend_analysis["memory"]
            lines.extend(
                [
                    "## Memory Trend",
                    "",
                    f"- **Latest:** {m['latest']:.0f} MB",
                    f"- **Average:** {m['avg']:.0f} MB",
                    f"- **Range:** {m['min']:.0f} MB - {m['max']:.0f} MB",
                    f"- **Trend:** {m['trend']} ({m['change_percent']:+.1f}%)",
                    "",
                ]
            )

        # Throughput section
        if "throughput" in trend_analysis:
            t = trend_analysis["throughput"]
            lines.extend(
                [
                    "## Throughput Trend",
                    "",
                    f"- **Latest:** {t['latest']:.0f} records/sec",
                    f"- **Average:** {t['avg']:.0f} records/sec",
                    f"- **Range:** {t['min']:.0f} - {t['max']:.0f} records/sec",
                    f"- **Trend:** {t['trend']} ({t['change_percent']:+.1f}%)",
                    "",
                ]
            )

        # Match rate section
        if "match_rate" in trend_analysis:
            mr = trend_analysis["match_rate"]
            lines.extend(
                [
                    "## Match Rate Trend",
                    "",
                    f"- **Latest:** {mr['latest']:.1%}",
                    f"- **Average:** {mr['avg']:.1%}",
                    f"- **Range:** {mr['min']:.1%} - {mr['max']:.1%}",
                    f"- **Trend:** {mr['trend']} ({mr['change_percent']:+.1f}pp)",
                    "",
                ]
            )

        lines.append("## Interpretation")
        lines.extend(
            [
                "",
                "- **improving:** Metric trending in positive direction (↓ duration/memory, ↑ throughput/match_rate)",
                "- **degrading:** Metric trending in negative direction",
                "- **stable:** Changes within ±5% tolerance",
                "",
            ]
        )

        return "\n".join(lines)


def main():
    """Run performance history analysis."""
    parser = argparse.ArgumentParser(description="Analyze historical performance metrics")
    parser.add_argument(
        "--archive", action="store_true", help="Archive current metrics with timestamp"
    )
    parser.add_argument(
        "--query",
        action="store_true",
        help="Query historical metrics",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Days to look back (default: 7)",
    )
    parser.add_argument(
        "--metric-type",
        choices=["benchmark", "quality", "all"],
        default="benchmark",
        help="Type of metrics to query",
    )
    parser.add_argument("--list", action="store_true", help="List all archived metrics")
    parser.add_argument(
        "--trend-report",
        action="store_true",
        help="Generate trend report",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output path for reports",
    )

    args = parser.parse_args()

    archive = PerformanceMetricsArchive()

    try:
        if args.archive:
            logger.info("Archiving current metrics...")
            archived = archive.archive_current_metrics()
            for metric_type, path in archived.items():
                logger.info(f"✓ Archived {metric_type}: {path}")

        elif args.list:
            logger.info("Archived metrics:")
            files = archive.list_archived_metrics()
            for file_info in files:
                logger.info(f"  {file_info['filename']} ({file_info['size_kb']} KB)")
                if "duration_seconds" in file_info:
                    logger.info(
                        f"    Duration: {file_info['duration_seconds']:.2f}s, "
                        f"Match Rate: {file_info['match_rate']:.1%}"
                    )

        elif args.query:
            logger.info(f"Querying metrics for last {args.days} days...")
            metrics_list = archive.query_metrics(days=args.days, metric_type=args.metric_type)
            logger.info(f"Found {len(metrics_list)} metric files")

            if metrics_list:
                for file_path, metrics in metrics_list:
                    perf = metrics.get("performance_metrics", {})
                    logger.info(
                        f"  {file_path.name}: "
                        f"{perf.get('total_duration_seconds', 0):.2f}s, "
                        f"{perf.get('peak_memory_mb', 0):.0f}MB"
                    )

        elif args.trend_report:
            logger.info(f"Generating trend report for last {args.days} days...")
            metrics_list = archive.query_metrics(days=args.days, metric_type=args.metric_type)

            if metrics_list:
                report = archive.generate_trend_report(metrics_list, args.output)
                print("\n" + report)
            else:
                logger.warning(f"No metrics found for last {args.days} days")

        else:
            parser.print_help()
            return 0

        return 0

    except Exception as e:
        logger.error(f"Analysis failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
