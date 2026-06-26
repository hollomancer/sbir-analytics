# Configuration Reference

**Type**: Reference
**Owner**: Engineering Team
**Last-Updated**: 2025-11-05
**Status**: Active

## Overview

The SBIR ETL pipeline is configuration-driven. Settings live in YAML files under `config/`, are validated by Pydantic schemas in `sbir_etl/config/schemas/`, and can be overridden at runtime with environment variables. The same mechanism covers file system paths (local or AWS S3) and every other pipeline section (data quality, enrichment, pipeline orchestration, performance, Neo4j, ModernBert, CET).

This document is the canonical configuration reference: paths first, then the remaining sections, then the shared override mechanics.

### Three-layer configuration system

```text
Layer 1: YAML Files (config/)
    ↓
Layer 2: Pydantic Validation (sbir_etl/config/schemas/)
    ↓
Layer 3: Runtime Configuration with Environment Overrides
```

### Configuration files structure

```text
config/
├── base.yaml              # Default settings (version controlled)
├── dev.yaml               # Development overrides
├── prod.yaml              # Production settings
├── cet/                   # CET-specific configurations
└── envs/                  # Environment-specific configs
```

Schemas are defined in `sbir_etl/config/schemas/` (`data.py`, `domain.py`, `pipeline.py`) and loaded/merged by `sbir_etl/config/loader.py`. Treat those files — not this doc — as the source of truth for defaults and validation bounds; the YAML examples below are illustrative.

## Table of Contents

