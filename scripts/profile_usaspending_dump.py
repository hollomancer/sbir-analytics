#!/usr/bin/env python3
"""Profile USAspending Postgres dump for SBIR ETL evaluation.

This script analyzes the USAspending Postgres dump stored on removable media
to provide schema information, table statistics, and enrichment coverage assessment
without requiring full database restoration.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

import duckdb
import pandas as pd
from loguru import logger


class USAspendingDumpProfiler:
    """Profiler for USAspending Postgres dumps."""

    def __init__(self, dump_path: Path, temp_dir: Optional[Path] = None):
        """Initialize profiler.

        Args:
            dump_path: Path to the zipped Postgres dump
            temp_dir: Temporary directory for scratch files (optional)
        """
        self.dump_path = dump_path
        self.temp_dir = temp_dir or Path("/tmp")
        self.connection: Optional[duckdb.DuckDBPyConnection] = None

    def validate_dump_access(self) -> bool:
        """Validate that the dump file is accessible and appears valid.

        Returns:
            True if dump is accessible and valid
        """
        if not self.dump_path.exists():
            logger.error(f"Dump file not found: {self.dump_path}")
            return False

        # Check file size (should be ~51GB)
        size_gb = self.dump_path.stat().st_size / (1024**3)
        logger.info(".2f")

        if size_gb < 40:  # Allow some tolerance
            logger.warning(".2f")
            return False

        # Try to read first few bytes to verify it's a ZIP file
        try:
            with open(self.dump_path, "rb") as f:
                header = f.read(4)
                if header != b"PK\x03\x04":
                    logger.error("File does not appear to be a valid ZIP archive")
                    return False
        except Exception as e:
            logger.error(f"Cannot read dump file: {e}")
            return False

        logger.info("Dump file validation passed")
        return True

    def get_dump_metadata_pg_restore(self) -> Dict:
        """Get dump metadata using pg_restore --list.

        Returns:
            Dictionary with dump metadata
        """
        logger.info("Analyzing dump with pg_restore --list")

        try:
            cmd = ["pg_restore", "--list", str(self.dump_path)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode != 0:
                logger.error(f"pg_restore failed: {result.stderr}")
                return {"error": f"pg_restore failed: {result.stderr}"}

            # Parse pg_restore output
            lines = result.stdout.strip().split("\n")
            tables = []
            for line in lines:
                if line.strip() and not line.startswith(";"):
                    parts = line.split()
                    if len(parts) >= 2 and parts[0] in ["TABLE", "TABLE DATA"]:
                        table_name = parts[-1]
                        if table_name not in [t["name"] for t in tables]:
                            tables.append({"name": table_name, "type": parts[0]})

            return {"tool": "pg_restore", "tables": tables, "total_tables": len(tables)}

        except subprocess.TimeoutExpired:
            logger.error("pg_restore --list timed out")
            return {"error": "pg_restore timed out"}
        except FileNotFoundError:
            logger.error("pg_restore command not found. Install PostgreSQL client tools.")
            return {"error": "pg_restore not available"}

    def get_table_sample_duckdb(self, table_name: str, limit: int = 5) -> Dict:
        """Get sample rows from a table using DuckDB postgres_scanner.

        Args:
            table_name: Name of the table to sample
            limit: Number of rows to sample

        Returns:
            Dictionary with sample data
        """
        logger.info(f"Sampling {limit} rows from table: {table_name}")

        try:
            # Create connection if needed
            if self.connection is None:
                self.connection = duckdb.connect(":memory:")
                # Install and load postgres_scanner extension
                self.connection.execute("INSTALL postgres_scanner;")
                self.connection.execute("LOAD postgres_scanner;")

            # Create a temporary file path for the dump (postgres_scanner needs a file path)
            temp_dump = self.temp_dir / f"temp_{table_name}_dump.sql"
            if not temp_dump.exists():
                # For ZIP files, we might need to extract or use a different approach
                # For now, try direct access
                pass

            # Query using postgres_scanner
            # Note: This is a simplified approach. Real implementation may need
            # to handle ZIP extraction or use pg_restore piping
            query = f"""
            SELECT * FROM postgres_scan('{self.dump_path}', '{table_name}')
            LIMIT {limit}
            """

            df = self.connection.execute(query).fetchdf()

            return {
                "table_name": table_name,
                "sample_rows": len(df),
                "columns": list(df.columns),
                "sample_data": df.head(limit).to_dict("records"),
            }

        except Exception as e:
            logger.error(f"Failed to sample table {table_name}: {e}")
            return {"table_name": table_name, "error": str(e)}

    def profile_dump(self, sample_tables: Optional[List[str]] = None) -> Dict:
        """Profile the entire dump.

        Args:
            sample_tables: List of specific tables to sample (None for all)

        Returns:
            Complete profiling report
        """
        logger.info("Starting USAspending dump profiling")

        report = {
            "dump_path": str(self.dump_path),
            "dump_size_gb": round(self.dump_path.stat().st_size / (1024**3), 2),
            "profiling_timestamp": pd.Timestamp.now().isoformat(),
            "metadata": {},
            "table_samples": [],
        }

        # Get basic metadata
        report["metadata"] = self.get_dump_metadata_pg_restore()

        # Sample tables if requested
        if sample_tables:
            for table_name in sample_tables:
                sample = self.get_table_sample_duckdb(table_name)
                report["table_samples"].append(sample)

        return report

    def save_report(self, report: Dict, output_path: Path):
        """Save profiling report to file.

        Args:
            report: Profiling report dictionary
            output_path: Path to save the report
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(report, f, indent=2, default=str)

        logger.info(f"Report saved to: {output_path}")

    def close(self):
        """Clean up resources."""
        if self.connection:
            self.connection.close()
            self.connection = None


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Profile USAspending Postgres dump for SBIR ETL evaluation"
    )
    parser.add_argument(
        "--dump-path",
        type=Path,
        default=Path("/Volumes/X10 Pro/usaspending-db-subset_20251006.zip"),
        help="Path to the USAspending dump file",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/usaspending_subset_profile.json"),
        help="Output path for profiling report",
    )
    parser.add_argument(
        "--sample-tables",
        nargs="*",
        help="Specific tables to sample (default: transaction_normalized, awards, recipient_lookup)",
    )
    parser.add_argument(
        "--temp-dir", type=Path, default=Path("/tmp"), help="Temporary directory for scratch files"
    )
    parser.add_argument(
        "--validate-only", action="store_true", help="Only validate dump access, don't profile"
    )

    args = parser.parse_args()

    # Set up logging
    logger.add(sys.stderr, level="INFO")

    # Default sample tables if none specified
    sample_tables = args.sample_tables or [
        "transaction_normalized",
        "awards",
        "recipient_lookup",
        "recipient_profile",
    ]

    profiler = USAspendingDumpProfiler(args.dump_path, args.temp_dir)

    try:
        # Validate dump access
        if not profiler.validate_dump_access():
            logger.error("Dump validation failed")
            sys.exit(1)

        if args.validate_only:
            logger.info("Validation successful")
            return

        # Run profiling
        logger.info(f"Profiling dump with sample tables: {sample_tables}")
        report = profiler.profile_dump(sample_tables)

        # Save report
        profiler.save_report(report, args.output)

        logger.info("Profiling complete")

    except KeyboardInterrupt:
        logger.info("Profiling interrupted by user")
    except Exception as e:
        logger.error(f"Profiling failed: {e}")
        sys.exit(1)
    finally:
        profiler.close()


if __name__ == "__main__":
    main()
