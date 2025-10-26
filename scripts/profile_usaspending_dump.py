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
from typing import Dict, List, Optional

import duckdb
import pandas as pd
from loguru import logger


class USAspendingDumpProfiler:
    """Profiler for USAspending PostgreSQL COPY dumps."""

    def __init__(self, dump_path: Path, temp_dir: Optional[Path] = None):
        """Initialize profiler.

        Args:
            dump_path: Path to the zipped PostgreSQL COPY dump
            temp_dir: Temporary directory for scratch files (optional)
        """
        self.dump_path = dump_path
        self.temp_dir = temp_dir or Path("/tmp")
        self.connection: Optional[duckdb.DuckDBPyConnection] = None

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

    def get_dump_metadata_from_files(self) -> Dict:
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

    def get_table_sample_from_copy_file(self, table_oid: int, limit: int = 10000) -> Dict:
        """Get sample rows from a PostgreSQL COPY file.

        Args:
            table_oid: PostgreSQL object ID for the table
            limit: Number of rows to sample

        Returns:
            Dictionary with sample data
        """
        table_name = self.table_oid_map.get(table_oid, f"unknown_table_{table_oid}")
        logger.info(f"Sampling {limit} rows from table {table_name} (OID: {table_oid})")

        try:
            # Create connection if needed
            if self.connection is None:
                self.connection = duckdb.connect(":memory:")

            # Create temporary directory for extraction
            temp_dir = self.temp_dir / f"usaspending_extract_{table_oid}"
            temp_dir.mkdir(exist_ok=True)

            # Extract the specific file
            filename = f"pruned_data_store_api_dump/{table_oid}.dat.gz"
            temp_file = temp_dir / f"{table_oid}.dat"

            cmd = ["unzip", "-p", str(self.dump_path), filename]
            with open(temp_file, "wb") as f:
                result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, timeout=60)

            if result.returncode != 0:
                return {
                    "table_name": table_name,
                    "error": f"Failed to extract file: {result.stderr.decode()}",
                }

            # Decompress the gzipped content
            decompressed_file = temp_file.with_suffix(".decompressed")
            try:
                with open(temp_file, "rb") as f_in, open(decompressed_file, "wb") as f_out:
                    import gzip

                    f_out.write(gzip.decompress(f_in.read()))
                temp_file = decompressed_file
            except gzip.BadGzipFile:
                # File might not be gzipped, use as-is
                pass

            # Count total rows
            cmd_count = ["wc", "-l", str(temp_file)]
            result_count = subprocess.run(cmd_count, capture_output=True, text=True, timeout=30)
            if result_count.returncode == 0:
                row_count = int(result_count.stdout.split()[0])
            else:
                row_count = None
                logger.warning(f"Could not count rows for {table_name}")

            # Read with pandas for PostgreSQL COPY format
            df = pd.read_csv(
                temp_file,
                sep="\t",
                header=None,
                na_values=["\\N"],
                nrows=limit,
                on_bad_lines="skip",
                engine="python",  # More flexible for complex formats
            )

            # Clean up
            import shutil

            shutil.rmtree(temp_dir)

            return {
                "table_name": table_name,
                "oid": table_oid,
                "total_rows": row_count,
                "sampled_rows": len(df),
                "columns": list(df.columns),
                "sample_data": df.head(limit).to_dict("records"),
            }

        except Exception as e:
            logger.error(f"Failed to sample table {table_name}: {e}")
            return {"table_name": table_name, "oid": table_oid, "error": str(e)}

    def profile_dump(self, sample_oids: Optional[List[int]] = None) -> Dict:
        """Profile the entire dump.

        Args:
            sample_oids: List of specific table OIDs to sample (None for all tables)

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
            sample = self.get_table_sample_from_copy_file(oid)
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

        # Also save a human-readable summary
        summary_path = output_path.with_suffix(".summary.md")
        self.save_summary_report(report, summary_path)

    def save_summary_report(self, report: Dict, output_path: Path):
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
        "--sample-oids",
        nargs="*",
        type=int,
        help="Specific table OIDs to sample (default: all tables)",
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

        # Run profiling
        logger.info(f"Profiling dump with sample OIDs: {sample_oids}")
        report = profiler.profile_dump(sample_oids)

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
