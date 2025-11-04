#!/usr/bin/env python3
"""
OpenSpec to Kiro Migration Script

This script orchestrates the complete migration from OpenSpec to Kiro specifications.
It analyzes existing OpenSpec content, transforms it to Kiro format, and establishes
new development workflows while preserving historical context.

Usage:
    python scripts/migrate_openspec_to_kiro.py [--dry-run] [--verbose]
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path


# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from migration.analyzer import OpenSpecAnalyzer
from migration.generator import KiroSpecGenerator
from migration.models import (
    ContentParsingError,
    FileSystemError,
    MigrationConfig,
    MigrationError,
    MigrationReport,
    TransformationError,
    ValidationError,
)
from migration.preserver import HistoricalPreserver
from migration.transformer import ContentTransformer
from migration.validator import MigrationValidator


class OpenSpecToKiroMigrator:
    """Main migration orchestrator for OpenSpec to Kiro transition."""

    def __init__(self, config: MigrationConfig):
        """Initialize migrator with configuration."""
        self.config = config
        self._validate_config()
        self.logger = self._setup_logging()

        # Initialize migration components
        self.analyzer = OpenSpecAnalyzer(config.openspec_path)
        self.transformer = ContentTransformer()
        self.generator = KiroSpecGenerator(config.kiro_path)
        self.validator = MigrationValidator()
        self.preserver = HistoricalPreserver()

        # Migration state
        self.migration_start_time = datetime.now()
        self.progress_tracker = ProgressTracker()
        self.performance_metrics = {}

    def migrate(self) -> MigrationReport:
        """Execute complete migration process."""
        self.logger.info("Starting OpenSpec to Kiro migration")
        self.logger.info(f"OpenSpec path: {self.config.openspec_path}")
        self.logger.info(f"Kiro path: {self.config.kiro_path}")

        try:
            # Phase 1: Analysis
            self.logger.info("Phase 1: Analyzing OpenSpec content")
            self.progress_tracker.update("analysis", "started")
            openspec_content = self.analyzer.analyze_openspec_structure()
            self.progress_tracker.update("analysis", "completed")

            # Phase 2: Transformation
            self.logger.info("Phase 2: Transforming content to Kiro format")
            self.progress_tracker.update("transformation", "started")
            kiro_content = self.transformer.transform_content(openspec_content)
            self.progress_tracker.update("transformation", "completed")

            # Phase 3: Generation
            self.logger.info("Phase 3: Generating Kiro specification files")
            self.progress_tracker.update("generation", "started")
            if not self.config.dry_run:
                generated_specs = self.generator.generate_kiro_specs(kiro_content)
            else:
                self.logger.info("DRY RUN: Would generate Kiro specs")
                generated_specs = []
            self.progress_tracker.update("generation", "completed")

            # Phase 4: Validation
            self.logger.info("Phase 4: Validating migration")
            self.progress_tracker.update("validation", "started")
            validation_report = self.validator.validate_migration(generated_specs, openspec_content)
            self.progress_tracker.update("validation", "completed")

            # Phase 5: Historical Preservation
            if not self.config.dry_run and self.config.preserve_history:
                self.logger.info("Phase 5: Preserving OpenSpec history")
                self.progress_tracker.update("preservation", "started")
                self.preserver.archive_openspec(
                    self.config.openspec_path, self.config.archive_path, generated_specs
                )
                self.progress_tracker.update("preservation", "completed")

            # Generate migration report
            migration_report = MigrationReport(
                migration_id=f"migration_{self.migration_start_time.strftime('%Y%m%d_%H%M%S')}",
                start_time=self.migration_start_time,
                end_time=datetime.now(),
                config=self.config,
                openspec_content=openspec_content,
                generated_specs=generated_specs,
                validation_report=validation_report,
                progress=self.progress_tracker.get_summary(),
            )

            self._write_migration_report(migration_report)

            if validation_report.passed:
                self.logger.info("Migration completed successfully!")
            else:
                self.logger.warning(
                    f"Migration completed with {len(validation_report.issues)} validation issues"
                )

            return migration_report

        except (ContentParsingError, TransformationError, ValidationError, FileSystemError) as e:
            self.logger.error(f"Migration failed during {type(e).__name__}: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected migration failure: {e}", exc_info=True)
            raise MigrationError(f"Migration failed with unexpected error: {e}") from e

    def _setup_logging(self) -> logging.Logger:
        """Set up logging for migration process."""
        logger = logging.getLogger("openspec_migration")

        # Clear any existing handlers to avoid duplicates
        logger.handlers.clear()

        logger.setLevel(logging.DEBUG if self.config.verbose else logging.INFO)

        # Console handler with colored output
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG if self.config.verbose else logging.INFO)

        # File handler with rotation
        log_file = self.config.output_path / "migration.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, mode="w")  # Overwrite previous log
        file_handler.setLevel(logging.DEBUG)

        # Enhanced formatter with more context
        console_formatter = logging.Formatter(
            "%(asctime)s [%(levelname)8s] %(message)s", datefmt="%H:%M:%S"
        )
        file_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s"
        )

        console_handler.setFormatter(console_formatter)
        file_handler.setFormatter(file_formatter)

        logger.addHandler(console_handler)
        logger.addHandler(file_handler)

        # Log configuration info
        logger.info(
            f"Logging initialized - Console: {'DEBUG' if self.config.verbose else 'INFO'}, File: DEBUG"
        )
        logger.info(f"Log file: {log_file}")

        return logger

    def _write_migration_report(self, report: MigrationReport):
        """Write migration report to file."""
        report_file = self.config.output_path / f"migration_report_{report.migration_id}.json"
        report_file.parent.mkdir(parents=True, exist_ok=True)

        with open(report_file, "w") as f:
            json.dump(report.to_dict(), f, indent=2, default=str)

        self.logger.info(f"Migration report written to: {report_file}")

    def _validate_config(self):
        """Validate migration configuration."""
        if not self.config.openspec_path.exists():
            raise MigrationError(f"OpenSpec path does not exist: {self.config.openspec_path}")

        if not self.config.openspec_path.is_dir():
            raise MigrationError(f"OpenSpec path is not a directory: {self.config.openspec_path}")

        # Check for required OpenSpec structure
        required_paths = ["changes", "specs"]
        missing_paths = []
        for path_name in required_paths:
            path = self.config.openspec_path / path_name
            if not path.exists():
                missing_paths.append(path_name)

        if missing_paths:
            self.logger.warning(
                f"OpenSpec structure incomplete. Missing: {', '.join(missing_paths)}"
            )

        # Validate output paths are writable
        try:
            self.config.output_path.mkdir(parents=True, exist_ok=True)
            if not self.config.dry_run:
                self.config.kiro_path.mkdir(parents=True, exist_ok=True)
                if self.config.preserve_history:
                    self.config.archive_path.mkdir(parents=True, exist_ok=True)
        except PermissionError as e:
            raise MigrationError(f"Cannot create output directories: {e}")


class ProgressTracker:
    """Tracks migration progress across phases."""

    def __init__(self):
        self.phases = {
            "analysis": {"status": "pending", "start_time": None, "end_time": None},
            "transformation": {"status": "pending", "start_time": None, "end_time": None},
            "generation": {"status": "pending", "start_time": None, "end_time": None},
            "validation": {"status": "pending", "start_time": None, "end_time": None},
            "preservation": {"status": "pending", "start_time": None, "end_time": None},
        }

    def update(self, phase: str, status: str):
        """Update phase status."""
        if phase in self.phases:
            if status == "started":
                self.phases[phase]["status"] = "in_progress"
                self.phases[phase]["start_time"] = datetime.now()
            elif status == "completed":
                self.phases[phase]["status"] = "completed"
                self.phases[phase]["end_time"] = datetime.now()

    def get_summary(self) -> dict:
        """Get progress summary."""
        return {
            "phases": self.phases,
            "completed_phases": len(
                [p for p in self.phases.values() if p["status"] == "completed"]
            ),
            "total_phases": len(self.phases),
        }


def main():
    """Main entry point for migration script."""
    parser = argparse.ArgumentParser(
        description="Migrate OpenSpec to Kiro specifications",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run to analyze what would be migrated
  python scripts/migrate_openspec_to_kiro.py --dry-run --verbose

  # Full migration with custom paths
  python scripts/migrate_openspec_to_kiro.py --openspec-path ./my-openspec --kiro-path ./.kiro/specs

  # Migration without preserving history
  python scripts/migrate_openspec_to_kiro.py --no-preserve-history
        """,
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Perform analysis without creating files"
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument(
        "--openspec-path",
        type=Path,
        default=Path("openspec"),
        help="Path to OpenSpec directory (default: openspec)",
    )
    parser.add_argument(
        "--kiro-path",
        type=Path,
        default=Path(".kiro/specs"),
        help="Path to Kiro specs directory (default: .kiro/specs)",
    )
    parser.add_argument(
        "--archive-path",
        type=Path,
        default=Path("archive/openspec"),
        help="Path for OpenSpec archive (default: archive/openspec)",
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=Path("migration_output"),
        help="Path for migration output files (default: migration_output)",
    )
    parser.add_argument(
        "--no-preserve-history", action="store_true", help="Skip historical preservation step"
    )

    args = parser.parse_args()

    # Validate paths
    if not args.openspec_path.exists():
        print(f"Error: OpenSpec path does not exist: {args.openspec_path}")
        sys.exit(1)

    # Create migration configuration
    config = MigrationConfig(
        openspec_path=args.openspec_path,
        kiro_path=args.kiro_path,
        archive_path=args.archive_path,
        output_path=args.output_path,
        dry_run=args.dry_run,
        verbose=args.verbose,
        preserve_history=not args.no_preserve_history,
    )

    # Execute migration
    try:
        migrator = OpenSpecToKiroMigrator(config)
        report = migrator.migrate()

        # Print enhanced summary
        _print_migration_summary(report, config)

    except Exception as e:
        print(f"Migration failed: {e}")
        sys.exit(1)


