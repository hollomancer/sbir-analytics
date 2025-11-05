#!/usr/bin/env python3
"""Profile USAspending PostgreSQL COPY dump for SBIR ETL evaluation.

This script analyzes the USAspending PostgreSQL data stored as compressed COPY files
on removable media to provide schema information, table statistics, and enrichment
coverage assessment.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import duckdb
import pandas as pd
from loguru import logger

# Import config loader for default paths
try:
    from src.config.loader import get_config
    _config_available = True
except ImportError:
    _config_available = False


class USAspendingDumpProfiler:
    """Profiler for USAspending PostgreSQL COPY dumps."""

    def __init__(self, dump_path: Path, temp_dir: Path | None = None):
        """Initialize profiler.

        Args:
            dump_path: Path to the zipped PostgreSQL COPY dump
            temp_dir: Temporary directory for scratch files (optional)
        """
        self.dump_path = dump_path
        self.temp_dir = temp_dir or Path("/tmp")
        self.connection: duckdb.DuckDBPyConnection | None = None

        # Known table OID mappings (PostgreSQL object IDs to table names)
        # These may need to be verified/updated based on actual dump
        self.table_oid_map = {
            5412: "recipient_lookup",  # Appears to contain recipient/company data
            5420: "transaction_normalized",  # Appears to contain transaction data
            # Add more mappings as discovered
        }

    def validate_dump_access(self) -> bool:
        """Validate that the dump file is accessible and appears valid.

        Returns:
            True if dump is accessible and valid
        """
        if not self.dump_path.exists():
            logger.error(f"Dump file not found: {self.dump_path}")
            return False

        # Check file size (should be ~17GB for subset)
        size_gb = self.dump_path.stat().st_size / (1024**3)
        logger.info(".2f")

        if size_gb < 5:  # Allow reasonable minimum for subset
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

    def get_dump_metadata_from_files(self) -> dict:
        """Get dump metadata by analyzing the ZIP file contents.

        Returns:
            Dictionary with dump metadata
        """
        logger.info("Analyzing dump file contents")

        try:
            # List contents of the ZIP file
            cmd = ["unzip", "-l", str(self.dump_path)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            if result.returncode != 0:
                logger.error(f"unzip -l failed: {result.stderr}")
                return {"error": f"unzip failed: {result.stderr}"}

            # Parse unzip output to find data files
            lines = result.stdout.strip().split("\n")
            data_files = []
            for line in lines:
                if "pruned_data_store_api_dump/" in line and ".dat.gz" in line:
                    parts = line.split()
                    if len(parts) >= 4:
                        size = int(parts[0])
                        filename = parts[-1]
                        oid = int(filename.split("/")[-1].split(".")[0])
                        data_files.append(
                            {
                                "oid": oid,
                                "filename": filename,
                                "size_compressed": size,
                                "table_name": self.table_oid_map.get(oid, f"unknown_table_{oid}"),
                            }
                        )

            return {
                "tool": "unzip_analysis",
                "data_files": data_files,
                "total_files": len(data_files),
                "tables_identified": len(
                    [f for f in data_files if f["table_name"] != f"unknown_table_{f['oid']}"]
                ),
            }

        except subprocess.TimeoutExpired:
            logger.error("unzip -l timed out")
            return {"error": "unzip timed out"}
        except FileNotFoundError:
            logger.error("unzip command not found.")
            return {"error": "unzip not available"}

    def get_table_sample_from_copy_file(
        self, table_oid: int, limit: int = 10000, chunk_size: int = 100000
    ) -> dict:
        """Stream-sample rows from a PostgreSQL COPY file inside the ZIP archive.

        This implementation streams the compressed `.dat.gz` file directly from the ZIP
        (via `unzip -p`) and reads it incrementally so we:
          - avoid extracting large files to disk,
          - can report progress while scanning large files,
          - produce a representative sample (first `limit` rows by default),
          - and return an overall row count computed while streaming.

        Additionally, this method writes per-OID progress JSON files to `reports/progress/`
        and instruments the sampling block with the global `performance_monitor` so we
        capture duration and memory usage for each table scan.

        Args:
            table_oid: PostgreSQL object ID for the table
            limit: Number of rows to sample (kept in memory)
            chunk_size: Progress reporting interval (number of rows)

        Returns:
            Dictionary with sample data and simple progress/diagnostics
        """
        # Local imports to keep top-level imports stable
        import json

        from src.utils.performance_monitor import performance_monitor

        table_name = self.table_oid_map.get(table_oid, f"unknown_table_{table_oid}")
        logger.info(
            f"Streaming sample up to {limit} rows from table {table_name} (OID: {table_oid})"
        )

        filename = f"pruned_data_store_api_dump/{table_oid}.dat.gz"
        cmd = ["unzip", "-p", str(self.dump_path), filename]

        sample_records = []
        total_rows = 0
        columns_detected = None
        last_report = 0

        progress_dir = Path("reports/progress")
        progress_dir.mkdir(parents=True, exist_ok=True)
        progress_path = progress_dir / f"{table_oid}.json"

        # Ensure we write an initial progress file to indicate start
        with open(progress_path, "w") as pf:
            json.dump(
                {
                    "table_name": table_name,
                    "oid": table_oid,
                    "status": "started",
                    "sample_limit": limit,
                },
                pf,
                indent=2,
            )

        try:
            # Instrument the streaming scan with performance monitoring
            with performance_monitor.monitor_block(f"profile_oid_{table_oid}"):
                # Start the unzip subprocess and stream stdout
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

                # Attempt to treat stdout as a gzip stream; fall back to raw stream if not gzipped.
                import gzip
                from io import BufferedReader, TextIOWrapper

                stream = proc.stdout  # binary stream

                try:
                    gz = gzip.GzipFile(fileobj=stream)
                    reader = TextIOWrapper(BufferedReader(gz), encoding="utf-8", errors="replace")
                    logger.info(f"Using gzip stream reader for {filename}")
                except (OSError, gzip.BadGzipFile):
                    # Not gzipped; read directly
                    reader = TextIOWrapper(
                        BufferedReader(stream), encoding="utf-8", errors="replace"
                    )
                    logger.info(f"Using raw stream reader for {filename}")

                # Iterate lines and build small in-memory sample (first `limit` rows)
                for line in reader:
                    total_rows += 1

                    # Progress reporting every chunk_size rows
                    if total_rows - last_report >= chunk_size:
                        logger.info(
                            f"Sampling progress for OID {table_oid}: {total_rows} rows scanned..."
                        )
                        last_report = total_rows

                        # Write intermediate progress file
                        with open(progress_path, "w") as pf:
                            json.dump(
                                {
                                    "table_name": table_name,
                                    "oid": table_oid,
                                    "status": "in-progress",
                                    "total_rows_scanned": total_rows,
                                    "sampled_rows": len(sample_records),
                                    "reported_interval": chunk_size,
                                },
                                pf,
                                indent=2,
                            )

                    # Parse COPY (tab-separated) row
                    row_vals = line.rstrip("\n").split("\t")
                    # Lazily determine number of columns from first row we keep
                    if columns_detected is None:
                        columns_detected = list(range(len(row_vals)))

                    # Only keep up to `limit` sample rows
                    if len(sample_records) < limit:
                        # Represent row as dict: column_index -> value (mimic pandas read_csv behavior earlier)
                        row_dict = {i: (v if v != "\\N" else None) for i, v in enumerate(row_vals)}
                        sample_records.append(row_dict)

                # Finish reading; ensure subprocess ended
                proc.stdout.close()
                _, stderr = proc.communicate(timeout=30)
                if proc.returncode not in (0, None):
                    stderr_text = (
                        stderr.decode("utf-8", errors="replace")
                        if isinstance(stderr, bytes)
                        else str(stderr)
                    )
                    logger.warning(f"Stream reader subprocess returned non-zero: {stderr_text}")

            # Build a small DataFrame for column metadata using the sampled rows (if any)
            if sample_records:
                df_sample = pd.DataFrame(sample_records)
                sampled_rows = len(df_sample)
                columns = list(df_sample.columns)
            else:
                df_sample = pd.DataFrame()
                sampled_rows = 0
                columns = columns_detected or []

            # Write final progress with metrics
            final_progress = {
                "table_name": table_name,
                "oid": table_oid,
                "status": "completed",
                "total_rows_scanned": total_rows,
                "sampled_rows": sampled_rows,
                "columns_detected": columns,
                "reported_interval": chunk_size,
                "metrics": performance_monitor.get_latest_metric(f"profile_oid_{table_oid}"),
            }
            with open(progress_path, "w") as pf:
                json.dump(final_progress, pf, indent=2, default=str)

            return {
                "table_name": table_name,
                "oid": table_oid,
                "total_rows": total_rows,
                "sampled_rows": sampled_rows,
                "columns": columns,
                "sample_data": df_sample.head(limit).to_dict("records"),
                "progress_file": str(progress_path),
            }

        except subprocess.TimeoutExpired:
            logger.error(f"Streaming timed out for {filename}")
            try:
                proc.kill()
            except Exception:
                pass
            with open(progress_path, "w") as pf:
                json.dump(
                    {"table_name": table_name, "oid": table_oid, "status": "timeout"}, pf, indent=2
                )
            return {"table_name": table_name, "oid": table_oid, "error": "stream timeout"}
        except Exception as e:
            # Log full exception with stack trace for easier debugging
            logger.exception(f"Failed to stream-sample table {table_name}")
            # Attempt to kill subprocess if still running
            try:
                proc.kill()
            except Exception:
                pass
            with open(progress_path, "w") as pf:
                json.dump(
                    {
                        "table_name": table_name,
                        "oid": table_oid,
                        "status": "error",
                        "error": str(e),
                    },
                    pf,
                    indent=2,
                )
            return {"table_name": table_name, "oid": table_oid, "error": str(e)}

    def profile_dump(
        self,
        sample_oids: list[int] | None = None,
        sample_limit: int = 10000,
        chunk_size: int = 100000,
    ) -> dict:
        """Profile the entire dump.

        Args:
            sample_oids: List of specific table OIDs to sample (None for all tables)
            sample_limit: Number of sample rows to collect per table
            chunk_size: Progress reporting interval (rows)

        Returns:
            Complete profiling report
        """
        logger.info("Starting USAspending PostgreSQL COPY dump profiling")

        report = {
            "dump_path": str(self.dump_path),
            "dump_size_gb": round(self.dump_path.stat().st_size / (1024**3), 2),
            "profiling_timestamp": pd.Timestamp.now().isoformat(),
            "data_format": "PostgreSQL COPY files (.dat.gz)",
            "metadata": {},
            "table_samples": [],
        }

        # Get basic metadata
        report["metadata"] = self.get_dump_metadata_from_files()

        # Sample tables - use all OIDs if none specified
        if sample_oids is None:
            sample_oids = [f["oid"] for f in report["metadata"].get("data_files", [])]

        for oid in sample_oids:
            logger.info(
                f"Beginning sample for OID: {oid} with limit={sample_limit}, chunk_size={chunk_size}"
            )
            sample = self.get_table_sample_from_copy_file(
                oid, limit=sample_limit, chunk_size=chunk_size
            )
            report["table_samples"].append(sample)

        return report

    def save_report(self, report: dict, output_path: Path):
        """Save profiling report to file.

        Args:
            report: Profiling report dictionary
            output_path: Path to save the report
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(report, f, indent=2, default=str)

        logger.info(f"Report saved to: {output_path}")

        # Also save a human-readable summary
        summary_path = output_path.with_suffix(".summary.md")
        self.save_summary_report(report, summary_path)

    def save_summary_report(self, report: dict, output_path: Path):
        """Save a human-readable summary report.

        Args:
            report: Profiling report dictionary
            output_path: Path to save the summary
        """
        with open(output_path, "w") as f:
            f.write("# USAspending PostgreSQL COPY Dump Profile Summary\n\n")
            f.write(f"**Generated:** {report['profiling_timestamp']}\n")
            f.write(f"**Dump Path:** {report['dump_path']}\n")
            f.write(f"**Dump Size:** {report['dump_size_gb']} GB\n")
            f.write(f"**Data Format:** {report['data_format']}\n\n")

            metadata = report.get("metadata", {})
            if "data_files" in metadata:
                f.write("## Data Files\n\n")
                f.write(f"**Total Files:** {metadata['total_files']}\n")
                f.write(f"**Tables Identified:** {metadata['tables_identified']}\n\n")

                f.write("| OID | Table Name | Size (compressed) |\n")
                f.write("|-----|------------|-------------------|\n")
                for file_info in metadata["data_files"]:
                    f.write(
                        f"| {file_info['oid']} | {file_info['table_name']} | {file_info['size_compressed']:,} bytes |\n"
                    )
                f.write("\n")

            f.write("## Table Samples\n\n")
            for sample in report.get("table_samples", []):
                f.write(f"### {sample['table_name']} (OID: {sample.get('oid', 'unknown')})\n\n")
                if "error" in sample:
                    f.write(f"**Error:** {sample['error']}\n\n")
                else:
                    f.write(f"**Total Rows:** {sample.get('total_rows', 'unknown')}\n")
                    f.write(f"**Sampled Rows:** {sample['sampled_rows']}\n")
                    f.write(f"**Columns:** {len(sample['columns'])}\n\n")

                    if sample["sample_data"]:
                        f.write("**Sample Data:**\n")
                        f.write("```\n")
                        for row in sample["sample_data"][:3]:  # Show first 3 rows
                            f.write(f"{row}\n")
                        f.write("```\n\n")

        logger.info(f"Summary report saved to: {output_path}")

    def close(self):
        """Clean up resources."""
        if self.connection:
            self.connection.close()
            self.connection = None


