"""Configuration for Neo4j migrations."""

from pathlib import Path

# Migration directory
MIGRATIONS_DIR = Path(__file__).parent / "versions"

# Migration tracking node label
TRACKING_LABEL = "__MigrationTracking"
TRACKING_ID = "migration_tracker"

