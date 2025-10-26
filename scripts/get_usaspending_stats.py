#!/usr/bin/env python3
"""CLI hook to retrieve USAspending profiling statistics.

This script provides a command-line interface to access the latest USAspending
dump profiling statistics, useful for Dagster assets and automation.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Optional

from loguru import logger


class USAspendingStatsProvider:
    """Provides access to USAspending profiling statistics."""

    def __init__(self, profile_path: Path = Path("reports/usaspending_subset_profile.json")):
        """Initialize stats provider.

        Args:
            profile_path: Path to the profiling report JSON
        """
        self.profile_path = profile_path

    def get_stats(self) -> Optional[Dict]:
        """Get the profiling statistics.

        Returns:
            Dictionary with profiling stats, or None if not available
        """
        if not self.profile_path.exists():
            logger.warning(f"Profile file not found: {self.profile_path}")
            return None

        try:
            with open(self.profile_path) as f:
                stats = json.load(f)
            return stats
        except Exception as e:
            logger.error(f"Failed to load profile: {e}")
            return None

    def is_data_available(self) -> bool:
        """Check if profiling data is available and valid.

        Returns:
            True if data is available and appears valid
        """
        stats = self.get_stats()
        if not stats:
            return False

        # Check for required fields
        required_fields = ["dump_path", "dump_size_gb", "profiling_timestamp"]
        return all(field in stats for field in required_fields)

    def get_table_count(self) -> int:
        """Get the number of tables found in the dump.

        Returns:
            Number of tables, or 0 if unknown
        """
        stats = self.get_stats()
        if not stats:
            return 0

        metadata = stats.get("metadata", {})
        return metadata.get("total_tables", 0)

    def get_approximate_row_count(self, table_name: str = "transaction_normalized") -> int:
        """Get approximate row count for a table.

        Args:
            table_name: Name of the table

        Returns:
            Approximate row count, or 0 if unknown
        """
        stats = self.get_stats()
        if not stats:
            return 0

        # Look for table in samples
        for sample in stats.get("table_samples", []):
            if sample.get("table_name") == table_name:
                # This is approximate since we only sample
                sample_rows = sample.get("sample_rows", 0)
                # Rough estimate: assume sample represents a fraction of total
                # This is very approximate and should be updated with actual counts
                return max(sample_rows * 100, sample_rows)  # Conservative estimate

        return 0

    def get_dump_info(self) -> Dict:
        """Get basic dump information.

        Returns:
            Dictionary with dump metadata
        """
        stats = self.get_stats()
        if not stats:
            return {"available": False}

        return {
            "available": True,
            "path": stats.get("dump_path"),
            "size_gb": stats.get("dump_size_gb"),
            "profiling_date": stats.get("profiling_timestamp"),
            "table_count": self.get_table_count(),
        }

    def get_coverage_assessment(self) -> Dict:
        """Get enrichment coverage assessment if available.

        Returns:
            Dictionary with coverage stats
        """
        coverage_path = self.profile_path.parent / "usaspending_coverage_assessment.json"

        if not coverage_path.exists():
            return {"available": False}

        try:
            with open(coverage_path) as f:
                coverage = json.load(f)
            return {"available": True, **coverage}
        except Exception as e:
            logger.error(f"Failed to load coverage assessment: {e}")
            return {"available": False, "error": str(e)}


def format_stats_for_display(stats: Dict) -> str:
    """Format statistics for human-readable display.

    Args:
        stats: Statistics dictionary

    Returns:
        Formatted string
    """
    if not stats.get("available", False):
        return "USAspending profiling data not available"

    lines = [
        "USAspending Dump Statistics:",
        f"  Path: {stats.get('path', 'Unknown')}",
        f"  Size: {stats.get('size_gb', 'Unknown')} GB",
        f"  Tables: {stats.get('table_count', 'Unknown')}",
        f"  Profile Date: {stats.get('profiling_date', 'Unknown')}",
    ]

    return "\n".join(lines)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Retrieve USAspending profiling statistics")
    parser.add_argument(
        "--profile-path",
        type=Path,
        default=Path("reports/usaspending_subset_profile.json"),
        help="Path to profiling report JSON",
    )
    parser.add_argument(
        "--check-available",
        action="store_true",
        help="Check if profiling data is available (exit code 0 if yes, 1 if no)",
    )
    parser.add_argument(
        "--get-table-count",
        action="store_true",
        help="Print the number of tables found",
    )
    parser.add_argument(
        "--get-row-count",
        type=str,
        help="Print approximate row count for specified table",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress informational output",
    )

    args = parser.parse_args()

    # Set up logging
    if not args.quiet:
        logger.add(sys.stderr, level="INFO")

    provider = USAspendingStatsProvider(args.profile_path)

    if args.check_available:
        available = provider.is_data_available()
        if args.json:
            print(json.dumps({"available": available}))
        else:
            print("Available" if available else "Not available")
        sys.exit(0 if available else 1)

    if args.get_table_count:
        count = provider.get_table_count()
        if args.json:
            print(json.dumps({"table_count": count}))
        else:
            print(count)
        return

    if args.get_row_count:
        count = provider.get_approximate_row_count(args.get_row_count)
        if args.json:
            print(json.dumps({"table": args.get_row_count, "approximate_row_count": count}))
        else:
            print(count)
        return

    # Default: show all stats
    stats = provider.get_stats()
    coverage = provider.get_coverage_assessment()

    if args.json:
        output = {
            "profiling_stats": stats,
            "coverage_assessment": coverage,
        }
        print(json.dumps(output, indent=2, default=str))
    else:
        dump_info = provider.get_dump_info()
        print(format_stats_for_display(dump_info))

        if coverage.get("available"):
            print(f"\nCoverage Assessment:")
            print(
                f"  Overall Match Rate: {coverage.get('overall_coverage', {}).get('match_rate', 0):.1%}"
            )
            print(f"  Target Achieved: {coverage.get('target_achieved', False)}")


if __name__ == "__main__":
    main()