def main():
    """Main entry point."""
    # Determine default dump path from config if available
    default_dump_path = Path("data/usaspending/usaspending-db_20251006.zip")
    if _config_available:
        try:
            config = get_config()
            default_dump_path = config.paths.resolve_path("usaspending_dump_file")
        except Exception:
            pass  # Fall back to hardcoded default

    parser = argparse.ArgumentParser(
        description="Profile USAspending Postgres dump for SBIR ETL evaluation"
    )
    parser.add_argument(
        "--dump-path",
        type=Path,
        default=default_dump_path,
        help="Path to the USAspending dump file",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/usaspending_subset_profile.json"),
        help="Output path for profiling report",
    )
    parser.add_argument(
        "--sample-oids",
        nargs="*",
        type=int,
        help="Specific table OIDs to sample (default: all tables)",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=10000,
        help="Number of sample rows to collect per table (kept in memory)",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=100000,
        help="Progress reporting chunk size (number of rows)",
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

    # Create profiler instance
    profiler = USAspendingDumpProfiler(args.dump_path, args.temp_dir)

    # Default sample OIDs if none specified (None means all)
    sample_oids = args.sample_oids

    try:
        # Validate dump access
        if not profiler.validate_dump_access():
            logger.error("Dump validation failed")
            sys.exit(1)

        if args.validate_only:
            logger.info("Validation successful")
            return

        # Run profiling (respect sample limits and chunk size)
        logger.info(
            f"Profiling dump with sample OIDs: {sample_oids} (sample_limit={args.sample_limit}, chunk_size={args.chunk_size})"
        )
        report = profiler.profile_dump(
            sample_oids, sample_limit=args.sample_limit, chunk_size=args.chunk_size
        )

        # Save report
        profiler.save_report(report, args.output)

        logger.info("Profiling complete")

    except KeyboardInterrupt:
        logger.info("Profiling interrupted by user")
    except Exception:
        # Emit full stacktrace to make root cause debugging easier
        logger.exception("Profiling failed")
        sys.exit(1)
    finally:
        profiler.close()


if __name__ == "__main__":
    main()