def _print_migration_summary(report: MigrationReport, config: MigrationConfig):
    """Print enhanced migration summary."""
    duration = report.end_time - report.start_time

    print("\n" + "=" * 70)
    print("🔄 OPENSPEC TO KIRO MIGRATION SUMMARY")
    print("=" * 70)

    # Basic info
    print(f"📋 Migration ID: {report.migration_id}")
    print(f"⏱️  Duration: {duration}")
    print(f"🔧 Mode: {'DRY RUN' if config.dry_run else 'FULL MIGRATION'}")

    # Content summary
    print("\n📊 Content Summary:")
    print(f"   • OpenSpec Changes: {len(report.openspec_content.active_changes)}")
    print(f"   • OpenSpec Specs: {len(report.openspec_content.specifications)}")
    print(f"   • Generated Kiro Specs: {len(report.generated_specs)}")
    print(f"   • Archived Changes: {len(report.openspec_content.archived_changes)}")

    # Validation results
    if report.validation_report:
        errors = len(report.validation_report.get_issues_by_severity("ERROR"))
        warnings = len(report.validation_report.get_issues_by_severity("WARNING"))
        infos = len(report.validation_report.get_issues_by_severity("INFO"))

        status_icon = "✅" if report.validation_report.passed else "⚠️"
        status_text = "SUCCESS" if report.validation_report.passed else "COMPLETED WITH ISSUES"

        print(f"\n{status_icon} Status: {status_text}")
        print(f"   • Errors: {errors}")
        print(f"   • Warnings: {warnings}")
        print(f"   • Info: {infos}")

        # Show critical issues
        critical_issues = report.validation_report.get_issues_by_severity("ERROR")
        if critical_issues:
            print("\n🚨 Critical Issues:")
            for issue in critical_issues[:3]:
                print(f"   • {issue.spec_name}: {issue.message}")
            if len(critical_issues) > 3:
                print(f"   • ... and {len(critical_issues) - 3} more errors")

    # Next steps
    print("\n📁 Output Locations:")
    if not config.dry_run:
        print(f"   • Kiro Specs: {config.kiro_path}")
        if config.preserve_history:
            print(f"   • Archive: {config.archive_path}")
    print(
        f"   • Migration Report: {config.output_path}/migration_report_{report.migration_id}.json"
    )
    print(f"   • Migration Log: {config.output_path}/migration.log")

    if not config.dry_run and report.validation_report and report.validation_report.passed:
        print("\n🎉 Migration completed successfully!")
        print(f"   Next: Review generated specs in {config.kiro_path}")
    elif config.dry_run:
        print("\n💡 Dry run completed. Use without --dry-run to perform actual migration.")
    else:
        print("\n⚠️  Migration completed with issues. Review the detailed report.")

    print("=" * 70)


if __name__ == "__main__":
    main()