- [Cloud Storage (AWS S3)](#cloud-storage-aws-s3)
- [Configuration Structure](#configuration-structure)
- [Default Paths](#default-paths)
- [Path Resolution](#path-resolution)
- [Validation](#validation)
- [Configuration Sections](#configuration-sections)
  - [Data Quality](#data-quality-configuration)
  - [Enrichment](#enrichment-configuration)
  - [Pipeline Orchestration](#pipeline-orchestration-configuration)
  - [Neo4j](#neo4j-configuration)
  - [ModernBert](#modernbert-configuration)
  - [CET Classification](#cet-classification-configuration)
- [Environment Variable Overrides](#environment-variable-overrides)
- [Docker Deployment](#docker-deployment)
- [Troubleshooting](#troubleshooting)

## Cloud Storage (AWS S3)

### S3 Path Support

The pipeline supports AWS S3 paths for the optional cloud deployment path:

```yaml
paths:
  # S3 paths (optional cloud setup)
  data_root: "s3://sbir-analytics-data-prod"
  raw_data: "s3://sbir-analytics-data-prod/raw"
  usaspending_dump_file: "s3://sbir-analytics-data-prod/usaspending/dump.zip"

  # Local paths (development)
  # data_root: "data"
  # raw_data: "data/raw"
```

### S3 Configuration

Enable S3 storage via environment variables:

```bash
# Optional cloud setup (S3)
export SBIR_ETL_USE_S3=true
export SBIR_ETL_S3_BUCKET=sbir-analytics-data-prod
export AWS_REGION=us-east-1

# Development (local filesystem)
export SBIR_ETL_USE_S3=false
```

### S3 Path Resolution

The path resolver automatically handles S3 paths:

```python
from sbir_etl.config.loader import get_config

config = get_config()

# Resolves to S3 path if USE_S3=true
# Resolves to local path if USE_S3=false
dump_file = config.paths.resolve_path("usaspending_dump_file")

# Examples:
# S3:    s3://sbir-analytics-data-prod/usaspending/dump.zip
# Local: /home/user/sbir-analytics/data/usaspending/dump.zip
```

### S3 Access Patterns

```python
import boto3
from sbir_etl.utils.s3 import get_s3_client, s3_file_exists, download_from_s3

# Check if S3 file exists
if s3_file_exists("s3://bucket/key.parquet"):
    # Download to local temp file
    local_path = download_from_s3("s3://bucket/key.parquet", "/tmp/key.parquet")

# Upload to S3
upload_to_s3("/tmp/output.parquet", "s3://bucket/output.parquet")

# Stream from S3 with pandas
import pandas as pd
df = pd.read_parquet("s3://bucket/data.parquet")  # DuckDB supports this too!
```

### S3 + DuckDB Integration

DuckDB can directly query S3 files:

```python
import duckdb

# Load AWS credentials
duckdb.sql("""
    INSTALL httpfs;
    LOAD httpfs;
    SET s3_region='us-east-1';
""")

# Query S3 CSV directly
df = duckdb.sql("""
    SELECT * FROM read_csv_auto('s3://sbir-analytics-data-prod/raw/sbir_awards.csv')
    WHERE award_amount > 100000
""").df()
```

### S3 Best Practices

1. **Use S3 for larger or repeatable cloud runs** - Scalable, durable, managed
2. **Use local filesystem for development** - Faster iteration, no AWS costs
3. **Store credentials securely** - Use AWS Secrets Manager or IAM roles
4. **Enable versioning** - Protect against accidental deletions
5. **Use lifecycle policies** - Archive old data to S3 Glacier
6. **Monitor costs** - Use S3 analytics to track storage and transfer costs

## Configuration Structure

Path configuration is defined in `config/base.yaml` under the `paths` section:

```yaml
paths:
  # Root data directory
  data_root: "data"
  raw_data: "data/raw"

  # USAspending database dumps
  usaspending_dump_dir: "data/usaspending"
  usaspending_dump_file: "data/usaspending/usaspending-db_20251006.zip"

  # Transition detection outputs
  transition_contracts_output: "data/transition/contracts_ingestion.parquet"
  transition_dump_dir: "data/transition/pruned_data_store_api_dump"
  transition_vendor_filters: "data/transition/sbir_vendor_filters.json"

  # Scripts output
  scripts_output: "data/scripts_output"
```

## Default Paths

### Relative vs Absolute Paths

- **Relative paths** (default): Paths are relative to the project root directory
- **Absolute paths**: Can be specified for deployment environments

The path resolver automatically:

1. Expands environment variables (`$HOME`, `$USER`, etc.)
2. Expands tilde `~` for home directory
3. Converts relative paths to absolute based on project root
4. Resolves symbolic links

### Default Directory Structure

```text
/home/user/sbir-analytics/
├── data/
│   ├── raw/
│   │   ├── sbir/
│   │   └── uspto/
│   ├── usaspending/
│   │   └── usaspending-db_20251006.zip
│   ├── transition/
│   │   ├── contracts_ingestion.parquet
│   │   ├── pruned_data_store_api_dump/
│   │   └── sbir_vendor_filters.json
│   └── scripts_output/
├── reports/
└── logs/
```

## Environment Variable Overrides

Any configuration value can be overridden at runtime with an environment variable that mirrors the YAML path. The override applies after YAML files are merged and before Pydantic validation.

### Override Format

```text
SBIR_ETL__SECTION__SUBSECTION__KEY=value
```

Convert each YAML key segment to uppercase, join with double underscores, and prefix with `SBIR_ETL__`:

```bash
export SBIR_ETL__DATA_QUALITY__MAX_DUPLICATE_RATE=0.05
export SBIR_ETL__ENRICHMENT__BATCH_SIZE=200
export SBIR_ETL__NEO4J__URI="bolt://localhost:7687"
export SBIR_ETL__PIPELINE__CHUNK_SIZE=5000
export SBIR_ETL__PERFORMANCE__PARALLEL_THREADS=8
export SBIR_ETL__CET__CLASSIFICATION__MAX_FEATURES=75000
export SBIR_ETL__ML__MODERNBERT__USE_LOCAL=true
```

### Path Overrides

Path values follow the same convention under the `PATHS` section:

```bash
# YAML: paths.data_root
export SBIR_ETL__PATHS__DATA_ROOT=/mnt/data

# YAML: paths.usaspending_dump_file
export SBIR_ETL__PATHS__USASPENDING_DUMP_FILE=/mnt/dumps/usaspending.zip

# YAML: paths.transition_contracts_output
export SBIR_ETL__PATHS__TRANSITION_CONTRACTS_OUTPUT=/mnt/output/contracts.parquet
```

### Override Model and Secret Mapping

There are two complementary layers for runtime configuration:

- **`SBIR_ETL__...` overrides**: env vars that mirror the YAML structure and directly override loaded config values.
- **Secret mapping**: some sections (e.g., `neo4j`) reference raw env var *names* such as `NEO4J_URI`, `NEO4J_USER`, and `NEO4J_PASSWORD`. The YAML keys (e.g., `uri_env_var`) specify which raw environment variables to read.

You can either set raw secrets:

```bash
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="dev_password"  # pragma: allowlist secret
```

Or override resolved values directly via `SBIR_ETL` overrides:

```bash
export SBIR_ETL__NEO4J__URI="bolt://localhost:7687"
export SBIR_ETL__NEO4J__PASSWORD="dev_password"  # pragma: allowlist secret
```

Prefer `SBIR_ETL` overrides in development/CI for clarity and portability; use raw env secrets where infrastructure already manages them.

### Common Deployment Examples

#### Development Environment

```bash
# Use local project paths (default behavior - no overrides needed)
cd /home/user/sbir-analytics
uv run dagster dev
```

#### Cloud or Server Environment (Mounted Volumes)

```bash
# Override paths to use mounted volumes
export SBIR_ETL__PATHS__DATA_ROOT=/mnt/data
export SBIR_ETL__PATHS__USASPENDING_DUMP_FILE=/mnt/dumps/usaspending-db_latest.zip
export SBIR_ETL__PATHS__TRANSITION_DUMP_DIR=/mnt/transition/api_dump

uv run dagster dev
```

#### Docker Deployment

```bash
# Set environment variables in docker-compose.yml or .env file
docker-compose up -d
```

See [Docker Deployment](#docker-deployment) section for details.

## Path Resolution

### Using Paths in Code

The `PathsConfig` class provides a `resolve_path()` method for resolving configured paths:

```python
from sbir_etl.config.loader import get_config

# Load configuration
config = get_config()

# Resolve a path
dump_file = config.paths.resolve_path("usaspending_dump_file")
print(dump_file)  # /home/user/sbir-analytics/data/usaspending/usaspending-db_20251006.zip

# Optionally create parent directories
output_path = config.paths.resolve_path(
    "transition_contracts_output",
    create_parent=True  # Creates parent dirs if they don't exist
)
```

### Path Resolution Order

When resolving paths, the system checks in this order:

1. **Environment variables** (`SBIR_ETL__PATHS__*`)
2. **Environment-specific config** (`config/prod.yaml`, `config/dev.yaml`)
3. **Base config** (`config/base.yaml`)
4. **Default values** (hardcoded in `PathsConfig` schema)

## Validation

### Automatic Validation

The pipeline includes automatic path validation that runs on startup:

```python
from sbir_etl.utils.path_validator import validate_paths_on_startup

# Validate paths before starting pipeline
if not validate_paths_on_startup(create_missing_dirs=True):
    raise SystemExit("Path validation failed")
```

### Validation Behavior

The validator checks:

- ✅ **Directory paths exist** or can be created
- ✅ **Parent directories exist** for file paths
- ✅ **Paths are accessible** (read/write permissions)
- ⚠️ **Files may not exist yet** (output files are created during pipeline execution)

### Validation Modes

```python
# Strict validation (fail if any files don't exist)
validate_paths_on_startup(
    create_missing_dirs=False,
    require_files_exist=True
)

# Lenient validation (create dirs, allow missing files)
validate_paths_on_startup(
    create_missing_dirs=True,
    require_files_exist=False  # Default
)
```

### Manual Validation

You can manually validate paths using the `PathValidator` class:

```python
from sbir_etl.config.loader import get_config
from sbir_etl.utils.path_validator import PathValidator

config = get_config()
validator = PathValidator(config.paths)

# Validate all configured paths
success = validator.validate_all_paths(create_missing_dirs=True)

if not success:
    # Print detailed error report
    validator.print_validation_summary()
    # Get list of errors
    errors = validator.get_validation_errors()
```

## Configuration Sections

Beyond paths, the pipeline exposes the following YAML sections in `config/base.yaml`. The examples below are illustrative; the authoritative defaults and validation bounds live in the Pydantic schemas under `sbir_etl/config/schemas/` (data quality, extraction, validation, Neo4j, DuckDB, logging, etc. in `data.py`; CET / ModernBert / enrichment / pipeline domain models in `domain.py` and `pipeline.py`).

### Data Quality Configuration

```yaml
data_quality:
  # SBIR-specific validation thresholds
  sbir_awards:
    pass_rate_threshold: 0.95      # 95% of records must pass validation
    completeness_threshold: 0.90   # 90% completeness for individual fields
    uniqueness_threshold: 0.99     # 99% unique Contract IDs (allows phase progressions)

  # Completeness requirements (fraction of non-null values required)
  completeness:
    award_id: 1.00          # 100% required
    company_name: 0.95      # 95% required
    award_amount: 0.90      # 90% required
    award_date: 0.95        # 95% required
    program: 0.98           # 98% required

  # Uniqueness requirements (no duplicates allowed)
  uniqueness:
    award_id: 1.00          # No duplicate award IDs

  # Value range validation
  validity:
    award_amount_min: 0.0
    award_amount_max: 5000000.0   # $5M max SBIR award
    award_year_min: 1983          # SBIR program start
    award_year_max: 2030          # Future limit

  # Enrichment success rates
  enrichment:
    sam_gov_success_rate: 0.85      # 85% of companies should enrich successfully
    usaspending_match_rate: 0.70    # 70% of awards should match USAspending data
```

Schema: `DataQualityConfig` in `sbir_etl/config/schemas/data.py`.

### Enrichment Configuration

Enrichment sources, fallback chain, batch processing, and confidence thresholds are configured under the `enrichment` section. See `config/base.yaml` for the full block and the enrichment domain schema in `sbir_etl/config/schemas/domain.py` for fields and bounds. Key elements:

- **Source priority chain**: `original_data` → `usaspending_api` → `sam_gov_api` → `fuzzy_match`, each with `enabled`, `priority`, and `confidence`.
- **Batch processing**: `batch_size`, `max_retries`, `timeout_seconds`, `rate_limit_per_second`.
- **Confidence thresholds**: `high` / `medium` / `low` bands.
- **Quality targets**: `min_success_rate`, `min_high_confidence`, `max_fallback_rate`.
- **Fallback rules**: agency/sector default NAICS mappings.

### Pipeline Orchestration Configuration

```yaml
pipeline:
  chunk_size: 10000              # Records per processing chunk
  memory_threshold_mb: 2048      # Memory pressure threshold
  timeout_seconds: 300           # Processing timeout per chunk
  enable_incremental: true       # Support incremental processing

  asset_execution:
    max_retries: 3
    retry_delay_seconds: 5
    enable_parallel: true
    max_parallel_assets: 4

performance:
  batch_size: 1000              # Neo4j batch size
  parallel_threads: 4           # Parallel processing threads
  retry_attempts: 3             # Retry failed operations
  backoff_strategy: exponential # Retry backoff strategy

  memory_monitoring:
    enabled: true
    warning_threshold_mb: 1500
    critical_threshold_mb: 2000

  thresholds:
    duration_warning_seconds: 5.0
    memory_delta_warning_mb: 500.0
    memory_pressure_warn_percent: 80.0
    memory_pressure_critical_percent: 95.0
```

Schemas: pipeline/performance models in `sbir_etl/config/schemas/pipeline.py`.

### Neo4j Configuration

```yaml
neo4j:
  # Secret mapping — names of the raw env vars to read for connection secrets
  uri_env_var: "NEO4J_URI"
  user_env_var: "NEO4J_USER"
  password_env_var: "NEO4J_PASSWORD"  # pragma: allowlist secret

  loading:
    batch_size: 1000
    parallel_threads: 4
    transaction_timeout_seconds: 300
    retry_on_deadlock: true
    max_deadlock_retries: 3

  performance:
    create_indexes: true
    create_constraints: true
    batch_operations: true
    enable_query_cache: true

  quality:
    load_success_threshold: 0.99   # 99% success rate required
    max_constraint_violations: 10
    enable_data_validation: true
```

Schema: `Neo4jConfig` in `sbir_etl/config/schemas/data.py`.

### ModernBert Configuration

ModernBert embedding/similarity settings live under `ml.modernbert`. Notable fields: `use_local` (API vs local inference), `api` (token env, batch size, QPS, retries), `local` (model name, device), `text` (max length, award/patent fields), `similarity_threshold`, `top_k`, and coverage thresholds. See `config/base.yaml` and the ML domain schema in `sbir_etl/config/schemas/domain.py`.

### CET Classification Configuration

CET taxonomy and classifier settings live under the `cet` section: `taxonomy` (version, file, hierarchy), `classification.vectorizer` (TF-IDF n-grams, max features), `feature_selection`, `classifier`, `calibration`, and `scoring.bands` (high/medium/low). See `config/base.yaml` and `sbir_etl/config/schemas/domain.py`.

## Docker Deployment

### Docker Compose Configuration

Mount volumes for data directories in `docker-compose.yml`:

```yaml
services:
  dagster:
    image: sbir-analytics:latest
    volumes:
      # Mount data directory
      - /mnt/data:/app/data
      # Mount logs directory
      - /mnt/logs:/app/logs
    environment:
      # Override paths if needed
      - SBIR_ETL__PATHS__DATA_ROOT=/app/data
      - SBIR_ETL__PATHS__USASPENDING_DUMP_FILE=/app/data/usaspending/dump.zip
```

### Best Practices for Docker

1. **Use absolute paths** in environment variables for clarity
2. **Mount volumes** for data persistence
3. **Set proper permissions** on mounted volumes
4. **Use named volumes** for logs and temporary files

```yaml
volumes:
  data:
    driver: local
    driver_opts:
      type: none
      device: /mnt/sbir-data
      o: bind
```

## Troubleshooting

### Common Issues

#### Issue: "Path validation failed"

**Symptom**: Pipeline fails to start with path validation errors

**Solutions**:

1. Check that data directories exist:

   ```bash
   mkdir -p data/usaspending data/transition data/scripts_output
   ```

2. Verify environment variables are set correctly:

   ```bash
   echo $SBIR_ETL__PATHS__DATA_ROOT
   ```

3. Check file permissions:

   ```bash
   chmod -R 755 data/
   ```

#### Issue: "Parent directory doesn't exist"

**Symptom**: Error creating output files

**Solution**: Enable automatic directory creation:

```python
validate_paths_on_startup(create_missing_dirs=True)
```

#### Issue: "Path is a directory, expected file"

**Symptom**: Path resolves to directory instead of file

**Solution**: Check configuration - ensure path includes filename:

```yaml
# ❌ Wrong
usaspending_dump_file: "data/usaspending"

# ✅ Correct
usaspending_dump_file: "data/usaspending/dump.zip"
```

#### Issue: Hardcoded paths in error messages

**Symptom**: Seeing references to `/Volumes/X10 Pro/` in logs

**Solution**: This indicates old code is still using hardcoded paths. Check:

1. All source files have been updated to use `config.paths.resolve_path()`
2. No scripts are using old hardcoded defaults
3. Clear any cached Python bytecode: `find . -type d -name __pycache__ -exec rm -rf {} +`

### Debugging Path Resolution

Add logging to see resolved paths:

```python
from sbir_etl.config.loader import get_config
from loguru import logger

config = get_config()

# Log all resolved paths
for key in ["usaspending_dump_file", "transition_contracts_output", "transition_vendor_filters"]:
    try:
        path = config.paths.resolve_path(key)
        logger.info(f"{key}: {path}")
    except Exception as e:
        logger.error(f"Failed to resolve {key}: {e}")
```

### Getting Help

If you encounter path-related issues:

1. **Check logs**: Look for `FileSystemError` exceptions with detailed context
2. **Verify configuration**: Review `config/base.yaml` and environment variables
3. **Run validation**: Use `PathValidator` to get detailed error report
4. **Check permissions**: Ensure user has read/write access to paths
5. **Report issues**: Include error messages, configuration, and environment details

## Migration Guide

If you're upgrading from a version with hardcoded paths:

### Step 1: Review Current Paths

Check your current data locations:

```bash
# Find all data files
find . -name "*.parquet" -o -name "*.json" -o -name "*.zip" | grep -v node_modules
```

### Step 2: Configure Paths

Add paths to your environment-specific config or set environment variables:

```bash
# Option A: Update config/prod.yaml
echo "paths:
  usaspending_dump_file: /your/actual/path/dump.zip
  transition_dump_dir: /your/actual/path/api_dump
" >> config/prod.yaml

# Option B: Set environment variables
export SBIR_ETL__PATHS__USASPENDING_DUMP_FILE=/your/actual/path/dump.zip
```

### Step 3: Test Configuration

Run validation to ensure paths are correct:

```python
from sbir_etl.utils.path_validator import validate_paths_on_startup

validate_paths_on_startup(create_missing_dirs=True)
```

### Step 4: Update Scripts

Any custom scripts should use configuration instead of hardcoded paths:

```python
# OLD
output_file = Path("/Volumes/X10 Pro/data/output.parquet")

# NEW
from sbir_etl.config.loader import get_config
config = get_config()
output_file = config.paths.resolve_path("transition_contracts_output")
```

## Related Documentation

- Config schemas: `sbir_etl/config/schemas/` (`data.py`, `domain.py`, `pipeline.py`)
- Config loader: `sbir_etl/config/loader.py`
- [Configuration Overview](index.md)
- [Docker Guide](development/docker.md)
- [Exception Handling](development/exception-handling.md)

## Change Log

| Date | Version | Changes |
|------|---------|---------|
| 2025-11-05 | 1.0 | Initial path configuration system |
