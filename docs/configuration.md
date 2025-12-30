# Path Configuration Guide

**Type**: Reference
**Owner**: Engineering Team
**Last-Updated**: 2025-11-05
**Status**: Active

## Overview

The SBIR ETL pipeline uses a flexible, configuration-driven approach to file system paths that supports both cloud storage (AWS S3) and local filesystem. All paths are configurable via YAML configuration files and can be overridden using environment variables, making the pipeline portable across different deployment environments.

**Cloud-First Architecture**: The pipeline automatically detects S3 paths (`s3://bucket/key`) and uses boto3 for cloud storage operations, with automatic fallback to local filesystem for development.

## Table of Contents

- [Cloud Storage (AWS S3)](#cloud-storage-aws-s3)
- [Configuration Structure](#configuration-structure)
- [Default Paths](#default-paths)
- [Environment Variable Overrides](#environment-variable-overrides)
- [Path Resolution](#path-resolution)
- [Validation](#validation)
- [Docker Deployment](#docker-deployment)
- [Troubleshooting](#troubleshooting)

## Cloud Storage (AWS S3)

### S3 Path Support

The pipeline supports AWS S3 paths for cloud-first deployments:

```yaml
paths:
  # S3 paths (production)
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
# Production (S3)
export SBIR_ETL_USE_S3=true
export SBIR_ETL_S3_BUCKET=sbir-analytics-data-prod
export AWS_REGION=us-east-1

# Development (local filesystem)
export SBIR_ETL_USE_S3=false
```

### S3 Path Resolution

The path resolver automatically handles S3 paths:

```python
from src.config.loader import get_config

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
from src.utils.s3 import get_s3_client, s3_file_exists, download_from_s3

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

1. **Use S3 for production** - Scalable, durable, managed
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

All path configuration values can be overridden using environment variables with the `SBIR_ETL__PATHS__` prefix.

### Naming Convention

Convert the YAML key to uppercase and add the prefix:

```bash
# YAML: paths.data_root
export SBIR_ETL__PATHS__DATA_ROOT=/mnt/data

# YAML: paths.usaspending_dump_file
export SBIR_ETL__PATHS__USASPENDING_DUMP_FILE=/mnt/dumps/usaspending.zip

# YAML: paths.transition_contracts_output
export SBIR_ETL__PATHS__TRANSITION_CONTRACTS_OUTPUT=/mnt/output/contracts.parquet
```

### Common Deployment Examples

#### Development Environment

```bash
# Use local project paths (default behavior - no overrides needed)
cd /home/user/sbir-analytics
uv run dagster dev
```

#### Production Environment (Mounted Volumes)

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
from src.config.loader import get_config

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
from src.utils.path_validator import validate_paths_on_startup

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
from src.config.loader import get_config
from src.utils.path_validator import PathValidator

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
from src.config.loader import get_config
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
from src.utils.path_validator import validate_paths_on_startup

validate_paths_on_startup(create_missing_dirs=True)
```

### Step 4: Update Scripts

Any custom scripts should use configuration instead of hardcoded paths:

```python
# OLD
output_file = Path("/Volumes/X10 Pro/data/output.parquet")

# NEW
from src.config.loader import get_config
config = get_config()
output_file = config.paths.resolve_path("transition_contracts_output")
```

## Related Documentation

- [Configuration Overview](index.md)
- [Deployment Guide](deployment/containerization.md)
- [Exception Handling](development/exception-handling.md)

## Change Log

| Date | Version | Changes |
|------|---------|---------|
| 2025-11-05 | 1.0 | Initial path configuration system |
